#!/bin/bash
set -euo pipefail

require_var() {
	if [ -z "${!1:-}" ]; then
		echo "ERROR: $1 is not set" >&2
		exit 1
	fi
}

require_var FRAPPE_DB_HOST
require_var FRAPPE_DB_PASSWORD
require_var RFP_SITE_ADMIN_PASSWORD
require_var FRAPPE_REDIS_CACHE
require_var FRAPPE_REDIS_QUEUE

SITE_NAME="${SITE_NAME:-frontend}"
DB_PORT="${FRAPPE_DB_PORT:-3306}"
SITES_DIR="/home/frappe/frappe-bench/sites"
BENCH_BIN="${BENCH_BIN:-/usr/local/bin/bench}"

run_bench() {
	su frappe -s /bin/bash -c "cd /home/frappe/frappe-bench && ${BENCH_BIN} $*"
}

mkdir -p /home/frappe/frappe-bench/logs /home/frappe/logs "${SITES_DIR}"
chown -R frappe:frappe /home/frappe/frappe-bench/logs /home/frappe/logs || true

cd /home/frappe/frappe-bench

/usr/local/bin/railway-prepare-sites.sh

echo "-> Waiting for MariaDB at ${FRAPPE_DB_HOST}:${DB_PORT}"
for _ in $(seq 1 90); do
	if mysqladmin ping -h "$FRAPPE_DB_HOST" -P "$DB_PORT" -uroot -p"$FRAPPE_DB_PASSWORD" --silent 2>/dev/null; then
		echo "-> MariaDB is up"
		break
	fi
	sleep 2
done

echo "-> Writing common site config"
run_bench set-config -g db_host "${FRAPPE_DB_HOST}" || true
run_bench set-config -g db_port "${DB_PORT}" || true
run_bench set-config -g redis_cache "${FRAPPE_REDIS_CACHE}" || true
run_bench set-config -g redis_queue "${FRAPPE_REDIS_QUEUE}" || true
run_bench set-config -g redis_socketio "${FRAPPE_REDIS_QUEUE}" || true

if [ -f "${SITES_DIR}/${SITE_NAME}/site_config.json" ]; then
	echo "-> Site ${SITE_NAME} already exists, skipping new-site"
else
	echo "-> Creating site ${SITE_NAME} and installing ERPNext"
	if run_bench new-site "${SITE_NAME}" \
		--admin-password "${RFP_SITE_ADMIN_PASSWORD}" \
		--db-host "${FRAPPE_DB_HOST}" \
		--db-port "${DB_PORT}" \
		--db-root-username root \
		--db-root-password "${FRAPPE_DB_PASSWORD}" \
		--mariadb-user-host-login-scope='%' \
		--install-app erpnext; then
		run_bench use "${SITE_NAME}" || true
		run_bench --site "${SITE_NAME}" enable-scheduler || true
		echo "-> Site created"
	else
		echo "-> new-site failed; continuing so the web server can start"
	fi
fi

echo "-> Ensuring login user"
export SITE_NAME
export FRAPPE_STREAM_LOGGING=1
su frappe -s /bin/bash -c "cd /home/frappe/frappe-bench/sites && SITE_NAME='${SITE_NAME}' FRAPPE_STREAM_LOGGING=1 /home/frappe/frappe-bench/env/bin/python /usr/local/bin/railway-ensure-login.py" || echo "-> Login user step skipped"
echo "-> Setup finished"
