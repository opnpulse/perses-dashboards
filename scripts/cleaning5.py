import os
import json

# Root directory to start traversal
root_dir = '.'   # change if needed

# Prometheus datasource on the Perses server; injected onto targets so
# `percli migrate` deterministically picks PrometheusTimeSeriesQuery. Without
# an explicit type, migrate randomly maps PromQL targets to LokiLogQuery
# (Go-map iteration order), which never executes against Prometheus.
PROM_DATASOURCE = {"type": "prometheus", "uid": "global-ds-proxy"}

def clean_panel(panel):
    # Remove unsupported keys
    for key in ["pluginVersion", "iteration", "links", "transformations"]:
        panel.pop(key, None)
    # Remove row panels
    if panel.get("type") == "row":
        return None
    # Clean fieldConfig mappings
    if "fieldConfig" in panel and "defaults" in panel["fieldConfig"]:
        panel["fieldConfig"]["defaults"].pop("mappings", None)
    # Pin each target to the Prometheus datasource unless it already carries a typed one
    for target in panel.get("targets", []):
        if not isinstance(target.get("datasource"), dict):
            target["datasource"] = dict(PROM_DATASOURCE)
    return panel

def process_file(filepath):
    try:
        with open(filepath) as f:
            data = json.load(f)

        if "panels" in data:
            data["panels"] = [p for p in (clean_panel(p) for p in data["panels"]) if p]

        # Construct output filename (optional: overwrite or save separately)
#         new_filename = filepath.replace('-ready.json', '-cleaned.json')
        new_filename = filepath

        with open(new_filename, "w") as f:
            json.dump(data, f, indent=2)

        print(f"Cleaned {filepath} → {new_filename}")

    except Exception as e:
        print(f"Error cleaning {filepath}: {e}")

# Traverse directories and process JSON files
for subdir, _, files in os.walk(root_dir):
    for file in files:
        if file.endswith('-ready.json'):
            filepath = os.path.join(subdir, file)
            process_file(filepath)

print("Cleaning complete.")
