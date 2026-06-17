#!/bin/bash

set -euo pipefail  # Exit on error, unset variables, and pipe failures

# Resolve dirs: scripts live next to this file; grafana repo is env-overridable.
SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GRAFANA_DIR="${GRAFANA_DIR:-$HOME/go/src/opnpulse/grafana-dashboards}"

DEFAULT_FOLDERS=(
# working
    cassandra
    druid
    elasticsearch
    ferretdb
    hazelcast
    kafka
    mariadb
    memcached
    mongodb
    mysql
    pgbouncer
    pgpool
    postgres
    proxysql
    rabbitmq
    redis
    singlestore
    solr
    zookeeper
    falco
    kubestash
    kubevault
    policy
    scanner
    stash

# Still issue
#    connectcluster
#    ignite
#    mssqlserver

)

# Folders to process: CLI args win, else the default list above.
if (($# > 0)); then
    FOLDERS=("$@")
else
    FOLDERS=("${DEFAULT_FOLDERS[@]}")
fi

# Colors for nice output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}Starting migration sequence on all top-level folders...${NC}\n"

# Counter for summary
success_count=0
fail_count=0
total_folders=0

for folder in "${FOLDERS[@]}"; do
    total_folders=$((total_folders + 1))

    echo -e "${YELLOW}════════════════════════════════════════════════${NC}"
    echo -e "${YELLOW}Processing folder: $folder${NC}"
    echo -e "${YELLOW}════════════════════════════════════════════════${NC}"

    fldr="$GRAFANA_DIR/$folder"
    echo "$fldr"
    if cd "$fldr" 2>/dev/null; then
        (
            set -e

            echo "0. Running wipeout0.py"
            python3 "$SCRIPTS_DIR/wipeout0.py"

            echo "1. Running modify1.py"
            python3 "$SCRIPTS_DIR/modify1.py"

            echo "2. Running curl2.py"
            python3 "$SCRIPTS_DIR/curl2.py"

            echo "3. Running revert_modify3.py"
            python3 "$SCRIPTS_DIR/revert_modify3.py"

            echo "4. Running filecleanup4.py"
            python3 "$SCRIPTS_DIR/filecleanup4.py"

            echo "5. Running cleaning5.py"
            python3 "$SCRIPTS_DIR/cleaning5.py"

            echo "6. Running migrate6.py"
            if python3 "$SCRIPTS_DIR/migrate6.py"; then
                echo "Migration succeeded"
            else
                echo "Migration failed"
                exit 1
            fi

            echo "6b. Running fixups67.py"
            python3 "$SCRIPTS_DIR/fixups67.py"

            echo -e "\n${GREEN}✓ All Python scripts completed successfully in $folder${NC}\n"
        ) && subshell_ok=1 || subshell_ok=0

        # Capture via && / || so `set -e` doesn't abort the whole run when one folder fails.
        if [[ $subshell_ok -eq 1 ]]; then
            success_count=$((success_count + 1))
        else
            echo -e "${RED}✗ One or more Python scripts failed in $folder${NC}"
            fail_count=$((fail_count + 1))
            cd ..  # Go back even if failed
            continue
        fi

        # Look for any *-perses.json files in this folder and apply with percli
        shopt -s nullglob
        json_files=( *-perses.json )
        if ((${#json_files[@]})); then
            echo "Found ${#json_files[@]} migrated JSON files in $folder"
            for jf in "${json_files[@]}"; do
                echo "Applying percli to: $jf"
                # Don't let one failed apply abort the batch (set -e); report and continue.
                percli apply -f "$jf" || echo -e "${RED}✗ percli apply failed for $jf${NC}"
            done
            echo -e "${GREEN}✓ percli apply done for all migrated files in $folder${NC}\n"
        else
            echo -e "${YELLOW}⚠ No *-perses.json file found in $folder, skipping percli apply${NC}\n"
        fi
        shopt -u nullglob

        cd ..
    else
        echo -e "${RED}Could not enter directory: $folder${NC}"
        fail_count=$((fail_count + 1))
    fi
done

# Final summary
echo -e "${YELLOW}════════════════════════════════════════════════${NC}"
echo -e "${YELLOW}Migration sequence completed!${NC}"
echo -e "${YELLOW}Total folders processed: $total_folders${NC}"
echo -e "${GREEN}Successful: $success_count${NC}"
if [[ $fail_count -gt 0 ]]; then
    echo -e "${RED}Failed: $fail_count${NC}"
else
    echo -e "${GREEN}Failed: 0${NC}"
fi
echo -e "${YELLOW}════════════════════════════════════════════════${NC}"
