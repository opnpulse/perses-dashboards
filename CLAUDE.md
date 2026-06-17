# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Purpose

This repo converts Grafana dashboards into Perses dashboards. The core problem it solves: `percli migrate` cannot directly migrate old Grafana-8 dashboard JSON (fails with errors like `unable to decode the response body. Error name cannot be empty`). The workaround is a multi-stage pipeline that round-trips each dashboard through a live Grafana-12 instance (import → re-export → normalize) so it becomes migratable, then runs `percli migrate` and applies the result to a running Perses server.

The Python scripts in `scripts/` operate on the sibling repo `~/go/src/go.opscenter.dev/grafana-dashboards`, not on this repo's own JSON files. The JSON folders here (`basics/`, `grafana12/`, `migrated/`, `test/`) are hand-curated examples / fixtures from working through the process manually.

## Infrastructure setup

The pipeline depends on three local services. Started with docker.

- Perses server: `http://localhost:8090` (`percli login http://localhost:8090`)
- Grafana: `http://localhost:3002` (admin/admin) — used as the round-trip converter
- Prometheus: `http://localhost:9092`
- Perses reaches Prometheus at `http://prometheus:9090/` via a Proxy datasource. `config.yaml` enables anonymous auth.


## The migration pipeline

`scripts/run.bash` is the entry point. With no args it iterates over the default `FOLDERS` list (database/tool names); pass folder names as args (e.g. `./run.bash postgres`) to process only those. Folders live under `$GRAFANA_DIR/<folder>` (env var, defaults to `~/go/src/opnpulse/grafana-dashboards`); the scripts dir is auto-derived from the script location. For each folder it runs the numbered Python scripts in order, then `percli apply`s every resulting `*-migrated.json`. The default `FOLDERS` list also documents which dashboards work vs. which still have issues (e.g. `connectcluster`, `ignite`, `mssqlserver` are commented out).

The numbered scripts form a strict chain — each consumes the file-suffix the previous one produced. Run them from inside a dashboard folder, in order:

| Step | Script | Action | Suffix in → out |
|------|--------|--------|-----------------|
| 0 | `wipeout0.py` | Delete leftover intermediates from prior runs | removes `-hi/-grafana12/-migrated/-ready.json` |
| 1 | `modify1.py` | Wrap raw dashboard in `{dashboard, overwrite, folderId}` for Grafana import API | `.json` → `-hi.json` |
| 2 | `curl2.py` | POST to Grafana `/api/dashboards/import`, then GET it back | `-hi.json` → `-grafana12.json` |
| 3 | `revert_modify3.py` | Unwrap the `dashboard` key from the re-exported file | `-grafana12.json` → `-ready.json` |
| 4 | `filecleanup4.py` | Delete `-hi/-grafana12/-migrated.json` intermediates | — |
| 5 | `cleaning5.py` | Strip unsupported keys (`pluginVersion`, `iteration`, `links`, `transformations`), drop `row` panels, remove `fieldConfig.defaults.mappings`, pin each target to the Prometheus datasource (`{type:"prometheus", uid:"global-ds-proxy"}`) unless it already has a typed one | edits `-ready.json` in place |
| 6 | `migrate6.py` | `percli migrate --project pp --online -o json` | `-ready.json` → `-migrated.json` |
| 6b | `fixups67.py` | One pass over `-migrated.json`: delete remaining `mappings` arrays, rewrite `color: "text"` → `color: "#c4162a"`, delete `width: null` keys, drop query entries with an empty `query` string | edits `-migrated.json` |

The post-migration fixups (steps 5, 6b) encode Perses-specific quirks discovered manually: Perses rejects `mappings` arrays, `width: null`, and empty query strings, and `color: "text"` renders wrong.

The target-datasource pinning in step 5 fixes a `percli migrate` non-determinism: when a target has no resolvable datasource type (the Grafana round-trip leaves `datasource: null`), migrate randomly maps PromQL targets to `LokiLogQuery` instead of `PrometheusTimeSeriesQuery` via Go-map iteration order — those Loki-typed queries never execute against Prometheus. The hardcoded `global-ds-proxy` is the Prometheus datasource name on the Perses server; keep it in sync with the environment alongside the URLs/ports in `curl2.py`/`migrate6.py`.

## Key constraints when modifying scripts

- The Python scripts operate on the current working directory (`root_dir = '.'`); `run.bash` `cd`s into each `$GRAFANA_DIR/<folder>` before invoking them. `run.bash` derives `SCRIPTS_DIR` from its own location and reads `GRAFANA_DIR` from the env (defaults to `$HOME/go/src/opnpulse/grafana-dashboards`). The Grafana/Perses URLs and ports are hardcoded in the scripts (`curl2.py`, `migrate6.py`). Keep these in sync if the environment changes.
- The pipeline is suffix-driven: changing an output suffix in one script breaks the next. Treat the suffix contract as the interface between steps.
- `migrate6.py` exits non-zero on `percli migrate` failure, which causes `run.bash` to skip `percli apply` for that folder and continue.

## Manual single-dashboard flow

For one-off debugging without the batch script:
```
percli migrate -f <grafana12-exported>.json --project pp --online -o json > out.json
percli apply -f out.json
```
A Grafana-8 JSON that fails migration must first be imported into the Grafana-12 UI and re-exported (this is exactly what steps 1–3 automate). `migrate-err.txt` captures a representative failure log.
