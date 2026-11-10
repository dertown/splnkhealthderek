"""REST handler for the Splunk Health Derek+ HTML pages.

The browser asks for a search by name. The handler runs only the named searches in
default/health_queries.json, as the signed-in user, and never SPL sent from the
browser. A click can only run the five searches marked write=True (record a
decision, ask the AI provider, draft a support ticket, save the AI config, test
the connection). The ticket is only text returned to the page.

The AI provider key is the one value that is never placed into a search. On
save_config this handler writes it to Splunk's credential store
(storage/passwords, app splunk_exec_health, realm CRED_REALM, user CRED_NAME) as
the signed-in user, and the search only sees its length in tok_cfg_save. That
needs the list_storage_passwords capability and write access to [passwords] in
metadata/default.meta. bin/derekaiping.py reads the key back from there.
"""
from __future__ import annotations

import json
import logging
import os
import re
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
}

WRITES = {"decide", "ask", "ticket", "save_config", "conn_test"}
TOKEN_RE = re.compile(r"\$([a-z_]+)\$")
# Read only here and sent to storage/passwords; never a search parameter.
SECRET_PARAMS = {"tok_cfg_key"}

APP = "splunk_exec_health"
CRED_REALM = "splunk_exec_health_ai"
CRED_NAME = "provider_api_key"
CRED_PATH = f"/servicesNS/nobody/{APP}/storage/passwords"


def _catalog() -> dict:
    path = os.path.join(os.path.dirname(__file__), "..", "default", "health_queries.json")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _clean_key(params: dict) -> str:
    raw = str(params.get("tok_cfg_key") or "")
    pattern, unused = PARAMS["tok_cfg_key"]
    if not re.fullmatch(pattern, raw):
        raise ValueError("rejected tok_cfg_key")
    return "" if raw == "none" else raw


def _latch(params: dict) -> None:
    """The config searches only write when this matches, so compute it here.

    The key's length is the only thing about the key the searches ever see.
    """
    provider = re.sub(r"[^a-z]", "", str(params.get("tok_cfg_provider", "")).lower())
    model = re.sub(r"[^A-Za-z0-9._-]", "", str(params.get("tok_cfg_model", "")))
    params["tok_cfg_save"] = f"save|{provider}|{model}|{len(_clean_key(params))}"


def _store_key(session_key: str, params: dict) -> None:
    """Save the typed key in storage/passwords, or remove it when the provider is none.

    A blank key keeps whatever is stored. Raises on any failure so the search,
    which would otherwise record the key as stored, does not run.
    """
    key = _clean_key(params)
    provider = str(params.get("tok_cfg_provider") or "none")
    entity = CRED_PATH + "/" + quote(f"{CRED_REALM}:{CRED_NAME}:", safe="")
    if provider == "none":
        resp, unused = rest.simpleRequest(entity, sessionKey=session_key, method="DELETE", raiseAllErrors=False)
        if resp.status not in (200, 404):
            raise RuntimeError(f"credential delete returned HTTP {resp.status}")
        return
    if not key:
        return
    if len(key) < 8:
        raise ValueError("rejected tok_cfg_key")
    resp, unused = rest.simpleRequest(
        entity, sessionKey=session_key, method="POST",
        postargs={"password": key, "output_mode": "json"}, raiseAllErrors=False,
    )
    if resp.status == 404:
        resp, unused = rest.simpleRequest(
            CRED_PATH, sessionKey=session_key, method="POST",
            postargs={"name": CRED_NAME, "realm": CRED_REALM, "password": key, "output_mode": "json"},
            raiseAllErrors=False,
        )
    if resp.status not in (200, 201):
        # 403 means the user lacks list_storage_passwords or write on [passwords].
        raise RuntimeError(f"credential save returned HTTP {resp.status}")


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
            if name in SECRET_PARAMS:
                raise ValueError(f"{name} may not be placed into a search")
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
        spec = dict(spec, name=name)
        supplied = supplied if isinstance(supplied, dict) else {}
        values = self._fill(spec, supplied)
        if name == "save_config":
            try:
                _store_key(session_key, supplied)
            except ValueError:
                return self._render({"success": False, "error": "The API key must be 8 to 512 characters: "
                                     "letters, digits, and . _ / = + -"}, 400)
            except Exception as exc:  # noqa: BLE001 - the message never contains the key
                logger.warning("save_config credential store failed: %s", type(exc).__name__)
                return self._render({"success": False, "error": "The API key could not be saved to the credential store. "
                                     "Saving needs the list_storage_passwords capability."}, 403)
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
            return self._render({"success": False, "error": "The search could not run"}, 500)
        if isinstance(data, dict) and data.get("messages"):
            fatal = [m.get("text", "") for m in data["messages"] if m.get("type") == "FATAL"]
            if fatal:
                logger.warning("oneshot %s fatal: %s", name, fatal[0][:300])
                return self._render({"success": False, "error": fatal[0][:300]}, 500)
        rows = data.get("results") or [] if isinstance(data, dict) else []
        for row in rows:
            row.pop("api_key", None)
        return self._render({"success": True, "rows": rows})
