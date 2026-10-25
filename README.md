# Splunk Health Derek+

Dashboard Studio app for an executive traffic-light view of Splunk ingestion, host heartbeat, HEC tokens, SC4S syslog, and Edge / Ingest Processors. Built for **Splunk Cloud Platform** (Victoria and Classic) and Splunk Enterprise.

Baselines are **statistical**, not static GB thresholds. Daily license volume is compared to a 7-day moving average. Per-host volume uses `streamstats` mean and standard deviation. The scheduled ingestion alert uses Splunk’s built-in `predict` command so weekend and after-hours cycles are expected rather than treated as incidents.

The installable package folder name (app id) is `splunk_exec_health`. The visible name is **Splunk Health Derek+**.

Inside the app, **Help → README** is the operator guide and **Help → About** is version, license, and Cloud compatibility.

## What you get

| View | Purpose |
| --- | --- |
| **Splunk Health Derek+** | GREEN / YELLOW / RED rollup, GB/day vs 7-day MA, splunkd health report, search-head load, silent hosts, `_introspection` CPU/memory |
| **Host Heartbeat & Ingestion Latency** | Last indexed data vs last `_internal` heartbeat, `metadata type=hosts` inventory, 24-hour 2σ baseline table |
| **HEC Token Performance** | Events per HEC token, 1-hour rolling window, flag if a ~100 eps token sits at 0 for 5+ minutes |
| **SC4S Syslog & Edge/Ingest Processors** | Events per syslog source, Edge Processor in vs out, filter efficiency, dropped / queue metrics |
| **Data Topology** | Link graph and Sankey of data sources → Windows UF / Linux UF / HF / Other TCP:port / Other UDP:port / HEC / SC4S → index, plus forwarder → indexer |

Saved searches (all **disabled** on install):

- Ingestion below `predict()` 95% lower bound (hourly, scores the hour that just closed)
- Host volume 2σ drop (every 15 minutes, latest complete 15-minute bucket, zero-filled)
- HEC token silence (every 5 minutes)
- Host still heartbeating but not sending data (every 15 minutes)

The app does not use cluster-manager REST, SHC captain REST, custom Python, modular inputs, `indexes.conf`, or MLTK. `app.manifest` targets search heads only. That keeps Splunk Cloud AppInspect self-service install viable (0 failures, 0 errors, 0 manual checks on `private_app` / `private_victoria` / `private_classic`).

## Data sources

| Signal | Index / endpoint | Access method |
| --- | --- | --- |
| Event volume, last data per host | event indexes (`index=*` via macro `exec_health_idx`) | `tstats` |
| Internal heartbeat | `_internal` | `tstats latest(_time)` |
| GB/day | `_internal` `license_usage.log` `type=Usage` | event search (already aggregated) |
| Instance feature health | `_internal` `health.log` `component=PeriodicHealthReporter` (`feature`, `color`) | event search |
| Search head load | `_introspection` `sourcetype=splunk_resource_usage` | event search |
| HEC throughput | `_introspection` `sourcetype=http_event_collector_metrics` `data.series=http_event_collector_token` | event search |
| HEC request failures | `_internal` `component=HttpInputDataHandler` (`token name=`) | event search |
| Edge Processor | `_metrics` (`processor_events_in_total` and related counters) | `mstats rate_sum` |
| SC4S / syslog | macros `exec_health_idx` / `exec_health_sc4s_idx` | `tstats` + optional event search |

The viewing role needs search access to `_internal` and `_introspection` (HEC per-token metrics live in `_introspection`). Add `_metrics` if you use Edge Processor. On Splunk Cloud, `sc_admin` has this by default; grant those indexes to other roles that should open the app.

## Install

### Splunk Cloud

Use the packaged `.spl` (search-head only, no `local/`, no `tools/` Python, no `.git`):

1. Sign in as **sc_admin**.
2. **Apps → Manage apps → Install app from file**.
3. Upload `dist/splunk_exec_health-1.2.5.spl`.
4. Splunk Cloud runs AppInspect automatically. The report must show 0 failures, 0 errors, and 0 manual checks for self-service install.
5. Open **Splunk Health Derek+** from the app menu.

If AppInspect returns manual checks, install via Splunk Support / ACS instead, or rebuild from this repo (the Cloud package already excludes the dashboard generator).

Grant the viewing role:

- Indexes: `_internal`, `_introspection`, and `_metrics` if Edge panels should run
- Capabilities: `search`, `rest_properties_get` (standard for power / sc_admin)

On Cloud, override `exec_health_idx` and `exec_health_sc4s_idx` if `index=*` is too broad for your workload limits.

### Splunk Enterprise

1. Copy this directory to `$SPLUNK_HOME/etc/apps/splunk_exec_health` (or install the `.spl`).
2. Restart Splunk, or reload the app from **Manage apps**.
3. Open **Splunk Health Derek+** from the app menu.

## Enable alerts

Saved searches ship with `enableSched = 0` and **no email action**. That is intentional: this app must not send mail or call webhooks until you decide it should.

1. **Settings > Searches, reports, and alerts** (filter to this app).
2. Enable the four core alerts after you have confirmed the searches return expected rows on your stack.
3. Add an email (or Slack) action **in Splunk Web**. On Cloud, use Splunk’s email settings / allowed notification add-ons.

Do not put SMTP passwords, Slack webhook URLs, API tokens, or HEC token **secrets** in `default/` or `local/` of this app. Notification credentials belong in Splunk’s alert-action / email configuration, not in source control.

## Tune thresholds

Override these macros in **Settings > Advanced search > Search macros** (or `local/macros.conf`):

| Macro | Default | Meaning |
| --- | --- | --- |
| `exec_health_idx` | `*` | Index glob for `tstats` |
| `exec_health_sc4s_idx` | `*` | Index glob for SC4S error event searches |
| `exec_health_sigma` | `2` | Stdevs below host mean → ALERT |
| `exec_health_silence_sec` | `3600` | Seconds without data → DATA SILENT |
| `exec_health_heartbeat_sec` | `600` | Seconds without `_internal` → missing heartbeat |
| `exec_health_drop_red_pct` | `50` | % below 7-day MA → RED |
| `exec_health_drop_yellow_pct` | `20` | % below 7-day MA → YELLOW |
| `exec_health_hec_baseline_eps` | `100` | Previous-hour events/sec before silence is RED |
| `exec_health_hec_silence_min` | `5` | Silent minutes to flag a HEC token |
| `exec_health_sc4s` | `sourcetype=sc4s* OR ...` | Syslog / SC4S filter |
| `exec_health_health_report` | `index=_internal source=*health.log component=PeriodicHealthReporter` | splunkd health report |
| `exec_health_hec_metrics` | `index=_introspection sourcetype=http_event_collector_metrics data.series=http_event_collector_token` | Per-token HEC metrics |
| `exec_health_hec_normalize` | `eval token='data.token_name', ...` | Maps HEC metric fields |
| `exec_health_edge_mstats` | `index=_metrics` | Edge Processor metrics |

Map HEC token input names to display names in `lookups/hec_token_map.csv`. Columns are `token,token_name,owner`, where `token` is the HEC input name exactly as it appears in `data.token_name` — never the HEC token secret.

## Heartbeat vs data

| State | Meaning |
| --- | --- |
| OK | Recent indexed data |
| DELAYED | Data older than 15 minutes |
| DATA SILENT | `_internal` heartbeat is fresh, indexed data is not |
| HEARTBEAT ONLY | Heartbeat exists, no indexed data in range |
| HOST DOWN | Neither heartbeat nor data |

DATA SILENT is the failure mode this app is built to catch: the UF/HF is up, the pipeline is not.

## Edge Processor empty panels

Edge tiles use `mstats rate_sum` against the Edge Processor counters in `_metrics`. If those panels are empty, Edge Processor is not emitting metrics to this search head; `_internal` edge / Ingest Actions logs still populate the lower tables.

**Filter efficiency** is `(events_in - events_out) / events_in`. Treat a high percentage as “pipelines are dropping or routing away from indexers,” not as a hardware fault by itself.

## Search load

- Prefer `tstats` / `mstats` over raw event scans.
- License GB/day reads `license_usage.log`, which is already summarized.
- Default auto-refresh is 5 minutes (15 minutes for the 15-day license series, which covers complete days only).
- Narrow `exec_health_idx` if `index=*` is too wide (recommended on Splunk Cloud).

This app is an executive overlay. It does not replace the Cloud Monitoring Console.

## Rebuild dashboards / package

Dashboard Studio XML **and `default/savedsearches.conf`** are generated from `tools/build_dashboards.py` (development only — not shipped in the Cloud `.spl`). Edit the generator, not the generated files. `tools/validate_keys.py` checks every conf key, Dashboard Studio option, macro, lookup and cross-reference; `package.sh` runs it and refuses to package on errors.

```bash
python3 tools/build_dashboards.py
python3 tools/validate_keys.py
bash tools/package.sh
```

`tools/package.sh` writes `dist/splunk_exec_health-<version>.spl` with 644 file modes, no Python, and no `local/`. Validate Cloud self-service install with AppInspect 4.x:

```bash
splunk-appinspect inspect dist/splunk_exec_health-1.2.5.spl --included-tags private_app
```
