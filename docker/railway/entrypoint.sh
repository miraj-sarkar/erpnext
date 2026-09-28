#!/bin/bash
set -euo pipefail

mkdir -p /home/frappe/frappe-bench/logs /home/frappe/logs /home/frappe/frappe-bench/sites
chown -R frappe:frappe /home/frappe/frappe-bench/logs /home/frappe/logs || true

echo "-> Preparing sites volume"
/usr/local/bin/railway-prepare-sites.sh || echo "-> prepare-sites warning"

exec "$@"
