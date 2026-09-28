#!/bin/bash
# Restore files the Railway volume hides when it mounts over /sites.
set -euo pipefail

SITES="/home/frappe/frappe-bench/sites"
BAKED_ASSETS="/home/frappe/frappe-bench/assets"
BAKED_APPS_TXT="/home/frappe/frappe-bench/built_sites/apps.txt"
BAKED_APPS_JSON="/home/frappe/frappe-bench/built_sites/apps.json"

mkdir -p "$SITES"

echo "-> Waiting for sites volume"
for _ in $(seq 1 30); do
	if touch "$SITES/.volume-ready" 2>/dev/null; then
		chown frappe:frappe "$SITES/.volume-ready" 2>/dev/null || true
		break
	fi
	sleep 1
done

if [ -d "$BAKED_ASSETS" ]; then
	rm -rf "$SITES/assets"
	ln -sfn "$BAKED_ASSETS" "$SITES/assets"
fi

if [ ! -s "$SITES/apps.txt" ]; then
	if [ -f "$BAKED_APPS_TXT" ]; then
		cp -f "$BAKED_APPS_TXT" "$SITES/apps.txt"
	else
		printf 'frappe\nerpnext\n' > "$SITES/apps.txt"
	fi
fi

if [ ! -s "$SITES/apps.json" ] && [ -f "$BAKED_APPS_JSON" ]; then
	cp -f "$BAKED_APPS_JSON" "$SITES/apps.json"
fi

if [ ! -s "$SITES/common_site_config.json" ]; then
	echo '{}' > "$SITES/common_site_config.json"
fi

chown frappe:frappe "$SITES/apps.txt" "$SITES/common_site_config.json" 2>/dev/null || true
[ -f "$SITES/apps.json" ] && chown frappe:frappe "$SITES/apps.json" || true
chown -R frappe:frappe "$SITES" || true
