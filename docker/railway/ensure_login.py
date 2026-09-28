#!/usr/bin/env python3
"""Create the requested Railway login user on every boot. Never abort the container."""
import os
import sys

os.environ["FRAPPE_STREAM_LOGGING"] = "1"

BENCH = "/home/frappe/frappe-bench"
SITES = os.path.join(BENCH, "sites")


def ensure_dirs(*paths):
	for path in paths:
		try:
			os.makedirs(path, exist_ok=True)
		except OSError:
			pass


def main():
	ensure_dirs(
		os.path.join(BENCH, "logs"),
		"/home/frappe/logs",
		SITES,
	)
	os.chdir(SITES)
	sys.path.insert(0, os.path.join(BENCH, "apps/frappe"))

	import frappe
	from frappe.utils.password import update_password

	site = os.environ.get("SITE_NAME", "frontend")
	email = os.environ.get("SITE_ADMIN_EMAIL", "nawmi@arcloops.io")
	password = os.environ.get("SITE_ADMIN_PASSWORD", "12345678")
	site_config = os.path.join(SITES, site, "site_config.json")

	if not os.path.isfile(site_config):
		available = sorted(
			name
			for name in os.listdir(SITES)
			if os.path.isfile(os.path.join(SITES, name, "site_config.json"))
		)
		if not available:
			print("-> No site found on volume. Skip login user.")
			return
		site = available[0]
		print(f"-> Using existing site {site}")

	ensure_dirs(os.path.join(SITES, site, "logs"))

	frappe.init(site=site, sites_path=SITES)
	frappe.connect()
	frappe.set_user("Administrator")

	ss = frappe.get_single("System Settings")
	ss.enable_password_policy = 0
	ss.flags.ignore_mandatory = True
	ss.save(ignore_permissions=True)

	update_password("Administrator", password)

	if not frappe.db.exists("User", email):
		user = frappe.new_doc("User")
		user.email = email
		user.first_name = email.split("@")[0].title()
		user.send_welcome_email = 0
		user.enabled = 1
		user.append("roles", {"role": "System Manager"})
		user.flags.ignore_password_policy = True
		user.insert(ignore_permissions=True)
	else:
		user = frappe.get_doc("User", email)
		user.enabled = 1
		user.send_welcome_email = 0
		if not any(role.role == "System Manager" for role in user.roles):
			user.append("roles", {"role": "System Manager"})
		user.flags.ignore_password_policy = True
		user.save(ignore_permissions=True)

	update_password(email, password)
	frappe.db.commit()
	print(f"-> Login ready: {email}")


if __name__ == "__main__":
	try:
		main()
	except Exception as exc:
		print(f"-> Login user skipped ({type(exc).__name__}): {exc}")
		sys.exit(0)
