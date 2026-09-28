#!/bin/bash
set -euo pipefail

echo "-> Preparing sites volume"
/usr/local/bin/railway-prepare-sites.sh

exec "$@"
