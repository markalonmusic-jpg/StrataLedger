# Chart of accounts templates

Approved by the owner on 2026-11-11 (decision I1), from decision A7 and the
original construction chart. `create_company` loads them through
`modules/services/chart_templates.py`; "Import my own CSV" uses the same
columns and the same checks.

Columns
- account_number: 4 to 8 digits (C1). parent_number: the header it sits under.
- account_type: Asset, Liability, Equity, Revenue, Expense.
- subtype: statement grouping (current asset, cost of sales, other income...).
- normal_balance: D or C (A3). Contra accounts differ from their type:
  1590 Accumulated Depreciation (C), 3020 Owner Draws (D), 5055 Equipment
  Recovery (C), 4090 Discounts and Refunds Given (D, general only).
- control_type: blank, or a controlled type from A5 (subledger accounts).
- is_postable: 0 for headers (C2: accounts with children take no postings).
- system_role: the company_settings pointer this account fills (A6). The
  six required before first posting are ar, ap, sales_tax_payable,
  default_bank, retained_earnings, opening_balance_equity.

Decisions on the open points
- contract_cost (WIP cost pointer) stays unmapped; it is set with the
  construction release (v1.1).
- Line of Credit stays under current liabilities.
- One credit card account is included; companies add one per card.
- Income Tax Expense stays in the default chart.
