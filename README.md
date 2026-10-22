# Splunk Executive Health

Dashboard Studio app for an executive traffic-light view of Splunk ingestion, host heartbeat, HEC tokens, SC4S syslog, and Edge / Ingest Processors.

Baselines are **statistical**, not static GB thresholds. Daily license volume is compared to a 7-day moving average. Per-host volume uses `streamstats` mean and standard deviation. The scheduled ingestion alert uses Splunk’s built-in `predict` command so weekend and after-hours cycles are expected rather than treated as incidents.

Install this repository as `$SPLUNK_HOME/etc/apps/splunk_exec_health`.

## What you get

| View | Purpose |
| --- | --- |
| **Executive Health Overview** | GREEN / YELLOW / RED rollup, GB/day vs 7-day MA, indexer and search-head cluster tiles, silent hosts, `_introspection` CPU/memory |
| **Host Heartbeat & Ingestion Latency** | Last indexed data vs last `_internal` heartbeat, `metadata type=hosts` inventory, 24-hour 2σ baseline table |
| **HEC Token Performance** | Events per HEC token, 1-hour rolling window, flag if a ~100 eps token sits at 0 for 5+ minutes |
| **SC4S Syslog & Edge/Ingest Processors** | Events per syslog source, Edge Processor in vs out, filter efficiency, dropped / queue metrics |

Saved searches (all **disabled** on install):

- Ingestion below `predict()` 95% lower bound (every 15 minutes)
- Host volume 2σ drop
- HEC token silence
- Host still heartbeating but not sending data
- Optional MLTK `DensityFunction` fit/apply pair

## Data sources

| Signal | Index / endpoint | Access method |
| --- | --- | --- |
| Event volume, last data per host | all event indexes (`index=*` via macro `exec_health_idx`) | `tstats` |
| Internal heartbeat | `_internal` | `tstats latest(_time)` |
| GB/day | `_internal` `license_usage.log` `type=Usage` | event search (already aggregated) |
| Instance feature health | `_internal` `component=HealthReporter` | event search |
| CPU / memory | `_introspection` `sourcetype=splunk_resource_usage` | event search |
| HEC throughput | `_internal` `metrics.log` `group=http` plus `component=HttpInputDataHandler` | event search |
| Cluster status | `/services/cluster/master/peers`, `/services/shcluster/captain/members` | `rest` |
| Edge Processor | `_metrics` `sourcetype=edge-metrics` | `mstats` |
| SC4S / syslog | indexes matching macro `exec_health_sc4s` | `tstats` + error search |

The role that views this app needs search access to `_internal`, `_introspection`, and `_metrics` (if Edge Processor is in use), plus `list_indexer_cluster` / `list_search_head_clustering` for the cluster tiles.

## Install

### Splunk Enterprise

1. Copy this directory to `$SPLUNK_HOME/etc/apps/splunk_exec_health`.
2. Restart Splunk, or reload the app from **Manage apps**.
3. Open **Executive Health** from the app menu.

### Splunk Cloud

Package the app (no `local/` artifacts) and install through **Apps > Manage apps > Install app from file**, or request install via your Cloud operations process.

```bash
tar --exclude='.git' --exclude='local' --exclude='metadata/local.meta' \
  -czf splunk_exec_health.tgz -C /path/to/parent splunk_exec_health
```

## Enable alerts

Saved searches ship with `enableSched = 0` and **no email action**. That is intentional: this app must not send mail or call webhooks until you decide it should.

1. **Settings > Searches, reports, and alerts** (filter to this app).
2. Enable the four core alerts after you have confirmed the searches return expected rows on your stack.
3. Add an email (or Slack) action **in Splunk Web**. Configure SMTP under **Settings > Server settings > Email settings**.

Do not put SMTP passwords, Slack webhook URLs, API tokens, or HEC token **secrets** in `default/` or `local/` of this app. Notification credentials belong in Splunk’s alert-action / email configuration, not in source control.

## Tune thresholds

Override these macros in **Settings > Advanced search > Search macros** (or `local/macros.conf`):

| Macro | Default | Meaning |
| --- | --- | --- |
| `exec_health_idx` | `*` | Index glob for `tstats` |
| `exec_health_sigma` | `2` | Stdevs below host mean → ALERT |
| `exec_health_silence_sec` | `3600` | Seconds without data → DATA SILENT |
| `exec_health_heartbeat_sec` | `600` | Seconds without `_internal` → missing heartbeat |
| `exec_health_drop_red_pct` | `50` | % below 7-day MA → RED |
| `exec_health_drop_yellow_pct` | `20` | % below 7-day MA → YELLOW |
| `exec_health_hec_baseline_eps` | `100` | Rolling EPS before silence is RED |
| `exec_health_hec_silence_min` | `5` | Silent minutes to flag a HEC token |
| `exec_health_sc4s` | `sourcetype=sc4s* OR ...` | Syslog / SC4S filter |
| `exec_health_edge_mstats` | `index=_metrics sourcetype=edge-metrics` | Edge Processor metrics |

Map HEC token IDs to display names in `lookups/hec_token_map.csv`. Columns are `token,token_name,owner`. Store only the identifier that already appears in `_internal` metrics — never the HEC token secret.

## Optional: Splunk MLTK

The core app does **not** require the Machine Learning Toolkit. `predict` and `streamstats` ship with Splunk.

If MLTK is installed, you can enable:

1. `Exec Health - MLTK host density outliers (optional)` — daily `fit DensityFunction`
2. `Exec Health - MLTK apply host outliers (optional)` — 15-minute `apply`

Those searches write an ML model named `exec_health_ingestion_baseline` inside this app.

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

Edge tiles use `mstats` against `_metrics` / `sourcetype=edge-metrics` (`processor_events_in_total`, `processor_events_out_total`, queue and export-error metrics). If those panels are empty, Edge Processor is not emitting metrics to this stack; `_internal` edge / Ingest Actions logs still populate the lower tables.

**Filter efficiency** is `(events_in - events_out) / events_in`. Treat a high percentage as “pipelines are dropping or routing away from indexers,” not as a hardware fault by itself.

## Search load

- Prefer `tstats` / `mstats` over raw event scans.
- License GB/day reads `license_usage.log`, which is already summarized.
- Default auto-refresh is 5 minutes (15 minutes for the 8-day license series).
- Narrow `exec_health_idx` if `index=*` is too wide in your environment.

This app is an executive overlay. It does not replace the Monitoring Console.

## Rebuild dashboards

Dashboard Studio XML is generated from `tools/build_dashboards.py`:

```bash
python3 tools/build_dashboards.py
```
