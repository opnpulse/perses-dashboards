# Plan: Convert grafana-dashboards (single DB, e.g. postgres) → Perses

## Goal
Run the `scripts/` pipeline against one DB folder (postgres) under
`$GRAFANA_DIR/<db>` and `percli apply` the result.

## Run (postgres)
```
cd ~/go/src/opnpulse/perses-dashboards/scripts
./run.bash postgres
```
Preconditions (verify up first): Grafana :3002, Perses :8090, Prometheus :9092.
- `percli whoami` — must show a logged-in session (else `migrate6.py` fails opaquely).
- `curl2.py` hard-fails at step 2 if Grafana :3002 is unreachable.

## Verification
Confirm `*-migrated.json` produced for all 3 postgres dashboards
(databases/pods/summary) and `percli apply` succeeds for each.

## Overhead note
Never read full dashboard JSON into context — the Python scripts do all transforms
on disk. Debug a failed step with slices only: `jq`/`grep`, or
`percli migrate -f X-ready.json … 2>&1 | head`.
