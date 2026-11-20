"""REST handler for the Splunk Health Derek+ HTML pages.

The browser asks for a search by name. The handler runs only the named searches in
default/health_queries.json, as the signed-in user, and never SPL sent from the
browser. A click can only run the five searches marked write=True (record a
decision, ask the AI provider, draft a support ticket, save the AI config, test
the connection). Those writes change only this app's own records; the ticket is
only text returned to the page.

The one change to Splunk configuration is the self-heal on Host Heartbeat. Its
plan (GET) changes nothing. Its apply (POST, after a click that confirms it)
re-enables the app's own Exec Health saved searches and re-runs the newest
scheduled slot that never ran. It only touches names shipped in
default/savedsearches.conf, and it recomputes the plan itself on apply.

Knowledge objects can be disabled from that page after a confirmed click.
That POST only disables a dashboard, app, or macro that already exists, and
it never deletes anything. Lookup files have no disable in Splunk, so they
are refused. This app, the search and launcher apps, and this page itself
cannot be disabled from here.

Searches with a "cache" entry are answered from the KV Store collection that
their scheduled "Exec Health Cache - ..." search fills, when that cache is fresh.
Otherwise, or when the page asks with fresh=1, the live search runs as before.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from urllib.parse import quote

import splunk.rest as rest
from splunk.persistconn.application import PersistentServerConnectionApplication

logger = logging.getLogger("healthdash")

# Every value the browser supplies is checked against one of these before it is
# placed into a search. The default is used when the browser omits it.
PARAMS = {
    "host_filter": (r"^[\w.:*\-]{1,128}$", "*"),
    "tok_data_source": (r"^[\w.:\-]{1,128}$", "none"),
    "tok_topo_ingest": (r"^(?:\*|UF|HF|HEC|SC4S|Edge Processor|Syslog|NetFlow / IPFIX|Other TCP|Other|Universal Forwarder|Heavy Forwarder)$", "*"),
    "tok_topo_index": (r"^(?:\*|Other indexes|[\w.:\-]{1,128})$", "*"),
    "tok_topo_environment": (r"^(?:\*|Other sites|[0-9]{1,3}\.[0-9]{1,3}\.0\.0/16|[\w.:\-]{1,128})$", "*"),
    "tok_topo_family": (r"^(?:\*|Other sourcetypes|[^\"\\`$\r\n|]{1,80})$", "*"),
    "tok_topo_endpoint": (r"^(?:\*|[^\"\\`$\r\n|]{1,80})$", "*"),
    "tok_finding_id": (r"^(none|[a-fA-F0-9]{8,128})$", "none"),
    "tok_fix_type": (r"^(none|[a-z0-9_]{1,64})$", "none"),
    "tok_ask": (r"^[a-z0-9 ]{0,64}$", "all"),
    "tok_cell": (r"^(none|approve|dismiss|fix)$", "none"),
    "tok_row_status": (r"^(none|open|approved|dismissed)$", "none"),
    "tok_ai_ask": (r"^(ask|review|retry[0-9]{0,12})$", "review"),
    "tok_ai_list": (r"^(show|hide)$", "show"),
    "tok_entity": (r"^[^|\"\\`$\r\n]{0,200}$", "none"),
    "tok_issue": (r"^[^|\"\\`$\r\n]{0,300}$", "none"),
    "tok_ai_brief": (r"^[^|\"\\`$\r\n]{0,6000}$", "none"),
    "tok_cfg_provider": (r"^(none|openai|cisco|azure|anthropic|custom)$", "none"),
    "tok_cfg_model": (r"^[A-Za-z0-9._-]{0,64}$", "none"),
    "tok_cfg_key": (r"^[A-Za-z0-9._/=+\-]{0,512}$", ""),
    "tok_cfg_save": (r"^save\|[a-z]*\|[A-Za-z0-9._-]*\|[0-9]+$", "save|||0"),
    "tok_heal_window": (r"^(1h|6h|24h)$", "6h"),
    "tok_heal_confirm": (r"^(yes|no)$", "no"),
    "tok_ko_window": (r"^(7d|30d|90d)$", "30d"),
    "tok_ko_kind": (r"^(dashboard|app|macro|lookup)$", "dashboard"),
    "tok_ko_app": (r"^[\w.\-]{1,128}$", "search"),
    "tok_ko_name": (r"^[\w.:(),\-]{1,200}$", "none"),
    "tok_ko_owner": (r"^[\w.\-]{1,128}$", "nobody"),
    "tok_ko_confirm": (r"^(yes|no)$", "no"),
}

WRITES = {"decide", "ask", "ticket", "save_config", "conn_test"}
TOKEN_RE = re.compile(r"\$([a-z_]+)\$")

# Self-heal settings. A scheduled slot counts as run if the scheduler logged a run
# that started inside [slot - 2 min, slot + 5 min). A slot newer than the grace
# period may still be running, so it is not yet missed.
HEAL_APP = "splunk_exec_health"
HEAL_PREFIX = "Exec Health - "
HEAL_WINDOWS = {"1h": 3600, "6h": 6 * 3600, "24h": 24 * 3600}
HEAL_GRACE_SEC = 900
HEAL_COVER_BEFORE = 120
HEAL_COVER_AFTER = 300
_CRON_LIMITS = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 7))

# Written by the "Exec Health Cache - ..." searches: one record per dataset with
# cached_at (epoch) and, for knowledge-object usage, covered_from (epoch).
CACHE_META = "exec_health_cache_meta"

# Knowledge-object disable. Apps and views use Splunk's /disable or disabled=1.
# Lookup CSV files have no disable action, so they are refused.
KO_KINDS = frozenset({"dashboard", "app", "macro"})
KO_PROTECTED_APPS = frozenset({
    "splunk_exec_health", "search", "launcher", "learned", "introspection_generator",
    "splunk_httpinput", "splunk_instrumentation", "splunk_monitoring_console",
})
KO_PROTECTED_VIEWS = frozenset({
    ("splunk_exec_health", "knowledge_objects"),
    ("splunk_exec_health", "executive_overview"),
})


class SearchFailed(Exception):
    """Operator-facing failure. The message is safe to show on the page."""


def _cron_field(expr: str, low: int, high: int) -> set:
    values = set()
    for part in expr.split(","):
        step = 1
        if "/" in part:
            part, step_text = part.split("/", 1)
            if not step_text.isdigit() or int(step_text) < 1:
                raise ValueError("cron step")
            step = int(step_text)
        if part == "*":
            start, end = low, high
        elif re.fullmatch(r"\d{1,2}-\d{1,2}", part):
            start, end = (int(p) for p in part.split("-"))
        elif re.fullmatch(r"\d{1,2}", part):
            start = end = int(part)
        else:
            raise ValueError("cron field")
        if start < low or end > high or start > end:
            raise ValueError("cron range")
        values.update(range(start, end + 1, step))
    return values


def _parse_cron(expr: str):
    """Minute, hour, day-of-month, month, day-of-week sets, plus the star flags that
    decide whether day-of-month and day-of-week are combined with AND or OR."""
    fields = (expr or "").split()
    if len(fields) != 5:
        raise ValueError("cron must have five fields")
    sets = [_cron_field(f, low, high) for f, (low, high) in zip(fields, _CRON_LIMITS)]
    if 7 in sets[4]:
        sets[4].discard(7)
        sets[4].add(0)
    return sets, fields[2].startswith("*"), fields[4].startswith("*")


def _cron_matches(stamp: time.struct_time, parsed) -> bool:
    sets, dom_star, dow_star = parsed
    if stamp.tm_min not in sets[0] or stamp.tm_hour not in sets[1] or stamp.tm_mon not in sets[3]:
        return False
    dom_ok = stamp.tm_mday in sets[2]
    dow_ok = (stamp.tm_wday + 1) % 7 in sets[4]
    if not dom_star and not dow_star:
        return dom_ok or dow_ok
    return dom_ok and dow_ok


def _expected_slots(cron: str, start: int, end: int) -> list:
    """Whole-minute scheduled times in [start, end), in the server's local time."""
    parsed = _parse_cron(cron)
    stamp = start + (-start % 60)
    slots = []
    while stamp < end:
        if _cron_matches(time.localtime(stamp), parsed):
            slots.append(stamp)
        stamp += 60
    return slots


def _is_covered(slot: int, run_times: list) -> bool:
    return any(slot - HEAL_COVER_BEFORE <= run < slot + HEAL_COVER_AFTER for run in run_times)


def _shipped_names() -> list:
    """Exec Health searches shipped in this app. Only these names are ever touched."""
    path = os.path.join(os.path.dirname(__file__), "..", "default", "savedsearches.conf")
    names = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            match = re.fullmatch(r"\[(Exec Health - [^\]\r\n]{1,200})\]\s*", line)
            if match:
                names.append(match.group(1))
    return names


def _flag(value) -> bool:
    return str(value).strip().lower() in ("1", "true")


def _local_time(epoch) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(epoch))


def _catalog() -> dict:
    path = os.path.join(os.path.dirname(__file__), "..", "default", "health_queries.json")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _latch(params: dict) -> None:
    """The config searches only write when this matches, so compute it here."""
    provider = re.sub(r"[^a-z]", "", params.get("tok_cfg_provider", "").lower())
    model = re.sub(r"[^A-Za-z0-9._-]", "", params.get("tok_cfg_model", ""))
    key = re.sub(r"[^A-Za-z0-9._/=+\-]", "", params.get("tok_cfg_key", ""))
    params["tok_cfg_save"] = f"save|{provider}|{model}|{len(key)}"


class HealthDashHandler(PersistentServerConnectionApplication):
    def __init__(self, command_line, command_arg):
        # The base class takes no arguments. Passing them stops the handler from
        # loading, and Splunk then answers the page with an HTML error.
        PersistentServerConnectionApplication.__init__(self)
        self.catalog = _catalog()

    def _render(self, data: dict, status: int = 200) -> dict:
        return {"payload": json.dumps(data), "status": int(status)}

    def handle(self, in_string):
        try:
            if isinstance(in_string, bytes):
                in_string = in_string.decode("utf-8", "replace")
            args = json.loads(in_string or "{}")
        except (ValueError, TypeError):
            return self._render({"success": False, "error": "Invalid request"}, 400)

        session = args.get("session") or {}
        session_key = session.get("authtoken") or args.get("session_key")
        if not session_key:
            return self._render({"success": False, "error": "Authentication required"}, 401)
        # "-" is the signed-in user. The app name puts the search in this app, so
        # private macros and lookups such as exec_health_idx resolve.
        user = quote(session.get("user") or "-", safe="")

        method = (args.get("method") or "get").lower()
        path = (args.get("path_info") or args.get("path") or "").strip("/")
        path = path.split("healthdash/", 1)[-1]

        supplied = self._params(args)
        try:
            if method == "get" and path == "query":
                return self._run(session_key, user, supplied.get("name", ""), supplied, write=False)
            if method == "post" and path == "act":
                body = self._body(args)
                return self._run(session_key, user, body.get("name", ""), body.get("params") or {}, write=True)
            if method == "get" and path == "heal":
                return self._heal_plan_response(session_key, user, supplied)
            if method == "post" and path == "heal":
                body = self._body(args)
                return self._heal_apply_response(session_key, user, body.get("params") or {})
            if method == "post" and path == "ko":
                body = self._body(args)
                return self._ko_disable_response(session_key, user, body.get("params") or {})
        except Exception as exc:  # noqa: BLE001 - report a clean message, keep the detail in the log
            logger.warning("healthdash request failed: %s", exc)
            return self._render({"success": False, "error": "The search could not run"}, 500)
        return self._render({"success": False, "error": "Unknown endpoint"}, 404)

    def _params(self, args: dict) -> dict:
        out = {}
        for item in args.get("query") or []:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                out[item[0]] = item[1]
        return out

    def _body(self, args: dict) -> dict:
        payload = args.get("payload") or args.get("body") or ""
        if isinstance(payload, (bytes, bytearray)):
            payload = payload.decode("utf-8", "replace")
        if isinstance(payload, str) and payload.strip():
            try:
                return json.loads(payload)
            except ValueError:
                return {}
        return {}

    def _fill(self, spec: dict, supplied: dict) -> dict:
        if spec["name"] in ("save_config", "conn_test"):
            _latch(supplied)
        values = {}
        for name in spec["params"]:
            pattern, default = PARAMS[name]
            raw = supplied.get(name, "")
            value = default if raw == "" or raw is None else str(raw)
            if not re.fullmatch(pattern, value):
                raise ValueError(f"rejected {name}")
            values[name] = value
        return values

    def _run(self, session_key: str, user: str, name: str, supplied: dict, write: bool) -> dict:
        spec = self.catalog.get(name)
        if spec is None or bool(spec.get("write")) != write or (write and name not in WRITES):
            return self._render({"success": False, "error": "Unknown search"}, 404)
        rows, cached_at = None, None
        cache = spec.get("cache")
        if cache and not write and str(supplied.get("fresh", "")) != "1":
            cached_at = self._cache_time(session_key, cache, supplied)
            if cached_at is not None:
                reader = dict(spec, spl=cache["spl"], earliest=cache["earliest"], latest=cache["latest"])
                try:
                    rows = self._oneshot(session_key, user, name, reader, supplied)
                except SearchFailed as exc:
                    logger.warning("cache read %s failed, running live: %s", name, exc)
                    rows, cached_at = None, None
        try:
            if rows is None:
                rows = self._oneshot(session_key, user, name, spec, supplied)
        except SearchFailed as exc:
            return self._render({"success": False, "error": str(exc)}, 500)
        body = {"success": True, "rows": rows}
        if cached_at is not None:
            body["cached_at"] = int(cached_at)
        return self._render(body)

    def _cache_time(self, session_key: str, cache: dict, supplied: dict):
        """When the cache was built, if it is fresh enough to answer; otherwise None.

        A cache with cover_param must also hold at least that many days of history.
        """
        dataset = str(cache.get("dataset", ""))
        if not re.fullmatch(r"[a-z_]{1,40}", dataset):
            return None
        try:
            response, content = rest.simpleRequest(
                f"/servicesNS/nobody/{HEAL_APP}/storage/collections/data/{CACHE_META}/{dataset}",
                sessionKey=session_key, getargs={"output_mode": "json"}, raiseAllErrors=False,
            )
            if int(getattr(response, "status", 0) or 0) != 200:
                return None
            record = json.loads(content)
            cached_at = float(record.get("cached_at"))
        except Exception:  # noqa: BLE001 - no cache, unreadable, or wrong shape: run live
            return None
        now = time.time()
        if not 0 <= now - cached_at <= float(cache.get("max_age", 0)):
            return None
        param = cache.get("cover_param")
        if param:
            pattern, default = PARAMS[param]
            value = str(supplied.get(param) or default)
            days = re.fullmatch(r"(\d{1,3})d", value) if re.fullmatch(pattern, value) else None
            try:
                covered = float(record.get("covered_from"))
            except (TypeError, ValueError):
                return None
            if days is None or covered > now - int(days.group(1)) * 86400:
                return None
        return cached_at

    def _oneshot(self, session_key: str, user: str, name: str, spec: dict, supplied: dict) -> list:
        """Run one named catalog search as the signed-in user and return its rows."""
        spec = dict(spec, name=name)
        values = self._fill(spec, supplied if isinstance(supplied, dict) else {})
        spl = spec["spl"]
        for key in sorted(values, key=len, reverse=True):
            spl = spl.replace(f"${key}$", values[key])
        if TOKEN_RE.search(spl):
            raise ValueError("unresolved token")
        search = spl if spl.lstrip().startswith("|") else "| " + spl
        try:
            unused, content = rest.simpleRequest(
                f"/servicesNS/{user}/splunk_exec_health/search/jobs/oneshot",
                sessionKey=session_key,
                postargs={
                    "search": search,
                    "earliest_time": spec["earliest"],
                    "latest_time": spec["latest"],
                    "output_mode": "json",
                    "count": str(spec["count"]),
                    "timeout": str(spec["timeout"]),
                },
                raiseAllErrors=False,
                timeout=spec["timeout"] + 15,
            )
            data = json.loads(content)
        except Exception as exc:  # noqa: BLE001
            logger.warning("oneshot %s failed: %s", name, exc)
            raise SearchFailed("The search could not run") from exc
        if isinstance(data, dict) and data.get("messages"):
            fatal = [m.get("text", "") for m in data["messages"] if m.get("type") == "FATAL"]
            if fatal:
                logger.warning("oneshot %s fatal: %s", name, fatal[0][:300])
                raise SearchFailed(fatal[0][:300])
        rows = data.get("results") or [] if isinstance(data, dict) else []
        for row in rows:
            row.pop("api_key", None)
        return rows

    # -- self-heal -----------------------------------------------------------

    def _heal_values(self, supplied: dict) -> dict:
        values = {}
        for name in ("tok_heal_window", "tok_heal_confirm"):
            pattern, default = PARAMS[name]
            raw = supplied.get(name, "")
            value = default if raw == "" or raw is None else str(raw)
            if not re.fullmatch(pattern, value):
                raise ValueError(f"rejected {name}")
            values[name] = value
        return values

    def _saved_searches(self, session_key: str) -> dict:
        """The app's shipped Exec Health searches that exist, keyed by name."""
        try:
            response, content = rest.simpleRequest(
                f"/servicesNS/-/{HEAL_APP}/saved/searches",
                sessionKey=session_key,
                getargs={"count": "0", "output_mode": "json"},
                raiseAllErrors=False,
            )
            status = int(getattr(response, "status", 0) or 0)
            if not 200 <= status < 300:
                raise SearchFailed(f"could not read saved searches (HTTP {status})")
            payload = json.loads(content)
        except SearchFailed:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("heal list failed: %s", exc)
            raise SearchFailed("could not read saved searches") from exc
        shipped = set(_shipped_names())
        found = {}
        for entry in payload.get("entry") or []:
            name = entry.get("name") or ""
            if name not in shipped or name in found:
                continue
            body = entry.get("content") or {}
            acl = entry.get("acl") or {}
            found[name] = {
                "owner": acl.get("owner") or "nobody",
                "disabled": _flag(body.get("disabled")),
                "scheduled": _flag(body.get("is_scheduled")),
                "cron": str(body.get("cron_schedule") or "").strip(),
            }
        return found

    def _scheduler_runs(self, session_key: str, user: str, window_key: str) -> dict:
        """Start times of scheduler runs per Exec Health search, inside the window."""
        spec = self.catalog["heal_runs"]
        rows = self._oneshot(session_key, user, "heal_runs", spec, {"tok_heal_window": window_key})
        runs: dict = {}
        for row in rows:
            try:
                runs.setdefault(row.get("savedsearch_name") or "", []).append(float(row.get("run_epoch")))
            except (TypeError, ValueError):
                continue
        return runs

    def _heal_items(self, session_key: str, user: str, window_key: str) -> list:
        """Plan: what each shipped Exec Health search needs. Changes nothing."""
        window_sec = HEAL_WINDOWS[window_key]
        now = int(time.time())
        found = self._saved_searches(session_key)
        runs = self._scheduler_runs(session_key, user, window_key)
        items = []
        for name in _shipped_names():
            item = {
                "search": name, "owner": "", "state": "MISSING", "cron": "",
                "disabled": False, "scheduled": False, "expected": 0, "runs": 0,
                "missed": 0, "rerun": None, "note": "",
            }
            info = found.get(name)
            if info is None:
                item["note"] = "Not installed in this app"
                items.append(item)
                continue
            item.update(owner=info["owner"], cron=info["cron"], disabled=info["disabled"], scheduled=info["scheduled"])
            item["state"] = "DISABLED" if info["disabled"] else ("NOT SCHEDULED" if not info["scheduled"] else "OK")
            item["runs"] = len(runs.get(name, []))
            if not info["cron"]:
                item["note"] = "No schedule to check"
            else:
                try:
                    slots = _expected_slots(info["cron"], now - window_sec, now - HEAL_GRACE_SEC)
                except ValueError:
                    slots = None
                    item["note"] = "Schedule is not one this check reads"
                if slots is not None:
                    missed = [s for s in slots if not _is_covered(s, runs.get(name, []))]
                    item["expected"] = len(slots)
                    item["missed"] = len(missed)
                    if missed:
                        item["rerun"] = missed[-1]
            items.append(item)
        return items

    @staticmethod
    def _needs_enable(item: dict) -> bool:
        return item["state"] != "MISSING" and (item["disabled"] or not item["scheduled"])

    @classmethod
    def _heal_action(cls, item: dict) -> str:
        if item["state"] == "MISSING":
            return "None"
        if cls._needs_enable(item) and item["rerun"] is not None:
            return "Enable and re-run latest missed"
        if cls._needs_enable(item):
            return "Enable"
        if item["rerun"] is not None:
            return "Re-run latest missed"
        return "None"

    def _heal_plan_row(self, item: dict) -> dict:
        return {
            "search": item["search"],
            "state": item["state"],
            "schedule": item["cron"] or "none",
            "due_in_window": item["expected"],
            "ran_in_window": item["runs"],
            "missed": item["missed"],
            "latest_missed": _local_time(item["rerun"]) if item["rerun"] is not None else "",
            "action": self._heal_action(item),
            "note": item["note"],
        }

    def _post(self, session_key: str, path: str, postargs: dict) -> bytes:
        try:
            response, content = rest.simpleRequest(path, sessionKey=session_key, postargs=postargs, raiseAllErrors=False)
        except Exception as exc:  # noqa: BLE001
            logger.warning("heal post %s failed: %s", path, exc)
            raise SearchFailed("Splunk did not accept the change") from exc
        status = int(getattr(response, "status", 0) or 0)
        if not 200 <= status < 300:
            logger.warning("heal post %s returned HTTP %s", path, status)
            raise SearchFailed(f"Splunk did not accept the change (HTTP {status})")
        return content

    def _heal_saved_path(self, item: dict) -> str:
        return (f"/servicesNS/{quote(item['owner'], safe='')}/{HEAL_APP}"
                f"/saved/searches/{quote(item['search'], safe='')}")

    def _heal_apply_rows(self, session_key: str, user: str, window_key: str) -> list:
        """Apply: plan again on the server, then enable and re-run per search."""
        results = []
        for item in self._heal_items(session_key, user, window_key):
            needs_enable = self._needs_enable(item)
            result = {
                "search": item["search"],
                "enabled": "n/a" if item["state"] == "MISSING" else ("no" if needs_enable else "already on"),
                "rerun_at": "", "sid": "", "status": "nothing to do", "error": "",
            }
            if item["state"] == "MISSING" or (not needs_enable and item["rerun"] is None):
                results.append(result)
                continue
            try:
                if needs_enable:
                    base = self._heal_saved_path(item)
                    if item["disabled"]:
                        self._post(session_key, base + "/enable", {"output_mode": "json"})
                    if not item["scheduled"]:
                        self._post(session_key, base, {"is_scheduled": "1", "output_mode": "json"})
                    result["enabled"] = "yes"
                if item["rerun"] is not None:
                    content = self._post(session_key, self._heal_saved_path(item) + "/dispatch", {
                        "dispatch.now": str(int(item["rerun"])),
                        "trigger_actions": "1",
                        "force_dispatch": "1",
                        "output_mode": "json",
                    })
                    try:
                        sid = str(json.loads(content).get("sid") or "")
                    except (ValueError, AttributeError) as exc:
                        raise SearchFailed("re-run did not return a job id") from exc
                    result["sid"] = sid
                    result["rerun_at"] = _local_time(item["rerun"])
                result["status"] = "done"
            except SearchFailed as exc:
                result["status"] = "error"
                result["error"] = str(exc)
            results.append(result)
        return results

    def _heal_plan_response(self, session_key: str, user: str, supplied: dict) -> dict:
        try:
            values = self._heal_values(supplied if isinstance(supplied, dict) else {})
        except ValueError:
            return self._render({"success": False, "error": "Choose a look-back of 1h, 6h or 24h"}, 400)
        try:
            items = self._heal_items(session_key, user, values["tok_heal_window"])
        except SearchFailed as exc:
            return self._render({"success": False, "error": str(exc)}, 500)
        return self._render({"success": True, "rows": [self._heal_plan_row(i) for i in items]})

    def _heal_apply_response(self, session_key: str, user: str, params: dict) -> dict:
        try:
            values = self._heal_values(params if isinstance(params, dict) else {})
        except ValueError:
            return self._render({"success": False, "error": "Choose a look-back of 1h, 6h or 24h"}, 400)
        if values["tok_heal_confirm"] != "yes":
            return self._render({"success": False, "error": "Confirm the heal before it runs"}, 400)
        window_key = values["tok_heal_window"]
        try:
            rows = self._heal_apply_rows(session_key, user, window_key)
        except SearchFailed as exc:
            return self._render({"success": False, "error": str(exc)}, 500)
        logger.info("heal apply window=%s by=%s: %s", window_key, user,
                    "; ".join("%s=%s" % (r["search"], r["status"]) for r in rows))
        return self._render({"success": True, "rows": rows})

    def _ko_values(self, supplied: dict) -> dict:
        values = {}
        for name in ("tok_ko_kind", "tok_ko_app", "tok_ko_name", "tok_ko_owner", "tok_ko_confirm"):
            pattern, default = PARAMS[name]
            raw = supplied.get(name, "")
            value = default if raw == "" or raw is None else str(raw)
            if not re.fullmatch(pattern, value):
                raise ValueError(f"rejected {name}")
            values[name] = value
        return values

    def _get_json(self, session_key: str, path: str) -> dict:
        try:
            response, content = rest.simpleRequest(
                path, sessionKey=session_key, getargs={"output_mode": "json"}, raiseAllErrors=False,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("ko get %s failed: %s", path, exc)
            raise SearchFailed("could not read that object") from exc
        status = int(getattr(response, "status", 0) or 0)
        if status == 404:
            raise SearchFailed("that object is not on this search head")
        if not 200 <= status < 300:
            raise SearchFailed(f"could not read that object (HTTP {status})")
        try:
            return json.loads(content)
        except ValueError as exc:
            raise SearchFailed("could not read that object") from exc

    def _ko_entity_path(self, kind: str, app: str, name: str, owner: str) -> str:
        if kind == "app":
            return "/services/apps/local/%s" % quote(name, safe="")
        owner = owner or "nobody"
        if kind == "dashboard":
            return "/servicesNS/%s/%s/data/ui/views/%s" % (
                quote(owner, safe=""), quote(app, safe=""), quote(name, safe=""),
            )
        return "/servicesNS/%s/%s/admin/macros/%s" % (
            quote(owner, safe=""), quote(app, safe=""), quote(name, safe=""),
        )

    def _ko_disable_response(self, session_key: str, user: str, params: dict) -> dict:
        try:
            values = self._ko_values(params if isinstance(params, dict) else {})
        except ValueError:
            return self._render({"success": False, "error": "That object cannot be disabled from this page"}, 400)
        if values["tok_ko_confirm"] != "yes":
            return self._render({"success": False, "error": "Confirm before disabling"}, 400)
        kind, app, name, owner = (
            values["tok_ko_kind"], values["tok_ko_app"], values["tok_ko_name"], values["tok_ko_owner"],
        )
        if name in ("", "none") or kind not in KO_KINDS:
            return self._render({"success": False, "error": "Lookup files cannot be disabled. Pick a dashboard, app, or macro."}, 400)
        if kind == "app":
            app = name
        if kind == "app" and name in KO_PROTECTED_APPS:
            return self._render({"success": False, "error": "That app is left on so this stack stays usable"}, 400)
        if kind == "dashboard" and (app, name) in KO_PROTECTED_VIEWS:
            return self._render({"success": False, "error": "That view is left on so this app stays usable"}, 400)
        path = self._ko_entity_path(kind, app, name, owner)
        try:
            payload = self._get_json(session_key, path)
            entries = payload.get("entry") or []
            if not entries:
                raise SearchFailed("that object is not on this search head")
            body = entries[0].get("content") or {}
            if _flag(body.get("disabled")):
                return self._render({"success": True, "rows": [{
                    "kind": kind, "app_name": app, "ko_name": name, "status": "already off", "error": "",
                }]})
            if kind == "app":
                self._post(session_key, path + "/disable", {"output_mode": "json"})
            else:
                self._post(session_key, path, {"disabled": "1", "output_mode": "json"})
        except SearchFailed as exc:
            return self._render({"success": False, "error": str(exc)}, 500)
        logger.info("ko disable kind=%s app=%s name=%s by=%s", kind, app, name, user)
        return self._render({"success": True, "rows": [{
            "kind": kind, "app_name": app, "ko_name": name, "status": "disabled", "error": "",
        }]})
