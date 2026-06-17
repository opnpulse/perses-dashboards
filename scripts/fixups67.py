import os
import json

# Single post-migration pass over every *-migrated.json:
#   - drop unsupported `mappings` arrays (Perses rejects them)
#   - rewrite color "text" -> "#c4162a" (renders wrong otherwise)
#   - drop `width: null` keys
# Replaces the former mappings6.py + widthnull7.py (one read/write per file).

root_dir = '.'  # change as needed

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
        if file.endswith('-migrated.json'):
            process_file(os.path.join(subdir, file))

print("Fixups complete.")
