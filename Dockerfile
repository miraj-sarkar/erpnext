# Railway image for THIS Git repo (ERPNext 17 develop).
# Overlay our app onto the official Frappe/ERPNext develop image, then run
# nginx + gunicorn + workers + socketio in one container (Railway: one volume).
ARG ERPNEXT_BASE=frappe/erpnext:develop
FROM ${ERPNEXT_BASE}

USER root

# The develop image creates user frappe with group 0 (root), not a group named frappe.
# COPY --chown=frappe:frappe and later chown calls need that group name to exist.
RUN if ! getent group frappe >/dev/null 2>&1; then \
		groupadd --system --gid 1000 frappe 2>/dev/null || groupadd --system frappe; \
	fi \
	&& apt-get update \
	&& DEBIAN_FRONTEND=noninteractive apt-get install --no-install-recommends -y \
		supervisor \
		gettext-base \
	&& rm -rf /var/lib/apt/lists/* \
	&& rm -f /etc/nginx/sites-enabled/default \
	&& mkdir -p /etc/nginx/conf.d \
		/home/frappe/frappe-bench/logs \
		/home/frappe/logs \
	&& chown -R frappe:frappe /home/frappe/frappe-bench/logs /home/frappe/logs

COPY --chown=frappe:frappe docker/railway/nginx.conf /etc/nginx/conf.d/default.conf
COPY --chown=root docker/railway/supervisord.conf /home/frappe/supervisor.conf
COPY --chown=frappe:frappe --chmod=0755 docker/railway/setup.sh /home/frappe/frappe-bench/railway-setup.sh
COPY --chmod=0755 docker/railway/prepare-sites.sh /usr/local/bin/railway-prepare-sites.sh
COPY --chmod=0755 docker/railway/entrypoint.sh /usr/local/bin/railway-entrypoint.sh
COPY --chmod=0755 docker/railway/cmd.sh /usr/local/bin/railway-cmd.sh
COPY --chmod=0755 docker/railway/ensure_login.py /usr/local/bin/railway-ensure-login.py
COPY --chmod=0755 docker/railway/load-pharmacy-demo.sh /usr/local/bin/railway-pharmacy-demo.sh

# Replace the stock ERPNext app with this Git repo, but keep JS deps from
# the base image (Git and .dockerignore do not include node_modules).
RUN if [ -d /home/frappe/frappe-bench/apps/erpnext/node_modules ]; then \
		mv /home/frappe/frappe-bench/apps/erpnext/node_modules /tmp/erpnext-node_modules; \
	fi \
	&& if [ -d /home/frappe/frappe-bench/apps/erpnext/banking/node_modules ]; then \
		mv /home/frappe/frappe-bench/apps/erpnext/banking/node_modules /tmp/banking-node_modules; \
	fi \
	&& rm -rf /home/frappe/frappe-bench/apps/erpnext
COPY --chown=frappe:frappe . /home/frappe/frappe-bench/apps/erpnext
RUN if [ -d /tmp/erpnext-node_modules ]; then \
		mv /tmp/erpnext-node_modules /home/frappe/frappe-bench/apps/erpnext/node_modules \
		&& chown -R frappe:frappe /home/frappe/frappe-bench/apps/erpnext/node_modules; \
	fi \
	&& if [ -d /tmp/banking-node_modules ]; then \
		mkdir -p /home/frappe/frappe-bench/apps/erpnext/banking \
		&& mv /tmp/banking-node_modules /home/frappe/frappe-bench/apps/erpnext/banking/node_modules \
		&& chown -R frappe:frappe /home/frappe/frappe-bench/apps/erpnext/banking/node_modules; \
	fi

USER frappe
WORKDIR /home/frappe/frappe-bench

# The base image keeps the full Frappe + ERPNext build in /home/frappe/frappe-bench/assets
# and removes sites/assets, because sites/ is a volume. Rebuilding only ERPNext into an
# empty sites/assets writes an assets.json that has no login.bundle.css, so the login
# page requests /login.bundle.css and the browser never loads jQuery.
RUN echo '{"webserver_port": 8000}' > sites/common_site_config.json \
	&& if [ ! -e sites/assets ] && [ -d /home/frappe/frappe-bench/assets ]; then \
		ln -s /home/frappe/frappe-bench/assets sites/assets; \
	fi \
	&& ./env/bin/pip install -e apps/erpnext \
	&& yarn --cwd apps/erpnext --frozen-lockfile \
	&& /usr/local/bin/bench build --app erpnext \
	&& ./env/bin/python -c 'import json,os; d=json.load(open("sites/assets/assets.json")); req=["login.bundle.css","website.bundle.css","frappe-web.bundle.js"]; missing=[k for k in req if k not in d]; assert not missing, "assets.json missing %s" % missing; [open(os.path.join("sites", d[k].lstrip("/"))).close() for k in req]' \
	&& mkdir -p built_sites \
	&& printf 'frappe\nerpnext\n' > built_sites/apps.txt \
	&& printf 'frappe\nerpnext\n' > sites/apps.txt \
	&& if [ ! -L sites/assets ]; then \
		rm -rf /home/frappe/frappe-bench/assets; \
		mkdir -p /home/frappe/frappe-bench/assets; \
		cp -a sites/assets/. /home/frappe/frappe-bench/assets/; \
	fi \
	&& if [ -f sites/apps.json ]; then cp sites/apps.json built_sites/apps.json; fi

USER root
RUN chmod -R a+rX \
		/home/frappe/frappe-bench/assets \
		/home/frappe/frappe-bench/apps/frappe/frappe/public \
		/home/frappe/frappe-bench/apps/erpnext/erpnext/public \
	&& chmod 755 /home/frappe /home/frappe/frappe-bench /home/frappe/frappe-bench/apps \
		/home/frappe/frappe-bench/apps/frappe /home/frappe/frappe-bench/apps/frappe/frappe \
		/home/frappe/frappe-bench/apps/erpnext /home/frappe/frappe-bench/apps/erpnext/erpnext
EXPOSE 80
ENTRYPOINT ["/usr/local/bin/railway-entrypoint.sh"]
CMD ["/usr/local/bin/railway-cmd.sh"]
