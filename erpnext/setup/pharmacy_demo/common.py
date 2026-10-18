# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import calendar
import json
import os
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

COMPANY_NAME = "Cheer Health Inc"
COMPANY_ABBR = "CH"
OPERATING_ACCOUNT = "1010"
OPENING_DATE = "2021-12-31"
OPENING_TOTAL = Decimal("721530.86")
ADM_EXPENSE_ACCOUNTS = ("6030", "6610", "6620")
REVENUE_ACCOUNTS = {"4010": "RX", "4020": "POS", "4040": "340B"}
ALLOCATION_CENTRES = ("RX", "POS", "340B")
CENT = Decimal("0.01")


def read_data(name: str):
	path = os.path.join(os.path.dirname(__file__), "data", f"{name}.json")
	with open(path, encoding="utf-8") as handle:
		return json.load(handle)


def money(value) -> Decimal:
	return Decimal(str(value or 0)).quantize(CENT, rounding=ROUND_HALF_UP)


def rule_matches(rule: dict, description: str, deposit: float, withdrawal: float) -> bool:
	"""Same first-hit rules as Bank Transaction Rule.evaluate_rule."""
	transaction_type = rule.get("transaction_type") or "Any"
	if transaction_type == "Withdrawal" and not withdrawal:
		return False
	if transaction_type == "Deposit" and not deposit:
		return False

	amount = withdrawal or deposit or 0
	min_amount = rule.get("min_amount")
	max_amount = rule.get("max_amount")
	if min_amount and amount < min_amount:
		return False
	if max_amount and amount > max_amount:
		return False

	description = (description or "").lower()
	for value in rule.get("contains") or []:
		if value.lower() in description:
			return True
	return False


def first_matching_rule(rules: list[dict], description: str, deposit: float, withdrawal: float):
	ordered = sorted(rules, key=lambda rule: rule["priority"])
	for rule in ordered:
		if rule_matches(rule, description, deposit, withdrawal):
			return rule
	return None


def month_end(month_key: str) -> str:
	year, month = (int(part) for part in month_key.split("-"))
	return date(year, month, calendar.monthrange(year, month)[1]).isoformat()


def allocation_journals(transactions: list[dict]) -> tuple[list[dict], list[str]]:
	"""Move ADM expense onto RX, POS and 340B in proportion to that month's revenue.

	Account totals do not change: each journal debits and credits the same account.
	Months with ADM cost and no revenue are returned and left unallocated.
	"""
	revenue: dict[str, dict[str, Decimal]] = {}
	expense: dict[str, dict[str, Decimal]] = {}

	for row in transactions:
		if not row.get("post"):
			continue
		month = row["date"][:7]
		account = row["account"]
		deposit = money(row.get("deposit"))
		withdrawal = money(row.get("withdrawal"))
		if account in REVENUE_ACCOUNTS:
			centre = REVENUE_ACCOUNTS[account]
			revenue.setdefault(month, {})
			revenue[month][centre] = revenue[month].get(centre, Decimal("0.00")) + deposit - withdrawal
		if account in ADM_EXPENSE_ACCOUNTS:
			expense.setdefault(month, {})
			expense[month][account] = expense[month].get(account, Decimal("0.00")) + withdrawal - deposit

	journals = []
	flagged = []
	for month in sorted(expense):
		month_revenue = {centre: amount for centre, amount in revenue.get(month, {}).items() if amount > 0}
		total_revenue = sum(month_revenue.values(), Decimal("0.00"))
		month_expense = {account: amount for account, amount in expense[month].items() if amount != 0}
		if not month_expense:
			continue
		if total_revenue <= 0:
			flagged.append(month)
			continue

		for account, net_expense in month_expense.items():
			journals.append(_allocation_journal(month, account, net_expense, month_revenue, total_revenue))

	return journals, flagged


def _allocation_journal(month, account, net_expense, month_revenue, total_revenue) -> dict:
	amount = abs(net_expense)
	adm_is_credit = net_expense > 0
	positive = [
		(centre, month_revenue[centre])
		for centre in ALLOCATION_CENTRES
		if month_revenue.get(centre, 0) > 0
	]
	allocated = Decimal("0.00")
	shares = []
	for index, (centre, centre_revenue) in enumerate(positive):
		if index == len(positive) - 1:
			share = amount - allocated
		else:
			share = (amount * centre_revenue / total_revenue).quantize(CENT, rounding=ROUND_HALF_UP)
			allocated += share
		if share < 0:
			raise ValueError(f"Negative allocation share for {account} in {month}")
		if share != 0:
			shares.append((centre, share))

	if sum((share for _centre, share in shares), Decimal("0.00")) != amount:
		raise ValueError(f"Allocation for {account} in {month} does not add up to {amount}")

	accounts = [
		{
			"account": account,
			"cost_centre": "ADM",
			"debit": float(Decimal("0.00") if adm_is_credit else amount),
			"credit": float(amount if adm_is_credit else Decimal("0.00")),
		}
	]
	for centre, share in shares:
		accounts.append(
			{
				"account": account,
				"cost_centre": centre,
				"debit": float(share if adm_is_credit else Decimal("0.00")),
				"credit": float(Decimal("0.00") if adm_is_credit else share),
			}
		)

	return {
		"posting_date": month_end(month),
		"user_remark": f"Allocate ADM {account} for {month} in proportion to RX, POS and 340B revenue",
		"accounts": accounts,
	}
