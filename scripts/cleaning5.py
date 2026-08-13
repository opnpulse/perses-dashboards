import os
import json
import re

from statlabels import (PROTECTED_MAPPING_TITLES, VALUE_IS_LABEL,
                        VALUE_MAPPED_TITLES, bare_label)

# Root directory to start traversal
root_dir = '.'   # change if needed

# Prometheus datasource on the Perses server; injected onto targets so
# `percli migrate` deterministically picks PrometheusTimeSeriesQuery. Without
# an explicit type, migrate randomly maps PromQL targets to LokiLogQuery
# (Go-map iteration order), which never executes against Prometheus.
PROM_DATASOURCE = {"type": "prometheus", "uid": "global-ds-proxy"}

def is_label_stat(panel):
    # Whether this stat panel will display a label instead of its metric value.
    if panel.get("type") != "stat":
        return False
    targets = panel.get("targets", [])
    if len(targets) != 1:
        return False
    label = bare_label(targets[0].get("legendFormat"))
    if not label:
        return False
    return label in VALUE_IS_LABEL or panel.get("options", {}).get("textMode") == "name"

MODERN_MAPPING_TYPES = {"value", "range", "regex", "special"}

def normalize_mappings(defaults):
    # Grafana's pre-v8 mapping format (`"type": 1` with flat value/text, `"type": 2` with
    # from/to) makes `percli migrate` fail outright: "error in call to list.FlattenN".
    # Rewrite those entries into the modern options-based shape it understands.
    mappings = defaults.get("mappings")
    if not isinstance(mappings, list):
        return
    out = []
    for index, mapping in enumerate(mappings):
        if not isinstance(mapping, dict):
            continue
        kind = mapping.get("type")
        if kind in MODERN_MAPPING_TYPES:
            out.append(mapping)
        elif isinstance(mapping.get("options"), dict):
            # Modern options dict left carrying a legacy numeric type.
            out.append({"type": "value", "options": mapping["options"]})
        elif kind == 1 or (kind is None and "value" in mapping):
            # Grafana leaves behind blank placeholder rows; they map nothing.
            if mapping.get("value") and mapping.get("text"):
                out.append({"type": "value", "options": {
                    str(mapping["value"]): {"text": mapping["text"], "index": index},
                }})
        elif kind == 2:
            if mapping.get("from") and mapping.get("to"):
                out.append({"type": "range", "options": {
                    "from": mapping["from"],
                    "to": mapping["to"],
                    "result": {"text": mapping.get("text"), "index": index},
                }})
        # Anything else is unrecognised; dropping it beats failing the migration.
    defaults["mappings"] = out

def keeps_mappings(panel):
    title = panel.get("title")
    if title in PROTECTED_MAPPING_TITLES:
        return True
    return title in VALUE_MAPPED_TITLES and not is_label_stat(panel)

def clean_panel(panel):
    # Remove unsupported keys
    for key in ["pluginVersion", "iteration", "links", "transformations"]:
        panel.pop(key, None)
    # Remove row panels
    if panel.get("type") == "row":
        return None
    # Clean fieldConfig mappings, except on panels whose value mappings must survive
    # migration (they are the panel's whole purpose). See PROTECTED_MAPPING_TITLES.
    if "fieldConfig" in panel and "defaults" in panel["fieldConfig"]:
        if keeps_mappings(panel):
            normalize_mappings(panel["fieldConfig"]["defaults"])
        else:
            panel["fieldConfig"]["defaults"].pop("mappings", None)
    # Pin every target to the Prometheus datasource. A missing "type" makes `percli
    # migrate` randomly emit LokiLogQuery, and a variable uid (e.g. {"uid": "$datasource"})
    # is copied verbatim into the Perses query, where datasource refs are resolved by name
    # against the datasource registry rather than interpolated - so the dashboard fails
    # with "No datasource found for kind 'PrometheusDatasource' and name '$datasource'".
    for target in panel.get("targets", []):
        target["datasource"] = dict(PROM_DATASOURCE)
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

def normalize_tags(data):
    # Perses rejects any tag outside [a-z0-9 _-] ("contains invalid characters"),
    # so Grafana tags like "MongoDB", "JMX exporter" or "milvus2.0" fail migration.
    tags = data.get("tags")
    if not isinstance(tags, list):
        return
    out = []
    for tag in tags:
        if not isinstance(tag, str):
            continue
        clean = re.sub(r"[^a-z0-9 _-]", "-", tag.lower()).strip(" -")
        if clean and clean not in out:
            out.append(clean)
    data["tags"] = out

def process_file(filepath):
    try:
        with open(filepath) as f:
            data = json.load(f)

        normalize_tags(data)
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
