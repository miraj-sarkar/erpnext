#!/usr/bin/env python3
"""Create the requested Railway login user on every boot."""
import os
import sys

os.chdir("/home/frappe/frappe-bench")
sys.path.insert(0, "apps/frappe")

import frappe
from frappe.utils.password import update_password

SITE = os.environ.get("SITE_NAME", "frontend")
EMAIL = os.environ.get("SITE_ADMIN_EMAIL", "nawmi@arcloops.io")
PASSWORD = os.environ.get("SITE_ADMIN_PASSWORD", "12345678")

frappe.init(site=SITE)
frappe.connect()
frappe.set_user("Administrator")

ss = frappe.get_single("System Settings")
ss.enable_password_policy = 0
ss.flags.ignore_mandatory = True
ss.save(ignore_permissions=True)

update_password("Administrator", PASSWORD)

if not frappe.db.exists("User", EMAIL):
	user = frappe.new_doc("User")
	user.email = EMAIL
	user.first_name = EMAIL.split("@")[0].title()
	user.send_welcome_email = 0
	user.enabled = 1
	user.append("roles", {"role": "System Manager"})
	user.flags.ignore_password_policy = True
	user.insert(ignore_permissions=True)
else:
	user = frappe.get_doc("User", EMAIL)
	user.enabled = 1
	user.send_welcome_email = 0
	if not any(role.role == "System Manager" for role in user.roles):
		user.append("roles", {"role": "System Manager"})
	user.flags.ignore_password_policy = True
	user.save(ignore_permissions=True)

update_password(EMAIL, PASSWORD)
frappe.db.commit()
print(f"-> Login ready: {EMAIL}")
