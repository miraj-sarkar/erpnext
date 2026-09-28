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

cd /home/frappe/frappe-bench

echo "-> Waiting for MariaDB at ${FRAPPE_DB_HOST}:${DB_PORT}"
for _ in $(seq 1 90); do
	if mysqladmin ping -h "$FRAPPE_DB_HOST" -P "$DB_PORT" -uroot -p"$FRAPPE_DB_PASSWORD" --silent 2>/dev/null; then
		echo "-> MariaDB is up"
		break
	fi
	sleep 2
done

echo "-> Writing common site config"
run_bench set-config -g db_host "${FRAPPE_DB_HOST}"
run_bench set-config -g db_port "${DB_PORT}"
run_bench set-config -g redis_cache "${FRAPPE_REDIS_CACHE}"
run_bench set-config -g redis_queue "${FRAPPE_REDIS_QUEUE}"
run_bench set-config -g redis_socketio "${FRAPPE_REDIS_QUEUE}"

if [ -f "${SITES_DIR}/${SITE_NAME}/site_config.json" ]; then
	echo "-> Site ${SITE_NAME} already exists, skipping new-site"
	exit 0
fi

echo "-> Creating site ${SITE_NAME} and installing ERPNext"
run_bench new-site "${SITE_NAME}" \
	--admin-password "${RFP_SITE_ADMIN_PASSWORD}" \
	--db-host "${FRAPPE_DB_HOST}" \
	--db-port "${DB_PORT}" \
	--db-root-username root \
	--db-root-password "${FRAPPE_DB_PASSWORD}" \
	--mariadb-user-host-login-scope='%' \
	--install-app erpnext

run_bench use "${SITE_NAME}"
run_bench --site "${SITE_NAME}" enable-scheduler || true
echo "-> Site created"
