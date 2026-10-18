# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Load the Cheer Health pharmacy demo into a Frappe site.

	bench --site frontend execute erpnext.setup.pharmacy_demo.setup.setup_pharmacy_demo
"""

import frappe

from erpnext.accounts.doctype.account.chart_of_accounts.chart_of_accounts import create_charts
from erpnext.accounts.doctype.bank_reconciliation_tool.bank_reconciliation_tool import (
	reconcile_vouchers,
)
from erpnext.setup.pharmacy_demo.common import (
	COMPANY_ABBR,
	COMPANY_NAME,
	OPENING_DATE,
	OPERATING_ACCOUNT,
	allocation_journals,
	read_data,
)
from erpnext.setup.pharmacy_demo.verify import verify_pharmacy_demo

POSTABLE_LINES = 653


def setup_pharmacy_demo():
	"""Create Cheer Health Inc, post the opening trial balance, and book FY2022–FY2023."""
	frappe.set_user("Administrator")
	if frappe.db.exists("Company", COMPANY_NAME):
		frappe.throw(f"{COMPANY_NAME} already exists. The pharmacy demo was not posted again.")
	if frappe.db.exists("Company", {"abbr": COMPANY_ABBR}):
		frappe.throw(f"Abbreviation {COMPANY_ABBR} is already used. The pharmacy demo was not posted.")

	transactions = [row for row in read_data("transactions") if row["post"]]
	if len(transactions) != POSTABLE_LINES:
		frappe.throw(f"Expected {POSTABLE_LINES} bank lines to post, found {len(transactions)}.")

	company = read_data("company")
	_create_company()
	accounts = _create_chart()
	_ensure_fiscal_years()
	cost_centres = _create_cost_centres()
	_create_address(company)
	banks = _create_banks(company, accounts)
	_set_company_defaults(accounts, cost_centres)
	_post_opening_entry(accounts, cost_centres)
	_create_rules(accounts)
	_post_bank_lines(transactions, banks[OPERATING_ACCOUNT], accounts, cost_centres)
	_post_allocations(accounts, cost_centres)
	_create_statement_balances(banks[OPERATING_ACCOUNT])
	_create_queries()
	verify_pharmacy_demo()
	print(f"Pharmacy demo ready: {COMPANY_NAME}")


def _create_company():
	frappe.local.flags.ignore_chart_of_accounts = True
	company = frappe.get_doc(
		{
			"doctype": "Company",
			"company_name": COMPANY_NAME,
			"abbr": COMPANY_ABBR,
			"default_currency": "USD",
			"country": "United States",
			"enable_perpetual_inventory": 0,
			"create_chart_of_accounts_based_on": "Standard Template",
			"chart_of_accounts": "Standard",
		}
	)
	company.insert(ignore_permissions=True)
	frappe.local.flags.ignore_chart_of_accounts = False


def _create_chart():
	frappe.local.flags.ignore_root_company_validation = True
	create_charts(COMPANY_NAME, custom_chart=_chart(read_data("coa")))
	accounts = {}
	for row in frappe.get_all(
		"Account",
		filters={"company": COMPANY_NAME, "is_group": 0},
		fields=["name", "account_number"],
	):
		if row.account_number:
			accounts[row.account_number] = row.name
	missing = [row["code"] for row in read_data("coa") if row["code"] not in accounts]
	if missing:
		frappe.throw(f"Chart of accounts is missing {', '.join(missing)}.")
	return accounts


def _chart(accounts: list[dict]) -> dict:
	roots = {
		"Asset": "Assets",
		"Liability": "Liabilities",
		"Equity": "Equity",
		"Income": "Income",
		"Expense": "Expenses",
	}
	chart = {
		title: {"root_type": root_type, "is_group": 1, "account_currency": "USD"}
		for root_type, title in roots.items()
	}
	for row in accounts:
		leaf = {"account_number": row["code"], "account_currency": "USD"}
		if row.get("account_type"):
			leaf["account_type"] = row["account_type"]
		parent = chart[roots[row["root_type"]]]
		if row.get("group"):
			parent = parent.setdefault(row["group"], {"is_group": 1, "account_currency": "USD"})
		parent[row["name"]] = leaf
	return chart


def _ensure_fiscal_years():
	for year in (2021, 2022, 2023):
		start = f"{year}-01-01"
		end = f"{year}-12-31"
		if _fiscal_year_covers(start, end):
			continue
		year_name = str(year)
		if frappe.db.exists("Fiscal Year", year_name):
			year_name = f"{year} {COMPANY_ABBR}"
		frappe.get_doc(
			{
				"doctype": "Fiscal Year",
				"year": year_name,
				"year_start_date": start,
				"year_end_date": end,
				"companies": [{"company": COMPANY_NAME}],
			}
		).insert(ignore_permissions=True)


def _fiscal_year_covers(start: str, end: str) -> bool:
	for name in frappe.get_all(
		"Fiscal Year",
		filters={"year_start_date": start, "year_end_date": end, "disabled": 0},
		pluck="name",
	):
		companies = frappe.get_all("Fiscal Year Company", filters={"parent": name}, pluck="company")
		if not companies or COMPANY_NAME in companies:
			return True
		document = frappe.get_doc("Fiscal Year", name)
		document.append("companies", {"company": COMPANY_NAME})
		document.save(ignore_permissions=True)
		return True
	return False


def _create_cost_centres():
	parent = frappe.db.get_value(
		"Cost Center", {"company": COMPANY_NAME, "cost_center_name": COMPANY_NAME}, "name"
	)
	centres = {}
	for row in read_data("cost_centres"):
		document = frappe.get_doc(
			{
				"doctype": "Cost Center",
				"cost_center_name": row["name"],
				"cost_center_number": row["code"],
				"parent_cost_center": parent,
				"company": COMPANY_NAME,
				"is_group": 0,
			}
		)
		document.insert(ignore_permissions=True)
		centres[row["code"]] = document.name
	return centres


def _create_address(company: dict):
	frappe.get_doc(
		{
			"doctype": "Address",
			"address_title": COMPANY_NAME,
			"address_type": "Office",
			"address_line1": company["address_line1"],
			"city": company["city"],
			"state": company["state"],
			"pincode": company["pincode"],
			"country": company["country"],
			"is_your_company_address": 1,
			"links": [{"link_doctype": "Company", "link_name": COMPANY_NAME}],
		}
	).insert(ignore_permissions=True)


def _create_banks(company: dict, accounts: dict) -> dict:
	for bank_name in company["banks"]:
		if not frappe.db.exists("Bank", bank_name):
			frappe.get_doc({"doctype": "Bank", "bank_name": bank_name}).insert(ignore_permissions=True)

	created = {}
	for row in company["bank_accounts"]:
		document = frappe.get_doc(
			{
				"doctype": "Bank Account",
				"account_name": row["account_name"],
				"bank": row["bank"],
				"account": accounts[row["gl"]],
				"company": COMPANY_NAME,
				"is_company_account": 1,
				"is_default": 1 if row["is_default"] else 0,
				"is_credit_card": 1 if row["is_credit_card"] else 0,
				"bank_account_no": row.get("bank_account_no"),
			}
		)
		document.insert(ignore_permissions=True)
		created[row["gl"]] = document.name
	return created


def _set_company_defaults(accounts: dict, cost_centres: dict):
	company = frappe.get_doc("Company", COMPANY_NAME)
	previous_cost_centre = company.cost_center
	company.cost_center = cost_centres["ADM"]
	company.round_off_cost_center = cost_centres["ADM"]
	company.depreciation_cost_center = cost_centres["ADM"]
	company.default_bank_account = accounts[OPERATING_ACCOUNT]
	company.default_cash_account = accounts["1050"]
	company.accumulated_depreciation_account = accounts["1590"]
	company.bank_charges_account = accounts["6610"]
	company.save(ignore_permissions=True)
	if previous_cost_centre and previous_cost_centre != cost_centres["ADM"]:
		frappe.db.set_value("Cost Center", previous_cost_centre, "disabled", 1)


def _post_opening_entry(accounts: dict, cost_centres: dict):
	lines = []
	for row in read_data("opening_tb"):
		lines.append(
			_journal_line(
				accounts[row["code"]],
				row["debit"],
				row["credit"],
				cost_centres.get(row["cost_centre"]) if row.get("cost_centre") else None,
			)
		)
	_post_journal(
		"Opening Entry",
		OPENING_DATE,
		lines,
		"Opening trial balance at 31 Dec 2021. 2021 bank lines are not posted.",
	)


def _create_rules(accounts: dict):
	for rule in read_data("bank_rules"):
		document = frappe.get_doc(
			{
				"doctype": "Bank Transaction Rule",
				"rule_name": rule["rule_name"],
				"priority": rule["priority"],
				"transaction_type": rule["transaction_type"],
				"min_amount": rule.get("min_amount") or 0,
				"max_amount": rule.get("max_amount") or 0,
				"rule_description": rule["meaning"],
				"company": COMPANY_NAME,
				"description_rules": [
					{"check": "Contains", "value": value} for value in rule["contains"]
				],
				"classify_as": "Bank Entry",
				"bank_entry_type": "Single Account",
				"account": accounts[rule["account"]],
			}
		)
		document.insert(ignore_permissions=True)


def _post_bank_lines(transactions, bank_account: str, accounts: dict, cost_centres: dict):
	bank = accounts[OPERATING_ACCOUNT]
	for index, row in enumerate(transactions, start=1):
		amount = row["deposit"] or row["withdrawal"]
		offset = accounts[row["account"]]
		cost_centre = cost_centres.get(row["cost_centre"]) if row.get("cost_centre") else None
		if row["deposit"]:
			lines = [
				_journal_line(bank, amount, 0, None),
				_journal_line(offset, 0, amount, cost_centre),
			]
		else:
			lines = [
				_journal_line(offset, amount, 0, cost_centre),
				_journal_line(bank, 0, amount, None),
			]
		journal = _post_journal(
			"Bank Entry",
			row["date"],
			lines,
			f"{row['rule']}: {row['description']}",
			cheque_no=f"CH-{row['id']}",
			cheque_date=row["date"],
		)
		bank_transaction = frappe.get_doc(
			{
				"doctype": "Bank Transaction",
				"date": row["date"],
				"bank_account": bank_account,
				"company": COMPANY_NAME,
				"deposit": row["deposit"],
				"withdrawal": row["withdrawal"],
				"currency": "USD",
				"description": row["description"],
				"reference_number": f"CH-{row['id']}",
				"is_rule_evaluated": 1,
				"matched_transaction_rule": f"CH-{row['rule']}",
			}
		)
		bank_transaction.flags.ignore_permissions = True
		bank_transaction.insert(ignore_permissions=True)
		bank_transaction.submit()
		reconcile_vouchers(
			bank_transaction.name,
			[{"payment_doctype": "Journal Entry", "payment_name": journal}],
		)
		if index % 50 == 0:
			print(f"Posted {index} of {len(transactions)} bank lines")


def _post_allocations(accounts: dict, cost_centres: dict):
	journals, flagged = allocation_journals(read_data("transactions"))
	for journal in journals:
		lines = [
			_journal_line(
				accounts[row["account"]],
				row["debit"],
				row["credit"],
				cost_centres[row["cost_centre"]],
			)
			for row in journal["accounts"]
		]
		_post_journal("Journal Entry", journal["posting_date"], lines, journal["user_remark"])
	if flagged:
		print("ADM left unallocated in months with no revenue: " + ", ".join(flagged))


def _create_statement_balances(bank_account: str):
	for row in read_data("bank_rec"):
		if not row["statement"].startswith(("2022", "2023")):
			continue
		frappe.get_doc(
			{
				"doctype": "Bank Account Balance",
				"bank_account": bank_account,
				"date": row["period_end"],
				"balance": row["statement_closing"],
			}
		).insert(ignore_permissions=True)


def _create_queries():
	for query in read_data("queries"):
		frappe.get_doc(
			{
				"doctype": "ToDo",
				"description": (
					f"{query['number']}. {query['item']}\n\n"
					f"Ask the client: {query['ask']}\n"
					f"Until answered: {query['where']}"
				),
				"reference_type": "Company",
				"reference_name": COMPANY_NAME,
				"priority": "Medium",
				"status": "Open",
			}
		).insert(ignore_permissions=True)


def _post_journal(
	voucher_type: str,
	posting_date: str,
	accounts: list[dict],
	user_remark: str,
	cheque_no: str | None = None,
	cheque_date: str | None = None,
) -> str:
	document = frappe.get_doc(
		{
			"doctype": "Journal Entry",
			"voucher_type": voucher_type,
			"posting_date": posting_date,
			"company": COMPANY_NAME,
			"user_remark": user_remark,
			"cheque_no": cheque_no,
			"cheque_date": cheque_date,
			"accounts": accounts,
		}
	)
	document.flags.ignore_permissions = True
	document.insert(ignore_permissions=True)
	document.submit()
	return document.name


def _journal_line(account: str, debit: float, credit: float, cost_center: str | None) -> dict:
	line = {
		"account": account,
		"debit_in_account_currency": debit,
		"credit_in_account_currency": credit,
	}
	if cost_center:
		line["cost_center"] = cost_center
	return line
