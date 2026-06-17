import os
import json

# Single post-migration pass over every *-perses.json:
#   - drop unsupported `mappings` arrays (Perses rejects them)
#   - rewrite color "text" -> "#c4162a" (renders wrong otherwise)
#   - drop `width: null` keys
#   - drop query entries with an empty query string (Perses rejects them)
#   - fix bare-number `minStep` (e.g. "2") -> duration string ("2s")
#   - drop threshold steps whose `value` is non-numeric (e.g. "SECONDARY")
#   - drop table `columnSettings` entries with an empty `name`, strip
#     `align` values outside left|center|right (Perses Table schema rejects "" / null),
#     and strip `dataLink` (Grafana-only; Perses Table schema rejects it)
# Replaces the former mappings6.py + widthnull7.py (one read/write per file).

root_dir = '.'  # change as needed

VALID_ALIGN = {"left", "center", "right"}

def is_empty_query(q):
    # A migrated query whose plugin spec carries an empty `query` string.
    spec = q.get('spec', {}).get('plugin', {}).get('spec', {}) if isinstance(q, dict) else {}
    return 'query' in spec and spec['query'] == ''

def numeric_value(v):
    # Return v as int/float if it already is one or is a numeric string; else None.
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return v
    if isinstance(v, str):
        try:
            return int(v) if v.lstrip('-').isdigit() else float(v)
        except ValueError:
            return None
    return None

def process_file(filepath):
    with open(filepath, 'r') as f:
        data = json.load(f)

    changed = [False]

    def modify(obj):
        if isinstance(obj, dict):
            if isinstance(obj.get('mappings'), list):
                del obj['mappings']
                changed[0] = True
            if obj.get('width') is None and 'width' in obj:
                del obj['width']
                changed[0] = True
            if isinstance(obj.get('queries'), list):
                kept = [q for q in obj['queries'] if not is_empty_query(q)]
                if len(kept) != len(obj['queries']):
                    obj['queries'] = kept
                    changed[0] = True
            # Bare-number minStep (e.g. "2") -> duration string ("2s").
            ms = obj.get('minStep')
            if isinstance(ms, str) and ms.isdigit():
                obj['minStep'] = ms + 's'
                changed[0] = True
            # Drop threshold steps with a non-numeric value (e.g. "SECONDARY").
            if isinstance(obj.get('steps'), list):
                kept = [s for s in obj['steps']
                        if not isinstance(s, dict) or numeric_value(s.get('value')) is not None]
                if len(kept) != len(obj['steps']):
                    obj['steps'] = kept
                    changed[0] = True
            # Table columnSettings: drop entries with empty name, strip bad align.
            if isinstance(obj.get('columnSettings'), list):
                kept = []
                for cs in obj['columnSettings']:
                    if isinstance(cs, dict):
                        if not cs.get('name'):
                            changed[0] = True
                            continue
                        if 'align' in cs and cs['align'] not in VALID_ALIGN:
                            del cs['align']
                            changed[0] = True
                        if 'dataLink' in cs:  # Perses Table schema has no dataLink (Grafana leftover)
                            del cs['dataLink']
                            changed[0] = True
                    kept.append(cs)
                obj['columnSettings'] = kept
            for k, v in list(obj.items()):
                if k == 'color' and v == 'text':
                    obj[k] = '#c4162a'
                    changed[0] = True
                modify(v)
        elif isinstance(obj, list):
            for item in obj:
                modify(item)

    modify(data)

    if changed[0]:
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
        print(f"Modified {filepath}")
    else:
        print(f"No changes needed for {filepath}")

for subdir, _, files in os.walk(root_dir):
    for file in files:
        if file.endswith('-perses.json'):
            process_file(os.path.join(subdir, file))

print("Fixups complete.")
