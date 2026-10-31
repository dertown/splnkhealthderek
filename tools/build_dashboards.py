#!/usr/bin/env python3
"""Generate Dashboard Studio XML views. Run from the repo root."""
from __future__ import annotations

import csv
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

ROOT = Path(__file__).resolve().parents[1]
VIEWS = ROOT / "default" / "data" / "ui" / "views"

GREEN = "#53A051"
YELLOW = "#F8BE34"
RED = "#DC4E41"
ACCENT = ["#7B56DB", "#009CEB", "#00CDAF", "#DD9900", "#FF677B"]

HEALTH_COLORS = [
    {"value": RED, "to": 0.5},
    {"value": YELLOW, "from": 0.5, "to": 1.5},
    {"value": GREEN, "from": 1.5},
]

# Map the status word itself to that word's color (GREEN is green, RED is red).
STATUS_COLORS = [
    {"match": "GREEN", "value": GREEN},
    {"match": "YELLOW", "value": YELLOW},
    {"match": "RED", "value": RED},
    {"match": "N/A", "value": YELLOW},
    {"match": "LOCAL", "value": GREEN},
    {"match": "READY", "value": GREEN},
    {"match": "PROVIDER", "value": GREEN},
    {"match": "FAILED", "value": RED},
    {"match": "MISCONFIG", "value": RED},
    {"match": "WAITING", "value": YELLOW},
    {"match": "STALLED", "value": RED},
    {"match": "REPLIED", "value": GREEN},
    {"match": "IDLE", "value": "#6B6B6B"},
    {"match": "WAIT", "value": "#6B6B6B"},
    {"match": "PASS", "value": GREEN},
    {"match": "TESTING", "value": YELLOW},
    {"match": "SKIP", "value": "#6B6B6B"},
    {"match": "FAIL", "value": RED},
]

# Row colors: 1=red/alert, 2=yellow, 3=green/ok
ROW_COLORS = [
    {"from": 0, "to": 1.5, "value": "#5C1A1A"},
    {"from": 1.5, "to": 2.5, "value": "#5C4A12"},
    {"from": 2.5, "to": 4, "value": "#14301A"},
]


def model_dropdown_items() -> list[dict]:
    """Static Model dropdown entries so Studio always renders a list of names."""
    prov_labels: dict[str, str] = {}
    with (ROOT / "lookups" / "dq_agent_ai_providers.csv").open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            prov_labels[(row.get("provider") or "").strip()] = (row.get("provider_label") or row.get("provider") or "").strip()
    items: list[dict] = []
    seen: set[str] = set()
    with (ROOT / "lookups" / "dq_agent_ai_models.csv").open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            provider = (row.get("provider") or "none").strip()
            model = (row.get("model") or "none").strip()
            name = (row.get("model_label") or model).strip()
            if provider == "none" or model == "none":
                if "none" not in seen:
                    seen.add("none")
                    items.append({"label": "None — local briefing only", "value": "none"})
                continue
            key = f"{provider}|{model}"
            if key in seen:
                continue
            seen.add(key)
            pl = prov_labels.get(provider, provider)
            items.append({"label": f"{name} ({pl})", "value": model})
    return items


def wrap(label: str, description: str, definition: dict) -> str:
    body = json.dumps(definition, indent=2)
    return (
        f'<dashboard version="2" theme="dark">\n'
        f"  <label>{xml_escape(label)}</label>\n"
        f"  <description>{xml_escape(description)}</description>\n"
        f"  <definition><![CDATA[\n{body}\n]]></definition>\n"
        f"</dashboard>\n"
    )


def ds(name: str, query: str, earliest: str | None = None, latest: str | None = None, refresh: str | None = "5m") -> dict:
    options: dict = {"query": query.strip()}
    if refresh:
        options["refresh"] = refresh
        options["refreshType"] = "delay"
    if earliest is not None or latest is not None:
        options["queryParameters"] = {
            "earliest": earliest if earliest is not None else "$global_time.earliest$",
            "latest": latest if latest is not None else "$global_time.latest$",
        }
    return {"type": "ds.search", "name": name, "options": options}


def chain(name: str, parent: str, query: str) -> dict:
    return {
        "type": "ds.chain",
        "name": name,
        "options": {"extend": parent, "query": query.strip()},
    }


def timerange(default: str = "-24h@h,now") -> dict:
    return {
        "type": "input.timerange",
        "title": "Time range",
        "options": {"token": "global_time", "defaultValue": default},
    }


def defaults() -> dict:
    return {
        "dataSources": {
            "ds.search": {
                "options": {
                    "queryParameters": {
                        "earliest": "$global_time.earliest$",
                        "latest": "$global_time.latest$",
                    }
                }
            }
        }
    }


def md(text: str, font: str = "default") -> dict:
    return {
        "type": "splunk.markdown",
        "options": {"markdown": text, "fontSize": font, "backgroundColor": "transparent"},
    }


def decision_button(title: str, ds_id: str, token: str = "tok_decision", fill: str | None = None) -> dict:
    """One-row table so row._click_action.value is a real table drilldown.

    The action lives in a hidden _ field so the label is the only visible column and
    fills the table; a second visible column forces Studio scrollbars in the pill.
    """
    viz = table(title, ds_id, count=1)
    viz["showLastUpdated"] = False
    viz["showProgressBar"] = False
    viz["eventHandlers"] = [
        {
            "type": "drilldown.setToken",
            "options": {
                "tokens": [{"token": token, "key": "row._click_action.value"}],
            },
        }
    ]
    viz["options"]["headerVisibility"] = "none"
    viz["options"]["fontSize"] = "default"
    viz["options"]["columnFormat"] = {"button_label": {"align": "center"}}
    if fill:
        viz["options"]["backgroundColor"] = fill
        viz["options"]["tableFormat"] = {
            "rowBackgroundColors": "> table | seriesByName(\"_color_rank\") | rangeValue(btnColors)",
            "headerBackgroundColor": fill,
            "headerColor": "#FFFFFF",
            "cellTextColor": "#FFFFFF",
            "align": "center",
        }
        viz["context"] = {"btnColors": [{"from": 0, "to": 10, "value": fill}]}
    return viz


def single_status(title: str, ds_id: str, value_field: str, score_field: str) -> dict:
    return {
        "type": "splunk.singlevalue",
        "title": title,
        "dataSources": {"primary": ds_id},
        "showLastUpdated": True,
        "showProgressBar": True,
        "options": {
            "majorValue": f"> primary | seriesByName(\"{value_field}\") | lastPoint()",
            "majorColor": f"> primary | seriesByName(\"{value_field}\") | lastPoint() | matchValue(statusColors)",
            "backgroundColor": "transparent",
            "majorFontSize": 36,
        },
        "context": {"statusColors": STATUS_COLORS},
    }


def single_number(title: str, ds_id: str, field: str, unit: str = "", spark: str | None = None, precision: int = 1) -> dict:
    options = {
        "majorValue": f"> primary | seriesByName(\"{field}\") | lastPoint()",
        "backgroundColor": "transparent",
        "shouldUseThousandSeparators": True,
        "numberPrecision": precision,
        "majorFontSize": 32,
    }
    if unit:
        options["unit"] = unit
        options["unitPosition"] = "after"
    if spark:
        options["sparklineValues"] = f"> primary | seriesByName(\"{spark}\")"
        options["sparklineDisplay"] = "below"
        options["showSparklineAreaGraph"] = True
        options["trendDisplay"] = "percent"
        options["trendValue"] = "> sparklineValues | delta(-2)"
    else:
        options["sparklineDisplay"] = "off"
        options["trendDisplay"] = "off"
    return {
        "type": "splunk.singlevalue",
        "title": title,
        "dataSources": {"primary": ds_id},
        "showLastUpdated": True,
        "showProgressBar": True,
        "options": options,
    }


def table(title: str, ds_id: str, rank_field: str = "_color_rank", count: int = 20) -> dict:
    return {
        "type": "splunk.table",
        "title": title,
        "dataSources": {"primary": ds_id},
        "showLastUpdated": True,
        "showProgressBar": True,
        "options": {
            "count": count,
            "showRowNumbers": False,
            "showInternalFields": False,
            "tableFormat": {
                "rowBackgroundColors": f"> table | seriesByName(\"{rank_field}\") | rangeValue(rowColors)"
            },
        },
        "context": {"rowColors": ROW_COLORS},
        "eventHandlers": [
            {
                "type": "drilldown.linkToSearch",
                "options": {
                    "type": "auto",
                    "newTab": True,
                },
            }
        ],
    }


def drill_source(viz: dict, field: str = "data_source") -> dict:
    """Click a topology row or node to set tok_data_source (does not open Search)."""
    viz = dict(viz)
    viz["eventHandlers"] = [
        {
            "type": "drilldown.setToken",
            "options": {
                "tokens": [{"token": "tok_data_source", "key": f"row.{field}.value"}],
            },
        }
    ]
    return viz


def line(title: str, ds_id: str, y_title: str) -> dict:
    return {
        "type": "splunk.line",
        "title": title,
        "dataSources": {"primary": ds_id},
        "showLastUpdated": True,
        "showProgressBar": True,
        "options": {
            "seriesColors": ACCENT,
            "legendDisplay": "right",
            "yAxisTitleText": y_title,
            "nullValueDisplay": "connect",
            "lineWidth": 2,
            "markerDisplay": "off",
        },
    }


def area(title: str, ds_id: str, y_title: str) -> dict:
    return {
        "type": "splunk.area",
        "title": title,
        "dataSources": {"primary": ds_id},
        "showLastUpdated": True,
        "showProgressBar": True,
        "options": {
            "seriesColors": ACCENT,
            "legendDisplay": "right",
            "yAxisTitleText": y_title,
            "areaOpacity": 0.35,
            "nullValueDisplay": "connect",
        },
    }


def column(title: str, ds_id: str, y_title: str) -> dict:
    return {
        "type": "splunk.column",
        "title": title,
        "dataSources": {"primary": ds_id},
        "showLastUpdated": True,
        "showProgressBar": True,
        "options": {
            "seriesColors": ACCENT,
            "legendDisplay": "right",
            "yAxisTitleText": y_title,
            "dataValuesDisplay": "off",
        },
    }


def block(item: str, x: int, y: int, w: int, h: int) -> dict:
    return {"item": item, "type": "block", "position": {"x": x, "y": y, "w": w, "h": h}}


def input_block(item: str, x: int, y: int, w: int, h: int) -> dict:
    return {"item": item, "type": "input", "position": {"x": x, "y": y, "w": w, "h": h}}


def linkgraph(title: str, ds_id: str, field_order: list[str]) -> dict:
    return {
        "type": "splunk.linkgraph",
        "title": title,
        "dataSources": {"primary": ds_id},
        "showLastUpdated": True,
        "showProgressBar": True,
        "options": {
            # Must be a JSON array. A comma-separated string makes Dashboard Studio
            # throw "f.forEach is not a function" because getField() is an array.
            "fieldOrder": field_order,
            "linkColor": "#009CEB",
            "nodeHighlightColor": "#7B56DB",
            "nodeWidth": 170,
            "nodeHeight": 22,
            "nodeSpacingX": 40,
            "nodeSpacingY": 12,
            "resultLimit": 40,
            "showNodeCounts": True,
            "showValueCounts": True,
        },
    }


def sankey(title: str, ds_id: str) -> dict:
    return {
        "type": "splunk.sankey",
        "title": title,
        "dataSources": {"primary": ds_id},
        "showLastUpdated": True,
        "showProgressBar": True,
        "options": {
            "colorMode": "categorical",
            "linkOpacity": 0.6,
            "seriesColors": ACCENT,
        },
    }


def grid(structure: list, extra_inputs: list | None = None, include_time: bool = True) -> dict:
    inputs = (["input_global_trp"] if include_time else []) + (extra_inputs or [])
    layout: dict = {"type": "grid", "structure": structure}
    if inputs:
        layout["globalInputs"] = inputs
    return layout


# ---------------------------------------------------------------------------
# Dashboard Studio card styling
#
# Every view is written as a grid of blocks. studio_cards() turns that grid into a
# Dashboard Studio absolute layout: a dark canvas, a rounded card behind each panel,
# and a thin colored accent bar per panel type. Panels keep their ids and data.
# ---------------------------------------------------------------------------

CANVAS = "#0B0F19"
CARD_FILL = "#151B2B"
CARD_LINE = "#26304A"
HEADER_FILL = "#1B2342"
ACCENT_KPI = "#00CDAF"
ACCENT_TABLE = "#7B56DB"
ACCENT_CHART = "#009CEB"
ACCENT_GRAPH = "#DD9900"
GUTTER = 6
BAR_H = 4
# Buttons render as a compact rounded pill centered in their grid cell. The table
# inside shows a single auto-width column; a fixed-width or second column makes
# Studio add scrollbars that hide the label.
BUTTON_W = 260
BUTTON_H = 56
BUTTON_RX = 8
BUTTON_PAD_X = 8
BUTTON_PAD_Y = 4
HIDDEN_PREFIXES = ()
TRANSPARENT_TYPES = (
    "splunk.table", "splunk.line", "splunk.area", "splunk.column", "splunk.linkgraph", "splunk.sankey",
    "splunk.singlevalue", "splunk.markdown",
)


def _rect(fill: str, stroke: str | None = None, rx: int = 10) -> dict:
    options: dict = {"fillColor": fill, "rx": rx}
    if stroke:
        options["strokeColor"] = stroke
        options["strokeWidth"] = 1
    return {"type": "splunk.rectangle", "options": options}


def _accent_for(viz: dict) -> str | None:
    vtype = viz.get("type", "")
    if vtype == "splunk.singlevalue":
        return ACCENT_KPI
    if vtype == "splunk.table":
        return ACCENT_TABLE
    if vtype in ("splunk.linkgraph", "splunk.sankey"):
        return ACCENT_GRAPH
    if vtype in ("splunk.line", "splunk.area", "splunk.column"):
        return ACCENT_CHART
    return None


def studio_cards(definition: dict) -> dict:
    layout = definition.get("layout", {})
    if layout.get("type") != "grid":
        return definition
    vizzes = definition.setdefault("visualizations", {})
    for viz in vizzes.values():
        if viz.get("type") in TRANSPARENT_TYPES:
            viz.setdefault("options", {}).setdefault("backgroundColor", "transparent")
        if "showLastUpdated" in viz:
            viz["showLastUpdated"] = False

    structure: list = []
    bottom = 0
    n = 0
    for block_def in layout.get("structure", []):
        item = block_def["item"]
        pos = block_def["position"]
        x, y, w, h = pos["x"], pos["y"], pos["w"], pos["h"]
        bottom = max(bottom, y + h)
        if block_def.get("type") == "input":
            structure.append(block(item, x + GUTTER, y + GUTTER, w - 2 * GUTTER, h - GUTTER) | {"type": "input"})
            continue
        viz = vizzes[item]
        is_button = viz.get("type") == "splunk.table" and viz.get("options", {}).get("headerVisibility") == "none"
        if is_button:
            n += 1
            bw = min(BUTTON_W, w - 2 * GUTTER)
            bx = x + (w - bw) // 2
            by = y + (h - BUTTON_H) // 2
            pill_id = f"pill_{n}"
            vizzes[pill_id] = _rect(viz["options"].get("backgroundColor", ACCENT_TABLE), None, rx=BUTTON_RX)
            structure.append(block(pill_id, bx, by, bw, BUTTON_H))
            structure.append(block(
                item, bx + BUTTON_PAD_X, by + BUTTON_PAD_Y, bw - 2 * BUTTON_PAD_X, BUTTON_H - 2 * BUTTON_PAD_Y,
            ))
            continue
        if item.startswith(HIDDEN_PREFIXES):
            structure.append(block(item, x + GUTTER, y + GUTTER, w - 2 * GUTTER, h - 2 * GUTTER))
            continue
        n += 1
        header = item == "viz_header"
        card_id, bar_id = f"card_{n}", f"bar_{n}"
        vizzes[card_id] = _rect(HEADER_FILL if header else CARD_FILL, CARD_LINE)
        structure.append(block(card_id, x + GUTTER, y + GUTTER, w - 2 * GUTTER, h - 2 * GUTTER))
        accent = ACCENT_TABLE if header else _accent_for(viz)
        inset_left, inset_top = 14, 14
        if header:
            vizzes[bar_id] = _rect(accent, None, rx=3)
            structure.append(block(bar_id, x + GUTTER, y + GUTTER, 6, h - 2 * GUTTER))
            inset_left = 22
        elif accent:
            vizzes[bar_id] = _rect(accent, None, rx=2)
            structure.append(block(bar_id, x + GUTTER, y + GUTTER, w - 2 * GUTTER, BAR_H))
            inset_top = 14
        structure.append(block(item, x + inset_left, y + inset_top, w - inset_left - 14, h - inset_top - 12))

    new_layout: dict = {
        "type": "absolute",
        "options": {"width": 1200, "height": bottom + GUTTER * 2, "display": "auto-scale", "backgroundColor": CANVAS},
        "structure": structure,
    }
    if layout.get("globalInputs"):
        new_layout["globalInputs"] = layout["globalInputs"]
    definition["layout"] = new_layout
    return definition


# ---------------------------------------------------------------------------
# Executive Overview
# ---------------------------------------------------------------------------

# Worst current color per health-report feature across every instance.
Q_HEALTH_BY_FEATURE = r"""
search `exec_health_health_report`
| eval health_val=lower(coalesce(color, "unknown"))
| stats latest(health_val) as health_val by host, feature
| eval score=case(health_val="green", 2, health_val="yellow", 1, health_val="red", 0, 1=1, 1)
| stats min(score) as score, count(eval(score<2)) as unhealthy_hosts by feature
""".strip()

Q_HEALTH_COMPONENTS = (
    Q_HEALTH_BY_FEATURE
    + "\n"
    + r"""| eval component="instance:".feature
| table component, score
| append [
    | tstats count as events where index=`exec_health_idx` earliest=-15m latest=now
    | eval component="ingestion_live_15m", score=if(events>0, 2, 0)
    | table component, score
]
| append [
    search `exec_health_license_usage` earliest=-8d@d latest=@d
    | eval GB=b/1024/1024/1024
    | bin _time span=1d
    | stats sum(GB) as daily_GB by _time
    | streamstats window=7 current=f avg(daily_GB) as ma_7d
    | sort 0 -_time
    | head 1
    | eval drop_pct=if(ma_7d>0, round(((ma_7d-daily_GB)/ma_7d)*100, 1), 0)
    | eval component="ingest_vs_7d_ma", score=case(isnull(ma_7d) OR ma_7d=0, 2, drop_pct>=`exec_health_drop_red_pct`, 0, drop_pct>=`exec_health_drop_yellow_pct`, 1, 1=1, 2)
    | table component, score
]
| append [
    | tstats latest(_time) as last_data where index=`exec_health_idx` earliest=-24h latest=now by host
    | eval silent=if((now()-last_data)>`exec_health_silence_sec`, 1, 0)
    | stats count as hosts, sum(silent) as silent_hosts
    | eval silent_ratio=if(hosts>0, silent_hosts/hosts, 1)
    | eval component="host_silence", score=case(hosts=0, 0, silent_hosts=0, 2, silent_ratio>0.2, 0, 1=1, 1)
    | table component, score
]
| eval _color_rank=case(score<=0, 1, score<2, 2, 1=1, 3)
""".strip()
)

# Complete days only (the data source ends at @d): a partial "today" would always
# look like a large drop against the 7-day average.
Q_LICENSE_DAILY = r"""
search `exec_health_license_usage`
| bin _time span=1d
| stats sum(b) as bytes by _time
| eval daily_GB=bytes/1024/1024/1024
| streamstats window=7 current=f avg(daily_GB) as ma_7d
| eval ma_7d=round(ma_7d, 3), daily_GB=round(daily_GB, 3)
| eval variance_pct=if(ma_7d>0, round(((daily_GB-ma_7d)/ma_7d)*100, 1), 0)
| eval health_score=case(isnull(ma_7d), 2, daily_GB < ma_7d*(1-`exec_health_drop_red_pct`/100), 0, daily_GB < ma_7d*(1-`exec_health_drop_yellow_pct`/100), 1, 1=1, 2)
| eval health_label=case(health_score=0, "RED", health_score=1, "YELLOW", 1=1, "GREEN")
| sort _time
""".strip()

Q_INDEXER_CLUSTER = (
    Q_HEALTH_BY_FEATURE
    + "\n"
    + r"""| stats min(score) as health_score, count as features, count(eval(score<2)) as unhealthy
| where features>0
| eval clustering_status=case(health_score>=2, "GREEN", health_score>=1, "YELLOW", 1=1, "RED")
| eval status_detail=unhealthy." / ".features." features not green"
| appendpipe [
    stats count
    | where count=0
    | eval clustering_status="N/A", health_score=1, status_detail="No health.log events"
]
""".strip()
)

# Hostwide fields are nested JSON (data.cpu_user_pct, data.mem_used in MB).
Q_SHC = r"""
search index=_introspection sourcetype=splunk_resource_usage component=Hostwide
| eval cpu_pct=coalesce('data.cpu_system_pct', 0)+coalesce('data.cpu_user_pct', 0)
| stats avg(cpu_pct) as avg_cpu, dc(host) as hosts
| where hosts>0
| eval avg_cpu=round(avg_cpu, 1)
| eval health_score=case(avg_cpu>=90, 0, avg_cpu>=75, 1, 1=1, 2)
| eval shc_status=case(health_score=2, "GREEN", health_score=1, "YELLOW", 1=1, "RED")
| eval status_detail=avg_cpu."% CPU across ".hosts." host(s)"
| appendpipe [
    stats count
    | where count=0
    | eval shc_status="N/A", health_score=1, status_detail="No _introspection data"
]
""".strip()

Q_SILENT = r"""
| tstats latest(_time) as last_data where index=`exec_health_idx` by host
| eval silent=if((now()-last_data)>`exec_health_silence_sec`, 1, 0)
| stats count as hosts, sum(silent) as silent_hosts
| fillnull value=0 hosts, silent_hosts
| eval health_score=case(hosts=0, 0, silent_hosts=0, 2, silent_hosts/hosts>0.2, 0, 1=1, 1)
""".strip()

Q_LIVE = r"""
| tstats count as events where index=`exec_health_idx` earliest=-15m latest=now
| appendpipe [ stats count | where count=0 | eval events=0 ]
| eval events_per_sec=round(events/900, 1)
""".strip()

Q_TOP_INDEXES = r"""
search `exec_health_license_usage`
| eval GB=round(b/1024/1024/1024, 3)
| stats sum(GB) as GB by idx
| rename idx as index
| sort 0 -GB
| head 20
| eval _color_rank=3
""".strip()

Q_INTROSPECTION = r"""
search index=_introspection sourcetype=splunk_resource_usage component=Hostwide
| eval cpu_pct=coalesce('data.cpu_system_pct', 0)+coalesce('data.cpu_user_pct', 0)
| eval mem_used_gb=round(coalesce('data.mem_used', 0)/1024, 2)
| stats avg(cpu_pct) as avg_cpu_pct, max(cpu_pct) as max_cpu_pct, latest(mem_used_gb) as mem_used_gb by host
| eval avg_cpu_pct=round(avg_cpu_pct, 1), max_cpu_pct=round(max_cpu_pct, 1)
| eval _color_rank=case(max_cpu_pct>=90, 1, max_cpu_pct>=75, 2, 1=1, 3)
| sort 0 -max_cpu_pct
""".strip()

def host_baseline_core(host_clause: str = "") -> str:
    """Per-host 15m volume vs the prior 24h (96 buckets) of the same host.

    - timechart + fillnull + untable zero-fills buckets, so a host that drops to 0
      events still produces a row (tstats alone emits nothing for an empty bucket).
    - Only the newest bucket that closed at least 5 minutes ago is scored, so a
      still-filling bucket or normal indexing lag is never read as a drop.
    Shared by the dashboards and savedsearches.conf so the logic cannot drift.
    """
    where_host = f" {host_clause}" if host_clause else ""
    return (
        f"| tstats count as events where index=`exec_health_idx`{where_host} earliest=-25h@m latest=@m by _time span=15m host\n"
        "| timechart span=15m limit=0 useother=f sum(events) as events by host\n"
        "| fillnull value=0\n"
        "| untable _time host events\n"
        "| where _time+900+300 <= now()\n"
        "| streamstats window=96 current=f avg(events) as mean_vol stdev(events) as stdev_vol count as samples by host\n"
        "| eventstats max(_time) as scored_bucket\n"
        "| where _time=scored_bucket\n"
        "| eval sigma=`exec_health_sigma`, mean_vol=round(mean_vol, 1), stdev_vol=round(stdev_vol, 1), lower_bound=round(mean_vol-(sigma*stdev_vol), 1)\n"
        '| eval baseline_state=case(samples<8, "WARMUP", stdev_vol>0 AND events < lower_bound AND mean_vol>10, "ALERT", 1=1, "OK")\n'
        "| eval z_score=if(stdev_vol>0, round((events-mean_vol)/stdev_vol, 2), 0)"
    )


Q_HOST_ALERTS = host_baseline_core() + r"""
| where baseline_state="ALERT"
| eval _color_rank=1
| table host, events, mean_vol, stdev_vol, lower_bound, z_score, baseline_state, _color_rank
| sort host
"""

Q_TOPO_ENRICH = r"""
| rex field=source "(?i)(?:^|[^A-Za-z])(?<net_proto>tcp|udp)[:/](?<net_port>\d+)"
| eval net_label=case(
    lower(net_proto)="udp" AND isnotnull(net_port), "UDP:".net_port,
    lower(net_proto)="tcp" AND isnotnull(net_port), "TCP:".net_port,
    1=1, null())
| eval os_class=case(
    match(sourcetype, "(?i)wineventlog|WinHostMon|XmlWinEventLog|^Perfmon|WinRegistry|powershell|^windows:|MSAD:|DhcpSrvLog|^IIS"), "Windows",
    match(source, "(?i)WinEventLog|Perfmon:|\\\\Windows\\\\"), "Windows",
    match(sourcetype, "(?i)^linux_|^osnix|^unix:|^auditd|^journald|^selinux|^secure$|^messages$|^df$|^cpu$|^iostat|^vmstat|^interfaces|^lastlog|^openPorts|^hardware|^netstat|^yum"), "Linux",
    match(source, "(?i)^/var/|^/opt/|^/etc/|^/usr/|^/home/"), "Linux",
    1=1, null())
| append [
    search index=_internal source=*metrics.log group=tcpin_connections
    | eval host=coalesce(sourceHost, hostname)
    | eval fwd=lower(trim(coalesce(fwdType, "")))
    | eval conn=lower(trim(coalesce(connectionType, "")))
    | eval forwarder_class=case(
        match(fwd, "^(uf|lwf)$"), "UF",
        match(fwd, "^(full|hf|hwf)$"), "HF",
        1=1, null())
    | eval metrics_net=if(isnull(forwarder_class) AND match(conn, "raw") AND isnum(coalesce(destPort, dest_port)), "TCP:".coalesce(destPort, dest_port), null())
    | where isnotnull(host) AND (isnotnull(forwarder_class) OR isnotnull(metrics_net))
    | stats latest(forwarder_class) as forwarder_class, latest(metrics_net) as metrics_net by host
]
| append [
    search index=_internal source=*metrics.log group=udpin_connections
    | eval host=coalesce(sourceHost, hostname)
    | eval metrics_net="UDP:".coalesce(destPort, dest_port, port)
    | where isnotnull(host) AND match(metrics_net, "^UDP:[0-9]+$")
    | stats latest(metrics_net) as metrics_net by host
]
| eventstats latest(forwarder_class) as forwarder_class, latest(metrics_net) as metrics_net by host
| eventstats values(os_class) as os_classes by host
| where isnotnull(events)
| eval host_os=case(
    isnotnull(mvfind(os_classes, "Windows")), "Windows",
    isnotnull(mvfind(os_classes, "Linux")), "Linux",
    1=1, os_class)
| eval net_label=coalesce(net_label, metrics_net)
| eval ingest_path=case(
    match(sourcetype, "(?i)httpevent|^aws:|^azure:|^gcp:|^google:|kube:container"), "HEC / API / cloud",
    match(sourcetype, "(?i)edge.?processor|ingest.?processor"), "Edge / Ingest Processor",
    match(sourcetype, "(?i)sc4s"), "SC4S",
    forwarder_class="HF", "HF",
    forwarder_class="UF" AND host_os="Windows", "Windows UF",
    forwarder_class="UF", "Linux UF",
    host_os="Windows", "Windows UF",
    isnotnull(net_label), "Other ".net_label,
    1=1, "Other")
""".strip()

Q_TOPO_PATHS = (
    "| tstats count as events where index=`exec_health_idx` by host sourcetype source index\n"
    + Q_TOPO_ENRICH
    + "\n| stats sum(events) as events by host, ingest_path, index"
    + "\n| sort 0 -events"
    + "\n| head 100"
    + "\n| rename host as data_source, index as splunk_index"
    + "\n| eval _color_rank=3"
    + "\n| table data_source, ingest_path, splunk_index, events, _color_rank"
)

Q_TOPO_OVERVIEW = (
    "| tstats count as events where index=`exec_health_idx` by host sourcetype source index\n"
    + Q_TOPO_ENRICH
    + "\n| stats sum(events) as events by host, ingest_path, index"
    + "\n| sort 0 -events"
    + "\n| head 40"
    + "\n| rename host as data_source, index as splunk_index"
    + "\n| table data_source, ingest_path, splunk_index"
)

Q_TCPIN_PATHS = r"""
search index=_internal source=*metrics.log group=tcpin_connections
| eval data_source=coalesce(sourceHost, hostname)
| eval receiver=host
| eval fwd=lower(trim(coalesce(fwdType, "")))
| eval connection=case(
    match(fwd, "^(uf|lwf)$"), "UF",
    match(fwd, "^(full|hf|hwf)$"), "HF",
    match(lower(coalesce(connectionType, "")), "raw"), "TCP raw",
    1=1, coalesce(fwdType, connectionType, "s2s"))
| where isnotnull(data_source) AND isnotnull(receiver)
| stats sum(kb) as kb, sum(tcp_eps) as eps by data_source, connection, receiver
| eval kb=round(kb, 1), eps=round(eps, 2)
| sort 0 -kb
| head 80
| eval _color_rank=3
| table data_source, connection, receiver, kb, eps, _color_rank
""".strip()

Q_HEC_PATHS = r"""
search `exec_health_hec_metrics`
| `exec_health_hec_normalize`
| lookup hec_token_map token OUTPUT token_name
| eval data_source=coalesce(token_name, token)
| stats sum(hec_events) as events, sum(hec_bytes) as bytes by data_source
| eval kb=round(bytes/1024, 1), ingest_path="HEC", splunk_index="HTTP Event Collector", _color_rank=3
| sort 0 -events
| head 40
| table data_source, ingest_path, splunk_index, events, kb, _color_rank
""".strip()

# Per-source drill-down. tok_data_source is set by clicking data_source in the
# topology table or graph (hidden token latch, no dropdown). tstats cannot
# aggregate index / splunk_server / splunk_server_group, so do not dc(index).
# Main topology searches must not reference this token.
Q_TOPO_SRC_STATS = r"""
| tstats count as events, latest(_time) as last_event, earliest(_time) as first_event, dc(sourcetype) as sourcetypes where index=`exec_health_idx` host="$tok_data_source$"
| eval data_source=replace("$tok_data_source$", "[^A-Za-z0-9._:-]", "")
| where data_source!="none" AND data_source!="" AND data_source!="*"
| eval age_min=round((now()-last_event)/60, 0)
| eval last_event=strftime(last_event, "%Y-%m-%d %H:%M:%S")
| eval first_event=strftime(first_event, "%Y-%m-%d %H:%M:%S")
| eval _color_rank=if(age_min>(`exec_health_silence_sec`/60), 1, 3)
| table data_source, first_event, last_event, events, sourcetypes, _color_rank
""".strip()

Q_TOPO_SRC_TREND = r"""
| tstats count as events where index=`exec_health_idx` host="$tok_data_source$" earliest=-25h@m latest=@m by _time span=15m
| eval data_source=replace("$tok_data_source$", "[^A-Za-z0-9._:-]", "")
| where data_source!="none" AND data_source!="" AND data_source!="*"
| timechart span=15m sum(events) as events
| fillnull value=0 events
| streamstats window=96 current=f avg(events) as mean_vol stdev(events) as stdev_vol count as samples
| eval sigma=`exec_health_sigma`
| eval mean=if(samples>=8, round(mean_vol, 1), null())
| eval drop_bound=if(samples>=8 AND stdev_vol>0, round(mean_vol-(sigma*stdev_vol), 1), null())
| eval burst_bound=if(samples>=8 AND stdev_vol>0, round(mean_vol+(sigma*stdev_vol), 1), null())
| eval drop_bound=if(drop_bound<0, 0, drop_bound)
| table _time, events, mean, drop_bound, burst_bound
""".strip()

Q_TOPO_SRC_OUTLIERS = r"""
| tstats count as events where index=`exec_health_idx` host="$tok_data_source$" earliest=-25h@m latest=@m by _time span=15m
| eval data_source=replace("$tok_data_source$", "[^A-Za-z0-9._:-]", "")
| where data_source!="none" AND data_source!="" AND data_source!="*"
| timechart span=15m sum(events) as events
| fillnull value=0 events
| streamstats window=96 current=f avg(events) as mean_vol stdev(events) as stdev_vol count as samples
| where _time+900+300 <= now()
| eval sigma=`exec_health_sigma`
| eval mean_vol=round(mean_vol, 1), stdev_vol=round(stdev_vol, 1)
| eval drop_bound=round(mean_vol-(sigma*stdev_vol), 1), burst_bound=round(mean_vol+(sigma*stdev_vol), 1)
| eval z_score=if(stdev_vol>0, round((events-mean_vol)/stdev_vol, 2), 0)
| eval outlier=case(
    samples<8, "WARMUP",
    stdev_vol>0 AND events < drop_bound AND mean_vol>10, "DROP",
    stdev_vol>0 AND events > burst_bound AND events>10, "BURST",
    1=1, "OK")
| where outlier="DROP" OR outlier="BURST"
| eval _color_rank=if(outlier="DROP", 1, 2)
| eval bucket=strftime(_time, "%Y-%m-%d %H:%M")
| eval data_source=replace("$tok_data_source$", "[^A-Za-z0-9._:-]", "")
| sort -_time
| table bucket, data_source, events, mean_vol, stdev_vol, z_score, outlier, _color_rank
""".strip()


def dq_agent_findings_core() -> str:
    """Diagnose Splunk Health traffic lights vs learned baselines.

    Emits one row per issue with a suggested fix. Covers ingestion, hosts, HEC,
    instance health, search CPU, SC4S, and Edge. The agent never writes Splunk
    configuration; humans click APPROVE or DISMISS
    before a decision is recorded in dq_agent_approvals.
    """
    host_findings = host_baseline_core() + r"""
| where baseline_state="ALERT"
| eval issue="Host volume below learned 2-sigma bound", severity="RED", entity=host, evidence="events="+tostring(events)+", mean="+tostring(mean_vol)+", lower="+tostring(lower_bound)+", z="+tostring(z_score), suggested_fix="Compare this host's sourcetypes to the prior 24 hours. Repair the stopped monitor, UF outputs.conf, or an index-time filter. Do not suppress the host without change control.", fix_type="runbook_input", proposed_config="none — human repairs the forwarder or input", action="Review"
| head 25
| table issue, severity, entity, evidence, suggested_fix, fix_type, proposed_config, action
"""
    hec_findings = hec_state_core() + r"""
| where hec_state="ALERT"
| eval issue="HEC token silent vs learned baseline", severity="RED", entity=token_label, evidence="baseline_eps="+tostring(baseline_eps)+", recent_events="+tostring(recent_events)+", silent_min="+tostring(silent_minutes), suggested_fix="In Splunk Web open Settings > Data inputs > HTTP Event Collector and confirm this input is enabled. Then check the sender, network path, and index routing. Never paste the HEC token secret into this app.", fix_type="runbook_hec", proposed_config="none — human checks the HEC input and sender", action="Review"
| table issue, severity, entity, evidence, suggested_fix, fix_type, proposed_config, action
"""
    return (
        r"""
| makeresults
| eval _seed=1
| append [
    | tstats count as count where index=`exec_health_idx` earliest=-7d@h latest=@h by _time span=1h
    | timechart span=1h sum(count) as count
    | fillnull value=0 count
    | predict count as prediction future_timespan=0 holdback=0 upper95=upper lower95=lower algorithm=LLP5
    | tail 1
    | where isnotnull(lower) AND count < lower
    | eval issue="Ingestion below learned predict() bound", severity="RED", entity="environment", evidence="hour_count="+tostring(count)+", predict="+tostring(round(prediction,0))+", lower="+tostring(round(lower,0)), suggested_fix="Identify which index dropped vs the 7-day seasonal baseline. Check UF/HF phone-home, HEC tokens, and syslog listeners. Do not raise the learned bound to hide a real drop.", fix_type="investigate", proposed_config="none — human investigates the dropped source", action="Review"
    | table issue, severity, entity, evidence, suggested_fix, fix_type, proposed_config, action
]
| append [
    | tstats count as events where index=`exec_health_idx` earliest=-8d@h latest=@h by _time span=1h index
    | streamstats window=168 current=f avg(events) as ma_7d by index
    | where _time >= relative_time(now(), "-1h@h") AND _time < relative_time(now(), "@h")
    | eval drop_pct=if(ma_7d>0, round(((ma_7d-events)/ma_7d)*100, 1), 0)
    | where drop_pct >= `exec_health_drop_red_pct` AND ma_7d>10
    | eval issue="Index volume below 7-day moving average", severity="RED", entity=index, evidence="last_hour="+tostring(events)+", ma_7d="+tostring(round(ma_7d,0))+", drop_pct="+tostring(drop_pct)+"%", suggested_fix="Confirm whether this index was expected to be quiet (maintenance, source retirement). If not, check the last forwarder or HEC route that writes here. Macro exec_health_idx can be narrowed after review.", fix_type="runbook_index", proposed_config="optional: Settings > Search macros > exec_health_idx", action="Review"
    | table issue, severity, entity, evidence, suggested_fix, fix_type, proposed_config, action
]
| append [
"""
        + host_findings
        + "]\n| append [\n"
        + hec_findings
        + r"""
]
| append [
    | tstats latest(_time) as last_seen where (index=`exec_health_idx` OR index=_internal) earliest=-24h latest=now by index host
    | eval kind=if(index="_internal", "heartbeat", "data")
    | stats max(eval(if(kind="data", last_seen, null()))) as last_data, max(eval(if(kind="heartbeat", last_seen, null()))) as last_heartbeat by host
    | eval data_age_sec=now()-last_data, heartbeat_age_sec=now()-last_heartbeat
    | eval state=case(isnull(last_data) AND heartbeat_age_sec < `exec_health_heartbeat_sec`, "HEARTBEAT ONLY", data_age_sec > `exec_health_silence_sec` AND heartbeat_age_sec < `exec_health_heartbeat_sec`, "DATA SILENT", (isnull(last_data) OR data_age_sec > `exec_health_silence_sec`) AND (isnull(last_heartbeat) OR heartbeat_age_sec > `exec_health_heartbeat_sec`), "HOST DOWN", 1=1, "OK")
    | where state="DATA SILENT" OR state="HEARTBEAT ONLY" OR state="HOST DOWN"
    | eval issue=case(state="HOST DOWN", "Host down — no heartbeat and no indexed data", 1=1, "Host data silent while heartbeat is fresh")
    | eval severity="RED", entity=host, evidence="state="+state+", data_age_sec="+tostring(data_age_sec)+", heartbeat_age_sec="+tostring(heartbeat_age_sec)
    | eval suggested_fix=case(state="HOST DOWN", "The host is not phoning home and not sending data. Check power, network, and splunkd. Do not remove the host from this app.", 1=1, "The UF is up but indexed data stopped. Check outputs.conf, blocked queues, sourcetype transforms, and the destination index. Restart the forwarder only after change control.")
    | eval fix_type=if(state="HOST DOWN", "runbook_host_down", "runbook_uf")
    | eval proposed_config=if(state="HOST DOWN", "none — human restores the endpoint", "none — human repairs the UF pipeline"), action="Review"
    | head 40
    | table issue, severity, entity, evidence, suggested_fix, fix_type, proposed_config, action
]
| append [
    search `exec_health_health_report` earliest=-15m
    | eval health_val=lower(coalesce(color, "unknown"))
    | stats latest(health_val) as health_val by host, feature
    | eval score=case(health_val="green", 2, health_val="yellow", 1, health_val="red", 0, 1=1, 1)
    | where score<2
    | eval issue="Instance health feature not GREEN", severity=if(score=0, "RED", "YELLOW"), entity=host." / ".feature, evidence="host="+host+", feature="+feature+", color="+health_val, suggested_fix="On that instance inspect the red or yellow feature (disk, buckets, splunkd). Do not clear or suppress the health report from this dashboard.", fix_type="runbook_instance", proposed_config="none — human inspects the instance feature", action="Review"
    | sort score, host, feature
    | head 25
    | table issue, severity, entity, evidence, suggested_fix, fix_type, proposed_config, action
]
| append [
    | tstats count as events where index=`exec_health_idx` earliest=-15m latest=now
    | appendpipe [ stats count | where count=0 | eval events=0 ]
    | where events=0
    | eval issue="No live indexed events in the last 15 minutes", severity="RED", entity="environment", evidence="events_15m=0", suggested_fix="Check UF/HF phone-home, HEC tokens, syslog listeners, and whether macro exec_health_idx excludes the indexes that should be live.", fix_type="runbook_ingest_live", proposed_config="optional: Settings > Search macros > exec_health_idx", action="Review"
    | table issue, severity, entity, evidence, suggested_fix, fix_type, proposed_config, action
]
| append [
    search `exec_health_license_usage` earliest=-8d@d latest=@d
    | bin _time span=1d
    | stats sum(b) as bytes by _time
    | eval daily_GB=bytes/1024/1024/1024
    | streamstats window=7 current=f avg(daily_GB) as ma_7d
    | sort 0 -_time
    | head 1
    | eval drop_pct=if(ma_7d>0, round(((ma_7d-daily_GB)/ma_7d)*100, 1), 0)
    | eval health_score=case(isnull(ma_7d), 2, drop_pct>=`exec_health_drop_red_pct`, 0, drop_pct>=`exec_health_drop_yellow_pct`, 1, 1=1, 2)
    | where health_score<2
    | eval issue="Daily ingestion below 7-day moving average", severity=if(health_score=0, "RED", "YELLOW"), entity="environment", evidence="daily_GB="+tostring(round(daily_GB,2))+", ma_7d="+tostring(round(ma_7d,2))+", drop_pct="+tostring(drop_pct)+"%", suggested_fix="Compare indexes and sourcetypes for yesterday vs the prior week. Confirm maintenance or a retired source before treating this as an outage.", fix_type="runbook_license_ma", proposed_config="none — human reviews license usage", action="Review"
    | table issue, severity, entity, evidence, suggested_fix, fix_type, proposed_config, action
]
| append [
    search index=_introspection sourcetype=splunk_resource_usage component=Hostwide earliest=-15m
    | eval cpu_pct=coalesce('data.cpu_system_pct', 0)+coalesce('data.cpu_user_pct', 0)
    | stats avg(cpu_pct) as avg_cpu, max(cpu_pct) as max_cpu by host
    | eval avg_cpu=round(avg_cpu, 1), max_cpu=round(max_cpu, 1)
    | where max_cpu>=75
    | eval issue="Instance CPU above health bound", severity=if(max_cpu>=90, "RED", "YELLOW"), entity=host, evidence="avg_cpu="+tostring(avg_cpu)+"%, max_cpu="+tostring(max_cpu)+"%", suggested_fix="List expensive searches on this host and pause non-essential scheduled searches after change control. Do not kill user searches from this dashboard.", fix_type="runbook_sh", proposed_config="none — human manages search load", action="Review"
    | head 15
    | table issue, severity, entity, evidence, suggested_fix, fix_type, proposed_config, action
]
| append [
    search index=`exec_health_sc4s_idx` `exec_health_sc4s` (error OR warn OR fail OR "connection refused" OR hang OR dropped) earliest=-15m
    | stats count as sc4s_issues, dc(sourcetype) as sourcetypes by host
    | where sc4s_issues>0
    | eval issue="SC4S / syslog errors in the last 15 minutes", severity="RED", entity=host, evidence="issues="+tostring(sc4s_issues)+", sourcetypes="+tostring(sourcetypes), suggested_fix="Check the collector process, destination port, TLS, and that the destination index exists. Use this app's SC4S view for the time series.", fix_type="runbook_sc4s", proposed_config="none — human repairs the syslog collector", action="Review"
    | sort 0 -sc4s_issues
    | head 15
    | table issue, severity, entity, evidence, suggested_fix, fix_type, proposed_config, action
]
| append [
    | mstats max(queue_size_bytes) as queue_size_bytes, max(queue_max_bytes) as queue_max_bytes, rate_sum(export_destination_errors_total) as export_errors_per_sec, rate_sum(processor_events_in_total) as events_in_eps, rate_sum(processor_events_out_total) as events_out_eps where `exec_health_edge_mstats` earliest=-15m latest=now by host
    | eval queue_fill_pct=if(queue_max_bytes>0, round(queue_size_bytes/queue_max_bytes*100, 1), null())
    | eval export_errors_per_sec=round(coalesce(export_errors_per_sec, 0), 3)
    | eval events_in_eps=round(coalesce(events_in_eps, 0), 2), events_out_eps=round(coalesce(events_out_eps, 0), 2)
    | where export_errors_per_sec>0 OR queue_fill_pct>=80 OR (events_in_eps>0 AND events_out_eps=0)
    | eval issue="Edge / Ingest Processor queue or export unhealthy", severity="RED", entity=host, evidence="queue_fill_pct="+tostring(queue_fill_pct)+", export_errors_per_sec="+tostring(export_errors_per_sec)+", in_eps="+tostring(events_in_eps)+", out_eps="+tostring(events_out_eps), suggested_fix="Inspect Edge pipelines for a blocked destination or a filter that drops everything. Do not clear the queue from this dashboard.", fix_type="runbook_edge", proposed_config="none — human repairs the processor pipeline", action="Review"
    | head 15
    | table issue, severity, entity, evidence, suggested_fix, fix_type, proposed_config, action
]
| where isnull(_seed)
| append [
    search index=_internal source=*metrics.log group=tcpin_connections earliest=-2h
    | eval entity=coalesce(sourceHost, hostname)
    | eval tool_fwdType=lower(trim(coalesce(fwdType, "")))
    | eval tool_conn=lower(trim(coalesce(connectionType, "")))
    | where isnotnull(entity)
    | stats latest(tool_fwdType) as tool_fwdType, latest(tool_conn) as tool_conn by entity
]
| append [
    search index=_internal sourcetype=splunkd (log_level=ERROR OR log_level=WARN) earliest=-2h
    | eval entity=host
    | where isnotnull(entity)
    | stats count as tool_err_count, latest(component) as tool_err_component by entity
]
| eventstats latest(tool_fwdType) as tool_fwdType, latest(tool_conn) as tool_conn, latest(tool_err_component) as tool_err_component, max(tool_err_count) as tool_err_count by entity
| where isnotnull(issue)
""".strip()
    )


def executive_overview() -> dict:
    return {
        "title": "Splunk Health Derek+",
        "description": "Traffic-light health for Splunk ingestion, clustering, and host baselines.",
        "defaults": defaults(),
        "inputs": {"input_global_trp": timerange("-24h@h,now")},
        "dataSources": {
            "ds_health_components": ds("Health components", Q_HEALTH_COMPONENTS, "-15m", "now"),
            "ds_overall_health": chain(
                "Overall health",
                "ds_health_components",
                """
| stats min(score) as overall_score
| eval overall_status=case(overall_score>=2, "GREEN", overall_score>=1, "YELLOW", 1=1, "RED")
| eval overall_score=coalesce(overall_score, 0)
| appendpipe [ stats count | where count=0 | eval overall_score=1, overall_status="YELLOW" ]
""".strip(),
            ),
            "ds_license_daily": ds("License GB/day vs 7d MA", Q_LICENSE_DAILY, "-15d@d", "@d", refresh="15m"),
            "ds_indexer_cluster": ds("Indexer cluster peers", Q_INDEXER_CLUSTER, "-15m", "now"),
            "ds_shc": ds("Search head cluster", Q_SHC, "-15m", "now"),
            "ds_silent": ds("Silent hosts", Q_SILENT, "-24h", "now"),
            "ds_live": ds("Live indexed events 15m", Q_LIVE, "-15m", "now"),
            "ds_top_indexes": ds("Top indexes by GB", Q_TOP_INDEXES),
            "ds_introspection": ds("Hostwide introspection", Q_INTROSPECTION),
            "ds_host_alerts": ds("Host 2-sigma alerts", Q_HOST_ALERTS, "-25h@m", "@m"),
            "ds_topo_overview": ds("Data topology preview", Q_TOPO_OVERVIEW),
            "ds_dq_preview": ds("Data quality agent preview", Q_DQ_AGENT_PREVIEW, "-24h", "now"),
        },
        "visualizations": {
            "viz_header": md(
                "# Splunk Health Derek+\n"
                "Traffic lights combine the splunkd health report, live ingestion, 7-day volume baseline, and silent hosts. "
                "GREEN = within baseline · YELLOW = watch · RED = action required."
            ),
            "viz_overall": single_status("Overall health", "ds_overall_health", "overall_status", "overall_score"),
            "viz_gb": single_number("Ingestion (complete days)", "ds_license_daily", "daily_GB", " GB", spark="daily_GB", precision=2),
            "viz_var": {
                "type": "splunk.singlevalue",
                "title": "vs 7-day moving average",
                "dataSources": {"primary": "ds_license_daily"},
                "showLastUpdated": True,
                "showProgressBar": True,
                "options": {
                    "majorValue": "> primary | seriesByName(\"variance_pct\") | lastPoint()",
                    "majorColor": "> primary | seriesByName(\"health_score\") | lastPoint() | rangeValue(healthColors)",
                    "unit": "%",
                    "unitPosition": "after",
                    "sparklineDisplay": "off",
                    "trendDisplay": "off",
                    "numberPrecision": 1,
                    "majorFontSize": 32,
                },
                "context": {"healthColors": HEALTH_COLORS},
            },
            "viz_live": single_number("Indexed events (15m)", "ds_live", "events", "", spark=None, precision=0),
            "viz_idx_cluster": single_status("Instance health", "ds_indexer_cluster", "clustering_status", "health_score"),
            "viz_shc": single_status("Search head load", "ds_shc", "shc_status", "health_score"),
            "viz_silent": {
                "type": "splunk.singlevalue",
                "title": "Silent hosts (>1h no data)",
                "dataSources": {"primary": "ds_silent"},
                "showLastUpdated": True,
                "showProgressBar": True,
                "options": {
                    "majorValue": "> primary | seriesByName(\"silent_hosts\") | lastPoint()",
                    "majorColor": "> primary | seriesByName(\"health_score\") | lastPoint() | rangeValue(healthColors)",
                    "sparklineDisplay": "off",
                    "trendDisplay": "off",
                    "majorFontSize": 32,
                },
                "context": {"healthColors": HEALTH_COLORS},
            },
            "viz_ingest_chart": line("Daily ingestion vs 7-day moving average", "ds_license_daily", "GB / day"),
            "viz_topo": {
                **linkgraph(
                    "Data topology — sources → ingest path → index (open Data Topology for the full map)",
                    "ds_topo_overview",
                    ["data_source", "ingest_path", "splunk_index"],
                ),
                "eventHandlers": [
                    {
                        "type": "drilldown.linkToDashboard",
                        "options": {
                            "app": "splunk_exec_health",
                            "dashboard": "data_topology",
                            "newTab": False,
                        },
                    }
                ],
            },
            "viz_top_indexes": table("Top indexes by license usage (GB)", "ds_top_indexes", count=15),
            "viz_intro": table("Indexer/SH resource usage (_introspection)", "ds_introspection", count=15),
            "viz_host_alerts": table("Hosts below 2σ 24-hour baseline (latest complete 15m)", "ds_host_alerts", count=25),
            "viz_components": table("Health component scores", "ds_health_components", count=20),
            "viz_dq_preview": {
                **table(
                    "Derek+ Data Quality Agent — open findings (click through; the agent never applies a fix unattended)",
                    "ds_dq_preview",
                    count=8,
                ),
                "eventHandlers": [
                    {
                        "type": "drilldown.linkToDashboard",
                        "options": {
                            "app": "splunk_exec_health",
                            "dashboard": "data_quality_agent",
                            "newTab": False,
                        },
                    }
                ],
            },
            "viz_footer": md(
                "Baselines use **streamstats** (host volume) and **predict**/moving average (daily GB), not static thresholds. "
                "Instance health is the splunkd health report (`health.log`, PeriodicHealthReporter); search-head load is `_introspection` (no cluster-manager REST — Splunk Cloud compatible). "
                "Tune `exec_health_*` macros in Settings > Advanced search > Search macros. "
                "Saved alerts ship **disabled** — enable them after configuring email in Splunk (do not put webhook URLs or passwords in this app)."
            ),
        },
        "layout": grid(
            [
                block("viz_header", 0, 0, 1200, 90),
                block("viz_overall", 0, 90, 300, 180),
                block("viz_gb", 300, 90, 300, 180),
                block("viz_var", 600, 90, 300, 180),
                block("viz_live", 900, 90, 300, 180),
                block("viz_idx_cluster", 0, 270, 400, 160),
                block("viz_shc", 400, 270, 400, 160),
                block("viz_silent", 800, 270, 400, 160),
                block("viz_ingest_chart", 0, 430, 1200, 300),
                block("viz_topo", 0, 730, 1200, 340),
                block("viz_top_indexes", 0, 1070, 600, 300),
                block("viz_intro", 600, 1070, 600, 300),
                block("viz_host_alerts", 0, 1370, 700, 320),
                block("viz_components", 700, 1370, 500, 320),
                block("viz_dq_preview", 0, 1690, 1200, 300),
                block("viz_footer", 0, 1990, 1200, 110),
            ]
        ),
    }


# ---------------------------------------------------------------------------
# Host heartbeat
# ---------------------------------------------------------------------------

Q_PHONE_HOME = r"""
| tstats latest(_time) as last_seen where (index=`exec_health_idx` OR index=_internal) host=$host_filter$ by index host
| eval kind=if(index="_internal", "heartbeat", "data")
| stats max(eval(if(kind="data", last_seen, null()))) as last_data, max(eval(if(kind="heartbeat", last_seen, null()))) as last_heartbeat by host
| eval data_age_sec=now()-last_data, heartbeat_age_sec=now()-last_heartbeat
| eval last_data_received=strftime(last_data, "%Y-%m-%d %H:%M:%S")
| eval last_internal_heartbeat=strftime(last_heartbeat, "%Y-%m-%d %H:%M:%S")
| eval data_age=tostring(data_age_sec, "duration"), heartbeat_age=tostring(heartbeat_age_sec, "duration")
| eval state=case(
    isnull(last_data) AND heartbeat_age_sec < `exec_health_heartbeat_sec`, "HEARTBEAT ONLY",
    data_age_sec > `exec_health_silence_sec` AND heartbeat_age_sec < `exec_health_heartbeat_sec`, "DATA SILENT",
    (isnull(last_heartbeat) OR heartbeat_age_sec > `exec_health_silence_sec`) AND data_age_sec > `exec_health_silence_sec`, "HOST DOWN",
    data_age_sec > 900, "DELAYED",
    1=1, "OK")
| eval _color_rank=case(state="HOST DOWN" OR state="DATA SILENT" OR state="HEARTBEAT ONLY", 1, state="DELAYED", 2, 1=1, 3)
| table host, last_data_received, last_internal_heartbeat, data_age, heartbeat_age, state, _color_rank
| sort _color_rank, host
""".strip()

Q_STATE_COUNTS = r"""
| tstats latest(_time) as last_seen where (index=`exec_health_idx` OR index=_internal) host=$host_filter$ by index host
| eval kind=if(index="_internal", "heartbeat", "data")
| stats max(eval(if(kind="data", last_seen, null()))) as last_data, max(eval(if(kind="heartbeat", last_seen, null()))) as last_heartbeat by host
| eval data_age_sec=now()-last_data, heartbeat_age_sec=now()-last_heartbeat
| eval state=case(
    isnull(last_data) AND heartbeat_age_sec < `exec_health_heartbeat_sec`, "HEARTBEAT ONLY",
    data_age_sec > `exec_health_silence_sec` AND heartbeat_age_sec < `exec_health_heartbeat_sec`, "DATA SILENT",
    (isnull(last_heartbeat) OR heartbeat_age_sec > `exec_health_silence_sec`) AND data_age_sec > `exec_health_silence_sec`, "HOST DOWN",
    data_age_sec > 900, "DELAYED",
    1=1, "OK")
| stats count as hosts by state
""".strip()

Q_LATENCY = r"""
search index=`exec_health_idx` host=$host_filter$ earliest=-15m@m latest=now
| eval lag=_indextime-_time
| stats count as events, avg(lag) as avg_lag, perc95(lag) as p95_lag, max(lag) as max_lag, min(lag) as min_lag by host
| eval avg_lag_sec=round(avg_lag, 1), p95_lag_sec=round(p95_lag, 1), max_lag_sec=round(max_lag, 1)
| eval latency_state=case(
    min_lag < -300, "CLOCK AHEAD",
    p95_lag > 3*`exec_health_latency_sec`, "HIGH",
    p95_lag > `exec_health_latency_sec`, "DELAYED",
    1=1, "OK")
| eval _color_rank=case(latency_state="HIGH" OR latency_state="CLOCK AHEAD", 1, latency_state="DELAYED", 2, 1=1, 3)
| table host, events, avg_lag_sec, p95_lag_sec, max_lag_sec, latency_state, _color_rank
| sort _color_rank, -p95_lag_sec
""".strip()

Q_BASELINE_ALL = host_baseline_core("host=$host_filter$") + r"""
| eval current_eps=round(events/900, 2), baseline_eps=round(mean_vol/900, 2)
| eval _color_rank=case(baseline_state="ALERT", 1, baseline_state="WARMUP", 2, 1=1, 3)
| table host, events, mean_vol, stdev_vol, lower_bound, current_eps, baseline_eps, z_score, baseline_state, _color_rank
| sort _color_rank, host
"""

Q_HOST_LIST = r"""
| tstats count where index=`exec_health_idx` by host
| rename host as label
| eval value=label
| table label, value
| sort label
""".strip()


def host_heartbeat() -> dict:
    return {
        "title": "Host Heartbeat & Ingestion Latency",
        "description": "Fleet liveness right now: last indexed data vs _internal heartbeat, ingestion latency, and current 2-sigma volume status per host.",
        "defaults": defaults(),
        "inputs": {
            "input_global_trp": timerange("-24h@h,now"),
            "input_host": {
                "type": "input.dropdown",
                "title": "Host",
                "options": {
                    "token": "host_filter",
                    "defaultValue": "*",
                    "items": "> frame(label, value) | prepend(prependItems)",
                },
                "dataSources": {"primary": "ds_host_list"},
                "context": {"prependItems": [{"label": "All hosts", "value": "*"}]},
            },
        },
        "dataSources": {
            "ds_host_list": ds("Host picker", Q_HOST_LIST, "-24h", "now", refresh="15m"),
            "ds_phone_home": ds("Last data vs heartbeat", Q_PHONE_HOME),
            "ds_state_counts": ds("Host state counts", Q_STATE_COUNTS),
            "ds_state_ok": chain(
                "Hosts OK",
                "ds_state_counts",
                '| append [| makeresults | eval state="OK", hosts=0] | where state="OK" | stats max(hosts) as hosts',
            ),
            "ds_state_delayed": chain(
                "Hosts delayed",
                "ds_state_counts",
                '| append [| makeresults | eval state="DELAYED", hosts=0] | where state="DELAYED" | stats max(hosts) as hosts',
            ),
            "ds_state_silent": chain(
                "Hosts data silent",
                "ds_state_counts",
                '| eval keep=if(state="DATA SILENT" OR state="HEARTBEAT ONLY", 1, 0) | stats sum(eval(if(keep=1, hosts, 0))) as hosts | eval hosts=coalesce(hosts, 0)',
            ),
            "ds_state_down": chain(
                "Hosts down",
                "ds_state_counts",
                '| append [| makeresults | eval state="HOST DOWN", hosts=0] | where state="HOST DOWN" | stats max(hosts) as hosts',
            ),
            "ds_latency": ds("Ingestion latency (last 15m)", Q_LATENCY, "-15m@m", "now"),
            "ds_baseline": ds("24h streamstats baseline", Q_BASELINE_ALL, "-25h@m", "@m"),
        },
        "visualizations": {
            "viz_header": md(
                "# Server phone-home vs data\n"
                "A host can still write `_internal` heartbeats while **indexed data** has stopped. "
                "Baseline alerts fire when the latest 15-minute volume is **2 standard deviations** below that host's 24-hour `streamstats` mean."
            ),
            "viz_ok": single_number("OK", "ds_state_ok", "hosts", "", None, 0),
            "viz_delayed": single_number("Delayed (>15m)", "ds_state_delayed", "hosts", "", None, 0),
            "viz_silent": single_number("Data silent / heartbeat only", "ds_state_silent", "hosts", "", None, 0),
            "viz_down": single_number("Host down", "ds_state_down", "hosts", "", None, 0),
            "viz_table": table("Last data received vs last internal heartbeat", "ds_phone_home", count=30),
            "viz_latency": table("Ingestion latency: index time minus event time, last 15 minutes (seconds)", "ds_latency", count=30),
            "viz_baseline": table("Current volume vs 24-hour baseline, all hosts (streamstats window=96 @ 15m)", "ds_baseline", count=30),
            "viz_footer": md(
                "`tstats latest(_time)` is the source of truth for last data / last heartbeat. "
                "This page is the **fleet-wide, right-now** view. For one source's history "
                "(first/last event, 24-hour trend, drop/burst buckets) and how it reaches Splunk, open **Data Topology** and click a source. "
                "**Latency** is `_indextime - _time` over the last 15 minutes (fixed window; the time picker does not change it): DELAYED above `exec_health_latency_sec`, HIGH above 3x that, CLOCK AHEAD when events are stamped more than 5 minutes in the future. "
                "Override `exec_health_silence_sec` (default 3600), `exec_health_latency_sec` (default 300) and `exec_health_sigma` (default 2) as needed."
            ),
        },
        "layout": grid(
            [
                block("viz_header", 0, 0, 1200, 90),
                block("viz_ok", 0, 90, 300, 150),
                block("viz_delayed", 300, 90, 300, 150),
                block("viz_silent", 600, 90, 300, 150),
                block("viz_down", 900, 90, 300, 150),
                block("viz_table", 0, 240, 1200, 340),
                block("viz_latency", 0, 580, 1200, 320),
                block("viz_baseline", 0, 900, 1200, 360),
                block("viz_footer", 0, 1260, 1200, 110),
            ],
            extra_inputs=["input_host"],
        ),
    }


# ---------------------------------------------------------------------------
# HEC
# ---------------------------------------------------------------------------

def hec_state_core() -> str:
    """Per-token baseline vs recent window, zero-filled.

    Token metrics are written once per metrics_report_interval (60s) and only while
    a token is active, so a silent token has no rows at all: timechart + fillnull
    turns that absence into zeros. The window ends one minute back to absorb
    indexing lag. "recent" is the last N complete minutes; "baseline" is the
    60 minutes before that, reported as events per second.
    Shared by the dashboard and savedsearches.conf.
    """
    return r"""
search `exec_health_hec_metrics` earliest=-2h@m latest=-1m@m
| `exec_health_hec_normalize`
| timechart span=1m limit=0 useother=f sum(hec_events) as events by token
| fillnull value=0
| untable _time token events
| eval minutes_ago=round((relative_time(now(), "-1m@m")-_time)/60, 0)
| eval window=case(minutes_ago>=1 AND minutes_ago<=`exec_health_hec_silence_min`, "recent", minutes_ago>`exec_health_hec_silence_min` AND minutes_ago<=`exec_health_hec_silence_min`+60, "baseline")
| stats sum(eval(if(window="recent", events, 0))) as recent_events, sum(eval(if(window="baseline", events, 0))) as baseline_events, count(eval(window="recent" AND events=0)) as silent_minutes by token
| eval baseline_eps=round(baseline_events/3600, 2), recent_eps=round(recent_events/(60*`exec_health_hec_silence_min`), 2)
| lookup hec_token_map token OUTPUT token_name, owner
| eval token_label=coalesce(token_name, token), owner=coalesce(owner, "unmapped")
| eval hec_state=case(
    baseline_eps >= `exec_health_hec_baseline_eps` AND recent_events=0, "ALERT",
    baseline_eps >= 10 AND recent_events=0, "YELLOW",
    1=1, "OK")
""".strip()


Q_HEC_TIMECHART = r"""
search `exec_health_hec_metrics`
| `exec_health_hec_normalize`
| lookup hec_token_map token OUTPUT token_name
| eval token_label=coalesce(token_name, token)
| timechart span=5m sum(hec_events) as events by token_label
""".strip()

Q_HEC_STATE = hec_state_core() + r"""
| eval _color_rank=case(hec_state="ALERT", 1, hec_state="YELLOW", 2, 1=1, 3)
| table token, token_label, owner, recent_events, recent_eps, baseline_eps, silent_minutes, hec_state, _color_rank
| sort _color_rank, token_label
"""

Q_DQ_AGENT_FINDINGS = dq_agent_findings_core() + r"""
| eval finding_id=sha256(issue."|".entity)
| lookup dq_agent_playbooks fix_type OUTPUT playbook_name, likely_cause, confidence, tool_plan, splunk_web_path
| lookup dq_agent_approvals finding_id OUTPUT decision, decided_at, actor
| eval status=case(decision="approve", "approved", decision="dismiss", "dismissed", 1=1, "open")
| eval action=if(status="open", "Review", "Resolved")
| eval agent_thought="OBSERVE: "+issue+" on "+entity+". INVESTIGATE: "+coalesce(tool_plan, "learned baselines")+". TOOLS: fwdType="+coalesce(tool_fwdType, "n/a")+" conn="+coalesce(tool_conn, "n/a")+" err_component="+coalesce(tool_err_component, "none")+" err_count="+coalesce(tostring(tool_err_count), "0")+". HYPOTHESIZE: "+coalesce(likely_cause, "needs human review")+" (confidence "+coalesce(confidence, "n/a")+"). PROPOSE: "+suggested_fix+". ACT: wait for human APPROVE or DISMISS — never change Splunk unattended."
| eval ai_brief="Role: Derek+ Health Agent. Goal: diagnose Splunk infrastructure health (instance features, ingestion, silent hosts, search CPU, HEC, SC4S, Edge) and propose fixes. Hard constraint: do not apply changes; a human must approve. Issue: "+issue+". Entity: "+entity+". Evidence: "+evidence+". Forwarder type: "+coalesce(tool_fwdType, "unknown")+". Connection: "+coalesce(tool_conn, "unknown")+". Recent _internal errors: "+coalesce(tostring(tool_err_count), "0")+" ("+coalesce(tool_err_component, "none")+"). Playbook: "+coalesce(playbook_name, "none")+". Likely cause: "+coalesce(likely_cause, "unknown")+". Suggested fix: "+suggested_fix+". Splunk Web: "+coalesce(splunk_web_path, "n/a")+". Reply with root cause, confidence, and step-by-step admin actions. Do not request secrets or HEC token values."
| eval _color_rank=case(status!="open", 3, severity="RED", 1, severity="YELLOW", 2, 1=1, 3)
| table finding_id, severity, issue, entity, evidence, suggested_fix, fix_type, proposed_config, playbook_name, likely_cause, confidence, tool_plan, splunk_web_path, tool_fwdType, tool_conn, tool_err_component, tool_err_count, agent_thought, ai_brief, status, action, _color_rank
| sort _color_rank, issue, entity
"""

Q_DQ_AGENT_PREVIEW = Q_DQ_AGENT_FINDINGS + r"""
| where status="open"
| head 8
| table severity, issue, entity, likely_cause, confidence, suggested_fix, action, _color_rank
"""

Q_HEC_TOTALS = r"""
search `exec_health_hec_metrics`
| `exec_health_hec_normalize`
| stats sum(hec_events) as events, dc(token) as tokens, sum(hec_bytes) as bytes
| fillnull value=0 events, tokens, bytes
| eval events_per_sec=round(events/3600, 1)
| eval gb=round(bytes/1024/1024/1024, 3)
""".strip()

# Failed requests log "token name=<input name>, channel=..., reply=<code>".
Q_HEC_HANDLER = r"""
search `exec_health_hec_handler`
| rex "token name=(?<token>[^,]+)"
| rex "reply=(?<reply>\d+)"
| eval token=coalesce(token, "n/a")
| eval is_error=if(log_level="ERROR" OR log_level="WARN", 1, 0)
| stats count as events, sum(is_error) as errors, values(reply) as reply_codes by token
| lookup hec_token_map token OUTPUT token_name, owner
| eval token_label=coalesce(token_name, token)
| eval _color_rank=if(errors>0, 1, 3)
| table token, token_label, owner, events, errors, reply_codes, _color_rank
| sort 0 -errors, -events
""".strip()

Q_HEC_ERRORS = r"""
search `exec_health_hec_handler` (log_level=ERROR OR log_level=WARN)
| timechart span=5m count as handler_issues
""".strip()


def hec_performance() -> dict:
    return {
        "title": "HEC Token Performance",
        "description": "HTTP Event Collector throughput per token with 1-hour rolling-window silence detection.",
        "defaults": defaults(),
        "inputs": {"input_global_trp": timerange("-4h@h,now")},
        "dataSources": {
            "ds_hec_time": ds("HEC events by token", Q_HEC_TIMECHART),
            "ds_hec_state": ds("HEC token state", Q_HEC_STATE, "-2h@m", "-1m@m"),
            "ds_hec_totals": ds("HEC totals", Q_HEC_TOTALS, "-1h", "now"),
            "ds_hec_handler": ds("HttpInputDataHandler by token", Q_HEC_HANDLER),
            "ds_hec_errors": ds("HttpInputDataHandler issues", Q_HEC_ERRORS),
            "ds_hec_alert_count": chain(
                "HEC alert count",
                "ds_hec_state",
                '| where hec_state="ALERT" | stats count as alerts',
            ),
        },
        "visualizations": {
            "viz_header": md(
                "# HEC token performance\n"
                "Throughput comes from the per-token HEC metrics in `_introspection` (`http_event_collector_metrics`, field `data.token_name`). "
                "A token whose previous hour averaged **100+ events/sec** (macro `exec_health_hec_baseline_eps`) and has sent **nothing for the last 5 complete minutes** is **ALERT**. "
                "Map token input names to friendly names in `lookups/hec_token_map.csv` — never put HEC token secrets in that file."
            ),
            "viz_tokens": single_number("Active tokens (1h)", "ds_hec_totals", "tokens", "", None, 0),
            "viz_eps": single_number("HEC events / sec (1h)", "ds_hec_totals", "events_per_sec", "", None, 1),
            "viz_gb": single_number("HEC volume (1h)", "ds_hec_totals", "gb", " GB", None, 3),
            "viz_alerts": single_number("Tokens in ALERT", "ds_hec_alert_count", "alerts", "", None, 0),
            "viz_time": area("HEC events by token", "ds_hec_time", "events / 5m"),
            "viz_state": table("Token: last 5 minutes vs previous hour", "ds_hec_state", count=25),
            "viz_errors": line("HttpInputDataHandler errors / warnings", "ds_hec_errors", "issues"),
            "viz_handler": table("Failed HEC requests by token (HttpInputDataHandler)", "ds_hec_handler", count=20),
            "viz_footer": md(
                "Populate `hec_token_map.csv` with `token,token_name,owner`, where `token` is the HEC input name exactly as it appears in `data.token_name`. Never store the HEC token **value** (the secret) in the lookup."
            ),
        },
        "layout": grid(
            [
                block("viz_header", 0, 0, 1200, 110),
                block("viz_tokens", 0, 110, 300, 150),
                block("viz_eps", 300, 110, 300, 150),
                block("viz_gb", 600, 110, 300, 150),
                block("viz_alerts", 900, 110, 300, 150),
                block("viz_time", 0, 260, 1200, 300),
                block("viz_state", 0, 560, 1200, 320),
                block("viz_errors", 0, 880, 600, 280),
                block("viz_handler", 600, 880, 600, 280),
                block("viz_footer", 0, 1160, 1200, 90),
            ]
        ),
    }


# ---------------------------------------------------------------------------
# SC4S + Edge / Ingest Processor
# ---------------------------------------------------------------------------

Q_SC4S_TIME = r"""
| tstats count as events where index=`exec_health_idx` `exec_health_sc4s` by _time span=5m sourcetype
| timechart span=5m sum(events) as events by sourcetype
""".strip()

Q_SC4S_HOSTS = r"""
| tstats count as events where index=`exec_health_idx` `exec_health_sc4s` by host sourcetype
| sort 0 -events
| head 50
| eval _color_rank=3
""".strip()

Q_SC4S_ERRORS = r"""
search index=`exec_health_sc4s_idx` `exec_health_sc4s` (error OR warn OR fail OR "connection refused" OR hang OR dropped)
| stats count as issues by host, sourcetype
| eval _color_rank=if(issues>0, 1, 3)
| sort 0 -issues
""".strip()

Q_SC4S_ERR_TIME = r"""
search index=`exec_health_sc4s_idx` `exec_health_sc4s` (error OR warn OR fail OR "connection refused")
| timechart span=5m count as sc4s_issues
""".strip()

Q_EDGE_THROUGHPUT = r"""
| mstats rate_sum(processor_events_in_total) as events_in_eps, rate_sum(processor_events_out_total) as events_out_eps, rate_sum(processor_bytes_in_total) as bytes_in_eps, rate_sum(processor_bytes_out_total) as bytes_out_eps where `exec_health_edge_mstats` by host span=5m
| eval filter_efficiency_pct=if(events_in_eps>0, round(((events_in_eps-events_out_eps)/events_in_eps)*100, 2), 0)
| eval dropped_or_filtered_eps=round(events_in_eps-events_out_eps, 2)
| eval events_in_eps=round(events_in_eps, 2), events_out_eps=round(events_out_eps, 2)
| eval _color_rank=case(events_in_eps>0 AND events_out_eps=0, 1, filter_efficiency_pct>50, 2, 1=1, 3)
""".strip()

Q_EDGE_SUMMARY = r"""
| mstats rate_sum(processor_events_in_total) as events_in_eps, rate_sum(processor_events_out_total) as events_out_eps, rate_sum(processor_bytes_in_total) as bytes_in_eps, rate_sum(processor_bytes_out_total) as bytes_out_eps where `exec_health_edge_mstats`
| appendpipe [ stats count | where count=0 | eval events_in_eps=0, events_out_eps=0, bytes_in_eps=0, bytes_out_eps=0 ]
| fillnull value=0 events_in_eps, events_out_eps, bytes_in_eps, bytes_out_eps
| eval filter_efficiency_pct=if(events_in_eps>0, round(((events_in_eps-events_out_eps)/events_in_eps)*100, 2), 0)
| eval events_in_eps=round(events_in_eps, 2), events_out_eps=round(events_out_eps, 2)
| eval bytes_in_mbps=round(bytes_in_eps/1024/1024, 3)
""".strip()

Q_EDGE_QUEUE = r"""
| mstats max(queue_size_bytes) as queue_size_bytes, max(queue_max_bytes) as queue_max_bytes, rate_sum(export_destination_errors_total) as export_errors_per_sec where `exec_health_edge_mstats` by host
| eval queue_mb=round(queue_size_bytes/1024/1024, 2)
| eval queue_fill_pct=if(queue_max_bytes>0, round(queue_size_bytes/queue_max_bytes*100, 1), null())
| eval export_errors_per_sec=round(coalesce(export_errors_per_sec, 0), 3)
| eval _color_rank=case(export_errors_per_sec>0 OR queue_fill_pct>=80, 1, queue_fill_pct>=50, 2, 1=1, 3)
| table host, queue_mb, queue_fill_pct, export_errors_per_sec, _color_rank
""".strip()

Q_EDGE_LOGS = r"""
search index=_internal (source="*edge.log" OR sourcetype=edge OR sourcetype=*edge*processor* OR component=IngestActions OR component=IngestProcessor)
| eval is_drop=if(match(_raw, "(?i)drop|filter|sending_queue is full"), 1, 0)
| stats count as events, sum(is_drop) as drop_mentions by sourcetype, host
| eval _color_rank=if(drop_mentions>0, 1, 3)
| sort 0 -drop_mentions, -events
""".strip()

Q_INDEXED_COMPARE = r"""
| tstats count as indexed_events where index=`exec_health_idx` by _time span=5m
| timechart span=5m sum(indexed_events) as indexed_events
""".strip()

Q_INGEST_ACTIONS = r"""
search index=_internal source=*metrics.log group=queue blocked=true
| timechart span=5m limit=10 count as blocked_reports by name
""".strip()


def sc4s_edge() -> dict:
    return {
        "title": "SC4S Syslog & Edge/Ingest Processors",
        "description": "Syslog/SC4S source volume plus Edge Processor in-flight vs indexed volume and filter efficiency.",
        "defaults": defaults(),
        "inputs": {"input_global_trp": timerange("-4h@h,now")},
        "dataSources": {
            "ds_sc4s_time": ds("SC4S / syslog over time", Q_SC4S_TIME),
            "ds_sc4s_hosts": ds("Events per syslog source", Q_SC4S_HOSTS),
            "ds_sc4s_errors": ds("SC4S container issues", Q_SC4S_ERRORS),
            "ds_sc4s_err_time": ds("SC4S issues over time", Q_SC4S_ERR_TIME),
            "ds_edge_summary": ds("Edge Processor summary", Q_EDGE_SUMMARY),
            "ds_edge_tp": ds("Edge throughput by host", Q_EDGE_THROUGHPUT),
            "ds_edge_queue": ds("Edge queues and export errors", Q_EDGE_QUEUE),
            "ds_edge_logs": ds("Edge / ingest processor logs", Q_EDGE_LOGS),
            "ds_indexed": ds("Indexed events reaching indexers", Q_INDEXED_COMPARE),
            "ds_ingest_actions": ds("Blocked ingestion queues", Q_INGEST_ACTIONS),
        },
        "visualizations": {
            "viz_header": md(
                "# SC4S and Edge / Ingest Processors\n"
                "Left side watches **syslog/SC4S** volume per source host (load-balancer hang = flatline). "
                "Right side compares **Edge Processor in vs out** (`mstats rate_sum` on `_metrics`) with **events reaching indexers**."
            ),
            "viz_ep_in": single_number("Edge events in / sec", "ds_edge_summary", "events_in_eps", "", None, 2),
            "viz_ep_out": single_number("Edge events out / sec", "ds_edge_summary", "events_out_eps", "", None, 2),
            "viz_filter": single_number("Filter efficiency", "ds_edge_summary", "filter_efficiency_pct", " %", None, 1),
            "viz_mbps": single_number("Edge bytes in", "ds_edge_summary", "bytes_in_mbps", " MB/s", None, 3),
            "viz_sc4s_time": area("SC4S / syslog events by sourcetype", "ds_sc4s_time", "events / 5m"),
            "viz_indexed": line("Events reaching indexers (tstats)", "ds_indexed", "indexed events / 5m"),
            "viz_sc4s_hosts": table("Events per source (host)", "ds_sc4s_hosts", count=20),
            "viz_sc4s_err_time": line("SC4S error / warn rate", "ds_sc4s_err_time", "issues"),
            "viz_sc4s_errors": table("SC4S container / syslog issues", "ds_sc4s_errors", count=15),
            "viz_edge_tp": table("Edge Processor in vs out (filter efficiency)", "ds_edge_tp", count=15),
            "viz_edge_queue": table("Edge queue fill and export errors", "ds_edge_queue", count=15),
            "viz_ingest": line("Blocked ingestion queues (metrics.log blocked=true)", "ds_ingest_actions", "blocked reports / 5m"),
            "viz_edge_logs": table("Edge / Ingest Processor _internal logs", "ds_edge_logs", count=15),
            "viz_footer": md(
                "Edge metrics come from the `_metrics` index (`processor_events_in_total` and related counters, macro `exec_health_edge_mstats`); grant the viewing role access to `_metrics` on Splunk Cloud. "
                "If those panels are empty or error, Edge Processor is not writing metrics to this stack — use `_internal` logs instead. "
                "**Filter efficiency** = `(events_in - events_out) / events_in`. High values mean pipelines are dropping or routing away from indexers. "
                "SC4S error scans use macro `exec_health_sc4s_idx` (default `*`). Narrow it on Cloud to avoid expensive `index=*` event searches."
            ),
        },
        "layout": grid(
            [
                block("viz_header", 0, 0, 1200, 100),
                block("viz_ep_in", 0, 100, 300, 150),
                block("viz_ep_out", 300, 100, 300, 150),
                block("viz_filter", 600, 100, 300, 150),
                block("viz_mbps", 900, 100, 300, 150),
                block("viz_sc4s_time", 0, 250, 600, 280),
                block("viz_indexed", 600, 250, 600, 280),
                block("viz_sc4s_hosts", 0, 530, 600, 300),
                block("viz_edge_tp", 600, 530, 600, 300),
                block("viz_sc4s_err_time", 0, 830, 600, 250),
                block("viz_sc4s_errors", 600, 830, 600, 250),
                block("viz_ingest", 0, 1080, 600, 260),
                block("viz_edge_queue", 600, 1080, 600, 260),
                block("viz_edge_logs", 0, 1340, 1200, 280),
                block("viz_footer", 0, 1620, 1200, 120),
            ]
        ),
    }


def data_topology() -> dict:
    src_out_n = single_number("Drop / burst buckets", "ds_topo_src_out_n", "outliers", "", None, 0)
    src_out_n["options"]["underLabel"] = "2σ vs prior 24h"
    return {
        "title": "Data Topology",
        "description": "Click a data source for latest event, volume, trend, and drop/burst outliers.",
        "defaults": defaults(),
        "inputs": {
            "input_global_trp": timerange("-4h@h,now"),
            "input_source": {
                "type": "input.text",
                "title": "Selected data source (set by clicking data_source)",
                "options": {"token": "tok_data_source", "defaultValue": "none"},
            },
        },
        "dataSources": {
            "ds_topo_paths": ds("Indexed source → ingest → index", Q_TOPO_PATHS),
            "ds_topo_sankey": chain(
                "Indexed flow sankey",
                "ds_topo_paths",
                """
| eval source=data_source, target=ingest_path, value=events
| appendpipe [
    eval source=ingest_path, target=splunk_index, value=events
    | fields source, target, value
]
| stats sum(value) as value by source, target
| eval value=tonumber(value)
| where value>0 AND isnotnull(source) AND isnotnull(target)
| table source, target, value
""".strip(),
            ),
            "ds_topo_counts": chain(
                "Topology counts",
                "ds_topo_paths",
                "| stats dc(data_source) as sources, dc(ingest_path) as ingest_paths, dc(splunk_index) as indexes, sum(events) as events",
            ),
            "ds_topo_methods": chain(
                "Events by ingest path",
                "ds_topo_paths",
                "| stats sum(events) as events by ingest_path | sort 0 -events",
            ),
            "ds_topo_src_stats": ds("Selected source latest and totals", Q_TOPO_SRC_STATS),
            "ds_topo_src_trend": ds("Selected source 24h trend", Q_TOPO_SRC_TREND, "-25h@m", "@m"),
            "ds_topo_src_outliers": ds("Selected source drop/burst outliers", Q_TOPO_SRC_OUTLIERS, "-25h@m", "@m"),
            "ds_topo_src_out_n": chain(
                "Selected source outlier count",
                "ds_topo_src_outliers",
                "| stats count as outliers",
            ),
            "ds_tcpin": ds("Forwarder → indexer connections", Q_TCPIN_PATHS),
            "ds_tcpin_sankey": chain(
                "Forwarder flow sankey",
                "ds_tcpin",
                """
| eval source=data_source, target=receiver, value=kb
| where isnotnull(source) AND isnotnull(target) AND value>0
| stats sum(value) as value by source, target
| fields source, target, value
""".strip(),
            ),
            "ds_tcpin_counts": chain(
                "Forwarder connection counts",
                "ds_tcpin",
                "| stats dc(data_source) as forwarders, dc(receiver) as receivers, sum(kb) as kb",
            ),
            "ds_hec_paths": ds("HEC tokens as sources", Q_HEC_PATHS),
            "ds_topo_link": chain(
                "Indexed topology nodes only",
                "ds_topo_paths",
                "| table data_source, ingest_path, splunk_index",
            ),
        },
        "visualizations": {
            "viz_header": md(
                "# Data topology\n"
                "How servers and data sources reach Splunk: **data source → ingest path → index**, "
                "plus **forwarder → indexer** from `_internal` `tcpin_connections`. "
                "**Click a data_source** in the graph or table for latest event, totals, "
                "24-hour trend, and sudden drops or bursts. Search does not open."
            ),
            "viz_sources": single_number("Data sources", "ds_topo_counts", "sources", "", None, 0),
            "viz_paths": single_number("Ingest paths", "ds_topo_counts", "ingest_paths", "", None, 0),
            "viz_indexes": single_number("Destination indexes", "ds_topo_counts", "indexes", "", None, 0),
            "viz_fwds": single_number("Forwarders (tcpin)", "ds_tcpin_counts", "forwarders", "", None, 0),
            "viz_link": drill_source(
                linkgraph(
                    "Sources → ingest path → Splunk index",
                    "ds_topo_link",
                    ["data_source", "ingest_path", "splunk_index"],
                )
            ),
            "viz_sankey": sankey("Volume flow (events) through ingest paths", "ds_topo_sankey"),
            "viz_methods": column("Indexed events by ingest path", "ds_topo_methods", "events"),
            "viz_table": drill_source(table("Top source → path → index flows — click data_source", "ds_topo_paths", count=20)),
            "viz_src_header": md(
                "## Selected data source\n"
                "Click a **data_source** above. First/latest event and totals follow the time picker; "
                "whether the host is alive right now is on **Host Heartbeat**. "
                "Trend and outliers use the last **24 hours** at 15-minute buckets vs that source's "
                "`streamstats` mean ± `exec_health_sigma` (default 2). "
                "**DROP** = sudden traffic loss. **BURST** = sudden spike. Empty panels mean nothing is selected yet."
            ),
            "viz_src_total": single_number("Total events", "ds_topo_src_stats", "events", "", None, 0),
            "viz_src_types": single_number("Sourcetypes", "ds_topo_src_stats", "sourcetypes", "", None, 0),
            "viz_src_out_n": src_out_n,
            "viz_src_stats": table("First event, latest event, and totals", "ds_topo_src_stats", count=1),
            "viz_src_trend": line("Event trend vs 24-hour mean and 2σ bounds", "ds_topo_src_trend", "events / 15m"),
            "viz_src_outliers": table("Sudden drops and traffic bursts (2σ)", "ds_topo_src_outliers", count=20),
            "viz_tcpin_sankey": sankey("Forwarder → indexer volume (KB)", "ds_tcpin_sankey"),
            "viz_hec": drill_source(table("HEC tokens as data sources — click data_source", "ds_hec_paths", count=15)),
            "viz_tcpin_table": drill_source(table("Forwarder connections (metrics.log tcpin) — click data_source", "ds_tcpin", count=15)),
            "viz_footer": md(
                "Ingest path: **Windows UF** / **Linux UF** / **HF** from `tcpin_connections` `fwdType` plus Windows vs Linux sourcetype. "
                "**Other** uses **TCP:port** or **UDP:port** from `source` (for example `udp:514`) or from `_internal` `udpin_connections` / raw TCP. "
                "HEC, SC4S, and Edge stay as their own paths. Source drill-down is `tstats` by `host`. "
                "Narrow `exec_health_idx` if the source list is too large."
            ),
        },
        "layout": grid(
            [
                block("viz_header", 0, 0, 1200, 90),
                block("viz_sources", 0, 90, 300, 140),
                block("viz_paths", 300, 90, 300, 140),
                block("viz_indexes", 600, 90, 300, 140),
                block("viz_fwds", 900, 90, 300, 140),
                block("viz_link", 0, 230, 1200, 380),
                block("viz_sankey", 0, 610, 700, 320),
                block("viz_methods", 700, 610, 500, 320),
                block("viz_table", 0, 930, 1200, 280),
                block("viz_src_header", 0, 1210, 1200, 90),
                block("viz_src_total", 0, 1300, 400, 140),
                block("viz_src_types", 400, 1300, 400, 140),
                block("viz_src_out_n", 800, 1300, 400, 140),
                block("viz_src_stats", 0, 1440, 1200, 150),
                block("viz_src_trend", 0, 1590, 1200, 280),
                block("viz_src_outliers", 0, 1870, 1200, 260),
                block("viz_tcpin_sankey", 0, 2130, 600, 300),
                block("viz_hec", 600, 2130, 600, 300),
                block("viz_tcpin_table", 0, 2430, 1200, 280),
                block("viz_footer", 0, 2710, 1200, 110),
            ],
        ),
    }


Q_DQ_AGENT_STATUS = r"""
| eval _gate="$tok_decision$"
| lookup dq_agent_approvals finding_id OUTPUT decision AS rec_decision
| eval status=case(rec_decision="approve", "approved", rec_decision="dismiss", "dismissed", 1=1, "open")
| where status="open"
| stats count as issues
| eval agent_status=if(issues>0, "RED", "GREEN")
| appendpipe [ stats count | where count=0 | eval issues=0, agent_status="GREEN" ]
"""

Q_DQ_CHOOSE_APPROVE = r"""
| makeresults
| eval finding_id="$tok_finding_id$"
| eval picked=if(finding_id!="none" AND finding_id!="", 1, 0)
| eval button_label=if(picked=1, "APPROVE", "PICK A ROW FIRST")
| eval _click_action="approve"
| eval _color_rank=if(picked=1, 2, 1)
| table button_label, _click_action, _color_rank
"""

Q_DQ_CHOOSE_DISMISS = r"""
| makeresults
| eval finding_id="$tok_finding_id$"
| eval picked=if(finding_id!="none" AND finding_id!="", 1, 0)
| eval button_label=if(picked=1, "DISMISS", "PICK A ROW FIRST")
| eval _click_action="dismiss"
| eval _color_rank=if(picked=1, 2, 1)
| table button_label, _click_action, _color_rank
"""

# Only writes when APPROVE/DISMISS is chosen. Empty results skip appendpipe, so
# page load does not rewrite the lookup (that long job was getting cancelled).
Q_DQ_SAVE_DECISION = r"""
| makeresults
| eval finding_id="$tok_finding_id$", decision="$tok_decision$"
| where (decision="approve" OR decision="dismiss") AND finding_id!="none" AND finding_id!="" AND finding_id!="placeholder"
| eval actor="human_dashboard", decided_at=strftime(now(), "%Y-%m-%d %H:%M:%S"), note="human_in_the_loop", entity="none"
| eval _key=finding_id
| table _key, finding_id, decision, actor, decided_at, note, entity
| appendpipe [
    | outputlookup append=true dq_agent_approvals
]
| where finding_id="$tok_finding_id$"
| eval _color_rank=if(decision="approve" OR decision="dismiss", 3, 2)
| table decided_at, finding_id, decision, actor, _color_rank
"""

Q_DQ_RECORDED_READ = r"""
| inputlookup dq_agent_approvals
| eval _gate="$tok_decision$"
| where finding_id="$tok_finding_id$" AND "$tok_finding_id$"!="none" AND finding_id!="placeholder"
| eval _color_rank=if(decision="approve" OR decision="dismiss", 3, 2)
| table decided_at, finding_id, decision, actor, _color_rank
"""

Q_DQ_AGENT_ASK = r"""
| eval q=lower("$tok_ask$")
| eval q=replace(q, "[^a-z0-9 ]", "")
| where q="all" OR q="" OR like(lower(issue." ".entity." ".coalesce(likely_cause, "")." ".suggested_fix." ".coalesce(fix_type, "")), "%".q."%")
"""

Q_DQ_QUEUE_VIEW = r"""
| eval _gate="$tok_decision$"
| lookup dq_agent_approvals finding_id OUTPUT decision AS rec_decision
| eval status=case(rec_decision="approve", "approved", rec_decision="dismiss", "dismissed", 1=1, "open")
| eval action=if(status="open", "Select", "Done")
| eval _color_rank=case(status!="open", 3, severity="RED", 1, severity="YELLOW", 2, 1=1, 3)
| eval fix=coalesce(suggested_fix, "")
| eval fix=if(len(fix)>80, substr(fix,1,80)."...", fix)
| eval _ai_brief=ai_brief, _reset_decision="review", _ai_auto="ask"
| table finding_id, severity, issue, entity, fix, confidence, action, status, _ai_brief, _reset_decision, _ai_auto, _color_rank
"""

Q_DQ_PICKER = r"""
| eval label=severity." · ".issue." — ".entity
| eval value=finding_id
| table label, value
"""

Q_DQ_SUGGESTION = r"""
| where finding_id="$tok_finding_id$" AND "$tok_finding_id$"!="none" AND finding_id!=""
| eval _gate="$tok_decision$"
| lookup dq_agent_approvals finding_id OUTPUT decision AS rec_decision
| eval status=case(rec_decision="approve", "approved", rec_decision="dismiss", "dismissed", 1=1, "open")
| eval _color_rank=case(status!="open", 3, severity="RED", 1, severity="YELLOW", 2, 1=1, 3)
| eval where_to_act=coalesce(splunk_web_path, "Open the matching dashboard in this app")
| table severity, issue, entity, likely_cause, suggested_fix, where_to_act, evidence, confidence, playbook_name, status, _color_rank
"""

Q_DQ_AI_CFG_ROW = r"""
| makeresults
| eval stanza="default", mode="off", provider="none", model="none", endpoint="none", api_key="none", inbox_index="_internal", inbox_sourcetype="derek_health_ai_unconfigured", updated_by="system", updated_at="0", note="seed", _seed=1
| inputlookup append=true dq_agent_ai_config
| eval stanza=coalesce(stanza, "default")
| eval _seed=coalesce(_seed, 0)
| eval key_ok=if(isnotnull(api_key) AND api_key!="" AND api_key!="none", 1, 0)
| eval rank=case(key_ok=1, 3, _seed=0, 2, 1=1, 1)
| sort 0 -rank
| dedup stanza
| where stanza="default"
| head 1
| eval _updated=coalesce(tostring(updated_at), "0")
| eval used_ui=if(_updated="0" OR _updated="", 0, 1)
| eval mode=if(used_ui=0, "`exec_health_ai_mode`", coalesce(mode, "off"))
| eval provider=if(used_ui=0, "`exec_health_ai_provider`", coalesce(provider, "none"))
| eval model=if(used_ui=0, "`exec_health_ai_model`", coalesce(model, "none"))
| eval endpoint=if(used_ui=0, "`exec_health_ai_endpoint`", coalesce(endpoint, "none"))
| eval inbox_index=coalesce(inbox_index, "_internal")
| eval inbox_sourcetype=coalesce(inbox_sourcetype, "derek_health_ai_unconfigured")
""".strip()

Q_DQ_AI_STATUS = Q_DQ_AI_CFG_ROW + r"""
| lookup dq_agent_ai_providers provider OUTPUT provider_label, default_endpoint, notes
| eval endpoint=if(endpoint="none" OR endpoint="", coalesce(default_endpoint, "none"), endpoint)
| eval key_state=if(isnotnull(api_key) AND api_key!="" AND api_key!="none", "SET", "MISSING")
| eval model_ok=if(isnotnull(model) AND model!="" AND model!="none", 1, 0)
| eval endpoint_ok=if(isnotnull(endpoint) AND endpoint!="" AND endpoint!="none", 1, 0)
| eval setup_reason=case(
    mode!="provider" OR provider="none" OR provider="", "Local only. No provider is saved.",
    key_state!="SET", "Setup incomplete: API key is missing. Enter a key and click SAVE.",
    model_ok=0, "Setup incomplete: model is missing. Enter a model id and click SAVE.",
    endpoint_ok=0, "Setup incomplete: ".coalesce(provider_label, provider)." has no endpoint. Set default_endpoint in the provider catalog, then SAVE again.",
    1=1, "Ready. Provider ".coalesce(provider_label, provider).", model ".model.", key SET.")
| eval ai_status=case(
    mode!="provider" OR provider="none" OR provider="", "LOCAL",
    key_state="SET" AND model_ok=1 AND endpoint_ok=1, "READY",
    1=1, "FAILED")
| eval status_color=ai_status
| eval _color_rank=case(ai_status="FAILED", 1, ai_status="READY", 3, 1=1, 3)
| table setup_reason, ai_status, status_color, mode, provider, provider_label, model, key_state, endpoint, inbox_index, inbox_sourcetype, notes, _color_rank
"""

Q_DQ_AI_ASK_BUTTON = r"""
| makeresults
| eval finding_id="$tok_finding_id$", stanza="default"
| lookup dq_agent_ai_config stanza OUTPUT mode, provider, api_key, updated_at
| eval _updated=coalesce(tostring(updated_at), "0")
| eval used_ui=if(_updated="0" OR _updated="", 0, 1)
| eval mode=if(used_ui=0, "`exec_health_ai_mode`", coalesce(mode, "off"))
| eval provider=if(used_ui=0, "`exec_health_ai_provider`", coalesce(provider, "none"))
| eval key_ok=if(isnotnull(api_key) AND api_key!="" AND api_key!="none", 1, 0)
| eval picked=if(finding_id!="none" AND finding_id!="" AND finding_id!="placeholder", 1, 0)
| eval configured=if(mode="provider" AND provider!="none" AND provider!="" AND key_ok=1, 1, 0)
| eval button_label=case(picked=0, "PICK A ROW FIRST", configured=0, "OPEN AI SETUP FIRST", 1=1, "ASK AGAIN")
| eval _click_action="retry".tostring(now())
| eval _color_rank=if(picked=1 AND configured=1, 3, 1)
| table button_label, _click_action, _color_rank
"""

# Writes a pending ASK row only after the ASK tile is clicked. Page load is a no-op.
Q_DQ_AI_ASK_WRITE = r"""
| makeresults
| eval ask="$tok_ai_ask$", finding_id="$tok_finding_id$", entity="$tok_entity$", issue="$tok_issue$", ai_brief="$tok_ai_brief$", stanza="default"
| lookup dq_agent_ai_config stanza OUTPUT mode, provider, model, endpoint, api_key, updated_at
| eval _updated=coalesce(tostring(updated_at), "0")
| eval used_ui=if(_updated="0" OR _updated="", 0, 1)
| eval mode=if(used_ui=0, "`exec_health_ai_mode`", coalesce(mode, "off"))
| eval provider=if(used_ui=0, "`exec_health_ai_provider`", coalesce(provider, "none"))
| eval model=if(used_ui=0, "`exec_health_ai_model`", coalesce(model, "none"))
| eval endpoint=if(used_ui=0, "`exec_health_ai_endpoint`", coalesce(endpoint, "none"))
| eval key_ok=if(isnotnull(api_key) AND api_key!="" AND api_key!="none", 1, 0)
| where match(ask, "^(ask|retry)") AND finding_id!="none" AND finding_id!="" AND finding_id!="placeholder" AND mode="provider" AND provider!="none" AND provider!="" AND key_ok=1
| lookup dq_agent_ai_requests finding_id OUTPUT status AS prev_status, requested_at AS prev_at
| eval prev_age=coalesce(now()-strptime(coalesce(tostring(prev_at), ""), "%Y-%m-%d %H:%M:%S"), 99999)
| where NOT (prev_status="replied" AND prev_age<3600 AND ask="ask")
| lookup dq_agent_ai_providers provider OUTPUT default_endpoint
| eval endpoint=if(endpoint="none" OR isnull(endpoint) OR endpoint="", coalesce(default_endpoint, "none"), endpoint)
| eval endpoint=if(provider="anthropic" AND NOT match(lower(coalesce(endpoint, "")), "anthropic"), "https://api.anthropic.com/v1/messages", endpoint)
| eval model=if(provider="anthropic" AND (NOT match(lower(coalesce(model, "")), "^claude") OR lower(coalesce(model, ""))="claude-opus-4" OR match(lower(coalesce(model, "")), "^claude-3-")), "claude-haiku-5-5", model)
| eval actor="human_dashboard", requested_at=strftime(now(), "%Y-%m-%d %H:%M:%S")
| eval entity=if(entity="" OR isnull(entity), "none", entity)
| eval issue=if(issue="" OR isnull(issue), "none", issue)
| eval ai_brief=if(ai_brief="" OR isnull(ai_brief), "none", ai_brief)
| eval is_ping=0
| derekaiping
| eval status=if(ai_result="replied", "replied", "failed")
| eval note=if(ai_result="replied", "ask_ai_provider", "ask failed: ".coalesce(ai_error, "no reply"))
| eval reply=if(ai_result="replied", ai_reply, "none")
| table finding_id, entity, issue, provider, model, endpoint, status, actor, requested_at, note, ai_brief, reply
| appendpipe [
    | inputlookup append=true dq_agent_ai_requests
    | stats latest(entity) as entity, latest(issue) as issue, latest(provider) as provider, latest(model) as model, latest(endpoint) as endpoint, latest(status) as status, latest(actor) as actor, latest(requested_at) as requested_at, latest(note) as note, latest(ai_brief) as ai_brief, latest(reply) as reply by finding_id
    | outputlookup dq_agent_ai_requests
]
| where finding_id="$tok_finding_id$"
| eval _color_rank=if(status="replied", 3, 1)
| table requested_at, finding_id, provider, status, _color_rank
"""

Q_DQ_AI_SAVE_BUTTON = r"""
| makeresults
| eval p=replace(lower("$tok_cfg_provider$"), "[^a-z]", ""), m=replace("$tok_cfg_model$", "[^A-Za-z0-9._-]", ""), k=len(replace("$tok_cfg_key$", "[^A-Za-z0-9._/=+-]", ""))
| eval button_label="SAVE"
| eval _click_action="save|".p."|".m."|".tostring(k)
| eval _color_rank=3
| table button_label, _click_action, _color_rank
"""

Q_DQ_AI_MODELS = r"""
| inputlookup dq_agent_ai_models
| eval p=replace(lower("$tok_cfg_provider$"), "[^a-z]", "")
| eval p=if(p="" OR isnull(p), "none", p)
| where provider=p
| eval label=coalesce(model_label, model), value=model
| table label, value
| sort label
"""

# Writes only after SAVE is clicked. Empty page-load skips outputlookup.
# api_key is stored in KV Store (dq_agent_ai_config), not in a packaged CSV, so app
# updates do not wipe it. Leave the key field blank to keep the stored value.
Q_DQ_AI_SAVE_CONFIG = r"""
| makeresults
| eval save="$tok_cfg_save$"
| eval want="save|".replace(lower("$tok_cfg_provider$"), "[^a-z]", "")."|".replace("$tok_cfg_model$", "[^A-Za-z0-9._-]", "")."|".tostring(len(replace("$tok_cfg_key$", "[^A-Za-z0-9._/=+-]", "")))
| eval stanza="default", _key="default"
| lookup dq_agent_ai_config stanza OUTPUT inbox_index AS prev_inbox, inbox_sourcetype AS prev_st, endpoint AS prev_endpoint, api_key AS prev_key
| eval provider=replace(lower("$tok_cfg_provider$"), "[^a-z]", "")
| eval provider=if(provider="openai" OR provider="cisco" OR provider="azure" OR provider="anthropic" OR provider="custom", provider, "none")
| eval model=replace("$tok_cfg_model$", "[^A-Za-z0-9._-]", "")
| eval model=if(model="" OR isnull(model), "none", model)
| eval api_key=replace("$tok_cfg_key$", "[^A-Za-z0-9._/=+-]", "")
| eval api_key=if(api_key="" OR isnull(api_key) OR api_key="none", coalesce(prev_key, "none"), api_key)
| eval api_key=if(provider="none", "none", api_key)
| where save=want
| eval mode=if(provider="none", "off", "provider")
| lookup dq_agent_ai_providers provider OUTPUT default_endpoint
| eval endpoint=coalesce(default_endpoint, prev_endpoint, "none")
| eval endpoint=if(provider="anthropic" AND NOT match(lower(coalesce(endpoint, "")), "anthropic"), "https://api.anthropic.com/v1/messages", endpoint)
| eval model=if(provider="anthropic" AND (NOT match(lower(coalesce(model, "")), "^claude") OR lower(coalesce(model, ""))="claude-opus-4" OR match(lower(coalesce(model, "")), "^claude-3-")), "claude-haiku-5-5", model)
| eval inbox_index=coalesce(prev_inbox, "main")
| eval inbox_sourcetype=coalesce(prev_st, "derek_health_ai")
| eval updated_by="human_dashboard", updated_at=strftime(now(), "%Y-%m-%d %H:%M:%S"), note="ui_config"
| table _key, stanza, mode, provider, model, endpoint, api_key, inbox_index, inbox_sourcetype, updated_by, updated_at, note
| appendpipe [
    | inputlookup append=true dq_agent_ai_config
    | stats latest(mode) as mode, latest(provider) as provider, latest(model) as model, latest(endpoint) as endpoint, latest(api_key) as api_key, latest(inbox_index) as inbox_index, latest(inbox_sourcetype) as inbox_sourcetype, latest(updated_by) as updated_by, latest(updated_at) as updated_at, latest(note) as note by stanza
    | eval _key=stanza
    | outputlookup dq_agent_ai_config
]
| where stanza="default"
| eval key_state=if(api_key!="none" AND api_key!="", "SET", "MISSING")
| eval _color_rank=3
| table updated_at, provider, model, key_state, mode, _color_rank
"""

# After SAVE, sends one short ping straight to the provider with the derekaiping
# command (Python, runs on the search head) and records PASS/FAIL in dq_agent_ai_requests.
Q_DQ_AI_CONN_WRITE = r"""
| makeresults
| eval save="$tok_cfg_save$"
| eval want="save|".replace(lower("$tok_cfg_provider$"), "[^a-z]", "")."|".replace("$tok_cfg_model$", "[^A-Za-z0-9._-]", "")."|".tostring(len(replace("$tok_cfg_key$", "[^A-Za-z0-9._/=+-]", "")))
| eval stanza="default"
| lookup dq_agent_ai_config stanza OUTPUT api_key AS prev_key, endpoint AS prev_endpoint
| eval provider=replace(lower("$tok_cfg_provider$"), "[^a-z]", "")
| eval provider=if(provider="openai" OR provider="cisco" OR provider="azure" OR provider="anthropic" OR provider="custom", provider, "none")
| eval model=replace("$tok_cfg_model$", "[^A-Za-z0-9._-]", "")
| eval model=if(model="" OR isnull(model), "none", model)
| eval api_key=replace("$tok_cfg_key$", "[^A-Za-z0-9._/=+-]", "")
| eval api_key=if(api_key="" OR isnull(api_key) OR api_key="none", coalesce(prev_key, "none"), api_key)
| eval api_key=if(provider="none", "none", api_key)
| lookup dq_agent_ai_providers provider OUTPUT default_endpoint
| eval endpoint=coalesce(default_endpoint, prev_endpoint, "none")
| eval endpoint=if(provider="anthropic" AND NOT match(lower(coalesce(endpoint, "")), "anthropic"), "https://api.anthropic.com/v1/messages", endpoint)
| eval model=if(provider="anthropic" AND (NOT match(lower(coalesce(model, "")), "^claude") OR lower(coalesce(model, ""))="claude-opus-4" OR match(lower(coalesce(model, "")), "^claude-3-")), "claude-haiku-5-5", model)
| eval key_ok=if(isnotnull(api_key) AND api_key!="" AND api_key!="none" AND len(api_key)>=8, 1, 0)
| eval model_ok=if(model!="none" AND model!="", 1, 0)
| eval endpoint_ok=if(match(lower(coalesce(endpoint, "")), "^https://[a-z0-9]"), 1, 0)
| where save=want AND provider!="none" AND key_ok=1 AND model_ok=1 AND endpoint_ok=1
| eval finding_id="connection_test", entity="ai_setup", issue="connection_test", actor="human_dashboard"
| eval requested_at=strftime(now(), "%Y-%m-%d %H:%M:%S")
| eval ai_brief="Connection test. Reply with the single word PONG."
| eval is_ping=1
| derekaiping
| eval status=if(ai_result="replied", "replied", "failed")
| eval note=if(ai_result="replied", "connection_test ok", "connection_test failed: ".coalesce(ai_error, "no reply"))
| eval reply=if(ai_result="replied", ai_reply, "none")
| table finding_id, entity, issue, provider, model, endpoint, status, actor, requested_at, note, ai_brief, reply
| appendpipe [
    | inputlookup append=true dq_agent_ai_requests
    | stats latest(entity) as entity, latest(issue) as issue, latest(provider) as provider, latest(model) as model, latest(endpoint) as endpoint, latest(status) as status, latest(actor) as actor, latest(requested_at) as requested_at, latest(note) as note, latest(ai_brief) as ai_brief, latest(reply) as reply by finding_id
    | outputlookup dq_agent_ai_requests
]
| where finding_id="connection_test"
| eval _color_rank=if(status="replied", 3, 1)
| table requested_at, finding_id, provider, status, _color_rank
"""

Q_DQ_AI_CONN_TEST = Q_DQ_AI_CFG_ROW + r"""
| lookup dq_agent_ai_providers provider OUTPUT provider_label, default_endpoint, notes
| eval endpoint=if(endpoint="none" OR endpoint="", coalesce(default_endpoint, "none"), endpoint)
| eval endpoint=if(provider="anthropic" AND NOT match(lower(coalesce(endpoint, "")), "anthropic"), "https://api.anthropic.com/v1/messages", endpoint)
| eval model=if(provider="anthropic" AND (NOT match(lower(coalesce(model, "")), "^claude") OR lower(coalesce(model, ""))="claude-opus-4" OR match(lower(coalesce(model, "")), "^claude-3-")), "claude-haiku-5-5", model)
| eval key_state=if(isnotnull(api_key) AND api_key!="" AND api_key!="none", "SET", "MISSING")
| eval model_ok=if(isnotnull(model) AND model!="" AND model!="none", 1, 0)
| eval endpoint_ok=if(isnotnull(endpoint) AND endpoint!="" AND endpoint!="none", 1, 0)
| eval endpoint_https=if(match(lower(coalesce(endpoint, "")), "^https://[a-z0-9]"), 1, 0)
| eval key_shape=if(key_state="SET" AND len(api_key)>=8, "ok", "bad")
| eval setup_reason=case(
    mode!="provider" OR provider="none" OR provider="", "Local only. No provider is saved.",
    key_state!="SET", "Setup incomplete: API key is missing. Enter a key and click SAVE.",
    model_ok=0, "Setup incomplete: model is missing. Enter a model id and click SAVE.",
    endpoint_ok=0, "Setup incomplete: ".coalesce(provider_label, provider)." has no endpoint. Set default_endpoint in the provider catalog, then SAVE again.",
    1=1, "Ready. Provider ".coalesce(provider_label, provider).", model ".model.", key SET.")
| eval ai_status=case(
    mode!="provider" OR provider="none" OR provider="", "LOCAL",
    key_state="SET" AND model_ok=1 AND endpoint_ok=1, "READY",
    1=1, "FAILED")
| fields - api_key
| eval finding_id="connection_test"
| lookup dq_agent_ai_requests finding_id OUTPUT status AS ping_status, requested_at AS ping_at, note AS ping_note, provider AS ping_provider
| eval ping_match=if(coalesce(ping_provider, "") = provider, 1, 0)
| eval conn_status=case(
    ai_status="LOCAL", "SKIP",
    ai_status="FAILED", "FAIL",
    key_shape!="ok", "FAIL",
    endpoint_https!=1, "FAIL",
    ping_match=1 AND ping_status="replied", "PASS",
    ping_match=1 AND (ping_status="failed" OR ping_status="error"), "FAIL",
    1=1, "TESTING")
| eval conn_reason=case(
    conn_status="SKIP", "No provider is set. Connection test was not run.",
    ai_status="FAILED", setup_reason,
    key_shape!="ok", "Connection test failed: API key is missing or too short. Enter a key and click SAVE.",
    endpoint_https!=1, "Connection test failed: endpoint is not HTTPS. Set default_endpoint to an https URL in the provider catalog, then SAVE.",
    conn_status="PASS" AND provider="anthropic", "Connection test passed at ".ping_at.". Anthropic Messages API (https://api.anthropic.com/v1/messages) replied from this search head.",
    conn_status="PASS", "Connection test passed at ".ping_at.". ".coalesce(provider_label, provider)." replied from this search head.",
    conn_status="FAIL", coalesce(ping_note, "Connection test failed.")." Fix it, then click SAVE to test again.",
    1=1, "No connection test has run for this provider yet. Click SAVE to test.")
| eval tile_status=case(conn_status="SKIP", "LOCAL", conn_status="FAIL", "FAILED", 1=1, conn_status)
| eval status_color=ai_status
| eval _color_rank=case(conn_status="FAIL" OR ai_status="FAILED", 1, conn_status="TESTING", 2, 1=1, 3)
| table setup_reason, ai_status, conn_status, conn_reason, tile_status, status_color, mode, provider, provider_label, model, key_state, endpoint, inbox_index, inbox_sourcetype, notes, _color_rank
"""

Q_DQ_AI_QUEUE = r"""
| inputlookup dq_agent_ai_requests
| where NOT (finding_id="placeholder" AND status="none")
| eval _color_rank=case(status="pending", 2, 1=1, 3)
| table requested_at, finding_id, entity, issue, provider, model, status, actor, note, _color_rank
| sort 0 -requested_at
"""

Q_DQ_AI_ASK_STATUS = r"""
| makeresults
| eval finding_id="$tok_finding_id$", ask="$tok_ai_ask$", stanza="default"
| lookup dq_agent_ai_config stanza OUTPUT mode, provider, model, api_key, endpoint, updated_at
| eval _updated=coalesce(tostring(updated_at), "0")
| eval used_ui=if(_updated="0" OR _updated="", 0, 1)
| eval mode=if(used_ui=0, "`exec_health_ai_mode`", coalesce(mode, "off"))
| eval provider=if(used_ui=0, "`exec_health_ai_provider`", coalesce(provider, "none"))
| eval model=if(used_ui=0, "`exec_health_ai_model`", coalesce(model, "none"))
| eval key_ok=if(isnotnull(api_key) AND api_key!="" AND api_key!="none", 1, 0)
| eval picked=if(finding_id!="none" AND finding_id!="" AND finding_id!="placeholder", 1, 0)
| eval configured=if(mode="provider" AND provider!="none" AND provider!="" AND key_ok=1 AND isnotnull(model) AND model!="none" AND model!="", 1, 0)
| lookup dq_agent_ai_requests finding_id OUTPUT status AS req_status, requested_at, provider AS req_provider, note AS req_note
| eval wait_sec=now()-strptime(coalesce(tostring(requested_at), ""), "%Y-%m-%d %H:%M:%S")
| eval wait_min=if(isnotnull(wait_sec), round(wait_sec/60, 0), null())
| eval ask_state=case(
    picked=0, "IDLE",
    mode!="provider", "IDLE",
    match(ask, "^(ask|retry)") AND configured=0, "FAILED",
    req_status="failed" OR req_status="error", "FAILED",
    req_status="done" OR req_status="replied", "REPLIED",
    req_status="pending" AND wait_min>=15, "STALLED",
    req_status="pending", "WAITING",
    match(ask, "^(ask|retry)") AND configured=1 AND (isnull(req_status) OR req_status="" OR req_status="none"), "WAITING",
    1=1, "IDLE")
| eval ask_message=case(
    ask_state="IDLE" AND picked=0, "Select a row in the work queue. The AI suggested fix fills in automatically.",
    ask_state="IDLE" AND mode!="provider", "AI provider is off, so the playbook fix above is the suggestion. Open AI provider setup and SAVE a provider to get an AI suggested fix automatically.",
    ask_state="IDLE", "No AI request yet for this suggestion.",
    ask_state="FAILED" AND configured=0, "ASK failed: AI provider is not ready. Open AI provider setup and SAVE provider, model, and key.",
    ask_state="FAILED", "ASK failed: ".coalesce(req_note, "the provider returned an error."),
    ask_state="WAITING", "Asking ".coalesce(req_provider, provider, "the provider")+" for a suggested fix...",
    ask_state="STALLED", "Still waiting after ".tostring(wait_min)." minutes. Click ASK AGAIN.",
    ask_state="REPLIED", "Provider replied. See the replies table below.",
    1=1, "ASK status unknown.")
| eval _color_rank=case(ask_state="FAILED" OR ask_state="STALLED", 1, ask_state="WAITING", 2, ask_state="REPLIED", 3, 1=1, 3)
| table ask_state, ask_message, _color_rank
"""

Q_DQ_AI_REPLIES = r"""
| makeresults
| eval _gate="$tok_ai_ask$", finding_id="$tok_finding_id$"
| eval picked=if(finding_id!="none" AND finding_id!="" AND finding_id!="placeholder", 1, 0)
| lookup dq_agent_ai_requests finding_id OUTPUT status AS req_status, requested_at, provider, model, reply, note AS req_note
| eval ai_suggested_fix=case(
    picked=0, "Select a row in the work queue. The AI suggested fix fills in here automatically.",
    req_status="replied", reply,
    req_status="failed", "The AI could not answer: ".coalesce(req_note, "provider error").". Use the playbook fix above or click ASK AGAIN.",
    1=1, "Asking the AI provider for a suggested fix... If no provider is set, use the playbook fix above.")
| eval from_ai=if(req_status="replied", provider." / ".model, "none")
| eval _color_rank=case(req_status="replied", 3, req_status="failed", 1, 1=1, 2)
| table ai_suggested_fix, from_ai, requested_at, _color_rank
"""


def data_quality_agent() -> dict:
    findings_table = table(
        "1. Work queue — click Select on a row",
        "ds_dq_queue",
        count=20,
    )
    findings_table["showLastUpdated"] = False
    findings_table["eventHandlers"] = [
        {
            "type": "drilldown.setToken",
            "options": {
                "tokens": [
                    {"token": "tok_finding_id", "key": "row.finding_id.value"},
                    {"token": "tok_entity", "key": "row.entity.value"},
                    {"token": "tok_issue", "key": "row.issue.value"},
                    {"token": "tok_ai_brief", "key": "row._ai_brief.value"},
                    {"token": "tok_decision", "key": "row._reset_decision.value"},
                    {"token": "tok_ai_ask", "key": "row._ai_auto.value"},
                ]
            },
        }
    ]
    findings_table["options"]["headerVisibility"] = "fixed"
    findings_table["options"]["columnFormat"] = {
        "severity": {"width": 90, "align": "center"},
        "issue": {"width": 220},
        "entity": {"width": 140},
        "fix": {"width": 320},
        "confidence": {"width": 80, "align": "center"},
        "action": {"width": 90, "align": "center"},
        "status": {"width": 90, "align": "center"},
        "finding_id": {"width": 80},
    }
    suggestion_table = table(
        "2. This suggestion — why it fired and what to do",
        "ds_dq_selected",
        count=3,
    )
    suggestion_table.pop("eventHandlers", None)
    suggestion_table["showLastUpdated"] = False
    recorded_table = table("Recorded decision", "ds_dq_recorded", count=3)
    recorded_table.pop("eventHandlers", None)
    recorded_table["showLastUpdated"] = False
    brief_table = table("Optional — briefing to paste into Splunk AI Assistant", "ds_dq_brief", count=1)
    brief_table.pop("eventHandlers", None)
    replies_table = table("3. AI suggested fix — fills in when you select a row", "ds_dq_ai_replies", count=1)
    replies_table.pop("eventHandlers", None)
    replies_table["showLastUpdated"] = False
    replies_table["options"]["columnFormat"] = {
        "ai_suggested_fix": {"width": 800},
        "from_ai": {"width": 160},
        "requested_at": {"width": 140},
    }
    ask_msg_table = table("ASK result — waiting or failed", "ds_dq_ai_ask_status", count=1)
    ask_msg_table.pop("eventHandlers", None)
    ask_msg_table["showLastUpdated"] = False
    return {
        "title": "Derek+ Data Quality Agent",
        "description": "Click Select, then click APPROVE or DISMISS. That records the decision. Search does not open.",
        "defaults": defaults(),
        "inputs": {
            "input_global_trp": timerange("-24h@h,now"),
            "input_ask": {
                "type": "input.text",
                "title": "Filter (try hec, cpu, silent, or all)",
                "options": {"token": "tok_ask", "defaultValue": "all"},
            },
            "input_finding": {
                "type": "input.text",
                "title": "Selected suggestion (click Select in the queue)",
                "options": {"token": "tok_finding_id", "defaultValue": "none"},
            },
            "input_decision": {
                "type": "input.text",
                "title": "Decision latch (set by APPROVE or DISMISS)",
                "options": {"token": "tok_decision", "defaultValue": "review"},
            },
            "input_ai_ask": {
                "type": "input.text",
                "title": "Ask latch (set by ASK)",
                "options": {"token": "tok_ai_ask", "defaultValue": "review"},
            },
            "input_entity": {
                "type": "input.text",
                "title": "Selected entity",
                "options": {"token": "tok_entity", "defaultValue": "none"},
            },
            "input_issue": {
                "type": "input.text",
                "title": "Selected issue",
                "options": {"token": "tok_issue", "defaultValue": "none"},
            },
            "input_ai_brief": {
                "type": "input.text",
                "title": "Selected briefing",
                "options": {"token": "tok_ai_brief", "defaultValue": "none"},
            },
        },
        "dataSources": {
            "ds_dq_findings": ds("Agent cycle findings", Q_DQ_AGENT_FINDINGS, "-24h", "now", refresh=None),
            "ds_dq_asked": chain("Asked findings", "ds_dq_findings", Q_DQ_AGENT_ASK),
            "ds_dq_queue": chain("Work queue", "ds_dq_asked", Q_DQ_QUEUE_VIEW),
            "ds_dq_status": chain("Agent status", "ds_dq_asked", Q_DQ_AGENT_STATUS),
            "ds_dq_selected": chain("Selected suggestion", "ds_dq_asked", Q_DQ_SUGGESTION),
            "ds_dq_brief": chain(
                "AI briefing",
                "ds_dq_asked",
                """
| where finding_id="$tok_finding_id$" AND "$tok_finding_id$"!="none"
| table ai_brief
""".strip(),
            ),
            "ds_dq_approve": ds("Approve control", Q_DQ_CHOOSE_APPROVE, "0", "now", refresh=None),
            "ds_dq_dismiss": ds("Dismiss control", Q_DQ_CHOOSE_DISMISS, "0", "now", refresh=None),
            "ds_dq_save": ds("Write agent decision", Q_DQ_SAVE_DECISION, "0", "now", refresh=None),
            "ds_dq_recorded": chain("Recorded decision", "ds_dq_save", "| where 1=0\n| append [\n" + Q_DQ_RECORDED_READ.strip() + "\n]"),
            "ds_dq_ai_status": ds("AI provider status", Q_DQ_AI_CONN_TEST, "0", "now", refresh=None),
            "ds_dq_ai_ready": ds("Ask AI control", Q_DQ_AI_ASK_BUTTON, "0", "now", refresh=None),
            "ds_dq_ai_write": ds("Write ASK request", Q_DQ_AI_ASK_WRITE, "0", "now", refresh=None),
            "ds_dq_ai_ask_status": chain("ASK wait or fail", "ds_dq_ai_write", "| where 1=0\n| append [\n" + Q_DQ_AI_ASK_STATUS.strip() + "\n]"),
            "ds_dq_ai_replies": chain("AI suggested fix", "ds_dq_ai_write", "| where 1=0\n| append [\n" + Q_DQ_AI_REPLIES.strip() + "\n]"),
        },
        "visualizations": {
            "viz_header": md(
                "# Derek+ Data Quality Agent\n"
                "**1. Click Select** on a row. The AI asks your saved provider for a suggested fix automatically. "
                "**2. Read** the playbook fix and the AI suggested fix. "
                "**3. Click APPROVE or DISMISS** to record the decision. "
                "Search does not open. The agent never changes Splunk by itself."
            ),
            "viz_status": single_status("Queue health", "ds_dq_status", "agent_status", "issues"),
            "viz_count": single_number("Open suggestions", "ds_dq_status", "issues", "", spark=None, precision=0),
            "viz_ai_status": {
                **single_status("AI setup (click to open)", "ds_dq_ai_status", "tile_status", "tile_status"),
                "eventHandlers": [
                    {
                        "type": "drilldown.linkToDashboard",
                        "options": {
                            "app": "splunk_exec_health",
                            "dashboard": "ai_provider_setup",
                            "newTab": False,
                        },
                    }
                ],
            },
            "viz_findings": findings_table,
            "viz_selected": suggestion_table,
            "viz_approve": decision_button("", "ds_dq_approve", fill=GREEN),
            "viz_dismiss": decision_button("", "ds_dq_dismiss", fill=RED),
            "viz_recorded": recorded_table,
            "viz_brief": brief_table,
            "viz_ai_ask": decision_button("", "ds_dq_ai_ready", token="tok_ai_ask", fill="#7B56DB"),
            "viz_ai_ask_state": single_status("ASK status", "ds_dq_ai_ask_status", "ask_state", "ask_state"),
            "viz_ai_ask_msg": ask_msg_table,
            "viz_ai_replies": replies_table,
            "viz_footer": md(
                "APPROVE or DISMISS only records a decision. UF, HEC, and index repairs stay runbooks. "
                "Selecting a row asks the saved provider automatically; **ASK AGAIN** retries. Search does not open. "
                "The API key stays in the AI provider lookup — never in this queue table."
            ),
        },
        "layout": grid(
            [
                block("viz_header", 0, 0, 1200, 90),
                block("viz_status", 0, 90, 400, 130),
                block("viz_count", 400, 90, 400, 130),
                block("viz_ai_status", 800, 90, 400, 130),
                block("viz_findings", 0, 220, 1200, 300),
                block("viz_selected", 0, 520, 1200, 220),
                block("viz_ai_replies", 0, 740, 1200, 170),
                block("viz_ai_ask_state", 0, 910, 280, 130),
                block("viz_ai_ask_msg", 280, 910, 920, 130),
                block("viz_approve", 0, 1040, 400, 90),
                block("viz_dismiss", 400, 1040, 400, 90),
                block("viz_ai_ask", 800, 1040, 400, 90),
                block("viz_recorded", 0, 1130, 1200, 130),
                block("viz_brief", 0, 1260, 1200, 130),
                block("viz_footer", 0, 1390, 1200, 80),
            ],
            extra_inputs=[
                "input_ask",
            ],
        ),
    }


def ai_provider_setup() -> dict:
    saved_table = table("Saved settings (key is stored, not displayed)", "ds_ai_saved", count=5)
    saved_table.pop("eventHandlers", None)
    reason_table = table("Why this status", "ds_ai_reason", count=1)
    reason_table.pop("eventHandlers", None)
    reason_table["showLastUpdated"] = False
    conn_reason_table = table("Connection test", "ds_ai_conn_reason", count=1)
    conn_reason_table.pop("eventHandlers", None)
    conn_reason_table["showLastUpdated"] = False
    providers_table = table("Supported providers", "ds_ai_providers", count=10)
    providers_table.pop("eventHandlers", None)
    return {
        "title": "AI provider setup",
        "description": "Set provider, model, and key, then click SAVE. Search does not open.",
        "defaults": {},
        "inputs": {
            "input_cfg_provider": {
                "type": "input.dropdown",
                "title": "AI provider",
                "options": {
                    "token": "tok_cfg_provider",
                    "defaultValue": "none",
                    "items": [
                        {"label": "None — local briefing only", "value": "none"},
                        {"label": "OpenAI", "value": "openai"},
                        {"label": "Cisco AI Defense", "value": "cisco"},
                        {"label": "Azure OpenAI", "value": "azure"},
                        {"label": "Anthropic", "value": "anthropic"},
                        {"label": "Custom OpenAI-compatible", "value": "custom"},
                    ],
                },
            },
            "input_cfg_model": {
                "type": "input.dropdown",
                "title": "Model",
                "options": {
                    "token": "tok_cfg_model",
                    "defaultValue": "none",
                    "selectFirstSearchResult": True,
                    "items": model_dropdown_items(),
                },
                "dataSources": {"primary": "ds_ai_models"},
            },
            "input_cfg_key": {
                "type": "input.text",
                "title": "API key",
                "options": {"token": "tok_cfg_key", "defaultValue": ""},
            },
            "input_cfg_save": {
                "type": "input.text",
                "title": "Save latch (set by SAVE)",
                "options": {"token": "tok_cfg_save", "defaultValue": "review"},
            },
        },
        "dataSources": {
            "ds_ai_current": chain(
                "Saved AI config",
                "ds_ai_conn_write",
                "| where 1=0\n| append [\n" + Q_DQ_AI_CONN_TEST.strip() + '\n| eval _gate="$tok_cfg_save$"\n]',
            ),
            "ds_ai_reason": chain(
                "Setup reason",
                "ds_ai_current",
                "| table setup_reason, ai_status, _color_rank",
            ),
            "ds_ai_conn_reason": chain(
                "Connection test reason",
                "ds_ai_current",
                "| table conn_reason, conn_status, _color_rank",
            ),
            "ds_ai_saved": chain(
                "Saved settings view",
                "ds_ai_current",
                "| table mode, provider, provider_label, model, key_state, endpoint, inbox_index, inbox_sourcetype, notes, _color_rank",
            ),
            "ds_ai_providers": ds(
                "Provider catalog",
                "| inputlookup dq_agent_ai_providers | eval _color_rank=3 | table provider, provider_label, default_endpoint, notes, _color_rank",
                "0",
                "now",
                refresh=None,
            ),
            "ds_ai_models": ds("Models for selected provider", Q_DQ_AI_MODELS, "0", "now", refresh=None),
            "ds_ai_save": ds("Save control", Q_DQ_AI_SAVE_BUTTON, "0", "now", refresh=None),
            "ds_ai_write": ds("Write AI config", Q_DQ_AI_SAVE_CONFIG, "0", "now", refresh=None),
            "ds_ai_conn_write": chain("Connection test", "ds_ai_write", "| where 1=0\n| append [\n" + Q_DQ_AI_CONN_WRITE.strip() + "\n]"),
        },
        "visualizations": {
            "viz_header": md(
                "# AI provider setup\n"
                "Pick an **AI provider**, then a **model** from the dropdown, enter the **API key**, and click **SAVE**. "
                "That writes provider config to KV Store on this search head (`dq_agent_ai_config`) and runs a **connection test**. Search does not open. "
                "The key is never shown after save and **survives app updates**. Leave key blank to keep the value already stored."
            ),
            "viz_status": single_status("Setup status", "ds_ai_current", "ai_status", "status_color"),
            "viz_conn": single_status("Connection test", "ds_ai_current", "conn_status", "conn_status"),
            "viz_reason": reason_table,
            "viz_conn_reason": conn_reason_table,
            "viz_steps": md(
                "## After a READY save\n"
                "SAVE sends one short ping **straight from this search head** to the provider with the `derekaiping` command. "
                "**Anthropic** goes to `https://api.anthropic.com/v1/messages` with a Claude model. No gateway or webhook. "
                "**PASS** means the provider replied. **FAIL** has the provider's reason in **Connection test** (for example HTTP 401 means the key was rejected).\n"
                "1. Pick the provider and model, enter the key, click **SAVE**.\n"
                "2. Splunk Cloud must allow outbound HTTPS from the search head to the provider host. If the reason says it cannot reach the provider, ask Splunk Support to allow it.\n"
                "3. Open **Derek+ Data Quality Agent**, review a finding, click **ASK**.\n"
                "**FAILED** setup means provider, model, key, or endpoint is missing. "
                "Pick **None** and SAVE to turn the provider off."
            ),
            "viz_current": saved_table,
            "viz_providers": providers_table,
            "viz_save": decision_button("", "ds_ai_save", token="tok_cfg_save", fill=GREEN),
            "viz_footer": md(
                "SAVE stores the key in KV Store collection `dq_agent_ai_config` on this search head. "
                "App updates do not overwrite it. The install package does not ship a live API key. "
                "HEC token secrets and webhook URLs still do not belong in this app. The key is read only by the search that calls the provider."
            ),
        },
        "layout": grid(
            [
                block("viz_header", 0, 0, 1200, 90),
                input_block("input_cfg_provider", 0, 90, 250, 95),
                input_block("input_cfg_model", 250, 90, 250, 95),
                input_block("input_cfg_key", 500, 90, 400, 95),
                block("viz_save", 900, 90, 300, 95),
                block("viz_status", 0, 185, 200, 140),
                block("viz_conn", 200, 185, 200, 140),
                block("viz_reason", 400, 185, 400, 140),
                block("viz_conn_reason", 800, 185, 400, 140),
                block("viz_steps", 0, 325, 1200, 150),
                block("viz_current", 0, 475, 1200, 180),
                block("viz_providers", 0, 655, 1200, 220),
                block("viz_footer", 0, 875, 1200, 80),
            ],
            include_time=False,
        ),
    }


APP_VERSION = "1.7.34"
APP_ID = "splunk_exec_health"
APP_LABEL = "Splunk Health Derek+"


def about() -> dict:
    return {
        "title": "About",
        "description": f"About {APP_LABEL}",
        "defaults": {},
        "inputs": {},
        "dataSources": {},
        "visualizations": {
            "viz_header": md(
                f"# About {APP_LABEL}\n"
                "Executive traffic-light health for Splunk Cloud Platform and Splunk Enterprise. "
                "This page is the in-app About view; open **README** in the Help menu for setup and tuning."
            ),
            "viz_what": md(
                "## What this app does\n"
                f"**{APP_LABEL}** watches whether data is still arriving, not only whether servers ping.\n\n"
                "- **Ingestion vs baseline** — daily GB compared to a 7-day moving average, not a static GB cap\n"
                "- **Heartbeat vs data** — `_internal` phone-home versus last indexed event (`tstats`)\n"
                "- **HEC tokens** — rolling 1-hour throughput and silence detection\n"
                "- **SC4S / syslog** — events per source so a hung collector is visible\n"
                "- **Edge / Ingest Processors** — in vs out, filter efficiency, dropped or queued data\n"
                "- **Derek+ Data Quality Agent** — Observe health tiles and learned ingest bounds, Investigate (tools), Hypothesize (playbooks), Propose, then **Human Act**\n\n"
                "It is an executive overlay. It does **not** replace the Cloud Monitoring Console or Monitoring Console."
            ),
            "viz_identity": md(
                "## App identity\n"
                f"- **Display name:** {APP_LABEL}\n"
                f"- **App id:** `{APP_ID}`\n"
                f"- **Version:** {APP_VERSION}\n"
                "- **Author:** SplunkHealth\n"
                "- **License:** Apache License 2.0 (`LICENSE` in the app package)\n"
                "- **UI:** Dashboard Studio (dark theme)\n"
                "- **Platforms:** Splunk Cloud (Victoria and Classic) and Splunk Enterprise\n\n"
                "The folder name must stay `splunk_exec_health`. Splunk app ids cannot contain spaces or `+`."
            ),
            "viz_cloud": md(
                "## Splunk Cloud compatibility\n"
                "- Search-head app only (`targetWorkloads: _search_heads` in `app.manifest`)\n"
                "- No cluster-manager or search-head-cluster REST (those endpoints 403 on Cloud)\n"
                "- Instance health from the `_internal` health report (PeriodicHealthReporter); search-head load from `_introspection`\n"
                "- One Python search command, `bin/derekaiping.py` (standard library only), calls the AI provider directly from the search head. No modular inputs or indexes.conf. Splunk Cloud vetting may ask for review of the command\n"
                "- No MLTK dependency; baselining uses `streamstats` and built-in `predict`\n"
                "- Knowledge objects writable by `admin`, `power`, and `sc_admin`\n"
                "- The Data Quality Agent records a decision only after a human clicks APPROVE or DISMISS AI provider, model, and key are saved from the setup page to KV Store so the key survives app updates; SAVE also runs a direct connection test against the provider\n"
                "- `commands.conf` marks `outputlookup` not-risky in this app so the approvals lookup can be written from the dashboard\n\n"
                "Self-service Cloud install requires AppInspect **0 failures, 0 errors, 0 manual checks** "
                "(`private_app` / `private_victoria` / `private_classic`). Install as **sc_admin** via "
                "**Apps → Manage apps → Install app from file**."
            ),
            "viz_security": md(
                "## Security\n"
                "This app does **not** store SMTP passwords, Slack webhooks, API tokens, LLM keys, HEC token secrets, "
                "certificates, or other credentials. Map HEC token **names** only in `lookups/hec_token_map.csv`. "
                "Playbooks, approvals, and AI request lookups hold runbook text only. "
                "Optional AI providers are configured on **Configure → AI provider**. The API key is entered once on the setup page and stored in KV Store; it is never in the package."
            ),
        },
        "layout": grid(
            [
                block("viz_header", 0, 0, 1200, 100),
                block("viz_what", 0, 100, 600, 380),
                block("viz_identity", 600, 100, 600, 380),
                block("viz_cloud", 0, 480, 600, 280),
                block("viz_security", 600, 480, 600, 280),
            ],
            include_time=False,
        ),
    }


def readme() -> dict:
    return {
        "title": "README",
        "description": f"How to use {APP_LABEL}",
        "defaults": {},
        "inputs": {},
        "dataSources": {},
        "visualizations": {
            "viz_header": md(
                f"# README — {APP_LABEL}\n"
                "How to read the dashboards, which indexes to grant, and how to tune macros and alerts. "
                "Open **About** for version, license, and Cloud packaging details."
            ),
            "viz_dashboards": md(
                "## Dashboards\n"
                f"- **{APP_LABEL}** — overall GREEN / YELLOW / RED, GB/day vs 7-day average, instance health, search-head load, silent hosts, data topology preview\n"
                "- **Host Heartbeat & Ingestion Latency** — last indexed data vs last `_internal` heartbeat; 24-hour 2σ volume baseline\n"
                "- **HEC Token Performance** — events per token; ALERT if a ~100 eps token sits at 0 for 5 minutes\n"
                "- **SC4S Syslog & Edge/Ingest Processors** — syslog sources, Edge in vs out, filter efficiency\n"
                "- **Data Topology** — sources → Windows UF / Linux UF / HF / Other TCP:port / Other UDP:port → index; click a source for latest event, totals, 24h trend, and 2σ drop/burst outliers\n"
                "- **Derek+ Data Quality Agent** — agentic loop over health tiles and learned ingest bounds; a human must APPROVE or DISMISS\n"
                "- **AI provider setup** — Configure → AI provider: provider, model dropdown, and key, then SAVE (runs a connection test; key persists in KV Store across app updates)\n\n"
                "**GREEN** = within baseline · **YELLOW** = watch · **RED** = action required."
            ),
            "viz_heartbeat": md(
                "## Heartbeat vs data\n"
                "- **OK** — recent indexed data\n"
                "- **DELAYED** — data older than 15 minutes\n"
                "- **DATA SILENT** — `_internal` heartbeat is fresh, indexed data is not\n"
                "- **HEARTBEAT ONLY** — heartbeat exists, no indexed data in range\n"
                "- **HOST DOWN** — neither heartbeat nor data\n\n"
                "DATA SILENT is the failure this app is built to catch: the forwarder is up, the pipeline is not."
            ),
            "viz_indexes": md(
                "## Indexes and role access\n"
                "Grant the viewing role search on:\n\n"
                "- `_internal` — heartbeats, license usage, health report, HEC request errors\n"
                "- `_introspection` — CPU / memory, per-token HEC metrics\n"
                "- `_metrics` — Edge Processor (optional)\n"
                "- Customer event indexes used in `exec_health_idx` (default `*`)\n\n"
                "On Splunk Cloud, `sc_admin` already has the internal indexes. Narrow `exec_health_idx` and "
                "`exec_health_sc4s_idx` if `index=*` is too wide for your workload limits."
            ),
            "viz_macros": md(
                "## Macros (Settings → Search macros)\n"
                "- `exec_health_idx` — `*` — index glob for `tstats`\n"
                "- `exec_health_sc4s_idx` — `*` — index glob for SC4S error event searches\n"
                "- `exec_health_sigma` — `2` — stdevs below host mean → ALERT\n"
                "- `exec_health_silence_sec` — `3600` — seconds without data → DATA SILENT\n"
                "- `exec_health_latency_sec` — `300` — p95 index lag (seconds) before a host is DELAYED\n"
                "- `exec_health_heartbeat_sec` — `600` — seconds without `_internal` → missing heartbeat\n"
                "- `exec_health_drop_red_pct` — `50` — % below 7-day MA → RED\n"
                "- `exec_health_drop_yellow_pct` — `20` — % below 7-day MA → YELLOW\n"
                "- `exec_health_hec_baseline_eps` — `100` — rolling EPS before HEC silence is RED\n"
                "- `exec_health_hec_silence_min` — `5` — silent minutes to flag a HEC token\n"
                "- `exec_health_sc4s` — syslog / SC4S sourcetype filter\n"
                "- `exec_health_health_report` — splunkd health report (`health.log`, PeriodicHealthReporter)\n"
                "- `exec_health_hec_metrics` / `exec_health_hec_normalize` — per-token HEC metrics in `_introspection`\n"
                "- `exec_health_edge_mstats` — `index=_metrics`"
            ),
            "viz_alerts": md(
                "## Alerts\n"
                "Health alerts ship **disabled** (`enableSched = 0`) with **no email action**. "
                "AI calls do not use an alert or a webhook. SAVE and ASK call the provider directly with the `derekaiping` command.\n\n"
                "1. Confirm the searches return expected rows on your stack\n"
                "2. **Settings → Searches, reports, and alerts** (this app) → enable the health alerts you want\n"
                "3. Attach email or Slack **in Splunk Web** — do not put webhook URLs or passwords in this app\n\n"
                "Searches:\n"
                "- Ingestion below `predict()` 95% lower bound (hourly, last complete hour)\n"
                "- Host volume 2σ drop\n"
                "- HEC token silence\n"
                "- Host data silent with heartbeat\n"
                "- Data quality agent report (open findings + proposed fixes; enable email yourself — the agent never auto-fixes)"
            ),
            "viz_hec": md(
                "## HEC token names\n"
                "Optional lookup `lookups/hec_token_map.csv` columns: `token`, `token_name`, `owner`. "
                "Store only the identifier that already appears in `_internal` metrics — **never** the HEC token secret."
            ),
        },
        "layout": grid(
            [
                block("viz_header", 0, 0, 1200, 100),
                block("viz_dashboards", 0, 100, 600, 320),
                block("viz_heartbeat", 600, 100, 600, 320),
                block("viz_indexes", 0, 420, 600, 300),
                block("viz_macros", 600, 420, 600, 300),
                block("viz_alerts", 0, 720, 600, 320),
                block("viz_hec", 600, 720, 600, 320),
            ],
            include_time=False,
        ),
    }


# ---------------------------------------------------------------------------
# Saved searches (alerts) — rendered from the same search cores as the dashboards
# ---------------------------------------------------------------------------

SAVEDSEARCHES = ROOT / "default" / "savedsearches.conf"

SS_HEADER = """# GENERATED by tools/build_dashboards.py — edit the generator, not this file.
# Scheduled alerts are disabled on install so this app cannot email or page
# until an admin enables them and configures notification settings in Splunk Web.
# Do not store SMTP passwords, API tokens, or Slack webhook URLs in this file.
"""

SS_INGESTION = r"""
| tstats count as count where index=`exec_health_idx` earliest=-7d@h latest=@h by _time span=1h
| timechart span=1h sum(count) as count
| fillnull value=0 count
| predict count as prediction future_timespan=0 holdback=0 upper95=upper lower95=lower algorithm=LLP5
| tail 1
| eval deviation_pct=if(prediction>0, round(((count-prediction)/prediction)*100, 1), 0)
| where isnotnull(lower) AND count < lower
""".strip()

SS_HOST_DROP = host_baseline_core() + r"""
| where baseline_state="ALERT"
| table _time, host, events, mean_vol, stdev_vol, lower_bound, z_score, baseline_state
"""

SS_HEC_SILENCE = hec_state_core() + r"""
| where hec_state="ALERT"
| table token, token_label, owner, baseline_eps, recent_events, silent_minutes
"""

SS_DATA_SILENT = r"""
| tstats latest(_time) as last_seen where (index=`exec_health_idx` OR index=_internal) earliest=-24h latest=now by index host
| eval kind=if(index="_internal", "heartbeat", "data")
| stats max(eval(if(kind="data", last_seen, null()))) as last_data, max(eval(if(kind="heartbeat", last_seen, null()))) as last_heartbeat by host
| eval data_age_sec=now()-last_data, heartbeat_age_sec=now()-last_heartbeat
| eval state=case(isnull(last_data) AND heartbeat_age_sec < `exec_health_heartbeat_sec`, "HEARTBEAT ONLY", data_age_sec > `exec_health_silence_sec` AND heartbeat_age_sec < `exec_health_heartbeat_sec`, "DATA SILENT", 1=1, "OK")
| where state="DATA SILENT" OR state="HEARTBEAT ONLY"
| eval last_data_received=strftime(last_data, "%Y-%m-%d %H:%M:%S"), last_internal_heartbeat=strftime(last_heartbeat, "%Y-%m-%d %H:%M:%S")
| table host, last_data_received, last_internal_heartbeat, data_age_sec, heartbeat_age_sec, state
""".strip()

# Shared alert settings. Per-entity alerts use digest_mode=0 because Splunk only
# applies alert.suppress.fields to per-result alerting.
SS_COMMON = [
    ("enableSched", "0"),
    ("realtime_schedule", "1"),
    ("schedule_window", "auto"),
    ("action.email", "0"),
    ("alert.expires", "24h"),
    ("alert.suppress", "1"),
    ("alert.track", "1"),
    ("alert_type", "number of events"),
    ("alert_comparator", "greater than"),
    ("alert_threshold", "0"),
    ("request.ui_dispatch_view", "search"),
    ("display.general.type", "statistics"),
    ("display.page.search.tab", "statistics"),
]

SAVED_SEARCHES = [
    (
        "Exec Health - Ingestion below predicted lower bound",
        SS_INGESTION,
        "Fires when the last complete hour of indexed volume falls below the predict() 95% lower bound over the previous 7 days. Runs hourly (each run scores the hour that just closed), so weekend/after-hours seasonality is expected rather than flagged.",
        [
            ("cron_schedule", "7 * * * *"),
            ("dispatch.earliest_time", "-7d@h"),
            ("dispatch.latest_time", "@h"),
            ("alert.digest_mode", "1"),
            ("alert.severity", "4"),
            ("alert.suppress.period", "1h"),
        ],
    ),
    (
        "Exec Health - Host volume 2-sigma drop",
        SS_HOST_DROP,
        "Per-host volume in the latest complete 15-minute bucket vs that host's prior 24 hours (zero-filled, so a host that drops to 0 events is caught). Alerts when volume is more than exec_health_sigma standard deviations below the host mean.",
        [
            ("cron_schedule", "*/15 * * * *"),
            ("dispatch.earliest_time", "-25h@m"),
            ("dispatch.latest_time", "@m"),
            ("alert.digest_mode", "0"),
            ("alert.severity", "4"),
            ("alert.suppress.fields", "host"),
            ("alert.suppress.period", "1h"),
        ],
    ),
    (
        "Exec Health - HEC token silence",
        SS_HEC_SILENCE,
        "Flags HEC tokens whose previous hour averaged at least exec_health_hec_baseline_eps events/sec and that sent nothing in the last exec_health_hec_silence_min complete minutes.",
        [
            ("cron_schedule", "*/5 * * * *"),
            ("dispatch.earliest_time", "-2h@m"),
            ("dispatch.latest_time", "-1m@m"),
            ("alert.digest_mode", "0"),
            ("alert.severity", "5"),
            ("alert.suppress.fields", "token"),
            ("alert.suppress.period", "30m"),
        ],
    ),
    (
        "Exec Health - Host data silent with heartbeat",
        SS_DATA_SILENT,
        "Distinguishes a host that is still phoning home in _internal from a host that has stopped sending indexed data.",
        [
            ("cron_schedule", "*/15 * * * *"),
            ("dispatch.earliest_time", "-24h"),
            ("dispatch.latest_time", "now"),
            ("alert.digest_mode", "0"),
            ("alert.severity", "4"),
            ("alert.suppress.fields", "host"),
            ("alert.suppress.period", "1h"),
        ],
    ),
    (
        "Exec Health - Data quality agent report",
        Q_DQ_AGENT_FINDINGS + "\n| where status=\"open\"",
        "Agent cycle report: when Splunk Health tiles or learned ingestion bounds are not GREEN, investigates with tools, attaches a playbook hypothesis, and lists a proposed fix. Enable this search and add an email action in Splunk Web. The search never changes Splunk configuration.",
        [
            ("cron_schedule", "12 * * * *"),
            ("dispatch.earliest_time", "-24h"),
            ("dispatch.latest_time", "now"),
            ("alert.digest_mode", "1"),
            ("alert.severity", "4"),
            ("alert.suppress.period", "1h"),
        ],
    ),
]


def render_savedsearches() -> str:
    out = [SS_HEADER.rstrip("\n")]
    for name, search, description, specific in SAVED_SEARCHES:
        lines = [ln.rstrip() for ln in search.strip().splitlines() if ln.strip()]
        body = " \\\n".join(lines)
        out.append(f"\n[{name}]")
        out.append(f"search = {body}")
        out.append(f"description = {description}")
        merged = dict(SS_COMMON)
        merged.update(dict(specific))
        for key, value in sorted(merged.items()):
            out.append(f"{key} = {value}")
    return "\n".join(out) + "\n"


def main() -> None:
    VIEWS.mkdir(parents=True, exist_ok=True)
    SAVEDSEARCHES.write_text(render_savedsearches(), encoding="utf-8")
    print(f"wrote {SAVEDSEARCHES.relative_to(ROOT)}")
    dashboards = {
        "executive_overview.xml": (
            "Splunk Health Derek+",
            "Traffic-light Splunk infrastructure health for executives.",
            executive_overview(),
        ),
        "host_heartbeat.xml": (
            "Host Heartbeat & Ingestion Latency",
            "Last data vs last heartbeat and 24-hour volume baselines.",
            host_heartbeat(),
        ),
        "hec_performance.xml": (
            "HEC Token Performance",
            "HTTP Event Collector throughput and silence detection.",
            hec_performance(),
        ),
        "sc4s_edge.xml": (
            "SC4S Syslog & Edge/Ingest Processors",
            "Syslog/SC4S sources and Edge/Ingest Processor in-flight metrics.",
            sc4s_edge(),
        ),
        "data_topology.xml": (
            "Data Topology",
            "Click a data source for latest event, volume, trend, and drop/burst outliers.",
            data_topology(),
        ),
        "data_quality_agent.xml": (
            "Derek+ Data Quality Agent",
            "Click Select, then APPROVE or DISMISS to record the decision. Search does not open.",
            data_quality_agent(),
        ),
        "ai_provider_setup.xml": (
            "AI provider setup",
            "Set provider, model, and key, then click SAVE. Search does not open.",
            ai_provider_setup(),
        ),
        "readme.xml": (
            "README",
            f"How to use {APP_LABEL}: dashboards, indexes, macros, and alerts.",
            readme(),
        ),
        "about.xml": (
            "About",
            f"About {APP_LABEL}: version, license, and Splunk Cloud compatibility.",
            about(),
        ),
    }
    for filename, (label, desc, definition) in dashboards.items():
        path = VIEWS / filename
        definition = studio_cards(definition)
        xml_text = wrap(label, desc, definition)
        path.write_text(xml_text, encoding="utf-8")
        json.loads(json.dumps(definition))
        ET.fromstring(xml_text)
        print(f"wrote {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
