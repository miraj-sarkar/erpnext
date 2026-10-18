# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Check Cheer Health against the trainer answer key.

	bench --site frontend execute erpnext.setup.pharmacy_demo.verify.verify_pharmacy_demo
"""

from collections import defaultdict

import frappe
from frappe.utils import flt, getdate

from erpnext.accounts.utils import get_balance_on
from erpnext.setup.pharmacy_demo.common import (
	ADM_EXPENSE_ACCOUNTS,
	COMPANY_NAME,
	OPENING_DATE,
	OPENING_TOTAL,
	OPERATING_ACCOUNT,
	REVENUE_ACCOUNTS,
	read_data,
)

CENT = 0.02


def verify_pharmacy_demo():
	"""Raise if the posted books do not match the answer key."""
	if not frappe.db.exists("Company", COMPANY_NAME):
		frappe.throw(f"{COMPANY_NAME} is not set up.")

	failures = []
	_check_opening(failures)
	_check_prior_period(failures)
	_check_bank_balances(failures)
	_check_expected_totals(failures)
	_check_cost_centres(failures)
	_check_adm_allocation(failures)
	_check_clearing_and_queries(failures)

	if failures:
		frappe.throw("<br>".join(failures), title="Pharmacy demo verification failed")

	print("Pharmacy demo verification passed.")


def _check_opening(failures: list[str]):
	journals = frappe.get_all(
		"Journal Entry",
		filters={"company": COMPANY_NAME, "voucher_type": "Opening Entry", "docstatus": 1},
		fields=["name", "posting_date", "total_debit", "total_credit"],
	)
	if len(journals) != 1:
		failures.append(f"Expected one opening entry, found {len(journals)}.")
		return
	journal = journals[0]
	if str(journal.posting_date) != OPENING_DATE:
		failures.append(f"Opening entry is dated {journal.posting_date}, expected {OPENING_DATE}.")
	if abs(flt(journal.total_debit) - float(OPENING_TOTAL)) > CENT:
		failures.append(f"Opening debits are {journal.total_debit}, expected {OPENING_TOTAL}.")
	if abs(flt(journal.total_credit) - float(OPENING_TOTAL)) > CENT:
		failures.append(f"Opening credits are {journal.total_credit}, expected {OPENING_TOTAL}.")
	if abs(_balance(account_by_number("3050"), OPENING_DATE)) > CENT:
		failures.append("Opening balance equity (3050) is not zero.")


def _check_prior_period(failures: list[str]):
	bank_lines = frappe.db.count(
		"Bank Transaction",
		{"company": COMPANY_NAME, "docstatus": 1, "date": ["<", "2022-01-01"]},
	)
	if bank_lines:
		failures.append(f"{bank_lines} bank lines are dated before 2022.")

	vouchers = frappe.db.sql(
		"""
		SELECT gle.voucher_type, IFNULL(je.voucher_type, '')
		FROM `tabGL Entry` gle
		LEFT JOIN `tabJournal Entry` je
			ON gle.voucher_type = 'Journal Entry' AND je.name = gle.voucher_no
		WHERE gle.company = %s AND gle.is_cancelled = 0 AND gle.posting_date < '2022-01-01'
		GROUP BY gle.voucher_type, je.voucher_type
		""",
		COMPANY_NAME,
	)
	unexpected = [
		journal_type or voucher_type
		for voucher_type, journal_type in vouchers
		if not (voucher_type == "Journal Entry" and journal_type == "Opening Entry")
	]
	if unexpected:
		failures.append("GL before 2022 includes " + ", ".join(unexpected) + ".")


def _check_bank_balances(failures: list[str]):
	account = account_by_number(OPERATING_ACCOUNT)
	for row in read_data("bank_rec"):
		if not row["statement"].startswith(("2022", "2023")):
			continue
		balance = _balance(account, row["period_end"])
		if abs(balance - row["statement_closing"]) > CENT:
			failures.append(
				f"…8905 on {row['period_end']} is {balance:.2f}, statement is {row['statement_closing']:.2f}."
			)


def _check_expected_totals(failures: list[str]):
	expected = read_data("expected_totals")
	for year, field in ((2022, "fy2022"), (2023, "fy2023")):
		movement = _account_movement(year)
		for row in expected["accounts"]:
			actual = movement.get(row["code"], 0.0)
			if abs(actual - row[field]) > CENT:
				failures.append(
					f"{row['code']} FY{year} net is {actual:.2f}, answer key is {row[field]:.2f}."
				)
		bank = _bank_movement(year)
		target = expected["bank_movement"][field]
		if abs(bank - target) > CENT:
			failures.append(f"…8905 FY{year} movement is {bank:.2f}, answer key is {target:.2f}.")


def _check_cost_centres(failures: list[str]):
	allowed = set(
		frappe.get_all(
			"Cost Center",
			filters={"company": COMPANY_NAME, "cost_center_number": ["in", ["RX", "POS", "340B", "ADM"]]},
			pluck="name",
		)
	)
	rows = frappe.db.sql(
		"""
		SELECT acc.account_number, gle.cost_center
		FROM `tabGL Entry` gle
		INNER JOIN `tabAccount` acc ON acc.name = gle.account
		WHERE gle.company = %s AND gle.is_cancelled = 0 AND acc.report_type = 'Profit and Loss'
			AND (gle.cost_center IS NULL OR gle.cost_center = '' OR gle.cost_center NOT IN %s)
		LIMIT 5
		""",
		(COMPANY_NAME, tuple(allowed) or ("",)),
		as_dict=True,
	)
	if rows:
		sample = ", ".join(f"{row.account_number} ({row.cost_center or 'blank'})" for row in rows)
		failures.append(f"Profit and loss lines are missing a pharmacy cost centre: {sample}.")


def _check_adm_allocation(failures: list[str]):
	revenue = defaultdict(float)
	adm = defaultdict(float)
	for row in _dimension_rows(tuple(REVENUE_ACCOUNTS) + ADM_EXPENSE_ACCOUNTS):
		month = str(row.posting_date)[:7]
		if row.account_number in REVENUE_ACCOUNTS:
			revenue[month] += flt(row.credit) - flt(row.debit)
		elif row.cost_centre == "ADM":
			adm[month] += flt(row.debit) - flt(row.credit)

	for month, balance in sorted(adm.items()):
		if abs(balance) <= CENT:
			continue
		if revenue.get(month, 0) > CENT:
			failures.append(
				f"ADM still has {balance:.2f} in {month} even though that month has revenue."
			)


def _check_clearing_and_queries(failures: list[str]):
	clearing = account_by_number("1090")
	for row in read_data("bank_rec"):
		if not row["statement"].startswith(("2022", "2023")):
			continue
		balance = _balance(clearing, row["period_end"])
		if abs(balance) > CENT:
			failures.append(f"Transfer clearing (1090) is {balance:.2f} on {row['period_end']}.")
			break

	posted = frappe.db.count("Bank Transaction", {"company": COMPANY_NAME, "docstatus": 1})
	if posted != 653:
		failures.append(f"Expected 653 bank transactions, found {posted}.")
	open_lines = frappe.db.count(
		"Bank Transaction",
		{"company": COMPANY_NAME, "docstatus": 1, "status": ["!=", "Reconciled"]},
	)
	if open_lines:
		failures.append(f"{open_lines} bank transactions are not reconciled.")
	queries = frappe.db.count("ToDo", {"reference_type": "Company", "reference_name": COMPANY_NAME})
	if queries < 11:
		failures.append(f"Expected 11 client queries, found {queries}.")


def _dimension_rows(account_numbers: tuple[str, ...]):
	return frappe.db.sql(
		"""
		SELECT gle.posting_date, acc.account_number, cc.cost_center_number AS cost_centre,
			gle.debit, gle.credit
		FROM `tabGL Entry` gle
		INNER JOIN `tabAccount` acc ON acc.name = gle.account
		LEFT JOIN `tabCost Center` cc ON cc.name = gle.cost_center
		WHERE gle.company = %s AND gle.is_cancelled = 0 AND acc.account_number IN %s
		""",
		(COMPANY_NAME, account_numbers),
		as_dict=True,
	)


def _account_movement(year: int) -> dict[str, float]:
	rows = frappe.db.sql(
		"""
		SELECT acc.account_number AS code, SUM(gle.credit) - SUM(gle.debit) AS net
		FROM `tabGL Entry` gle
		INNER JOIN `tabAccount` acc ON acc.name = gle.account
		WHERE gle.company = %s AND gle.is_cancelled = 0
			AND gle.posting_date BETWEEN %s AND %s
		GROUP BY acc.account_number
		""",
		(COMPANY_NAME, f"{year}-01-01", f"{year}-12-31"),
		as_dict=True,
	)
	return {row.code: flt(row.net) for row in rows}


def _bank_movement(year: int) -> float:
	row = frappe.db.sql(
		"""
		SELECT SUM(gle.debit) - SUM(gle.credit) AS net
		FROM `tabGL Entry` gle
		INNER JOIN `tabAccount` acc ON acc.name = gle.account
		WHERE gle.company = %s AND gle.is_cancelled = 0 AND acc.account_number = %s
			AND gle.posting_date BETWEEN %s AND %s
		""",
		(COMPANY_NAME, OPERATING_ACCOUNT, f"{year}-01-01", f"{year}-12-31"),
		as_dict=True,
	)
	return flt(row[0].net) if row else 0.0


def _balance(account: str, date: str) -> float:
	return flt(get_balance_on(account, getdate(date), company=COMPANY_NAME))


def account_by_number(code: str) -> str:
	name = frappe.db.get_value("Account", {"company": COMPANY_NAME, "account_number": code}, "name")
	if not name:
		frappe.throw(f"Account {code} was not found for {COMPANY_NAME}.")
	return name
