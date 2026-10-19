#!/bin/bash
# Load Cheer Health after the site exists. Safe to run on every boot:
# a finished demo returns immediately, and an interrupted one continues.
set -uo pipefail

sleep 20
cd /home/frappe/frappe-bench

echo "-> Loading Cheer Health pharmacy demo"
if /usr/local/bin/bench --site "${SITE_NAME:-frontend}" execute erpnext.setup.pharmacy_demo.setup.setup_pharmacy_demo; then
	echo "-> Pharmacy demo load finished"
else
	echo "-> Pharmacy demo load did not finish; it will continue on the next boot"
	exit 1
fi
