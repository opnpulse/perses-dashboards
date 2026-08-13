import os
import json

from statlabels import (PROTECTED_MAPPING_TITLES, VALUE_IS_LABEL,
                        VALUE_MAPPED_TITLES, bare_label)

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
#   - promote label-valued stat panels (see statlabels.py)
#   - expand merged table `pod` columns into pod #1..#N
#   - restore empty mapping display values, override Role mapping colors
# Replaces the former mappings6.py + widthnull7.py (one read/write per file).

root_dir = '.'  # change as needed

VALID_ALIGN = {"left", "center", "right"}

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

# Grafana's palette maps these to washed-out blues; #104 picked readable colors by hand.
MAPPING_COLORS = {
    ('Role', 'master'): '#5794f2',
    ('Role', 'slave'): '#8ab8ff',
    ('Role', 'Primary'): '#ffffff',
    ('Role', 'Standby'): '#ffffff',
}

def stat_label(panel_spec):
    # The label a stat panel should display instead of its (meaningless) metric value.
    plugin = panel_spec.get('plugin', {})
    if plugin.get('kind') != 'StatChart':
        return None
    queries = panel_spec.get('queries', [])
    if len(queries) != 1:
        return None
    snf = queries[0].get('spec', {}).get('plugin', {}).get('spec', {}).get('seriesNameFormat')
    label = bare_label(snf)
    if not label:
        return None
    existing = plugin.get('spec', {}).get('metricLabel')
    if isinstance(existing, str) and existing.strip():
        return label
    return label if label in VALUE_IS_LABEL else None

def promote_stat_label(panel_spec, label, changed):
    spec = panel_spec['plugin']['spec']
    query_spec = panel_spec['queries'][0]['spec']['plugin']['spec']
    if query_spec.get('seriesNameFormat') != '{{%s}}' % label:
        query_spec['seriesNameFormat'] = '{{%s}}' % label
        changed[0] = True
    if spec.get('metricLabel') != label:
        spec['metricLabel'] = label
        changed[0] = True
    # A sparkline behind a text value renders as a stray graph.
    if 'sparkline' in spec:
        del spec['sparkline']
        changed[0] = True
    # Averaging a label series yields NaN; take the last sample.
    if spec.get('calculation') == 'mean':
        spec['calculation'] = 'last-number'
        changed[0] = True

def expand_pod_columns(panel_spec, changed):
    # A table merging N instant queries gets one `pod` column per query (pod #1..#N).
    # The migration collapses them into a single `pod`, which then matches no column.
    plugin = panel_spec.get('plugin', {})
    if plugin.get('kind') != 'Table':
        return
    settings = plugin.get('spec', {}).get('columnSettings')
    if not isinstance(settings, list):
        return
    idx = next((i for i, c in enumerate(settings)
                if isinstance(c, dict) and c.get('name') == 'pod'), None)
    if idx is None:
        return
    n = len(panel_spec.get('queries', []))
    if n < 2:
        return
    first = {k: v for k, v in settings[idx].items() if k != 'format'}
    first['name'] = 'pod #1'
    first['align'] = 'left'
    settings[idx:idx + 1] = [first] + [{'name': 'pod #%d' % i, 'hide': True}
                                       for i in range(2, n + 1)]
    changed[0] = True

def fix_mappings(panel_spec, changed):
    title = panel_spec.get('display', {}).get('name')
    for mapping in panel_spec.get('plugin', {}).get('spec', {}).get('mappings') or []:
        if not isinstance(mapping, dict):
            continue
        spec = mapping.get('spec', {})
        result = spec.get('result', {})
        # Grafana omits `text` when the mapped value doubles as its own label
        # ("WipeOut" -> "WipeOut"); percli turns that into an empty display value.
        if result.get('value') == '' and spec.get('value'):
            result['value'] = spec['value']
            changed[0] = True
        color = MAPPING_COLORS.get((title, result.get('value')))
        if color and result.get('color') != color:
            result['color'] = color
            changed[0] = True

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

    # Label-valued stat panels keep their mappings (the mapped text *is* the display).
    label_panels = set()
    for panel in data.get('spec', {}).get('panels', {}).values():
        if not isinstance(panel, dict) or 'spec' not in panel:
            continue
        panel_spec = panel['spec']
        label = stat_label(panel_spec)
        if label:
            label_panels.add(id(panel))
            promote_stat_label(panel_spec, label, changed)
        expand_pod_columns(panel_spec, changed)
        fix_mappings(panel_spec, changed)

    def is_protected_panel(obj):
        return (isinstance(obj, dict) and obj.get('kind') == 'Panel'
                and (id(obj) in label_panels
                     or obj.get('spec', {}).get('display', {}).get('name')
                     in PROTECTED_MAPPING_TITLES | VALUE_MAPPED_TITLES))

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
