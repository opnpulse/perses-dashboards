import re

# Some stat panels display a *label* of an info-style metric, not the metric value.
# Grafana renders those via `textMode: name` (which migrates to a Perses metricLabel) or
# via `reduceOptions.fields: /^X$/` / plain `textMode: value` (which migrates to nothing,
# so Perses shows the raw number - the bug fixed by hand in #112).
#
# A single-query stat panel whose legendFormat/seriesNameFormat is a bare "{{label}}" is
# treated as label-valued when either the panel already carries a metricLabel (the
# textMode: name case) or the label is listed here. `{{pod}}` is why this cannot be a
# blanket rule: 68 stat panels use it as an ordinary series name and must keep showing
# their numeric value.
VALUE_IS_LABEL = {
    'backend',
    'clientTLS',
    'deletionPolicy',
    'kafkaRef',
    'master_host',
    'member_host',
    'mode',
    'phase',
    'redis_mode',
    'requireSSL',
    'role',
    'ssl',
    'sslMode',
    'storageType',
    'terminationPolicy',
    'useAddressType',
    'version',
    'wsrep_cluster_name',
}

BARE_LABEL = re.compile(r'^\s*\{\{\s*([A-Za-z_]\w*)\s*\}\}\s*$')

# Panels whose value mappings encode their whole meaning (numeric metric -> role/state
# text) and must survive migration. Everything else gets its mappings stripped.
PROTECTED_MAPPING_TITLES = {"Role", "ReplSet State", "Deletion Policy", "Termination Policy"}

# Same, but only when the panel still renders its metric value: these titles cover both
# label-valued panels (mappings are dead weight there - the label text is the display)
# and plain numeric ones that mean nothing without their mappings ("1" vs "Running").
VALUE_MAPPED_TITLES = {"Require Secure Transport", "Status"}

def bare_label(fmt):
    # The single label a series name template consists of, if that is all it is.
    m = BARE_LABEL.fullmatch(fmt) if isinstance(fmt, str) else None
    return m.group(1) if m else None
