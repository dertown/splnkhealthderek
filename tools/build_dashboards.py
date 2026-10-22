#!/usr/bin/env python3
"""Generate Dashboard Studio XML views. Run from the repo root."""
from __future__ import annotations

import json
from pathlib import Path

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

# Row colors: 1=red/alert, 2=yellow, 3=green/ok
ROW_COLORS = [
    {"from": 0, "to": 1.5, "value": "#5C1A1A"},
    {"from": 1.5, "to": 2.5, "value": "#5C4A12"},
    {"from": 2.5, "to": 4, "value": "#14301A"},
]


def wrap(label: str, description: str, definition: dict) -> str:
    body = json.dumps(definition, indent=2)
    return (
        f'<dashboard version="2" theme="dark">\n'
        f"  <label>{label}</label>\n"
        f"  <description>{description}</description>\n"
        f"  <definition><![CDATA[\n{body}\n]]></definition>\n"
        f"</dashboard>\n"
    )


def ds(name: str, query: str, earliest: str | None = None, latest: str | None = None, refresh: str = "5m") -> dict:
    options: dict = {
        "query": query.strip(),
        "refresh": refresh,
        "refreshType": "delay",
    }
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


def single_status(title: str, ds_id: str, value_field: str, score_field: str) -> dict:
    return {
        "type": "splunk.singlevalue",
        "title": title,
        "dataSources": {"primary": ds_id},
        "showLastUpdated": True,
        "showProgressBar": True,
        "options": {
            "majorValue": f"> primary | seriesByName(\"{value_field}\")",
            "majorColor": f"> primary | seriesByName(\"{score_field}\") | rangeValue(healthColors)",
            "backgroundColor": "transparent",
            "majorFontSize": 36,
        },
        "context": {"healthColors": HEALTH_COLORS},
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
                    "type": "global",
                    "newTab": True,
                },
            }
        ],
    }


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


def grid(structure: list, extra_inputs: list | None = None) -> dict:
    inputs = ["input_global_trp"] + (extra_inputs or [])
    return {"type": "grid", "globalInputs": inputs, "structure": structure}


# ---------------------------------------------------------------------------
# Executive Overview
# ---------------------------------------------------------------------------

Q_HEALTH_COMPONENTS = r"""
search index=_internal sourcetype=splunkd component=HealthReporter
| eval health_val=lower(coalesce(health, color, "unknown"))
| stats latest(health_val) as health_val by feature
| eval component="instance:"+feature, score=case(health_val="green", 2, health_val="yellow", 1, health_val="red", 0, 1=1, 1)
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

Q_LICENSE_DAILY = r"""
search `exec_health_license_usage`
| eval daily_GB=round(b/1024/1024/1024, 4)
| bin _time span=1d
| stats sum(daily_GB) as daily_GB by _time
| streamstats window=7 current=f avg(daily_GB) as ma_7d
| eval ma_7d=round(ma_7d, 3), daily_GB=round(daily_GB, 3)
| eval variance_pct=if(ma_7d>0, round(((daily_GB-ma_7d)/ma_7d)*100, 1), 0)
| eval health_score=case(isnull(ma_7d), 2, daily_GB < ma_7d*(1-`exec_health_drop_red_pct`/100), 0, daily_GB < ma_7d*(1-`exec_health_drop_yellow_pct`/100), 1, 1=1, 2)
| eval health_label=case(health_score=0, "RED", health_score=1, "YELLOW", 1=1, "GREEN")
| sort _time
""".strip()

Q_INDEXER_CLUSTER = r"""
| rest /services/cluster/master/peers count=0
| stats count as peers, count(eval(match(coalesce(status, ""), "(?i)up|heartbeat|batched"))) as peers_up
| eval health_score=case(peers=0, 1, peers_up=peers, 2, peers_up=0, 0, 1=1, 1)
| eval clustering_status=case(peers=0, "N/A", peers_up=peers, "GREEN", peers_up=0, "RED", 1=1, "YELLOW")
| eval status_detail=peers_up." / ".peers." peers up"
| appendpipe [
    stats count
    | where count=0
    | eval clustering_status="N/A", health_score=1, peers=0, peers_up=0, status_detail="Not clustered / no CM REST"
]
""".strip()

Q_SHC = r"""
| rest /services/shcluster/captain/members count=0
| stats count as members, count(eval(match(coalesce(status, 'status.label', ""), "(?i)up|ok"))) as members_up
| eval health_score=case(members=0, 1, members_up=members, 2, members_up=0, 0, 1=1, 1)
| eval shc_status=case(members=0, "N/A", members_up=members, "GREEN", members_up=0, "RED", 1=1, "YELLOW")
| eval status_detail=members_up." / ".members." members up"
| appendpipe [
    stats count
    | where count=0
    | eval shc_status="N/A", health_score=1, members=0, members_up=0, status_detail="Standalone / no SHC REST"
]
""".strip()

Q_SILENT = r"""
| tstats latest(_time) as last_data where index=`exec_health_idx` by host
| eval silent=if((now()-last_data)>`exec_health_silence_sec`, 1, 0)
| stats count as hosts, sum(silent) as silent_hosts
| appendpipe [ stats count | where count=0 | eval hosts=0, silent_hosts=0 ]
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
| eval cpu_pct=coalesce(cpu_system_pct, 0)+coalesce(cpu_user_pct, 0)
| eval mem_used_gb=round(coalesce(mem_used, 0)/1024/1024/1024, 2)
| stats avg(cpu_pct) as avg_cpu_pct, max(cpu_pct) as max_cpu_pct, latest(mem_used_gb) as mem_used_gb by host
| eval avg_cpu_pct=round(avg_cpu_pct, 1), max_cpu_pct=round(max_cpu_pct, 1)
| eval _color_rank=case(max_cpu_pct>=90, 1, max_cpu_pct>=75, 2, 1=1, 3)
| sort 0 -max_cpu_pct
""".strip()

Q_HOST_ALERTS = r"""
| tstats count as events where index=`exec_health_idx` earliest=-24h latest=now by host _time span=15m
| streamstats window=96 current=f avg(events) as mean_vol stdev(events) as stdev_vol by host
| eval sigma=`exec_health_sigma`, lower_bound=round(mean_vol-(sigma*stdev_vol), 1)
| eval baseline_state=case(isnull(mean_vol), "WARMUP", isnotnull(stdev_vol) AND events < lower_bound AND mean_vol>10, "ALERT", 1=1, "OK")
| sort 0 -_time
| dedup host
| where baseline_state="ALERT"
| eval z_score=if(stdev_vol>0, round((events-mean_vol)/stdev_vol, 2), 0)
| eval _color_rank=1
| table host, events, mean_vol, stdev_vol, lower_bound, z_score, baseline_state, _color_rank
| sort host
""".strip()


def executive_overview() -> dict:
    return {
        "title": "Executive Health Overview",
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
            "ds_license_daily": ds("License GB/day vs 7d MA", Q_LICENSE_DAILY, "-8d@d", "now", refresh="15m"),
            "ds_indexer_cluster": ds("Indexer cluster peers", Q_INDEXER_CLUSTER, "-15m", "now"),
            "ds_shc": ds("Search head cluster", Q_SHC, "-15m", "now"),
            "ds_silent": ds("Silent hosts", Q_SILENT, "-24h", "now"),
            "ds_live": ds("Live indexed events 15m", Q_LIVE, "-15m", "now"),
            "ds_top_indexes": ds("Top indexes by GB", Q_TOP_INDEXES),
            "ds_introspection": ds("Hostwide introspection", Q_INTROSPECTION),
            "ds_host_alerts": ds("Host 2-sigma alerts", Q_HOST_ALERTS, "-24h", "now"),
        },
        "visualizations": {
            "viz_header": md(
                "# Executive Health Overview\n"
                "Traffic lights combine instance HealthReporter, live ingestion, 7-day volume baseline, and silent hosts. "
                "**GREEN** = within baseline · **YELLOW** = watch · **RED** = action required."
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
            "viz_idx_cluster": single_status("Indexer clustering", "ds_indexer_cluster", "clustering_status", "health_score"),
            "viz_shc": single_status("Search head cluster", "ds_shc", "shc_status", "health_score"),
            "viz_silent": {
                "type": "splunk.singlevalue",
                "title": "Silent hosts (>1h no data)",
                "dataSources": {"primary": "ds_silent"},
                "showLastUpdated": True,
                "showProgressBar": True,
                "options": {
                    "majorValue": "> primary | seriesByName(\"silent_hosts\")",
                    "majorColor": "> primary | seriesByName(\"health_score\") | rangeValue(healthColors)",
                    "sparklineDisplay": "off",
                    "trendDisplay": "off",
                    "majorFontSize": 32,
                },
                "context": {"healthColors": HEALTH_COLORS},
            },
            "viz_ingest_chart": line("Daily ingestion vs 7-day moving average", "ds_license_daily", "GB / day"),
            "viz_top_indexes": table("Top indexes by license usage (GB)", "ds_top_indexes", count=15),
            "viz_intro": table("Indexer/SH resource usage (_introspection)", "ds_introspection", count=15),
            "viz_host_alerts": table("Hosts below 2σ 24-hour baseline (latest 15m)", "ds_host_alerts", count=25),
            "viz_components": table("Health component scores", "ds_health_components", count=20),
            "viz_footer": md(
                "Baselines use **streamstats** (host volume) and **predict**/moving average (daily GB), not static thresholds. "
                "Cluster tiles show **N/A** on standalone or Splunk Cloud stacks without cluster REST. "
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
                block("viz_top_indexes", 0, 730, 600, 300),
                block("viz_intro", 600, 730, 600, 300),
                block("viz_host_alerts", 0, 1030, 700, 320),
                block("viz_components", 700, 1030, 500, 320),
                block("viz_footer", 0, 1350, 1200, 110),
            ]
        ),
    }


# ---------------------------------------------------------------------------
# Host heartbeat
# ---------------------------------------------------------------------------

Q_PHONE_HOME = r"""
| tstats latest(_time) as last_data where index=`exec_health_idx` host=$host_filter$ by host
| append [
    | tstats latest(_time) as last_heartbeat where index=_internal host=$host_filter$ by host
]
| stats max(last_data) as last_data, max(last_heartbeat) as last_heartbeat by host
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
| tstats latest(_time) as last_data where index=`exec_health_idx` host=$host_filter$ by host
| append [
    | tstats latest(_time) as last_heartbeat where index=_internal host=$host_filter$ by host
]
| stats max(last_data) as last_data, max(last_heartbeat) as last_heartbeat by host
| eval data_age_sec=now()-last_data, heartbeat_age_sec=now()-last_heartbeat
| eval state=case(
    isnull(last_data) AND heartbeat_age_sec < `exec_health_heartbeat_sec`, "HEARTBEAT ONLY",
    data_age_sec > `exec_health_silence_sec` AND heartbeat_age_sec < `exec_health_heartbeat_sec`, "DATA SILENT",
    (isnull(last_heartbeat) OR heartbeat_age_sec > `exec_health_silence_sec`) AND data_age_sec > `exec_health_silence_sec`, "HOST DOWN",
    data_age_sec > 900, "DELAYED",
    1=1, "OK")
| stats count as hosts by state
""".strip()

Q_BASELINE_ALL = r"""
| tstats count as events where index=`exec_health_idx` host=$host_filter$ earliest=-24h latest=now by host _time span=15m
| streamstats window=96 current=f avg(events) as mean_vol stdev(events) as stdev_vol by host
| eval sigma=`exec_health_sigma`, lower_bound=round(mean_vol-(sigma*stdev_vol), 1)
| eval baseline_state=case(isnull(mean_vol), "WARMUP", isnotnull(stdev_vol) AND events < lower_bound AND mean_vol>10, "ALERT", 1=1, "OK")
| sort 0 -_time
| dedup host
| eval current_eps=round(events/900, 2), baseline_eps=round(mean_vol/900, 2)
| eval z_score=if(stdev_vol>0, round((events-mean_vol)/stdev_vol, 2), 0)
| eval _color_rank=case(baseline_state="ALERT", 1, baseline_state="WARMUP", 2, 1=1, 3)
| table host, events, mean_vol, stdev_vol, lower_bound, current_eps, baseline_eps, z_score, baseline_state, _color_rank
| sort _color_rank, host
""".strip()

Q_HOST_VOLUME = r"""
| tstats count as events where index=`exec_health_idx` host=$host_filter$ by _time span=15m host
| timechart span=15m sum(events) as events by host
""".strip()

Q_HOST_LIST = r"""
| tstats count where index=`exec_health_idx` by host
| rename host as label
| eval value=label
| table label, value
| sort label
""".strip()

Q_METADATA = r"""
| metadata type=hosts index=`exec_health_idx`
| eval last_seen=strftime(lastTime, "%Y-%m-%d %H:%M:%S"), first_seen=strftime(firstTime, "%Y-%m-%d %H:%M:%S"), age=tostring(now()-lastTime, "duration")
| eval _color_rank=if((now()-lastTime)>`exec_health_silence_sec`, 1, 3)
| table host, first_seen, last_seen, totalCount, age, _color_rank
| sort _color_rank, host
""".strip()


def host_heartbeat() -> dict:
    return {
        "title": "Host Heartbeat & Ingestion Latency",
        "description": "Last indexed data vs last _internal heartbeat, plus 24-hour streamstats baselines.",
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
            "ds_baseline": ds("24h streamstats baseline", Q_BASELINE_ALL, "-24h", "now"),
            "ds_host_volume": ds("Host volume over time", Q_HOST_VOLUME),
            "ds_metadata": ds("metadata type=hosts", Q_METADATA),
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
            "viz_baseline": table("Per-host 24-hour mean / stdev (streamstats window=96 @ 15m)", "ds_baseline", count=30),
            "viz_volume": area("Ingestion volume by host", "ds_host_volume", "events / 15m"),
            "viz_meta": table("Metadata inventory (type=hosts)", "ds_metadata", count=20),
            "viz_footer": md(
                "`tstats latest(_time)` is the source of truth for last data / last heartbeat. "
                "`| metadata type=hosts` is shown for inventory comparison. "
                "Override `exec_health_silence_sec` (default 3600) and `exec_health_sigma` (default 2) as needed."
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
                block("viz_baseline", 0, 580, 1200, 320),
                block("viz_volume", 0, 900, 1200, 300),
                block("viz_meta", 0, 1200, 1200, 280),
                block("viz_footer", 0, 1480, 1200, 90),
            ],
            extra_inputs=["input_host"],
        ),
    }


# ---------------------------------------------------------------------------
# HEC
# ---------------------------------------------------------------------------

Q_HEC_TIMECHART = r"""
search `exec_health_hec_metrics`
| eval token=coalesce(series, name, token)
| lookup hec_token_map token OUTPUT token_name, owner
| eval token_label=coalesce(token_name, token)
| timechart span=5m sum(ev) as events by token_label
""".strip()

Q_HEC_STATE = r"""
search `exec_health_hec_metrics`
| eval token=coalesce(series, name, token)
| lookup hec_token_map token OUTPUT token_name, owner
| eval token_label=coalesce(token_name, token)
| bin _time span=1m
| stats sum(ev) as events, sum(kb) as kb by _time, token, token_label, owner
| streamstats window=60 avg(events) as avg_1h by token
| eval is_silent=if(events=0, 1, 0)
| streamstats window=`exec_health_hec_silence_min` sum(is_silent) as silent_minutes by token
| sort 0 -_time
| dedup token
| eval avg_1h_eps=round(avg_1h, 2), kb=round(kb, 1)
| eval hec_state=case(
    avg_1h_eps >= `exec_health_hec_baseline_eps` AND silent_minutes >= `exec_health_hec_silence_min`, "ALERT",
    avg_1h_eps >= 10 AND silent_minutes >= `exec_health_hec_silence_min`, "YELLOW",
    1=1, "OK")
| eval _color_rank=case(hec_state="ALERT", 1, hec_state="YELLOW", 2, 1=1, 3)
| table token, token_label, owner, events, avg_1h_eps, silent_minutes, kb, hec_state, _color_rank
| sort _color_rank, token_label
""".strip()

Q_HEC_TOTALS = r"""
search `exec_health_hec_metrics`
| stats sum(ev) as events, dc(series) as tokens, sum(kb) as kb
| appendpipe [ stats count | where count=0 | eval events=0, tokens=0, kb=0 ]
| eval events_per_sec=round(events/3600, 1)
| eval gb=round(kb/1024/1024, 3)
""".strip()

Q_HEC_HANDLER = r"""
search `exec_health_hec_handler`
| eval token=coalesce(token, token_name, series)
| eval is_error=if(match(coalesce(log_level, ""), "(?i)error|warn") OR match(_raw, "(?i)error|fail|reject"), 1, 0)
| stats count as events, sum(is_error) as errors by token
| eval _color_rank=if(errors>0, 1, 3)
| sort 0 -errors, -events
""".strip()

Q_HEC_ERRORS = r"""
search `exec_health_hec_handler` (log_level=ERROR OR log_level=WARN OR error OR fail OR reject)
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
            "ds_hec_state": ds("HEC token state", Q_HEC_STATE, "-2h", "now"),
            "ds_hec_totals": ds("HEC totals", Q_HEC_TOTALS, "-1h", "now"),
            "ds_hec_handler": ds("HttpInputDataHandler by token", Q_HEC_HANDLER),
            "ds_hec_errors": ds("HttpInputDataHandler issues", Q_HEC_ERRORS),
            "ds_hec_alert_count": chain(
                "HEC alert count",
                "ds_hec_state",
                '| where hec_state="ALERT" | stats count as alerts | appendpipe [ stats count | where count=0 | eval alerts=0 ]',
            ),
        },
        "visualizations": {
            "viz_header": md(
                "# HEC token performance\n"
                "Throughput comes from `metrics.log` `group=http` (series = token). "
                "A token that usually sends **100+ events/sec** (macro `exec_health_hec_baseline_eps`) and stays at **0 for 5 minutes** is **ALERT**. "
                "Map token GUIDs to names in `lookups/hec_token_map.csv` — do not put HEC secrets in that file, only display names."
            ),
            "viz_tokens": single_number("Active tokens (1h)", "ds_hec_totals", "tokens", "", None, 0),
            "viz_eps": single_number("HEC events / sec (1h)", "ds_hec_totals", "events_per_sec", "", None, 1),
            "viz_gb": single_number("HEC volume (1h)", "ds_hec_totals", "gb", " GB", None, 3),
            "viz_alerts": single_number("Tokens in ALERT", "ds_hec_alert_count", "alerts", "", None, 0),
            "viz_time": area("HEC events by token", "ds_hec_time", "events / 5m"),
            "viz_state": table("Token vs 1-hour rolling window", "ds_hec_state", count=25),
            "viz_errors": line("HttpInputDataHandler errors / warnings", "ds_hec_errors", "issues"),
            "viz_handler": table("HttpInputDataHandler activity by token", "ds_hec_handler", count=20),
            "viz_footer": md(
                "Populate `hec_token_map.csv` with `token,token_name,owner`. Never store the HEC token **value** (the secret) in the lookup — only the token name or UUID that already appears in `_internal` metrics."
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
search index=* `exec_health_sc4s` (ERROR OR error OR WARN OR fail OR "connection refused" OR hang OR dropped)
| stats count as issues by host, sourcetype
| eval _color_rank=if(issues>0, 1, 3)
| sort 0 -issues
""".strip()

Q_SC4S_ERR_TIME = r"""
search index=* `exec_health_sc4s` (ERROR OR error OR WARN OR fail OR "connection refused")
| timechart span=5m count as sc4s_issues
""".strip()

Q_EDGE_THROUGHPUT = r"""
| mstats rate(processor_events_in_total) as events_in_eps, rate(processor_events_out_total) as events_out_eps, rate(processor_bytes_in_total) as bytes_in_eps, rate(processor_bytes_out_total) as bytes_out_eps where `exec_health_edge_mstats` by host span=5m
| eval filter_efficiency_pct=if(events_in_eps>0, round(((events_in_eps-events_out_eps)/events_in_eps)*100, 2), 0)
| eval dropped_or_filtered_eps=round(events_in_eps-events_out_eps, 2)
| eval events_in_eps=round(events_in_eps, 2), events_out_eps=round(events_out_eps, 2)
| eval _color_rank=case(events_in_eps>0 AND events_out_eps=0, 1, filter_efficiency_pct>50, 2, 1=1, 3)
""".strip()

Q_EDGE_SUMMARY = r"""
| mstats rate(processor_events_in_total) as events_in_eps, rate(processor_events_out_total) as events_out_eps, rate(processor_bytes_in_total) as bytes_in_eps, rate(processor_bytes_out_total) as bytes_out_eps where `exec_health_edge_mstats`
| appendpipe [ stats count | where count=0 | eval events_in_eps=0, events_out_eps=0, bytes_in_eps=0, bytes_out_eps=0 ]
| eval filter_efficiency_pct=if(events_in_eps>0, round(((events_in_eps-events_out_eps)/events_in_eps)*100, 2), 0)
| eval events_in_eps=round(events_in_eps, 2), events_out_eps=round(events_out_eps, 2)
| eval bytes_in_mbps=round(bytes_in_eps/1024/1024, 3)
""".strip()

Q_EDGE_QUEUE = r"""
| mstats latest(queue_size_bytes) as queue_size_bytes, latest(exporter_queue_size) as exporter_queue_size, sum(export_destination_errors_total) as export_errors where index=_metrics sourcetype=edge-metrics by host
| eval queue_mb=round(queue_size_bytes/1024/1024, 2)
| eval _color_rank=if(export_errors>0, 1, 3)
""".strip()

Q_EDGE_LOGS = r"""
search index=_internal (source="*edge.log" OR sourcetype=edge OR sourcetype=splunkd_ui_res OR sourcetype=*edge*processor* OR component=IngestActions OR component=IngestProcessor)
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
search index=_internal ((sourcetype=splunkd (component=IngestActions OR component=IngestProcessor)) OR (source=*metrics.log group=pipeline))
| eval dropped=coalesce(dropped_events, dropped, blocked, 0)
| timechart span=5m sum(dropped) as dropped_events, count as pipeline_events
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
            "ds_ingest_actions": ds("Ingest Actions / pipeline drops", Q_INGEST_ACTIONS),
        },
        "visualizations": {
            "viz_header": md(
                "# SC4S and Edge / Ingest Processors\n"
                "Left side watches **syslog/SC4S** volume per source host (load-balancer hang = flatline). "
                "Right side compares **Edge Processor in vs out** (`mstats` on `sourcetype=edge-metrics`) with **events reaching indexers**."
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
            "viz_edge_queue": table("Edge queues and destination errors", "ds_edge_queue", count=15),
            "viz_ingest": line("Ingest Actions / pipeline dropped events", "ds_ingest_actions", "dropped"),
            "viz_edge_logs": table("Edge / Ingest Processor _internal logs", "ds_edge_logs", count=15),
            "viz_footer": md(
                "Edge metrics require the `_metrics` index and `sourcetype=edge-metrics`. "
                "If those panels are empty, the deployment is not emitting Edge Processor metrics — use `_internal` logs instead. "
                "**Filter efficiency** = `(events_in - events_out) / events_in`. High values mean pipelines are dropping or routing away from indexers. "
                "SC4S sourcetypes vary by install; override macro `exec_health_sc4s` if your stream uses a custom sourcetype."
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


def main() -> None:
    VIEWS.mkdir(parents=True, exist_ok=True)
    dashboards = {
        "executive_overview.xml": (
            "Executive Health Overview",
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
    }
    for filename, (label, desc, definition) in dashboards.items():
        path = VIEWS / filename
        path.write_text(wrap(label, desc, definition), encoding="utf-8")
        json.loads(json.dumps(definition))
        print(f"wrote {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
