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

# Panels whose value mappings must survive (numeric metric -> role/state text).
PROTECTED_MAPPING_TITLES = {"Role", "ReplSet State"}

# Grafana's auto-interval template var migrates to the literal "$__auto_interval_<name>",
# which Perses rejects as a duration string. Drop it / replace it with a real duration.
AUTO_INTERVAL_PREFIX = "$__auto_interval"

# percli copies the source Grafana `uid` verbatim into `metadata.name`, and
# `.status.dashboard.id` surfaces that name. Duplicate/opaque source uids therefore
# make distinct dashboards collide on the same Perses dashboard (last writer wins).
# Derive a deterministic, self-documenting name from the display name instead - this
# matches how the installer chart derives the PersesDashboard CR name.
def deterministic_name(display, filepath):
    parts = [p for p in display.lower().replace(' ', '').split('/') if p]
    name = '-'.join(parts)[:63].rstrip('-')
    # legacy/* dashboards share a display name with their current counterpart.
    if 'legacy' in filepath.lower() and not name.endswith('-legacy'):
        name = (name[:56].rstrip('-')) + '-legacy'
    return name

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

    def is_protected_panel(obj):
        return (isinstance(obj, dict) and obj.get('kind') == 'Panel'
                and obj.get('spec', {}).get('display', {}).get('name') in PROTECTED_MAPPING_TITLES)

    def is_auto_interval(v):
        return isinstance(v, str) and v.startswith(AUTO_INTERVAL_PREFIX)

    def modify(obj, protected=False):
        if isinstance(obj, dict):
            # Keep mappings inside a protected panel subtree (role/state text); strip elsewhere.
            protected = protected or is_protected_panel(obj)
            if isinstance(obj.get('mappings'), list) and not protected:
                del obj['mappings']
                changed[0] = True
            # Sanitize Grafana auto-interval leftovers that Perses can't parse as durations.
            if is_auto_interval(obj.get('defaultValue')):
                obj['defaultValue'] = '1m'
                changed[0] = True
            if is_auto_interval(obj.get('minStep')):
                obj['minStep'] = ''
                changed[0] = True
            if isinstance(obj.get('values'), list):
                kept = [v for v in obj['values']
                        if not is_auto_interval(v)
                        and not (isinstance(v, dict) and is_auto_interval(v.get('value')))]
                if len(kept) != len(obj['values']):
                    obj['values'] = kept
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
                modify(v, protected)
        elif isinstance(obj, list):
            for item in obj:
                modify(item, protected)

    modify(data)

    display = data.get('spec', {}).get('display', {}).get('name')
    if display:
        want = deterministic_name(display, filepath)
        if data.get('metadata', {}).get('name') != want:
            data.setdefault('metadata', {})['name'] = want
            changed[0] = True

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
