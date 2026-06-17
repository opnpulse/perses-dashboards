# Plan: Convert grafana-dashboards (single DB) → Perses

## Goal
Run the `scripts/` pipeline against one DB folder under `$GRAFANA_DIR/<db>`
and `percli apply` the result.

## Run
```
cd ~/go/src/opnpulse/perses-dashboards/scripts
./run.bash <db>        # e.g. postgres
```

## Preconditions (verify up first)
- Grafana :3002, Perses :8090, Prometheus :9092 — all should return 200.
- **`percli login http://localhost:8090` before running.** `whoami` reports
  "not connected" even after a successful login (anonymous auth in
  `config.yaml`) — that's expected and harmless; migrate/apply work via
  `--online`. But if you never login, `migrate6.py` fails opaquely.
- The Prometheus datasource on the Perses server is named `global-ds-proxy`
  (`percli get datasource -p pp`). `cleaning5.py` hardcodes this name — if a
  different env uses another name, update `PROM_DATASOURCE` there.

## Gotchas learned (postgres run)
- **`run.bash` has `set -euo pipefail`**: the FIRST `percli apply` failure
  aborts the whole script, so later dashboards in the same folder never apply.
  A green "Successful: 1" only means no step errored — still spot-check.
- **Empty queries**: `percli migrate` can emit query entries with `query: ""`
  (from empty Grafana targets, refId B etc). Perses rejects them
  (`strings.MinRunes(1)`). `fixups67.py` now drops these automatically.
- **Loki vs Prometheus query type**: targets come out of the Grafana round-trip
  with `datasource: null`, so `percli migrate` randomly maps PromQL to
  `LokiLogQuery` (non-deterministic, Go-map order). `cleaning5.py` now pins each
  target to the Prometheus datasource so all queries become
  `PrometheusTimeSeriesQuery`. If a new DB still shows Loki queries, check the
  target actually picked up the injected datasource (i.e. it wasn't already a
  dict with a non-prometheus type).

## Verification
For each dashboard in the folder:
```
cd $GRAFANA_DIR/<db>
for f in *-perses.json; do echo -n "$f: "; \
  jq -rc '[.spec.panels[].spec.queries[]?.spec.plugin.kind] | group_by(.) | map("\(.[0]):\(length)")' "$f"; done
```
Expect only `PrometheusTimeSeriesQuery`. Confirm `percli apply` succeeded for
every `*-perses.json` (re-run individually if `run.bash` aborted early).

## Overhead note
Never read full dashboard JSON into context — the Python scripts do all
transforms on disk. Debug a failed step with slices only: `jq`/`grep`, or
`percli migrate -f X-ready.json … 2>&1 | head`. To debug query-type randomness,
re-run `percli migrate` a few times on the same `-ready.json` and diff the
plugin-kind counts.
