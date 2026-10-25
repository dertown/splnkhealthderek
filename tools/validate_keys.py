#!/usr/bin/env python3
"""Validate every configuration key in the app. Run from anywhere; exits 1 on errors.

Checks
  * .conf keys (and enum values) against the Splunk .spec settings this app can use
  * metadata/default.meta and app.manifest keys, and version agreement across files
  * every `macro` referenced in a search is defined in macros.conf
  * every `lookup` is defined in transforms.conf, its CSV exists, and the input /
    OUTPUT fields are CSV columns
  * Dashboard Studio JSON: top-level, data source, input, visualization, option,
    event handler and layout keys; enum option values; references between
    data sources, chains, visualizations, layout, global inputs, tokens and
    context palettes used by matchValue()/rangeValue()/prepend()

The allowlists are deliberately limited to documented settings. If you add a
valid setting that is not listed here, add it to the matching list.
"""
from __future__ import annotations

import csv
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "default"
VIEWS = DEFAULT / "data" / "ui" / "views"

errors: list[str] = []
warnings: list[str] = []


def err(where: str, msg: str) -> None:
    errors.append(f"{where}: {msg}")


def warn(where: str, msg: str) -> None:
    warnings.append(f"{where}: {msg}")


# ---------------------------------------------------------------------------
# .conf parsing
# ---------------------------------------------------------------------------

def parse_conf(path: Path) -> dict[str, dict[str, str]]:
    stanzas: dict[str, dict[str, str]] = {}
    current = "default"
    stanzas[current] = {}
    lines = path.read_text(encoding="utf-8").splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        i += 1
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            current = stripped[1:-1]
            if current in stanzas and stanzas[current]:
                err(path.name, f"duplicate stanza [{current}]")
            stanzas.setdefault(current, {})
            continue
        # line continuation
        while line.rstrip().endswith("\\") and i < len(lines):
            line = line.rstrip()[:-1] + "\n" + lines[i]
            i += 1
        if "=" not in line:
            err(path.name, f"[{current}] line without '=': {stripped[:60]}")
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key in stanzas[current]:
            err(path.name, f"[{current}] duplicate key {key}")
        stanzas[current][key] = value.strip()
    if not stanzas["default"]:
        del stanzas["default"]
    return stanzas


BOOL = {"0", "1", "true", "false", "True", "False"}

APP_CONF = {
    "install": {"is_configured", "state", "build", "allows_disable", "install_source_checksum",
                "install_source_local_checksum", "python.required"},
    "ui": {"is_visible", "is_manageable", "label", "show_in_nav", "docs_section_override",
           "setup_view", "attribution_link", "supported_themes"},
    "launcher": {"author", "description", "version", "remote_tab"},
    "package": {"id", "check_for_updates", "show_upgrade_notification"},
    "id": {"group", "name", "version"},
}

MACROS_KEYS = {"definition", "args", "validation", "errormsg", "iseval", "description"}

TRANSFORMS_LOOKUP_KEYS = {
    "filename", "max_matches", "min_matches", "default_match", "case_sensitive_match",
    "match_type", "external_cmd", "external_type", "fields_list", "collection",
    "time_field", "time_format", "max_offset_secs", "min_offset_secs",
    "batch_index_query", "allow_caching", "filter", "replicate", "feature_id_element",
}

SAVEDSEARCH_KEYS = {
    "search", "description", "disabled", "is_visible", "enableSched", "cron_schedule",
    "schedule_window", "schedule_priority", "realtime_schedule", "max_concurrent",
    "run_on_startup", "run_n_times", "allow_skew",
    "dispatch.earliest_time", "dispatch.latest_time", "dispatch.index_earliest",
    "dispatch.index_latest", "dispatch.ttl", "dispatch.buckets", "dispatch.max_count",
    "dispatch.max_time", "dispatch.lookups", "dispatch.spawn_process",
    "dispatch.time_format", "dispatch.auto_cancel", "dispatch.auto_pause",
    "dispatch.reduce_freq", "dispatch.rt_backfill", "dispatch.sample_ratio",
    "dispatchAs",
    "counttype", "relation", "quantity", "alert_condition",
    "alert_type", "alert_comparator", "alert_threshold",
    "alert.digest_mode", "alert.expires", "alert.severity", "alert.suppress",
    "alert.suppress.fields", "alert.suppress.group_name", "alert.suppress.period",
    "alert.track", "alert.display_view", "alert.managedBy",
    "action.email", "action.email.to", "action.email.cc", "action.email.bcc",
    "action.email.subject", "action.email.message.alert", "action.email.message.report",
    "action.email.sendcsv", "action.email.sendpdf", "action.email.sendresults",
    "action.email.inline", "action.email.format", "action.email.include.results_link",
    "action.email.include.search", "action.email.include.trigger",
    "action.email.include.trigger_time", "action.email.include.view_link",
    "action.email.useNSSubject",
    "action.script", "action.lookup", "action.populate_lookup", "action.rss",
    "action.summary_index", "action.summary_index._name",
    "request.ui_dispatch_app", "request.ui_dispatch_view",
    "display.general.type", "display.general.enablePreview",
    "display.general.timeRangePicker.show", "display.page.search.mode",
    "display.page.search.tab", "display.page.search.timeline.format",
    "display.page.search.timeline.scale", "display.page.search.showFields",
    "display.statistics.rowNumbers", "display.statistics.wrap",
    "display.statistics.drilldown", "display.events.type", "display.visualizations.show",
    "display.visualizations.type", "display.visualizations.charting.chart",
    "auto_summarize", "embed.enabled",
}

SAVEDSEARCH_ENUMS = {
    "alert_type": {"always", "custom", "number of events", "number of hosts", "number of sources"},
    "alert_comparator": {"greater than", "less than", "equal to", "not equal to", "drops by", "rises by"},
    "display.general.type": {"events", "statistics", "visualizations"},
    "display.page.search.tab": {"events", "statistics", "visualizations", "patterns"},
    "alert.severity": {"1", "2", "3", "4", "5", "6"},
}

SAVEDSEARCH_BOOLS = {
    "enableSched", "realtime_schedule", "alert.digest_mode", "alert.suppress", "alert.track",
    "action.email", "action.email.sendcsv", "disabled", "is_visible", "run_on_startup",
}

META_KEYS = {"access", "export", "owner", "version", "modtime", "import"}

MANIFEST_TOP = {"schemaVersion", "info", "dependencies", "tasks", "inputGroups",
                "incompatibleApps", "platformRequirements", "supportedDeployments",
                "targetWorkloads"}
MANIFEST_INFO = {"title", "id", "author", "releaseDate", "description", "classification",
                 "commonInformationModels", "license", "privacyPolicy", "releaseNotes"}


def check_keys(file: str, stanza: str, keys: dict[str, str], allowed: set[str]) -> None:
    for key in keys:
        if key not in allowed:
            err(file, f"[{stanza}] unknown key '{key}'")


def check_app_conf() -> dict:
    conf = parse_conf(DEFAULT / "app.conf")
    for stanza, keys in conf.items():
        if stanza not in APP_CONF:
            err("app.conf", f"unknown stanza [{stanza}]")
            continue
        check_keys("app.conf", stanza, keys, APP_CONF[stanza])
    for stanza, key in [("install", "is_configured"), ("ui", "is_visible"), ("package", "check_for_updates")]:
        value = conf.get(stanza, {}).get(key)
        if value is not None and value not in BOOL:
            err("app.conf", f"[{stanza}] {key} must be boolean, got {value!r}")
    if conf.get("install", {}).get("state") not in (None, "enabled", "disabled"):
        err("app.conf", "[install] state must be enabled or disabled")
    return conf


def check_macros() -> dict:
    conf = parse_conf(DEFAULT / "macros.conf")
    for stanza, keys in conf.items():
        check_keys("macros.conf", stanza, keys, MACROS_KEYS)
        if "definition" not in keys:
            err("macros.conf", f"[{stanza}] has no definition")
        if not re.fullmatch(r"[A-Za-z0-9_]+(\(\d+\))?", stanza):
            err("macros.conf", f"[{stanza}] invalid macro name")
        if "iseval" in keys and keys["iseval"] not in BOOL:
            err("macros.conf", f"[{stanza}] iseval must be boolean")
    return conf


def check_transforms() -> dict:
    conf = parse_conf(DEFAULT / "transforms.conf")
    for stanza, keys in conf.items():
        check_keys("transforms.conf", stanza, keys, TRANSFORMS_LOOKUP_KEYS)
        for key in ("case_sensitive_match", "replicate", "allow_caching"):
            if key in keys and keys[key] not in BOOL:
                err("transforms.conf", f"[{stanza}] {key} must be boolean")
        for key in ("max_matches", "min_matches"):
            if key in keys and not keys[key].isdigit():
                err("transforms.conf", f"[{stanza}] {key} must be an integer")
        if "filename" in keys and not (ROOT / "lookups" / keys["filename"]).is_file():
            err("transforms.conf", f"[{stanza}] lookups/{keys['filename']} does not exist")
    return conf


def check_savedsearches() -> dict:
    conf = parse_conf(DEFAULT / "savedsearches.conf")
    for stanza, keys in conf.items():
        check_keys("savedsearches.conf", stanza, keys, SAVEDSEARCH_KEYS)
        for key, allowed in SAVEDSEARCH_ENUMS.items():
            if key in keys and keys[key] not in allowed:
                err("savedsearches.conf", f"[{stanza}] {key}={keys[key]!r} not in {sorted(allowed)}")
        for key in SAVEDSEARCH_BOOLS:
            if key in keys and keys[key] not in BOOL:
                err("savedsearches.conf", f"[{stanza}] {key} must be boolean")
        if "cron_schedule" in keys and len(keys["cron_schedule"].split()) != 5:
            err("savedsearches.conf", f"[{stanza}] cron_schedule must have 5 fields")
        sw = keys.get("schedule_window")
        if sw is not None and sw != "auto" and not sw.isdigit():
            err("savedsearches.conf", f"[{stanza}] schedule_window must be auto or minutes")
        if keys.get("alert.suppress.fields") and keys.get("alert.digest_mode") != "0":
            err("savedsearches.conf", f"[{stanza}] alert.suppress.fields only applies when alert.digest_mode = 0")
        if keys.get("enableSched") == "1" and "cron_schedule" not in keys:
            err("savedsearches.conf", f"[{stanza}] scheduled without cron_schedule")
        if keys.get("enableSched") != "0":
            warn("savedsearches.conf", f"[{stanza}] ships enabled; README says alerts ship disabled")
        if keys.get("action.email") not in (None, "0"):
            warn("savedsearches.conf", f"[{stanza}] ships with an email action")
        if "search" not in keys:
            err("savedsearches.conf", f"[{stanza}] has no search")
    return conf


def check_meta() -> None:
    conf = parse_conf(ROOT / "metadata" / "default.meta")
    for stanza, keys in conf.items():
        check_keys("default.meta", stanza, keys, META_KEYS)
        if "export" in keys and keys["export"] not in ("none", "system"):
            err("default.meta", f"[{stanza}] export must be none or system")
        if "access" in keys and not re.fullmatch(r"read\s*:\s*\[[^\]]*\](\s*,\s*write\s*:\s*\[[^\]]*\])?", keys["access"]):
            err("default.meta", f"[{stanza}] malformed access {keys['access']!r}")


def check_manifest(app_conf: dict) -> None:
    manifest = json.loads((ROOT / "app.manifest").read_text())
    for key in manifest:
        if key not in MANIFEST_TOP:
            err("app.manifest", f"unknown top-level key '{key}'")
    for key in manifest.get("info", {}):
        if key not in MANIFEST_INFO:
            err("app.manifest", f"unknown info key '{key}'")
    ver = manifest["info"]["id"]["version"]
    name = manifest["info"]["id"]["name"]
    if name != app_conf.get("package", {}).get("id") or name != app_conf.get("id", {}).get("name"):
        err("app.manifest", "info.id.name does not match app.conf [package] id / [id] name")
    versions = {
        "app.manifest": ver,
        "app.conf [launcher]": app_conf.get("launcher", {}).get("version"),
        "app.conf [id]": app_conf.get("id", {}).get("version"),
    }
    gen = re.search(r'APP_VERSION = "([^"]+)"', (ROOT / "tools" / "build_dashboards.py").read_text())
    if gen:
        versions["build_dashboards.py APP_VERSION"] = gen.group(1)
    readme = re.search(r"splunk_exec_health-(\d+\.\d+\.\d+)\.spl", (ROOT / "README.md").read_text())
    if readme:
        versions["README .spl name"] = readme.group(1)
    if len(set(versions.values())) != 1:
        err("version", "mismatch: " + ", ".join(f"{k}={v}" for k, v in versions.items()))
    for t in manifest.get("targetWorkloads", []):
        if t not in ("_search_heads", "_indexers", "_forwarders", "*"):
            err("app.manifest", f"unknown targetWorkloads value {t!r}")


# ---------------------------------------------------------------------------
# Search references (macros, lookups)
# ---------------------------------------------------------------------------

MACRO_RE = re.compile(r"`([A-Za-z0-9_]+)(?:\([^`]*\))?`")
LOOKUP_RE = re.compile(r"\|\s*lookup\s+(\S+)\s+(\S+)(?:\s+AS\s+\S+)?\s+(?:OUTPUT|OUTPUTNEW)\s+([^|\n]+)", re.I)


def check_search_refs(where: str, query: str, macros: dict, transforms: dict) -> None:
    for name in MACRO_RE.findall(query):
        if name not in macros:
            err(where, f"undefined macro `{name}`")
    # Expand macros once so references inside definitions are checked too.
    for m in LOOKUP_RE.finditer(query):
        table, in_field, outputs = m.group(1), m.group(2), m.group(3)
        if table not in transforms:
            err(where, f"lookup '{table}' is not defined in transforms.conf")
            continue
        fname = transforms[table].get("filename")
        if not fname:
            continue
        path = ROOT / "lookups" / fname
        if not path.is_file():
            continue
        with path.open(newline="", encoding="utf-8") as fh:
            header = next(csv.reader(fh))
        if in_field not in header:
            err(where, f"lookup {table}: input field '{in_field}' not a column of {fname} {header}")
        for out in [o.strip().split()[0] for o in outputs.split(",") if o.strip()]:
            if out not in header:
                err(where, f"lookup {table}: OUTPUT field '{out}' not a column of {fname} {header}")


# ---------------------------------------------------------------------------
# Dashboard Studio
# ---------------------------------------------------------------------------

DASH_TOP = {"title", "description", "defaults", "inputs", "dataSources", "visualizations",
            "layout", "applicationProperties", "expressions"}
DS_KEYS = {"type", "name", "options", "meta"}
DS_OPTIONS = {
    "ds.search": {"query", "queryParameters", "refresh", "refreshType", "enableSmartSources"},
    "ds.chain": {"extend", "query", "enableSmartSources"},
    "ds.savedSearch": {"ref", "app", "queryParameters", "refresh", "refreshType"},
}
QUERY_PARAMS = {"earliest", "latest", "sampleRatio"}
VIZ_KEYS = {"type", "title", "description", "dataSources", "options", "context", "eventHandlers",
            "showLastUpdated", "showProgressBar", "containerOptions", "hideWhenNoData"}
COMMON_CHART = {"seriesColors", "seriesColorsByField", "legendDisplay", "legendTruncation",
                "xAxisTitleText", "yAxisTitleText", "xAxisTitleVisibility", "yAxisTitleVisibility",
                "yAxisAbbreviation", "yAxisScale", "yAxisMin", "yAxisMax", "x", "y", "y2",
                "dataValuesDisplay", "backgroundColor", "showSplitSeries", "stackMode",
                "resultLimit", "annotationX", "annotationLabel", "annotationColor"}
VIZ_OPTIONS = {
    "splunk.singlevalue": {"majorValue", "majorColor", "majorFontSize", "backgroundColor",
                           "numberPrecision", "shouldUseThousandSeparators", "unit",
                           "unitPosition", "sparklineValues", "sparklineDisplay",
                           "showSparklineAreaGraph", "sparklineStrokeColor", "sparklineAreaColor",
                           "sparklineHighlightDots", "sparklineHighlightSegments", "trendValue",
                           "trendDisplay", "trendColor", "trendFontSize",
                           "shouldAbbreviateTrendValue", "underLabel", "underLabelFontSize"},
    "splunk.table": {"count", "showRowNumbers", "showInternalFields", "tableFormat",
                     "columnFormat", "headerVisibility", "backgroundColor", "fontSize",
                     "table", "paginateDataSourceKey"},
    "splunk.line": COMMON_CHART | {"nullValueDisplay", "lineWidth", "markerDisplay", "lineDashStyle"},
    "splunk.area": COMMON_CHART | {"nullValueDisplay", "areaOpacity"},
    "splunk.column": COMMON_CHART | {"columnSpacing", "seriesSpacing"},
    "splunk.markdown": {"markdown", "fontColor", "backgroundColor", "fontSize", "fontFamily"},
    "splunk.linkgraph": {"backgroundColor", "fieldOrder", "linkColor", "linkWidth", "nodeColor",
                         "nodeTextColor", "nodeHeight", "nodeHighlightColor",
                         "nodeTextHighlightColor", "nodeSpacingX", "nodeSpacingY", "nodeWidth",
                         "resultLimit", "showNodeCounts", "showValueCounts"},
    "splunk.sankey": {"backgroundColor", "colorMode", "linkOpacity", "linkValues", "linkColors",
                      "resultLimit", "seriesColors"},
}
TABLE_FORMAT = {"rowBackgroundColors", "rowColors", "headerBackgroundColor", "headerColor",
                "cellTextColor", "align"}
ENUMS = {
    "legendDisplay": {"right", "left", "top", "bottom", "off"},
    "nullValueDisplay": {"gaps", "zero", "connect"},
    "markerDisplay": {"off", "filled", "outlined"},
    "sparklineDisplay": {"before", "after", "below", "off"},
    "trendDisplay": {"percent", "absolute", "off"},
    "unitPosition": {"before", "after"},
    "dataValuesDisplay": {"off", "all", "minmax"},
    "colorMode": {"categorical", "dynamic"},
}
MARKDOWN_FONT = {"extraSmall", "small", "default", "large", "extraLarge"}
HANDLERS = {
    "drilldown.linkToSearch": ({"type", "newTab", "query", "earliest", "latest"}, {"type": {"auto", "custom"}}),
    "drilldown.linkToDashboard": ({"app", "dashboard", "newTab", "tokens"}, {}),
    "drilldown.setToken": ({"tokens"}, {}),
    "drilldown.customUrl": ({"url", "newTab"}, {}),
    "drilldown.linkToReport": ({"app", "report", "newTab"}, {}),
}
INPUT_KEYS = {"type", "title", "options", "dataSources", "context", "encoding"}
INPUT_OPTIONS = {
    "input.timerange": {"token", "defaultValue"},
    "input.dropdown": {"token", "defaultValue", "items", "selectFirstSearchResult"},
    "input.multiselect": {"token", "defaultValue", "items", "selectFirstSearchResult"},
    "input.text": {"token", "defaultValue"},
}
LAYOUT_KEYS = {"type", "structure", "globalInputs", "options", "tabs", "layoutDefinitions"}
BLOCK_KEYS = {"item", "type", "position"}
TOKEN_RE = re.compile(r"\$([A-Za-z0-9_]+)(?:\.[A-Za-z0-9_]+)?\$")
CONTEXT_FN_RE = re.compile(r"(?:matchValue|rangeValue|prepend|gradient|pick)\(([A-Za-z0-9_]+)\)")


def check_dashboard(path: Path, macros: dict, transforms: dict) -> None:
    where = path.name
    try:
        root = ET.fromstring(path.read_text(encoding="utf-8"))
    except ET.ParseError as exc:
        err(where, f"XML parse error: {exc}")
        return
    if root.tag != "dashboard" or root.get("version") != "2":
        err(where, "root must be <dashboard version=\"2\">")
    if root.get("theme") not in (None, "light", "dark"):
        err(where, "theme must be light or dark")
    for child in root:
        if child.tag not in ("label", "description", "definition", "meta"):
            err(where, f"unexpected element <{child.tag}>")
    definition = root.find("definition")
    if definition is None or not (definition.text or "").strip():
        err(where, "missing <definition>")
        return
    try:
        dash = json.loads(definition.text)
    except json.JSONDecodeError as exc:
        err(where, f"definition JSON error: {exc}")
        return

    for key in dash:
        if key not in DASH_TOP:
            err(where, f"unknown top-level key '{key}'")

    data_sources = dash.get("dataSources", {})
    inputs = dash.get("inputs", {})
    vizzes = dash.get("visualizations", {})
    defined_tokens = {i.get("options", {}).get("token") for i in inputs.values()}

    for ds_id, ds in data_sources.items():
        loc = f"{where} dataSources.{ds_id}"
        for key in ds:
            if key not in DS_KEYS:
                err(loc, f"unknown key '{key}'")
        dtype = ds.get("type")
        if dtype not in DS_OPTIONS:
            err(loc, f"unknown type {dtype!r}")
            continue
        opts = ds.get("options", {})
        for key in opts:
            if key not in DS_OPTIONS[dtype]:
                err(loc, f"unknown option '{key}'")
        for key in opts.get("queryParameters", {}):
            if key not in QUERY_PARAMS:
                err(loc, f"unknown queryParameters key '{key}'")
        if "refreshType" in opts and opts["refreshType"] not in ("delay", "interval"):
            err(loc, "refreshType must be delay or interval")
        if dtype == "ds.chain" and opts.get("extend") not in data_sources:
            err(loc, f"extends missing data source {opts.get('extend')!r}")
        query = opts.get("query", "")
        check_search_refs(loc, query, macros, transforms)
        for tok in TOKEN_RE.findall(query + json.dumps(opts.get("queryParameters", {}))):
            if tok not in defined_tokens:
                err(loc, f"token ${tok}$ is not defined by any input")

    for in_id, inp in inputs.items():
        loc = f"{where} inputs.{in_id}"
        for key in inp:
            if key not in INPUT_KEYS:
                err(loc, f"unknown key '{key}'")
        itype = inp.get("type")
        if itype not in INPUT_OPTIONS:
            err(loc, f"unknown input type {itype!r}")
            continue
        for key in inp.get("options", {}):
            if key not in INPUT_OPTIONS[itype]:
                err(loc, f"unknown option '{key}'")
        for ref in inp.get("dataSources", {}).values():
            if ref not in data_sources:
                err(loc, f"references missing data source {ref!r}")
        ctx = set(inp.get("context", {}))
        for name in CONTEXT_FN_RE.findall(json.dumps(inp.get("options", {}))):
            if name not in ctx:
                err(loc, f"uses context '{name}' that is not defined")

    for viz_id, viz in vizzes.items():
        loc = f"{where} visualizations.{viz_id}"
        for key in viz:
            if key not in VIZ_KEYS:
                err(loc, f"unknown key '{key}'")
        vtype = viz.get("type")
        if vtype not in VIZ_OPTIONS:
            err(loc, f"unknown visualization type {vtype!r}")
            continue
        opts = viz.get("options", {})
        for key, value in opts.items():
            if key not in VIZ_OPTIONS[vtype]:
                err(loc, f"unknown option '{key}' for {vtype}")
            if key in ENUMS and isinstance(value, str) and not value.startswith(">") and value not in ENUMS[key]:
                err(loc, f"{key}={value!r} not in {sorted(ENUMS[key])}")
        if vtype == "splunk.markdown" and opts.get("fontSize", "default") not in MARKDOWN_FONT:
            err(loc, f"markdown fontSize must be one of {sorted(MARKDOWN_FONT)}")
        if vtype == "splunk.linkgraph" and not isinstance(opts.get("fieldOrder", []), list):
            err(loc, "fieldOrder must be a JSON array (a string breaks getField())")
        for key in opts.get("tableFormat", {}):
            if key not in TABLE_FORMAT:
                err(loc, f"unknown tableFormat key '{key}'")
        for ref in viz.get("dataSources", {}).values():
            if ref not in data_sources:
                err(loc, f"references missing data source {ref!r}")
        if vtype != "splunk.markdown" and not viz.get("dataSources"):
            err(loc, "has no data source")
        ctx = set(viz.get("context", {}))
        for name in CONTEXT_FN_RE.findall(json.dumps(opts)):
            if name not in ctx:
                err(loc, f"uses context '{name}' that is not defined")
        for handler in viz.get("eventHandlers", []):
            htype = handler.get("type")
            if htype not in HANDLERS:
                err(loc, f"unknown event handler {htype!r}")
                continue
            allowed, enums = HANDLERS[htype]
            for key, value in handler.get("options", {}).items():
                if key not in allowed:
                    err(loc, f"{htype}: unknown option '{key}'")
                if key in enums and value not in enums[key]:
                    err(loc, f"{htype}: {key}={value!r} not in {sorted(enums[key])}")
            if htype == "drilldown.linkToDashboard":
                target = handler.get("options", {}).get("dashboard")
                if target and not (VIEWS / f"{target}.xml").is_file():
                    err(loc, f"drilldown to missing dashboard {target!r}")

    layout = dash.get("layout", {})
    for key in layout:
        if key not in LAYOUT_KEYS:
            err(f"{where} layout", f"unknown key '{key}'")
    if layout.get("type") not in ("grid", "absolute"):
        err(f"{where} layout", "type must be grid or absolute")
    placed = set()
    for block in layout.get("structure", []):
        for key in block:
            if key not in BLOCK_KEYS:
                err(f"{where} layout", f"unknown block key '{key}'")
        item = block.get("item")
        placed.add(item)
        if item not in vizzes:
            err(f"{where} layout", f"places missing visualization {item!r}")
        pos = block.get("position", {})
        if set(pos) - {"x", "y", "w", "h"}:
            err(f"{where} layout", f"{item}: unknown position keys {sorted(set(pos) - {'x', 'y', 'w', 'h'})}")
        if layout.get("type") == "grid" and pos.get("x", 0) + pos.get("w", 0) > 1200:
            err(f"{where} layout", f"{item}: block extends past the 1200px grid")
    for viz_id in vizzes:
        if viz_id not in placed:
            err(f"{where} layout", f"visualization {viz_id!r} is not placed in the layout")
    for in_id in layout.get("globalInputs", []):
        if in_id not in inputs:
            err(f"{where} layout", f"globalInputs references missing input {in_id!r}")
    for in_id in inputs:
        if in_id not in layout.get("globalInputs", []):
            err(f"{where} layout", f"input {in_id!r} is defined but not shown")
    for tok in TOKEN_RE.findall(json.dumps(dash.get("defaults", {}))):
        if tok not in defined_tokens and inputs:
            err(f"{where} defaults", f"token ${tok}$ is not defined by any input")


def check_nav() -> None:
    root = ET.fromstring((DEFAULT / "data" / "ui" / "nav" / "default.xml").read_text())
    builtin = {"search", "reports", "alerts", "dashboards", "datasets", "analytics_workspace"}
    for view in root.iter("view"):
        name = view.get("name")
        if name not in builtin and not (VIEWS / f"{name}.xml").is_file():
            err("nav/default.xml", f"view {name!r} does not exist")
    for view in VIEWS.glob("*.xml"):
        if not any(v.get("name") == view.stem for v in root.iter("view")):
            warn("nav/default.xml", f"view {view.stem!r} is not in the nav")


def main() -> int:
    app_conf = check_app_conf()
    macros = check_macros()
    transforms = check_transforms()
    saved = check_savedsearches()
    check_meta()
    check_manifest(app_conf)
    check_nav()
    for stanza, keys in saved.items():
        check_search_refs(f"savedsearches.conf [{stanza}]", keys.get("search", ""), macros, transforms)
    for stanza, keys in macros.items():
        check_search_refs(f"macros.conf [{stanza}]", keys.get("definition", ""), macros, transforms)
    views = sorted(VIEWS.glob("*.xml"))
    for path in views:
        check_dashboard(path, macros, transforms)

    for w in warnings:
        print(f"WARN  {w}")
    for e in errors:
        print(f"ERROR {e}")
    print(f"checked app.conf, macros.conf ({len(macros)} macros), transforms.conf, "
          f"savedsearches.conf ({len(saved)} searches), default.meta, app.manifest, nav, "
          f"{len(views)} dashboards: {len(errors)} error(s), {len(warnings)} warning(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
