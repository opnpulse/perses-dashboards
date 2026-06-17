import os
import json

# Single post-migration pass over every *-perses.json:
#   - drop unsupported `mappings` arrays (Perses rejects them)
#   - rewrite color "text" -> "#c4162a" (renders wrong otherwise)
#   - drop `width: null` keys
#   - drop query entries with an empty query string (Perses rejects them)
# Replaces the former mappings6.py + widthnull7.py (one read/write per file).

root_dir = '.'  # change as needed

def is_empty_query(q):
    # A migrated query whose plugin spec carries an empty `query` string.
    spec = q.get('spec', {}).get('plugin', {}).get('spec', {}) if isinstance(q, dict) else {}
    return 'query' in spec and spec['query'] == ''

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
