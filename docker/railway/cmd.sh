#!/bin/bash
set -euo pipefail

cd /home/frappe/frappe-bench

mkdir -p /home/frappe/frappe-bench/logs /home/frappe/logs
chown -R frappe:frappe /home/frappe/frappe-bench/logs /home/frappe/logs || true

if /home/frappe/frappe-bench/railway-setup.sh; then
	echo "-> Setup complete"
else
	echo "-> Setup reported an error; starting web processes anyway"
fi

echo "-> Starting nginx"
if ! nginx; then
	echo "-> nginx start retry"
	nginx || true
fi

echo "-> Starting supervisor"
exec /usr/bin/supervisord -c /home/frappe/supervisor.conf
