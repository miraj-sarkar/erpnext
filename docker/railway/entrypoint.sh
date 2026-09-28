#!/bin/bash
set -euo pipefail

SITES="/home/frappe/frappe-bench/sites"
BAKED_ASSETS="/home/frappe/frappe-bench/assets"
BAKED_APPS_TXT="/home/frappe/frappe-bench/built_sites/apps.txt"
BAKED_APPS_JSON="/home/frappe/frappe-bench/built_sites/apps.json"

echo "-> Preparing sites volume"
mkdir -p "$SITES"
chown -R frappe:frappe "$SITES" || true

if [ -d "$BAKED_ASSETS" ]; then
	rm -rf "$SITES/assets"
	ln -sfn "$BAKED_ASSETS" "$SITES/assets"
fi

if [ -f "$BAKED_APPS_TXT" ]; then
	ln -sfn "$BAKED_APPS_TXT" "$SITES/apps.txt"
fi
if [ -f "$BAKED_APPS_JSON" ]; then
	ln -sfn "$BAKED_APPS_JSON" "$SITES/apps.json"
fi

exec "$@"
