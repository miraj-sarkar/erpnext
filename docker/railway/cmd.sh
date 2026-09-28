#!/bin/bash
set -euo pipefail

cd /home/frappe/frappe-bench

/home/frappe/frappe-bench/railway-setup.sh

echo "-> Starting nginx"
nginx

echo "-> Starting supervisor"
exec /usr/bin/supervisord -c /home/frappe/supervisor.conf
