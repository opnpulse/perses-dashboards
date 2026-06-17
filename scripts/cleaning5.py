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
    # Pin each target to the Prometheus datasource unless it already carries a typed one.
    # A datasource dict missing a "type" (e.g. {"uid": "${datasource}"}) is ambiguous and
    # makes `percli migrate` randomly emit LokiLogQuery, so set the type while keeping the uid.
    for target in panel.get("targets", []):
        ds = target.get("datasource")
        if not isinstance(ds, dict):
            target["datasource"] = dict(PROM_DATASOURCE)
        elif not ds.get("type"):
            ds["type"] = PROM_DATASOURCE["type"]
    return panel

def hoist_rows(panels):
    # Collapsed rows nest their child panels inside `row["panels"]`; clean_panel drops
    # the row, so hoist those children to the top level first to avoid losing them.
    # (Expanded rows keep their children as top-level siblings and an empty list here.)
    flat = []
    for p in panels:
        if p.get("type") == "row":
            flat.extend(p.get("panels", []))
        flat.append(p)
    return flat

def normalize_templating(data):
    # A single-select var (multi=false) with a list `current` value crashes
    # `percli migrate` ("you can not use a list of default values if allowMultiple
    # is set to false"); collapse the saved selection to its first element.
    for var in data.get("templating", {}).get("list", []):
        if var.get("multi"):
            continue
        current = var.get("current")
        if isinstance(current, dict):
            for key in ("value", "text"):
                if isinstance(current.get(key), list):
                    current[key] = current[key][0] if current[key] else ""

def process_file(filepath):
    try:
        with open(filepath) as f:
            data = json.load(f)

        normalize_templating(data)

        if "panels" in data:
            hoisted = hoist_rows(data["panels"])
            data["panels"] = [p for p in (clean_panel(p) for p in hoisted) if p]

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
