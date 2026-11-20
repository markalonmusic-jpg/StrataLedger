# Report builder service contracts (owner-approved 2026-11-19)

Written 2026-11-19 by Claude Code (Opus) for the planning chat, before design builds batch E. Docs only: no code,
schema or tests. Status: **Owner-approved 2026-11-19** (fix mode 1: owner answers Q1-Q18; fix mode 2: Q19-Q26,
section 11). Schema needs are in section 12, for the 2.9 replan.

Purpose: batch E pages are built against `mock-data/*.json` files in exactly these shapes and then switched to the
real services through the one data layer, with no page change (build rules b, c, e and g, shared_decisions
2026-11-19 1:21 AM and 2:29 AM).

Sources: to_planning 2026-11-19 "report builder service contracts" (the eight items) and 2026-11-18 "report
definitions with two kinds" and "financial layouts, formulas, non-financial data"; shared_decisions 2026-11-18
3:14, 3:16, 3:19 and 3:22 PM, 2026-11-19 12:40 AM, 12:45 AM, 1:21 AM and 2:29 AM; decisions A1, S4, L1, E11, RP2,
JD1, CB1, CF1, G6, G7, R27; area 18 (access model). Built code read: `ledger.py`, `periods.py` (`BASES`,
`period_ids_for_basis`, `list_periods`), `accounts.py`, `errors.py`, `permissions.py` and `001_company.sql`
(`journal_entry`, `journal_line`, `journal_line_dimension`, `fiscal_period`, `account`, `company_entity`,
`custom_field_def`). There is no report or dimension service yet.

**Two code families share numbers.** In this doc "R34" and "R35" mean the UX rules in shared_decisions (R34 one
shared print preview, 2026-11-18 2:38 AM; R35 every line drills to its source, 3:58 AM). The repo's R34 (limit
refusals) and R35 (`SaveFailedError`) are different decisions; R35 (repo) is cited once, as "repo R35", in
section 9.

---

## 1. Conventions (every service in this doc)

- **Transport.** Each service is one data-layer call (`data.reports.<name>(request)`), which in the app is a
  pywebview `js_api` call to a Python service. Requests and responses are plain JSON objects.
- **Envelope.** Success: `{"ok": true, "result": {...}, "warnings": [...]}` (`warnings` optional, each
  `{"message": "...", "field": "..."}`, never blocking). Failure: `{"ok": false, "error": {...}}` (section 9).
- **IDs** are opaque strings (`"lay_8f3k2"`). Pages never parse, compare, sort or do arithmetic on them (g1).
  Display numbers (`"JE-000412"`, `"INV-0391"`) come in their own `display_*` fields.
- **Dates** are `"YYYY-MM-DD"` (accounting dates have no time); timestamps are ISO 8601 UTC with `Z`
  (`"2026-11-19T14:05:00Z"`). Pages only format them (g2); periods, ranges and dynamic dates are resolved by the
  service from `context.today` (H2, G6).
- **Money** is `{"amount": "-1234.50", "currency": "USD"}`: a decimal string with exactly the currency's minor
  digits, minus sign for negative, no thousands separator. Services hold integer cents (rule 1) and convert at
  the edge. Non-money numbers (ratios, percents, quantities) are decimal strings: `"0.3500"`.
- **Display text.** Every value a page shows also comes as `display` (already formatted for the item's format,
  decimals, sign setting and the company's settings), so pages do no number formatting or arithmetic (rule e).
  Pages may still format dates (g2).
- **Files** are handles: `{"handle": "fh_...", "name": "P&L Oct 2026.xlsx", "content_type": "...",
  "size_bytes": 48211}`. Never a path (g3). A handle is opened with `data.files.open(handle)` or saved with
  `data.files.save_as(handle)`; storage is `storage.py` (H3).
- **Versions.** Every saved definition carries `version` (an opaque string). A save sends back the version it
  loaded; if the stored one differs, the save is refused with `kind: "conflict"` (g4). A new record is saved
  with `version: null`.
- **Permissions** are checked by the service on every call (`authorize`, rule 10), never by the page. Pages get
  `capabilities` (booleans) to decide what to show; they never decide what is allowed.
- **Lists** take `{"limit": 50, "cursor": null}` and return `{"items": [...], "next_cursor": "..." | null}`.

Permissions used (existing codes from `permissions.py`; new ones marked, section 12): `report.financial`,
`report.job_cost`, `report.export`, `money.view` (new, 12:45 AM), `report.records` (new, Q8 A: run Records
reports), `report.design` (new, Q8 A: edit layouts, KPIs, measures and shared saved reports), `report.schedule`
(new, Q8 A: schedules). None is sensitive.

---

## 2. Definitions (item 1)

Five kinds of saved definition: **layouts** (financial or records), **saved reports** (layout + parameters),
**packs** (ordered saved reports), **KPIs** (section 2.7, Q5) and **schedules** (section 7.3). All share list /
get / save / copy / delete shapes.

### 2.1 Services

| Service | Request | Result | Permission |
|---|---|---|---|
| `list_layouts` | `{kind?, report_type?, include_built_in, limit, cursor}` | `{items: [layout summary], next_cursor}` | `report.financial` (financial) or `report.records` (records) |
| `get_layout` | `{layout_id}` | `{layout, capabilities, unassigned_accounts}` | as above |
| `save_layout` | `{layout}` (with `version`) | `{layout}` (new `version`) | `report.design` |
| `copy_layout` | `{layout_id, name}` | `{layout}` (company-owned, `version: "1"`) | `report.design` |
| `delete_layout` | `{layout_id, version}` | `{deleted: true}`; refused while any pack uses it | `report.design` |
| `layout_usage` | `{layout_id}` | `{saved_reports: [...], packs: [...], pack_count}` | as `get_layout` |
| `list_saved_reports` / `get_saved_report` / `save_saved_report` / `delete_saved_report` | as layouts | as layouts | read: run permission; save: run permission (own) or `report.design` (shared) |
| `list_packs` / `get_pack` / `save_pack` / `delete_pack` | as layouts | as layouts | as saved reports |
| `list_kpis` / `get_kpi` / `save_kpi` / `deactivate_kpi` | as layouts | as layouts (section 2.7) | read: `report.financial` and `money.view`; save: `report.design` |
| `get_kpi_values` | `{kpi_ids, period_ids}` | values per period, frozen or live, with close history (2.7) | `report.financial` and `money.view` |

Built-in layouts (`built_in: true`) are read-only: `save_layout` and `delete_layout` refuse them, and
`capabilities.can_edit` is false with `edit_reason: "Built-in layouts can't be changed. Make a copy to edit."`.

### 2.2 Financial layout

```json
{
  "layout_id": "lay_8f3k2",
  "version": "7",
  "kind": "financial",
  "report_type": "profit_and_loss",
  "name": "P&L by trade (management)",
  "built_in": false,
  "copied_from": {"layout_id": "lay_builtin_pl", "name": "Profit and loss (standard)"},
  "updated_at": "2026-11-18T21:40:12Z",
  "updated_by": {"user_id": "usr_3", "name": "Dana Whitfield"},
  "items": [
    {
      "item_id": "itm_rev",
      "type": "group",
      "parent_id": null,
      "sort": 1,
      "name": "Revenue",
      "options": {
        "show_total": true,
        "collapsed": false,
        "hidden": false,
        "positive_when": "credit",
        "over_plan_is": "good",
        "show_accounts": true,
        "hide_if_zero": false
      },
      "accounts": [
        {"account_id": "acc_4000", "display_code": "4000", "name": "Contract revenue"},
        {"account_id": "acc_4100", "display_code": "4100", "name": "Service and repair revenue"}
      ],
      "auto_include": [{"rule": "account_range", "from_code": "4000", "to_code": "4999"}]
    },
    {
      "item_id": "itm_cogs",
      "type": "group",
      "parent_id": null,
      "sort": 2,
      "name": "Cost of sales",
      "options": {"show_total": true, "collapsed": true, "hidden": false,
                  "positive_when": "debit", "over_plan_is": "bad", "show_accounts": true, "hide_if_zero": true},
      "accounts": [],
      "auto_include": [{"rule": "account_type", "account_type": "Expense", "subtype": "Cost of sales"}]
    },
    {
      "item_id": "itm_cogs_mat",
      "type": "group",
      "parent_id": "itm_cogs",
      "sort": 1,
      "name": "Materials",
      "options": {"show_total": true, "collapsed": false, "hidden": false,
                  "positive_when": "debit", "over_plan_is": "bad", "show_accounts": true, "hide_if_zero": true},
      "accounts": [{"account_id": "acc_5200", "display_code": "5200", "name": "Materials"}],
      "auto_include": []
    },
    {
      "item_id": "itm_gp",
      "type": "formula",
      "parent_id": null,
      "sort": 3,
      "name": "Gross profit",
      "tokens": [
        {"t": "ref", "kind": "group", "id": "itm_rev"},
        {"t": "op", "op": "-"},
        {"t": "ref", "kind": "group", "id": "itm_cogs"}
      ],
      "format": "currency",
      "decimals": 2,
      "total_method": "calculate",
      "hide_if_zero": false,
      "over_plan_is": "good"
    },
    {
      "item_id": "itm_gpm",
      "type": "formula",
      "parent_id": null,
      "sort": 4,
      "name": "Gross margin",
      "tokens": [
        {"t": "ref", "kind": "formula", "id": "itm_gp"},
        {"t": "op", "op": "/"},
        {"t": "ref", "kind": "group", "id": "itm_rev"}
      ],
      "format": "percent",
      "decimals": 1,
      "total_method": "calculate",
      "hide_if_zero": true,
      "over_plan_is": "good"
    },
    {
      "item_id": "itm_rev_kw",
      "type": "formula",
      "parent_id": null,
      "sort": 5,
      "name": "Revenue per kW installed",
      "tokens": [
        {"t": "ref", "kind": "group", "id": "itm_rev"},
        {"t": "op", "op": "/"},
        {"t": "ref", "kind": "measure", "id": "nfm_kw"}
      ],
      "format": "currency",
      "decimals": 2,
      "total_method": "calculate",
      "hide_if_zero": true,
      "over_plan_is": "neutral"
    },
    {
      "item_id": "itm_chart1",
      "type": "chart",
      "parent_id": null,
      "sort": 1,
      "name": "Revenue and gross profit",
      "chart": {"chart_type": "bar", "series": ["itm_rev", "itm_gp"], "band": "top", "column": 1, "order": 1}
    }
  ]
}
```

Rules the service enforces on save (all refusals use the section 9 shape with `field`):
- `report_type`: `profit_and_loss`, `balance_sheet`, `cash_flow`, `combined` (P&L and balance sheet on one
  report). `kind` and `report_type` cannot change after the first save.
- `scope`: `single` (default) or `combined` (a layout for runs across company files, 4.7; only a combined layout
  may use the `company_group` and `company_account` operands). Matching across files is by account number
  (Q19 B): an account in another company whose number is not in this company's chart is "unmatched" and shows
  as its own row, labelled with its company, under the group its number or type fits, or under "Not in any
  group"; it counts in the totals (4.7).
- `items` is a tree by `parent_id` and `sort`. Groups nest under groups only; formulas and charts sit at any
  level; charts always render in the top band (`band: "top"`, `column` 1 or 2).
- An account sits in at most one group per layout. Explicit `accounts` win over `auto_include`. Two
  `auto_include` rules that can match the same account are refused (Q3). A parent account (C2) assigned to a
  group brings its whole sub-tree; the result lists the leaves under it.
- `options.positive_when`: `credit` or `debit` (A3 presentation). `over_plan_is`: `good`, `bad`, `neutral`.
- Formula fields: section 3.
- `chart_type`: `bar`, `line`, `donut`, `waterfall`. `series` lists group or formula item ids; a donut takes
  one column only (the first value column).
- KPIs are not a flag on items (Q5): a KPI definition (2.7) points at a group or formula. Removing an item that
  a KPI uses is refused ("Gross margin is used by the KPI Gross margin. Change or deactivate the KPI first."), and
  so is deleting a layout that an active KPI uses.

`get_layout` also returns:

```json
{
  "capabilities": {"can_edit": true, "can_delete": false, "delete_reason": "2 report packs use this layout. Remove it from them first.", "can_copy": true},
  "usage": {"pack_count": 2, "kpis": [{"kpi_id": "kpi_gpm", "name": "Gross margin", "item_id": "itm_gpm"}]},
  "unassigned_accounts": [
    {"account_id": "acc_6950", "display_code": "6950", "name": "Small tools", "account_type": "Expense",
     "matched_by_rule": false}
  ]
}
```

`unassigned_accounts` is the "accounts not in any group" list (to_planning 11-18 item 3): active accounts with
no explicit group and no `auto_include` match, for the report type (P&L: Revenue and Expense; balance sheet:
Asset, Liability, Equity).

### 2.3 Records layout

```json
{
  "layout_id": "lay_r_winrate",
  "version": "3",
  "kind": "records",
  "name": "Win rate by sales rep",
  "built_in": false,
  "source_id": "src_leads_estimates",
  "columns": [
    {"column_id": "col_rep", "field_id": "lead.sales_rep", "label": "Sales rep", "summary": "none", "format": null},
    {"column_id": "col_closed", "field_id": "lead.lead_id", "label": "Closed leads", "summary": "count",
     "where": [{"field_id": "lead.status", "op": "in", "values": ["Closed · Won", "Closed · Lost"]}], "format": "number"},
    {"column_id": "col_won", "field_id": "lead.lead_id", "label": "Won", "summary": "count",
     "where": [{"field_id": "lead.status", "op": "eq", "values": ["Closed · Won"]}], "format": "number"},
    {"column_id": "col_value", "field_id": "estimate.total", "label": "Signed value", "summary": "sum",
     "where": [{"field_id": "lead.status", "op": "eq", "values": ["Closed · Won"]}], "format": "currency"},
    {"column_id": "col_rate", "type": "formula", "label": "Win rate",
     "tokens": [{"t": "ref", "kind": "column", "id": "col_won"}, {"t": "op", "op": "/"},
                {"t": "ref", "kind": "column", "id": "col_closed"}],
     "format": "percent", "decimals": 1}
  ],
  "group_by": [{"field_id": "lead.sales_rep"}, {"field_id": "lead.created_on", "bucket": "quarter"}],
  "sort": [{"column_id": "col_rate", "direction": "desc"}],
  "filters": [{"field_id": "lead.job_type", "op": "in", "values": ["Re-roof", "Solar"]}],
  "charts": [{"chart_id": "ch_1", "chart_type": "bar", "series": ["col_rate"], "band": "top", "column": 1, "order": 1}]
}
```

- `summary`: `none`, `count`, `sum`, `avg`, `min`, `max`. `sum` and `avg` only on number and money fields.
- `where` on a column is a conditional summary (needed for "won ÷ closed"; Q11).
- `group_by`: up to 3; a date field takes `bucket`: `day`, `week`, `month`, `quarter`, `year` (fiscal quarter
  and year follow the company's fiscal year).
- Filter `op`: `eq`, `ne`, `in`, `not_in`, `gt`, `gte`, `lt`, `lte`, `between`, `is_empty`, `not_empty`,
  `contains`. Date filters may use a dynamic preset (`{"field_id": "...", "op": "in_range", "preset":
  "last_12_months"}`, section 4.1).
- Formula columns use section 3 tokens with `kind: "column"` references; they are evaluated per group and on
  the total row from the summaries, never on raw rows.

### 2.4 Saved report

```json
{
  "saved_report_id": "sr_oct_pl",
  "version": "2",
  "name": "P&L by trade, last closed month vs plan",
  "layout_id": "lay_8f3k2",
  "layout_name": "P&L by trade (management)",
  "kind": "financial",
  "shared": true,
  "owner": {"user_id": "usr_3", "name": "Dana Whitfield"},
  "parameters": {
    "dates": {"mode": "preset", "preset": "last_closed_month"},
    "columns": {"mode": "single_period"},
    "compare": [{"type": "plan", "plan_version_id": "opv_fy27_orig"}, {"type": "prior_year"}],
    "basis": {"method": "accrual", "adjustments": "gaap"},
    "entity": {"mode": "company"},
    "filters": {"dimensions": [{"dimension_type_id": "dt_pc", "value_ids": ["dv_res"], "include_children": true}],
                "project_ids": [], "cost_code_ids": [], "contact_ids": []},
    "reclass_view": "as_reclassed"
  },
  "updated_at": "2026-11-18T22:01:33Z"
}
```

A records saved report has `kind: "records"` and `parameters: {"dates": {...}, "date_field_id":
"lead.created_on", "filters": [...]}` (the layout's filters plus these). The plan version is kept as saved
(3:14 PM: "a saved report or pack keeps the version it was saved with").

Amendment 2026-11-19 (owner, area 17 Q8 A): `shared` is `share_mode`: `private`, `people` (with a `shared_with` list of
company users) or `everyone` (everyone with Reports access); `shared: true` in the samples reads as not `private`.
A saved report also gains `parameters.split_by` (Q11 A: `job`, `job_type`, `pm`, `dimension` (with a dimension type),
`cost_code`, `month` or `entity`; one column per value) and the `compare` type `job_budget` (the job's cost budget
from `project_budget`, never the operating plan). A customer or vendor filter (`filters.contact_ids`) is read from
`journal_line`, not the period summary (Q12 B), and cannot be combined with a `plan` compare.

### 2.5 Pack

```json
{
  "pack_id": "pk_board",
  "version": "5",
  "name": "Monthly board pack",
  "items": [
    {"saved_report_id": "sr_oct_pl", "name": "P&L by trade, last closed month vs plan", "kind": "financial"},
    {"saved_report_id": "sr_bs", "name": "Balance sheet, last closed month", "kind": "financial"},
    {"saved_report_id": "sr_winrate", "name": "Win rate by sales rep, last 12 months", "kind": "records"}
  ],
  "pack_dates": {"mode": "preset", "preset": "last_closed_month"},
  "updated_at": "2026-11-17T16:20:00Z"
}
```

`pack_dates`, when set, replaces each saved report's dates for a pack run (Q12); `null` keeps each report's own.

Amendment 2026-11-19 (owner, area 17 Q9 A): a pack item has a `kind`: `cover`, `contents` (built automatically),
`report` (a saved report) or `text` (a text page with a title and a body of at most 4,000 characters); the samples'
`items` list shows `report` items only.

### 2.6 "Packs using this layout"

`layout_usage` result:

```json
{
  "layout_id": "lay_8f3k2",
  "saved_reports": [{"saved_report_id": "sr_oct_pl", "name": "P&L by trade, last closed month vs plan"}],
  "packs": [{"pack_id": "pk_board", "name": "Monthly board pack"}, {"pack_id": "pk_bank", "name": "Bank covenant pack"}],
  "pack_count": 2,
  "message": "2 report packs use this layout. Saving changes them too."
}
```

### 2.7 KPIs: definitions and frozen values per period (Q5, owner 2026-11-19)

A KPI is its own record: a name, a source (one group or formula of a financial layout, or one non-financial
measure) and a format. It has a value per period. While a period is open the value is **live** (computed when
read). When the period closes, the close stores every active KPI's value for that period, **frozen**, in the
same transaction as the close (like the close snapshot, to_planning 11-18 11:32 PM). Each close keeps its own
values: a reopen and a new close store new ones, and the earlier ones are kept. Reports read the latest frozen
value for a closed period and the live value for an open one.

```json
{
  "kpi_id": "kpi_gpm",
  "version": "3",
  "name": "Gross margin",
  "source": {"kind": "formula", "layout_id": "lay_8f3k2", "item_id": "itm_gpm", "layout_name": "P&L by trade (management)"},
  "format": "percent",
  "decimals": 1,
  "over_plan_is": "good",
  "basis": {"method": "accrual", "adjustments": "pre_adjustment"},
  "range_method": "recalculate",
  "active": true,
  "updated_at": "2026-11-18T22:15:40Z"
}
```

- `source.kind`: `group`, `formula` (with `layout_id` and `item_id`) or `measure` (with `measure_id`).
- `basis`: the basis the stored values are computed on (Q24). No dimension or job filters: a KPI is a company
  figure.
- `range_method`: how a quarter, year or total column combines periods: `sum`, `average`, `last` of the
  per-period values, or `recalculate` (computed from the source over the range, live) (Q25).
- `format` and `decimals` as in section 3.4; `over_plan_is` gives the `tone`.
- Saving a KPI never changes values already frozen. A KPI added after a period closed has no frozen value for
  it (Q26).

`get_kpi_values` request: `{"kpi_ids": ["kpi_gpm"], "period_ids": ["per_2026_09", "per_2026_10"]}`

```json
{
  "values": [
    {
      "kpi_id": "kpi_gpm",
      "period_id": "per_2026_09",
      "label": "Sep 2026",
      "state": "frozen",
      "value": "0.3500",
      "display": "35.0%",
      "frozen": {"close_event_id": "pse_118", "closed_at": "2026-10-06T16:40:02Z", "closed_by": {"user_id": "usr_3", "name": "Dana Whitfield"}},
      "history": [
        {"close_event_id": "pse_104", "closed_at": "2026-10-03T18:01:11Z", "value": "0.3412", "display": "34.1%"},
        {"close_event_id": "pse_118", "closed_at": "2026-10-06T16:40:02Z", "value": "0.3500", "display": "35.0%"}
      ],
      "live_now": {"value": "0.3500", "display": "35.0%", "differs": false}
    },
    {
      "kpi_id": "kpi_gpm",
      "period_id": "per_2026_10",
      "label": "Oct 2026",
      "state": "live",
      "value": "0.3500",
      "display": "35.0%",
      "frozen": null,
      "history": []
    }
  ]
}
```

- `state`: `frozen`, `live`, or `not_frozen` (a closed period with no stored value, Q26).
- `history` lists every close of that period, oldest first; `live_now` shows what the value would be today and
  whether it differs (the period History panel, as for the close snapshot). Pages read `differs`, never compare.
- Frozen rows are insert-only, never edited, and written to the audit log (AX4).
- A failed value at close (for example a division by zero) is stored as `null` with its note; it never blocks the
  close.

Amendment 2026-11-19 (owner, area 17 Q13 B and Q14 A): KPI values are also frozen for periods 13 and 14 when the
KPI's basis includes them (period 13 for the gaap, tax and management bases, period 14 for the tax basis; a
measure-sourced KPI freezes months 1-12 only). A year or total column with `range_method` `sum`, `average` or `last`
uses the frozen values of the periods the basis includes that have a value, and leaves a period without one out and
says so. Any failure evaluating a KPI at close, expected or not, is stored as `null` with a note and the close
continues.

---

## 3. Formula engine (item 2)

### 3.1 Tokens

A formula is a flat list of tokens:

| `t` | Fields | Notes |
|---|---|---|
| `ref` | `kind`, `id` | `kind`: `group`, `formula`, `kpi`, `measure` (non-financial), `system`, `column` (records only) |
| `ref` | `kind`, `company_id`, `id` | combined runs only (4.7): `company_group` (`id` = a group item, that company's figure only) or `company_account` (`id` = the account number as it is in that company's chart) |
| `num` | `value` (decimal string) | e.g. `"100"`, `"0.15"` |
| `op` | `op`: `+`, `-`, `*`, `/` | usual precedence |
| `paren` | `p`: `(` or `)` | |

A `kpi` reference (`id` = `kpi_id`, section 2.7) reads the KPI's value for the column: frozen in a closed period,
live in an open one (Q5). System operands (`kind: "system"`): `days_in_period`, `days_in_year`,
`days_elapsed_in_year` (each per column).

Formulas compute on **presented** values: a group's value after its `positive_when` sign, so Revenue − Cost of
sales works with both shown positive (Q4). Division by zero, or a measure with no value for the column, gives
`value: null`, `display: "—"` and a cell `note` ("No kW installed entered for Oct 2026."), never an error.

### 3.2 `validate_formula`

Request (the layout as edited, so unsaved items count):

```json
{
  "layout": {"layout_id": "lay_8f3k2", "kind": "financial", "items": ["... the full items list as edited ..."]},
  "item_id": "itm_gpm",
  "tokens": [
    {"t": "ref", "kind": "formula", "id": "itm_gp"},
    {"t": "op", "op": "/"},
    {"t": "paren", "p": "("},
    {"t": "ref", "kind": "group", "id": "itm_rev"}
  ]
}
```

Result (failure is still `ok: true`: validation is the answer, not an error):

```json
{
  "valid": false,
  "problems": [
    {"position": 2, "message": "This bracket is never closed. Add a closing bracket or remove this one."}
  ],
  "references": [{"kind": "formula", "id": "itm_gp", "name": "Gross profit"}, {"kind": "group", "id": "itm_rev", "name": "Revenue"}],
  "preview_text": "Gross profit ÷ (Revenue"
}
```

`position` is the 0-based token index. Checks: syntax (operands and operators alternate, brackets balance, no
empty formula); every reference exists in the layout and is not a chart; no circular reference, direct or
through other formulas ("Gross margin uses Gross profit, which uses Gross margin. Remove one of these
references."); a deleted item ("This refers to an item that was deleted: Overhead. Remove it."); a `kpi`
reference whose KPI is sourced from this formula, directly or through others, is circular too; a deactivated
KPI is refused ("The KPI Backlog is turned off. Turn it on or remove it."); `company_group` and
`company_account` are refused outside a combined layout; a records formula refers only to columns with a
summary. `save_layout` runs the same checks on every formula and refuses
the save with the first problem per formula (`field: "items[4].tokens[2]"`).

### 3.3 `list_formula_operands`

Request: `{"layout_id": "lay_8f3k2", "item_id": "itm_gpm", "items": [... as edited ...]}`

```json
{
  "groups": [{"id": "itm_rev", "name": "Revenue"}, {"id": "itm_cogs", "name": "Cost of sales"},
             {"id": "itm_cogs_mat", "name": "Cost of sales › Materials"}],
  "formulas": [{"id": "itm_gp", "name": "Gross profit"}],
  "kpis": [{"id": "kpi_backlog", "name": "Backlog", "format": "currency"}, {"id": "kpi_headcount", "name": "Field headcount", "format": "number"}],
  "companies": null,
  "measures": [{"id": "nfm_kw", "name": "kW installed", "unit": "kW"}, {"id": "nfm_sq", "name": "Roof squares", "unit": "squares"}],
  "system": [{"id": "days_in_period", "name": "Days in period"}, {"id": "days_in_year", "name": "Days in year"},
             {"id": "days_elapsed_in_year", "name": "Days so far this year"}],
  "excluded": [{"id": "itm_gpm", "reason": "A formula can't refer to itself."},
               {"id": "kpi_gpm", "reason": "This KPI comes from this formula."}]
}
```

`companies` is `null` outside a combined layout. In one (4.7) it lists each company with its groups and the
accounts that can be referenced:
`[{"company_id": "co_ridge", "name": "Ridgeline Roofing & Solar LLC", "groups": [...], "accounts": [{"display_code":
"4900", "name": "Intercompany revenue"}]}]`.

### 3.4 Formats and the total column

| Field | Values | Meaning |
|---|---|---|
| `format` | `number`, `currency`, `percent`, `ratio` | Currency uses the company currency; percent shows value × 100 with "%"; ratio keeps `value: "1.85"` and displays "1.85 : 1" (Q6) |
| `decimals` | 0-4 | Rounding is the service's (half away from zero), on display only; values stay full precision |
| `total_method` | `calculate`, `sum`, `average`, `last` | Total column: evaluate the formula on the total column's inputs, or sum / average / take the last of the period values |
| `hide_if_zero` | bool | Row omitted when every value column displays zero or "—" |

KPIs keep their own `format`, `decimals` and `range_method` (2.7).

---

## 4. Financial run (item 3)

### 4.1 Request: `run_financial`

```json
{
  "layout_id": "lay_8f3k2",
  "saved_report_id": null,
  "parameters": {
    "dates": {"mode": "preset", "preset": "last_closed_month"},
    "columns": {"mode": "by_period", "range_preset": "this_fiscal_year_to_date", "add_total": true},
    "compare": [{"type": "plan", "plan_version_id": "opv_fy27_orig"}],
    "basis": {"method": "accrual", "adjustments": "gaap"},
    "entity": {"mode": "company"},
    "filters": {"dimensions": [], "project_ids": [], "cost_code_ids": [], "contact_ids": []},
    "reclass_view": "as_reclassed"
  }
}
```

- `dates.mode`: `preset` (`this_month`, `last_month`, `last_closed_month`, `this_quarter`, `last_quarter`,
  `quarter_to_date`, `this_fiscal_year`, `fiscal_year_to_date`, `last_fiscal_year`, `last_12_months`) or `fixed`
  (`{"from": "2026-07-01", "to": "2026-10-31"}`) or `periods` (`{"period_ids": [...]}`). Presets are resolved
  with `context.today` and the fiscal calendar; `last_closed_month` is the latest closed month period (L1).
- `columns.mode`: `single_period` (one column for the whole date range), `by_period` (one column per month
  period in the range), `by_quarter`, `by_year`. `add_total` adds a total column (formulas follow
  `total_method`). A balance sheet column is the balance **as of** the column's end date.
- `compare`: up to 2 of `{"type": "prior_period"}`, `{"type": "prior_year"}`, `{"type": "plan",
  "plan_version_id": "..."}`. Each adds a compare column and a variance column (amount and percent) per value
  column, or only beside the total when `columns.mode` is not `single_period` (Q13).
- `basis.method`: `accrual` or `cash` (CB1; the company default fills it). `basis.adjustments`:
  `pre_adjustment` (periods 1-12), `gaap` (1-13), `tax` (1-14), `management` (1-13 without
  `is_tax_strategy_only` accounts) (A1, `periods.BASES`). While "Adjustment periods" is off (S4), the only
  value offered is `pre_adjustment` and periods 13 and 14 never appear. With it on, a fiscal year column whose
  basis includes 13 or 14 includes their entries; `columns.show_adjustment_periods: true` adds them as their own
  columns after period 12 ("P13 Audit adj.", "P14 Tax adj.").
- `entity.mode`: `company` (the file's own books; `journal_line.entity_id` NULL or all), `entities`
  (`entity_ids`), or `consolidated` (planned; refused until consolidation is built: "Consolidated reports are not
  available yet."). Combining separate company files is a different call, `run_combined` (4.7, Q14).
- `filters`: dimension values (`include_children` follows `dimension_value.parent_value_id`), jobs, cost codes,
  customers or vendors. A job filter matches lines by `journal_line.project_id`; dimensions come from
  `journal_line_dimension` (JD1 already fixed them at posting).
- `reclass_view`: `as_reclassed` (default) or `full_trail` (section 4.4).

### 4.2 Result

```json
{
  "report": {
    "title": "P&L by trade (management)",
    "subtitle": "Jul 2026 – Oct 2026 · Accrual · GAAP/Audited · As reclassed",
    "basis_label": "Accrual basis · GAAP/Audited (periods 1-13)",
    "company": "Ridgeline Roofing & Solar LLC",
    "currency": "USD",
    "generated_at": "2026-11-19T14:05:00Z",
    "resolved_dates": {"preset": "fiscal_year_to_date", "from": "2026-07-01", "to": "2026-10-31",
                       "label": "FY2027 to date (Jul – Oct 2026)"},
    "includes_open_periods": true,
    "notices": [{"severity": "low", "message": "October 2026 is still open, so its figures can change."}]
  },
  "columns": [
    {"column_id": "c_2026_07", "label": "Jul 2026", "kind": "actual", "from": "2026-07-01", "to": "2026-07-31", "closed": true},
    {"column_id": "c_2026_08", "label": "Aug 2026", "kind": "actual", "from": "2026-08-01", "to": "2026-08-31", "closed": true},
    {"column_id": "c_2026_09", "label": "Sep 2026", "kind": "actual", "from": "2026-09-01", "to": "2026-09-30", "closed": true},
    {"column_id": "c_2026_10", "label": "Oct 2026", "kind": "actual", "from": "2026-10-01", "to": "2026-10-31", "closed": false},
    {"column_id": "c_total", "kind": "total", "label": "Total", "from": "2026-07-01", "to": "2026-10-31"},
    {"column_id": "c_plan", "kind": "compare", "label": "Plan", "compare": {"type": "plan", "plan_version_id": "opv_fy27_orig", "name": "FY2027 Original"}, "beside": "c_total"},
    {"column_id": "c_var", "kind": "variance", "label": "Variance vs plan", "of": ["c_total", "c_plan"]},
    {"column_id": "c_var_pct", "kind": "variance_percent", "label": "Var %", "of": ["c_total", "c_plan"]}
  ],
  "rows": [
    {
      "row_id": "r_itm_rev",
      "item_id": "itm_rev",
      "type": "group_header",
      "depth": 0,
      "label": "Revenue",
      "collapsed": false
    },
    {
      "row_id": "r_acc_4000",
      "item_id": "itm_rev",
      "type": "account",
      "depth": 1,
      "label": "4000 Contract revenue",
      "account_id": "acc_4000",
      "cells": {
        "c_2026_07": {"value": {"amount": "96500.00", "currency": "USD"}, "display": "96,500.00", "drill": "dh_a1"},
        "c_2026_08": {"value": {"amount": "104250.00", "currency": "USD"}, "display": "104,250.00", "drill": "dh_a2"},
        "c_2026_09": {"value": {"amount": "88900.00", "currency": "USD"}, "display": "88,900.00", "drill": "dh_a3"},
        "c_2026_10": {"value": {"amount": "91350.00", "currency": "USD"}, "display": "91,350.00", "drill": "dh_a4", "reclassed": true},
        "c_total":   {"value": {"amount": "381000.00", "currency": "USD"}, "display": "381,000.00", "drill": "dh_a5"},
        "c_plan":    {"value": {"amount": "372000.00", "currency": "USD"}, "display": "372,000.00", "drill": "dh_p1"},
        "c_var":     {"value": {"amount": "9000.00", "currency": "USD"}, "display": "9,000.00", "tone": "good", "drill": null},
        "c_var_pct": {"value": "0.0242", "display": "2.4%", "tone": "good", "drill": null}
      }
    },
    {
      "row_id": "r_acc_4100",
      "item_id": "itm_rev",
      "type": "account",
      "depth": 1,
      "label": "4100 Service and repair revenue",
      "account_id": "acc_4100",
      "cells": {
        "c_2026_07": {"value": {"amount": "7200.00", "currency": "USD"}, "display": "7,200.00", "drill": "dh_b1"},
        "c_2026_08": {"value": {"amount": "8100.00", "currency": "USD"}, "display": "8,100.00", "drill": "dh_b2"},
        "c_2026_09": {"value": {"amount": "7650.00", "currency": "USD"}, "display": "7,650.00", "drill": "dh_b3"},
        "c_2026_10": {"value": {"amount": "8550.00", "currency": "USD"}, "display": "8,550.00", "drill": "dh_b4"},
        "c_total":   {"value": {"amount": "31500.00", "currency": "USD"}, "display": "31,500.00", "drill": "dh_b5"},
        "c_plan":    {"value": {"amount": "36000.00", "currency": "USD"}, "display": "36,000.00", "drill": "dh_p2"},
        "c_var":     {"value": {"amount": "-4500.00", "currency": "USD"}, "display": "(4,500.00)", "tone": "bad", "drill": null},
        "c_var_pct": {"value": "-0.1250", "display": "(12.5%)", "tone": "bad", "drill": null}
      }
    },
    {
      "row_id": "r_itm_rev_total",
      "item_id": "itm_rev",
      "type": "group_total",
      "depth": 0,
      "label": "Total Revenue",
      "cells": {
        "c_total": {"value": {"amount": "412500.00", "currency": "USD"}, "display": "412,500.00", "drill": "dh_g1"},
        "c_plan":  {"value": {"amount": "408000.00", "currency": "USD"}, "display": "408,000.00", "drill": "dh_p3"},
        "c_var":   {"value": {"amount": "4500.00", "currency": "USD"}, "display": "4,500.00", "tone": "good", "drill": null},
        "c_var_pct": {"value": "0.0110", "display": "1.1%", "tone": "good", "drill": null}
      }
    },
    {
      "row_id": "r_itm_gpm",
      "item_id": "itm_gpm",
      "type": "formula",
      "depth": 0,
      "label": "Gross margin",
      "format": "percent",
      "cells": {
        "c_total": {"value": "0.3500", "display": "35.0%", "drill": null, "explain": "Gross profit 144,375.00 ÷ Revenue 412,500.00"},
        "c_plan":  {"value": "0.3400", "display": "34.0%", "drill": null}
      }
    }
  ],
  "kpis": [
    {"kpi_id": "kpi_rev", "item_id": "itm_rev", "label": "Revenue", "column_id": "c_total",
     "value": {"amount": "412500.00", "currency": "USD"}, "display": "$412,500.00", "range_method": "sum",
     "periods": [{"column_id": "c_2026_07", "state": "frozen"}, {"column_id": "c_2026_08", "state": "frozen"},
                 {"column_id": "c_2026_09", "state": "frozen"}, {"column_id": "c_2026_10", "state": "live"}],
     "compare_display": "Plan $408,000.00", "tone": "good"},
    {"kpi_id": "kpi_gpm", "item_id": "itm_gpm", "label": "Gross margin", "column_id": "c_total",
     "value": "0.3500", "display": "35.0%", "range_method": "recalculate",
     "periods": [{"column_id": "c_2026_07", "state": "frozen"}, {"column_id": "c_2026_08", "state": "frozen"},
                 {"column_id": "c_2026_09", "state": "frozen"}, {"column_id": "c_2026_10", "state": "live"}],
     "compare_display": "Plan 34.0%", "tone": "good"}
  ],
  "charts": [
    {
      "chart_id": "itm_chart1",
      "name": "Revenue and gross profit",
      "chart_type": "bar",
      "column": 1,
      "categories": [{"column_id": "c_2026_07", "label": "Jul 2026"}, {"column_id": "c_2026_08", "label": "Aug 2026"},
                     {"column_id": "c_2026_09", "label": "Sep 2026"}, {"column_id": "c_2026_10", "label": "Oct 2026"}],
      "series": [
        {"item_id": "itm_rev", "label": "Revenue", "points": ["103700.00", "112350.00", "96550.00", "99900.00"]},
        {"item_id": "itm_gp", "label": "Gross profit", "points": ["36295.00", "39322.50", "33792.50", "34965.00"]}
      ],
      "format": "currency"
    }
  ]
}
```

Notes:
- Cells are keyed by `column_id`; a missing key means "no value shown" (headers, charts). `value` is money for
  currency items and a decimal string otherwise; `display` already has the sign rule, parentheses and decimals.
- `tone` (`good`, `bad`, `neutral`) comes from the item's `over_plan_is` and the variance sign. Pages colour
  by `tone` only; they never compare numbers (rule e).
- `explain` is the R37 "(i)" text for a calculated cell.
- Collapsed groups come with their account rows and `collapsed: true`; expanding is a display preference.
- Hidden groups are computed (formulas can use them) and not returned as rows.
- Chart points are plain decimal strings in the chart's `format`, for the chart component only.
- `kpis` lists the active KPIs whose source is in this layout (2.7). A KPI's period values are frozen for closed
  periods and live for open ones, so a KPI tile can differ from its row when the layout or a measure changed
  after a close; `periods[].state` says which values were used. Rows are always computed live from the ledger
  (closed ledger periods never change; section 0).

### 4.3 Drill-down (R35): `drill`

Every amount cell from the ledger or the plan carries `drill`, an opaque handle. It encodes the resolved
query (account ids, period ids or date range, basis, entity, filters, reclass view), not the layout, so it stays
valid after the layout changes. The service re-authorizes on every use; a handle is never trusted to grant
anything. Formula and variance cells have `drill: null` (their `explain` names the inputs, each of which can be
drilled on its own row).

Request: `{"drill": "dh_a4", "limit": 100, "cursor": null}` → `drill_financial` result:

```json
{
  "title": "4000 Contract revenue · Oct 2026 · Accrual · GAAP/Audited · As reclassed",
  "total": {"amount": "91350.00", "currency": "USD"},
  "total_display": "91,350.00",
  "rows": [
    {
      "line_ref": "jl_77120",
      "date": "2026-10-06",
      "display_number": "INV-0391",
      "source_type": "invoice",
      "name": "Brennan residence",
      "memo": "Re-roof, pay app 7",
      "account": {"account_id": "acc_4000", "display_code": "4000", "name": "Contract revenue"},
      "job": {"project_id": "prj_ri1_002", "display_number": "RI0001-002"},
      "cost_code": {"cost_code_id": "cc_07_310", "display_code": "07-310", "name": "Shingles"},
      "dimensions": [{"type": "Profit center", "value": "Residential"}],
      "amount": {"amount": "42800.00", "currency": "USD"},
      "amount_display": "42,800.00",
      "link": {"kind": "invoice", "id": "inv_391", "line_id": "invl_1180"},
      "entry_link": {"kind": "journal_entry", "id": "je_412", "display_number": "JE-000412"}
    },
    {
      "line_ref": "jl_77355",
      "date": "2026-09-22",
      "display_number": "INV-0377",
      "source_type": "invoice",
      "name": "Okafor commercial",
      "memo": "Solar install deposit",
      "account": {"account_id": "acc_4000", "display_code": "4000", "name": "Contract revenue"},
      "job": {"project_id": "prj_pa6_002", "display_number": "PA0006-002"},
      "amount": {"amount": "6500.00", "currency": "USD"},
      "amount_display": "6,500.00",
      "reclass": {"from": "4100 Service and repair revenue", "to": "4000 Contract revenue", "by": "Dana Whitfield",
                  "at": "2026-10-03T17:12:00Z", "reason": "Deposit belongs to the install contract",
                  "reclass_entry": {"kind": "journal_entry", "id": "je_405", "display_number": "JE-000405"}},
      "link": {"kind": "invoice", "id": "inv_377", "line_id": "invl_1102"}
    }
  ],
  "next_cursor": "cur_2"
}
```

`link` is the R35 target: the page opens that record scrolled to `line_id`. Kinds: `invoice`, `bill`,
`credit_memo`, `vendor_credit`, `payment`, `journal_entry`, `pay_app`, `pull_ticket`, `receipt`, and later
documents as they are built. A plan cell drills to the plan version's lines for that account and month
(`link.kind: "plan_line"`).

### 4.4 "As reclassed" and full trail

Reclass entries (area 10; `journal_entry.source = 'Reclass'`, one line pair per original line carrying the
original's ids and details) are handled like this (12:45 AM: applies from the reclass entry's date on; earlier
periods keep the original account):

- **Amounts never differ between the two views.** Each cell is the GL total for its accounts and dates, so period
  totals match the GL, closed periods and the close snapshot never change, and the period balance summary
  (4.6) serves both views.
- **`as_reclassed` changes the detail rows.** In a drill (and in transaction-detail reports), a reclass line pair
  is shown as the original line: in the reclass entry's period, under the new account, job and dimensions, with
  the original's date, name, memo and amount and a `reclass` tag; the "out" side under the old account shows as
  one row tagged "Moved to 4000" with a negative amount. When the drill range contains both the original line and
  its reclass, the original and both reclass lines collapse into one row under the latest account (their net is
  the same). Chains of reclasses follow to the latest one inside the range.
- **Grouping by name, job and item** (vendor, customer, job and item reports) uses the original's details, which
  the reclass lines carry, so the two views group the same lines alike.
- **`full_trail`** returns every line as posted, reclass lines included, tagged `source_type: "reclass"`.
- A cell holding reclassed lines has `reclassed: true` (the page shows the "Reclassed" tag).

This is planning's reading of "period totals match the GL" with "each original line once, reclass lines
hidden"; Q1 asks the owner to confirm it.

### 4.5 money.view and the other checks

- `run_financial` and `drill_financial` need `report.financial` **and** `money.view` (Q7). Without either, the
  call is refused before any read with a plain sentence ("You can't run financial reports. Ask an Admin to give
  you access to reports."), and the code goes to `access_event` only (R27).
- A job cost layout needs `report.job_cost`; project scope (MR3) limits rows to assigned jobs, and the report says
  so in `notices` ("Showing your assigned jobs only.").
- The Agent origin may run reports (the `report.*` codes are in `AGENT_ALLOWED`) under the same checks (G7).

### 4.6 Staying fast: the period balance summary

Reading every `journal_line` for each cell is fine for a small file and too slow for a 12-column P&L with a plan
comparison on a few hundred thousand lines. Plan:

1. **`ledger_period_balance`**: one row per (period, account, entity, job, cost code, dimension set) holding
   `debit_cents`, `credit_cents` and `line_count`. Written only by `ledger.py` (rule 7), in the posting
   transaction, as an increment of the posted lines. Posted lines never change (RP2) and corrections are new
   entries, so the summary is increment-only: no updates on edit, no deletes.
2. **`dimension_set`**: a row per distinct combination of `journal_line_dimension` values, so the summary key stays
   one column. Posting looks up or adds the set.
3. **Reads.** A month or year cell sums summary rows for its period ids (`period_ids_for_basis` already gives the
   basis's periods). A balance sheet as-of cell sums every period up to the column's end. A date range not on
   period boundaries uses the summary for whole periods and `journal_line` for the partial ends.
4. **Checked, not trusted.** `ledger.verify` (and a close check) compares the summary with `journal_line` per
   period; a rebuild tool (`tools/`) re-derives it. A mismatch is an integrity alert, never a silent fix.
5. **Cash basis (CB1)** cannot come from the accrual summary: cash recognition follows payment application
   dates prorated across document lines. For v1 it is computed at run time from payments and allocations for the
   requested range (Q9); a cash summary is a later option if it proves slow.
6. **Plan and measures** are small tables read directly (`operating_plan_line`, `nonfinancial_value`).
7. **Indexes**: `journal_entry (period_id, is_posted)` for the partial-period and drill paths.
8. Budget for the 2.9 tests (Q10 A): a 12-column P&L with plan on 250,000 posted lines in under 1 second on the
   reference laptop.
9. **KPIs**: closed periods read the stored frozen value (`kpi_value`, 2.7), so a KPI tile over closed months
   needs no ledger read; open periods compute live through the same summary.

### 4.7 Combined run across company files (Q14, owner 2026-11-19)

One report across several company files: each company's figures are computed by its own file's services, then
combined. There is no automatic consolidation and no automatic elimination; eliminations are formula rows that
use the per-company operands (3.1). Consolidation within one file (`company_entity`) stays separate and planned.

**Who can run it.** The picker (`list_combinable_companies`) offers only companies the user can open in this
sign-in: an active access row (MR2; Deny wins), not archived, holding both `report.financial` and `money.view` in
that company. `run_combined` checks each chosen company again, in its own file (one `ServiceContext` per
company), before reading anything; if one fails, the whole run is refused, naming the company ("You can't run
financial reports in Ridgeline Solar LLC. Remove it from the report or ask its Admin for access."). It never
drops a company silently.

`list_combinable_companies` result:

```json
{
  "companies": [
    {"company_id": "co_ridge", "name": "Ridgeline Roofing & Solar LLC", "currency": "USD", "fiscal_year_start": "07", "is_current": true},
    {"company_id": "co_rsolar", "name": "Ridgeline Solar Leasing LLC", "currency": "USD", "fiscal_year_start": "07", "is_current": false}
  ],
  "not_offered_count": 1,
  "not_offered_message": "1 company isn't listed because you can't run financial reports there."
}
```

**Request** (`run_combined`). The layout lives in the current company's file and has `"scope": "combined"`; its
groups name accounts by the current company's chart.

```json
{
  "layout_id": "lay_combo_pl",
  "company_ids": ["co_ridge", "co_rsolar"],
  "parameters": {
    "dates": {"mode": "preset", "preset": "last_closed_month"},
    "columns": {"mode": "single_period"},
    "compare": [{"type": "prior_year"}],
    "basis": {"method": "accrual", "adjustments": "pre_adjustment"},
    "reclass_view": "as_reclassed"
  },
  "account_matching": "by_number"
}
```

Not in a combined run (refused with a sentence): dimension, job, cost code and contact filters, and `entities`
(those ids belong to one file), and plan comparisons (Q23 A). Prior period and prior year comparisons are allowed.

**How it is computed.**
1. For each company, map the layout's accounts to that company's chart by account number (Q19 B). An account of
   that company with activity whose number is not in the current company's chart is **unmatched**: it shows as
   its own account row, labelled with its company, under the group whose `auto_include` rule its number or type
   fits, or under a "Not in any group" group at the end when none fits. It counts in that group's total and in
   the report totals. The run returns a warning listing every unmatched account (company, number, name,
   amount).
2. Each company runs the layout through its own `run_financial` (its own period summary, basis, periods and
   reclass rules), so a company column equals that company's own report.
3. The service adds the company columns into the **Combined** column, so the combined total always equals the
   sum of the companies. Currencies must all match, or the run is refused: "These companies use different
   currencies (USD and PHP). Pick companies with the same currency." (Q20 A). Dates resolve on the current
   company's calendar and apply to each company by calendar date; when fiscal year starts differ only
   calendar-month columns are allowed, and the basis must be pre-adjustment unless every company has adjustment
   periods on (Q22 A).
4. Formulas are evaluated per column on that column's values. A formula that uses `company_group` or
   `company_account` is evaluated only in the Combined column (and its compare), and shows "—" in the
   company columns.

**Result**: the section 4.2 shape, with company columns and a Combined column. The sample shows one unmatched
account under Revenue (its 3,200.00 is inside Ridgeline Solar Leasing's 18,400.00 revenue total) and an
elimination row:

```json
{
  "report": {"title": "Group P&L", "subtitle": "Oct 2026 · Accrual · Pre-adjustment · 2 companies, not consolidated",
             "currency": "USD", "generated_at": "2026-11-19T14:22:10Z",
             "companies": [{"company_id": "co_ridge", "name": "Ridgeline Roofing & Solar LLC"}, {"company_id": "co_rsolar", "name": "Ridgeline Solar Leasing LLC"}],
             "notices": [{"severity": "medium", "message": "1 account isn't in this company's chart: Ridgeline Solar Leasing LLC 4950 Lease income (3,200.00). It is shown under Revenue and counted in the totals."}]},
  "unmatched_accounts": [{"company_id": "co_rsolar", "display_code": "4950", "name": "Lease income", "group_item_id": "itm_rev",
                          "amount": {"amount": "3200.00", "currency": "USD"}, "amount_display": "3,200.00"}],
  "columns": [
    {"column_id": "c_co_ridge", "kind": "company", "company_id": "co_ridge", "label": "Ridgeline Roofing & Solar"},
    {"column_id": "c_co_rsolar", "kind": "company", "company_id": "co_rsolar", "label": "Ridgeline Solar Leasing"},
    {"column_id": "c_combined", "kind": "combined", "label": "Combined"}
  ],
  "rows": [
    {"row_id": "r_unm_co_rsolar_4950", "item_id": "itm_rev", "type": "account", "depth": 1, "unmatched": true,
     "company_id": "co_rsolar", "label": "4950 Lease income (Ridgeline Solar Leasing LLC, not in this chart)",
     "cells": {
       "c_co_ridge":  {"value": null, "display": "—", "drill": null},
       "c_co_rsolar": {"value": {"amount": "3200.00", "currency": "USD"}, "display": "3,200.00", "drill": "dh_c4"},
       "c_combined":  {"value": {"amount": "3200.00", "currency": "USD"}, "display": "3,200.00", "drill": "dh_c5"}}},
    {"row_id": "r_itm_rev_total", "item_id": "itm_rev", "type": "group_total", "depth": 0, "label": "Total Revenue",
     "cells": {
       "c_co_ridge":  {"value": {"amount": "99900.00", "currency": "USD"}, "display": "99,900.00", "drill": "dh_c1"},
       "c_co_rsolar": {"value": {"amount": "18400.00", "currency": "USD"}, "display": "18,400.00", "drill": "dh_c2"},
       "c_combined":  {"value": {"amount": "118300.00", "currency": "USD"}, "display": "118,300.00", "drill": "dh_c3"}}},
    {"row_id": "r_itm_elim", "item_id": "itm_elim", "type": "formula", "depth": 0, "label": "Less intercompany lease revenue",
     "cells": {
       "c_co_ridge":  {"value": null, "display": "—", "drill": null},
       "c_co_rsolar": {"value": null, "display": "—", "drill": null},
       "c_combined":  {"value": {"amount": "-2500.00", "currency": "USD"}, "display": "(2,500.00)", "drill": null,
                       "explain": "− Ridgeline Solar Leasing LLC account 4900 Intercompany revenue 2,500.00"}}}
  ],
  "kpis": [],
  "charts": []
}
```

The elimination row's tokens: `[{"t": "op", "op": "-"}, {"t": "ref", "kind": "company_account", "company_id":
"co_rsolar", "id": "4900"}]` (a leading minus is allowed).

**Drill.** A company cell's handle carries its company; `drill_combined` re-checks access in that file and
returns that company's rows. A Combined cell returns every company's rows, each with `company` and a `link` that
includes `company_id` (opening it switches company through the shell). KPIs are not combined in v1 (`kpis` is
empty). Export and the R34 PDF take the `run_combined` request. A combined report can be saved in the current
company, with its company list, and added to packs; it cannot be scheduled in v1 (Q21 A).

---

## 5. Records sources and runs (item 4)

### 5.1 `list_sources`

Sources are defined in code (a catalogue), not by users. Each names its base table, its fixed joins along
existing foreign keys and the fields it exposes.

```json
{
  "sources": [
    {"source_id": "src_leads", "name": "Leads", "console": "crm", "base": "lead", "joins": []},
    {"source_id": "src_leads_estimates", "name": "Leads with estimates", "console": "crm", "base": "lead",
     "joins": [{"to": "estimate", "on": "estimate.lead_id = lead.lead_id", "type": "left", "cardinality": "many"}],
     "row_grain": "one row per estimate, or one per lead without an estimate"},
    {"source_id": "src_estimates", "name": "Estimates", "console": "crm", "base": "estimate", "joins": []},
    {"source_id": "src_activities", "name": "Activities", "console": "crm", "base": "activity", "joins": []},
    {"source_id": "src_jobs", "name": "Jobs", "console": "pm", "base": "project", "joins": []},
    {"source_id": "src_job_stages", "name": "Job stage history (time in stage)", "console": "pm", "base": "project_stage_history", "joins": []},
    {"source_id": "src_jobs_cancelled", "name": "Jobs cancelled (stage and reason)", "console": "pm", "base": "project", "joins": [], "fixed_filter": "status = Cancelled"},
    {"source_id": "src_cases", "name": "Service cases with status history", "console": "pm", "base": "service_case", "joins": []},
    {"source_id": "src_lead_job_invoices", "name": "Lead → Job → Invoices and payments", "console": "cross", "base": "lead",
     "joins": [{"to": "project"}, {"to": "invoice"}, {"to": "payment_allocation"}]},
    {"source_id": "src_rep_contract_payments", "name": "Sales rep → Contracts → Payments", "console": "cross", "base": "contract",
     "joins": [{"to": "payment_allocation"}]}
  ]
}
```

Join `on` text is for planning review only; the page receives `source_id`, `name`, `console` and `row_grain`.
Most base tables do not exist yet (section 12).

### 5.2 `list_source_fields`

Request: `{"source_id": "src_leads_estimates"}`

```json
{
  "source_id": "src_leads_estimates",
  "fields": [
    {"field_id": "lead.lead_id", "label": "Lead", "type": "record", "money": false, "custom": false, "groupable": false, "summaries": ["count"]},
    {"field_id": "lead.created_on", "label": "Created", "type": "date", "money": false, "custom": false, "groupable": true, "buckets": ["day", "week", "month", "quarter", "year"], "summaries": ["count", "min", "max"]},
    {"field_id": "lead.status", "label": "Status", "type": "choice", "choices": ["New", "Contacted", "Estimate sent", "Closed · Won", "Closed · Lost"], "money": false, "custom": false, "groupable": true, "summaries": ["count"]},
    {"field_id": "lead.sales_rep", "label": "Sales rep", "type": "person", "money": false, "custom": false, "groupable": true, "summaries": ["count"]},
    {"field_id": "lead.source", "label": "Lead source", "type": "choice", "money": false, "custom": false, "groupable": true, "summaries": ["count"]},
    {"field_id": "lead.days_in_stage", "label": "Days in current stage", "type": "duration_days", "money": false, "custom": false, "groupable": false, "summaries": ["avg", "min", "max"]},
    {"field_id": "estimate.total", "label": "Estimate total", "type": "money", "money": true, "custom": false, "groupable": false, "summaries": ["sum", "avg", "min", "max", "count"]},
    {"field_id": "cf.lead.roof_pitch", "label": "Roof pitch", "type": "choice", "money": false, "custom": true, "groupable": true, "summaries": ["count"]},
    {"field_id": "cf.lead.system_size_kw", "label": "System size (kW)", "type": "number", "money": false, "custom": true, "groupable": false, "summaries": ["sum", "avg", "min", "max", "count"]}
  ],
  "hidden_notice": null
}
```

Types: `text`, `number`, `money`, `date`, `datetime`, `bool`, `choice`, `person`, `record`, `duration_days`.
Custom fields come from `custom_field_def` (`Text`, `Number`, `Money`, `Date`, `Yes/No`, `Choice`; a `Money`
custom field has `money: true`). Stage durations come from the append-only history tables, not current status
(11-18 item 3). For a viewer without `money.view`, money fields are left out of `fields` and
`hidden_notice` reads "Money fields are hidden for your role."

### 5.3 `run_records`

Request: `{"layout_id": "lay_r_winrate", "saved_report_id": null, "parameters": {"dates": {"mode": "preset",
"preset": "last_12_months"}, "date_field_id": "lead.created_on", "filters": []}, "limit": 200, "cursor": null}`

```json
{
  "report": {
    "title": "Win rate by sales rep",
    "source": "Leads with estimates",
    "generated_at": "2026-11-19T14:07:41Z",
    "resolved_dates": {"from": "2025-12-01", "to": "2026-11-30", "label": "Last 12 months (Dec 2025 – Nov 2026)"},
    "notices": [{"severity": "low", "message": "Showing your own leads only."}]
  },
  "columns": [
    {"column_id": "col_rep", "label": "Sales rep", "format": null},
    {"column_id": "col_closed", "label": "Closed leads", "format": "number"},
    {"column_id": "col_won", "label": "Won", "format": "number"},
    {"column_id": "col_value", "label": "Signed value", "format": "currency"},
    {"column_id": "col_rate", "label": "Win rate", "format": "percent"}
  ],
  "groups": [
    {
      "group_key": "g_usr_7",
      "level": 1,
      "field_id": "lead.sales_rep",
      "label": "Luis Ortega",
      "summaries": {
        "col_closed": {"value": "38", "display": "38"},
        "col_won": {"value": "14", "display": "14"},
        "col_value": {"value": {"amount": "512400.00", "currency": "USD"}, "display": "$512,400.00"},
        "col_rate": {"value": "0.3684", "display": "36.8%", "explain": "Won 14 ÷ Closed leads 38"}
      },
      "drill": "dr_g1",
      "children": [
        {"group_key": "g_usr_7_2026q3", "level": 2, "field_id": "lead.created_on", "label": "Q1 FY2027 (Jul – Sep 2026)",
         "summaries": {"col_closed": {"value": "11", "display": "11"}, "col_won": {"value": "5", "display": "5"},
                       "col_value": {"value": {"amount": "186900.00", "currency": "USD"}, "display": "$186,900.00"},
                       "col_rate": {"value": "0.4545", "display": "45.5%"}},
         "drill": "dr_g1_1", "children": []}
      ]
    }
  ],
  "rows": null,
  "totals": {
    "col_closed": {"value": "38", "display": "38"},
    "col_won": {"value": "14", "display": "14"},
    "col_value": {"value": {"amount": "512400.00", "currency": "USD"}, "display": "$512,400.00"},
    "col_rate": {"value": "0.3684", "display": "36.8%"}
  },
  "charts": [{"chart_id": "ch_1", "chart_type": "bar", "categories": [{"group_key": "g_usr_7", "label": "Luis Ortega"}],
              "series": [{"column_id": "col_rate", "label": "Win rate", "points": ["0.3684"]}], "format": "percent"}],
  "next_cursor": null
}
```

- With `group_by` the result has `groups` (nested to 3 levels) and `rows: null`; a group's `drill` returns its
  rows. Without grouping, `rows` is a page of records: `{"row_key": "...", "cells": {"col_x": {"value": ...,
  "display": "..."}}, "link": {"kind": "lead", "id": "ld_118"}}`, and `next_cursor` pages them.
- Every row carries `link` (R35); a grouped row drill (`drill_records`, request `{"drill": "dr_g1", "limit",
  "cursor"}`) returns the same row shape.

### 5.4 Row limits and money.view (applied by the service, never the page)

- The service builds the query, then adds the viewer's row limits **before** grouping and summarising, so
  totals count only rows the viewer may see: project scope (MR3) on job-based sources; own-records limits by
  role (e.g. a Sales rep sees own leads unless granted the proposed `lead.own` alternative, area 18 2.2 and area
  15); contact sides (area 18 Q11) on sources that show customers or vendors.
- Without `money.view` (Q15 B, owner 2026-11-19): a records report that uses a money field anywhere (a column,
  a filter, a sort, a group-by, or a formula column that uses one) is **refused before the query runs**, with
  `kind: "permission"` and the message "This report uses money fields your role can't see." Nothing is
  dropped or partly shown. Building a report, the field catalogue (5.2) leaves money fields out, so such a viewer
  can only build reports without them.
- The same applies to drills, exports, PDFs, packs and scheduled runs: they run the same service, as the viewer
  (in a pack, the refused report is listed in `skipped` with that sentence and the rest of the pack renders).

---

## 6. Non-financial measures (item 5)

### 6.1 Measure definition

```json
{
  "measure_id": "nfm_kw",
  "version": "4",
  "name": "kW installed",
  "unit": "kW",
  "decimals": 1,
  "aggregate_over_periods": "sum",
  "source": {
    "type": "from_jobs",
    "rule": {"source_id": "src_jobs", "summary": "sum", "field_id": "cf.project.system_size_kw",
             "date_field_id": "project.completed_on",
             "filters": [{"field_id": "project.job_type", "op": "in", "values": ["Solar"]}]}
  },
  "active": true
}
```

- `source.type`: `typed` (entered or imported only) or `from_jobs` (derived monthly by the rule; typed values
  for a month override the derived one, 11-18 item 6).
- `aggregate_over_periods`: `sum` (kW installed), `average` or `last` (headcount): how a quarter, year or total
  column combines the months.
- Services: `list_measures`, `get_measure`, `save_measure` (version), `deactivate_measure` (refused while a layout
  formula uses it, with the layout names). Permission: `report.design`.

### 6.2 Values by month: `get_measure_values` / `save_measure_values`

```json
{
  "measure_id": "nfm_kw",
  "fiscal_year": "FY2027",
  "values": [
    {"period_id": "per_2026_07", "label": "Jul 2026", "derived": "42.6", "typed": null, "value": "42.6", "display": "42.6", "origin": "from_jobs", "version": "1"},
    {"period_id": "per_2026_08", "label": "Aug 2026", "derived": "38.0", "typed": "39.2", "value": "39.2", "display": "39.2", "origin": "typed",
     "entered_by": {"user_id": "usr_3", "name": "Dana Whitfield"}, "entered_at": "2026-09-03T15:22:10Z", "version": "2"},
    {"period_id": "per_2026_09", "label": "Sep 2026", "derived": null, "typed": null, "value": null, "display": "—", "origin": null, "version": null}
  ]
}
```

Save request: `{"measure_id": "nfm_kw", "values": [{"period_id": "per_2026_08", "typed": "39.2", "version":
"1"}]}`; `typed: null` clears the typed value (the derived one shows again). Each change writes the audit log
with before and after (AX4).

**Closed periods (Q16 B, owner 2026-11-19).** Typed values are locked with their period: a save for a closed
period is refused with `kind: "period_closed"` ("Sep 2026 is closed, so its values can't be changed. Reopen the
period first."), and each value row in `get_measure_values` carries `"locked": true` and `"locked_reason"` for
the R37 locked look. After a reopen the value can be changed again, and the change is logged. Derived values
follow the same rule: they are recomputed only for open periods and keep the value they had when the period
closed (so a closed period's figures never move).

### 6.3 Import (all-or-nothing, like every CSV upload)

1. `measure_import_template` → `{"file": {handle...}}` (CSV/Excel: one row per measure, one column per month of
   the chosen fiscal year).
2. `measure_import_preview` `{"file_handle": "fh_up_91", "fiscal_year": "FY2027"}` →
   `{"preview_id": "mip_5", "rows": [{"measure": "kW installed", "values": [...]}], "errors": [{"row": 4,
   "column": "Oct 2026", "message": "\"forty\" is not a number. Enter a number such as 40."}], "can_import":
   false}`. A value for a closed period is an error row too ("Sep 2026 is closed. Leave its column empty or
   reopen the period.") (Q16 B).
3. `measure_import_commit` `{"preview_id": "mip_5"}` → `{"imported_values": 36}`; refused while `errors` is not
   empty.

### 6.4 Fill from jobs

`refresh_derived_measures` `{"measure_ids": ["nfm_kw"], "period_ids": [...]}` recomputes derived values for open
periods only (also run on every report run for open periods; closed periods are skipped, Q16 B). Result:
`{"updated": [{"measure_id": "nfm_kw", "period_id": "per_2026_10", "derived": "51.3"}]}`. The rule runs through the records engine (section 5),
with the same row rules: a derived value is a company figure, computed with no row limits (Q17 A).

Amendment 2026-11-19 (owner, area 17 Q16 A): derived measure values are computed live for an open period and are
**not stored by a read**: `refresh_derived_measures` is not run by a report run. The period close stores the derived
value of each measure for the closing period, in the close transaction; a closed period then keeps that value.

---

## 7. Output (item 6)

### 7.1 Excel: `export_excel`

Request: the same object as a run (`run_financial` or `run_records` request) plus `{"options":
{"include_drill_sheet": false}}`. Needs `report.export` as well as the run's permissions. The service re-runs the
report (exports are not built from page data) and writes the workbook through `storage.py`.

```json
{
  "file": {"handle": "fh_x_20261119_1", "name": "P&L by trade - FY2027 to date.xlsx",
           "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "size_bytes": 48211},
  "generated_at": "2026-11-19T14:09:02Z"
}
```

Money cells are written as numbers with the currency format; the header rows carry the title, both basis labels
(CB1: "every report and export is labelled with both bases"), the resolved dates and the notices.

### 7.2 PDF through the R34 preview: `render_pdf`

Request: a run request, a `saved_report_id`, or `{"pack_id": "pk_board"}`. Result:

```json
{
  "preview": {"file": {"handle": "fh_pdf_441", "name": "Monthly board pack - Oct 2026.pdf", "content_type": "application/pdf", "size_bytes": 312904},
              "page_count": 9, "title": "Monthly board pack · Oct 2026"},
  "skipped": [{"saved_report_id": "sr_winrate", "name": "Win rate by sales rep", "message": "You can't run records reports, so this report was left out."}]
}
```

The page opens the shared R34 preview with `preview.file`; its Save PDF calls `data.files.save_as(handle)`. There
is no print button (R34). Each report starts a new page; charts are rendered by the service. `skipped` lists pack
reports the viewer may not run (the pack still renders).

### 7.3 Scheduled delivery on the desktop

Decided (Q2 A, Q18 B, owner 2026-11-19): a schedule runs **while the app is open on a computer where its owner is
signed in to that company**; a run that was due while the app was closed runs once at the next sign-in ("caught
up"). Delivery is **in-app only in v1**: the output lands in the company's report outbox (a storage folder, shown
on a "Delivered reports" list) and each recipient gets an in-app notification linking to it. There is no email
delivery in v1. Each run uses the **owner's permissions at run time** (G7); if the owner has lost a permission,
that report is skipped and the owner is told why. A recipient opens the delivered file only while they can still
run that report (the outbox read re-checks).

```json
{
  "schedule_id": "sch_board",
  "version": "2",
  "name": "Board pack after month close",
  "target": {"pack_id": "pk_board"},
  "format": "pdf",
  "when": {"rule": "after_period_close", "delay_days": 0},
  "owner": {"user_id": "usr_3", "name": "Dana Whitfield"},
  "recipients": [{"user_id": "usr_3", "name": "Dana Whitfield"}, {"user_id": "usr_9", "name": "Marcus Bell"}],
  "delivery": "in_app",
  "active": true,
  "last_run": {"run_id": "schr_77", "at": "2026-11-05T13:02:18Z", "status": "delivered", "period_label": "Oct 2026",
               "file": {"handle": "fh_pdf_431", "name": "Monthly board pack - Oct 2026.pdf"}},
  "next_run": {"label": "When Nov 2026 is closed"}
}
```

- `when.rule`: `monthly` (`day_of_month`), `weekly` (`weekday`), `after_period_close` (fires when a month period is
  closed; uses `last_closed_month`).
- Services: `list_schedules`, `get_schedule`, `save_schedule` (version), `delete_schedule`, `run_schedule_now`,
  `list_schedule_runs` (`status`: `delivered`, `partly_delivered`, `skipped`, `failed`, with a plain `message`).
  Permission: `report.schedule` (Q8 A) plus the run permissions. Recipients are users of the company only; a
  recipient who can't run the report is refused at save ("Marcus Bell can't run financial reports, so they can't
  receive this pack.").
- Outbox: `list_delivered_reports` → `{items: [{run_id, schedule_name, at, period_label, file: {handle, name}}],
  next_cursor}`, showing only deliveries addressed to the viewer.

---

## 8. Assistant draft (item 7)

The Assistant (v1.2) drafts a layout from a description. It never saves: the draft opens in the layout editor,
unsaved, and only the user's Save stores it (AI guardrails; section 0: the AI never posts, approves or moves
money, and here it does not save either).

1. **What the Assistant must produce**: a financial or records layout in the section 2.2 / 2.3 shape, without
   `layout_id`, `version`, `updated_*` and `built_in`, and with temporary ids (`"tmp_1"`, `"tmp_2"`) for its
   items, plus `{"what_to_check": [...]}` notes. Account references use `display_code` (the model sees codes and
   names, never balances or bank details, C4).
2. **Validation**: `validate_draft` `{"draft": {...}}` maps codes to accounts, replaces temporary ids, runs every
   save check (section 2.2) and every formula check (3.2) without saving, and returns:

```json
{
  "layout": {"layout_id": null, "version": null, "kind": "financial", "report_type": "profit_and_loss",
             "name": "Job profitability summary (draft)", "items": ["... normalized items with new ids ..."]},
  "problems": [
    {"field": "items[2].accounts[1]", "message": "There is no account 5150 in your chart. Pick the account or remove it."}
  ],
  "what_to_check": [
    {"item_id": "itm_n4", "message": "Cost of sales includes 5600 Equipment rental by its account range. Check it belongs there."},
    {"item_id": null, "message": "8 accounts are not in any group: 6950 Small tools, 7010 Interest income and 6 more."},
    {"item_id": "itm_n7", "message": "Gross margin is shown as Percent with 1 decimal."}
  ],
  "origin": "Agent"
}
```

3. The editor opens the normalized layout with the problems and the "what to check" list shown; Save calls
   `save_layout` as the user (`origin: "Human"`, E11), which runs every check again. A draft that still has
   problems cannot be saved until they are fixed.
4. The Assistant needs `ai.use` and the run permission for the kind; it may call `list_formula_operands`,
   `list_source_fields` and `validate_draft`, nothing that writes.

---

## 9. One error shape (item 8)

```json
{
  "ok": false,
  "error": {
    "kind": "conflict",
    "message": "Changed by someone else. Reload to see their changes.",
    "field": null,
    "problems": [],
    "current_version": "8",
    "ref": "err_20261119_140912_3f2a"
  }
}
```

| Field | Meaning |
|---|---|
| `kind` | One of `validation`, `not_found`, `permission`, `conflict`, `period_closed`, `confirm_required`, `save_failed`, `unavailable`. The page uses it only to pick the shared component (field error, R27 box, conflict bar "Changed by someone else. Reload", confirm dialog). It is a category, not a permission or database code. |
| `message` | One plain sentence that says what is wrong and what to do next (R27, 0b). Never a permission code, table name, SQL text or stack trace. |
| `field` | Path of the input at fault, e.g. `"layout.items[4].tokens[2]"`, `"parameters.compare[0].plan_version_id"`; `null` when it is not one field. |
| `problems` | Further `{"field", "message"}` pairs when several inputs are wrong (a draft, an import). |
| `current_version` | On `conflict` only: the stored version. |
| `ref` | An opaque reference that also appears in the log line, so support can find the details. |

Codes go to the log only: the permission code to `access_event` (R27), the database text to the log file (repo
R35, `SaveFailedError`), a typed reason never to the log (R30). Mapping from `errors.py`: `ValidationError` →
`validation`; `NotFoundError` → `not_found`; `PermissionDeniedError` → `permission`; `PeriodClosedError` →
`period_closed`; `ConfirmationRequiredError` → `confirm_required`; `SaveFailedError` → `save_failed`; a new
`StaleVersionError` → `conflict` (area 21); `KeyUnavailableError` and `InstallationError` → `unavailable`.

Samples:

```json
{"kind": "validation", "message": "This formula refers to itself through Gross profit. Remove one of the two references.", "field": "layout.items[3].tokens[0]", "problems": [], "ref": "err_..."}
{"kind": "permission", "message": "You can't export reports. Ask an Admin to give you access to exporting.", "field": null, "problems": [], "ref": "err_..."}
{"kind": "validation", "message": "2 report packs use this layout, so it can't be deleted. Remove it from Monthly board pack and Bank covenant pack first.", "field": null, "problems": [], "ref": "err_..."}
{"kind": "not_found", "message": "This saved report was deleted. Pick another report.", "field": "saved_report_id", "problems": [], "ref": "err_..."}
```

---

## 10. Mock-data files for batch E

One file per service result, named by service, with the samples above as the first content:
`mock-data/reports/layouts.json` (list and three layouts: built-in P&L, the sample financial, the sample
records), `saved_reports.json`, `packs.json`, `formula_operands.json`, `run_financial_pl.json`,
`run_financial_bs.json`, `drill_financial.json`, `sources.json`, `source_fields.json`, `run_records.json`,
`measures.json`, `measure_values.json`, `kpis.json`, `kpi_values.json` (frozen, live and not frozen),
`combinable_companies.json`, `run_combined.json`, `schedules.json`, `delivered_reports.json`,
`validate_draft.json`, `errors.json` (one of each kind).
The data layer fakes `version`, conflicts and file handles (g3, g4).

---

## 11. Questions for the owner

Each has the recommended option first. Every question is answered: Q1-Q18 in fix mode 1 and Q19-Q26 in fix
mode 2 (owner, 2026-11-19). No question is open.

**Q1. "As reclassed" amounts.**
- A. **Recommended:** amounts always equal the GL for each cell's dates (both views); "As reclassed" changes only
  the detail rows (the original line shown once, under the new account from the reclass period on). Closed
  periods, the close snapshot and period summaries never change.
- B. Move the original amount into the new account in the original line's own period whenever the report range
  includes the reclass date (period totals then differ from the GL).
- **Owner answer (2026-11-19): A.**

**Q2. What runs a schedule on the desktop?**
- A. **Recommended:** the app, while open with the owner signed in to that company; missed runs catch up once at
  the next sign-in.
- B. A Windows scheduled task that starts the app hidden (needs unattended sign-in and key access).
- C. No schedules on the desktop in v1; hosted only.
- **Owner answer (2026-11-19): A.**

**Q3. Two auto-include rules that could catch the same account.**
- A. **Recommended:** refused at save, naming both groups and the overlap.
- B. Allowed; the first group in tree order wins.
- **Owner answer (2026-11-19): A.**

**Q4. Do formulas use the shown sign or the ledger sign?**
- A. **Recommended:** the shown value (after "positive when Credit/Debit"), as Joiin does.
- B. The ledger's signed value (debit − credit).
- **Owner answer (2026-11-19): A.**

**Q5. KPIs as a formula operand.**
- A. **Recommended:** no separate kind: a KPI is a group or formula flagged KPI, referenced as itself.
- B. A separate KPI list that can hold values from other reports.
- **Owner answer (2026-11-19): neither as written.** KPIs get their own table (definition: name, source group,
  formula or measure, format) and a stored value per period. When a period closes, its KPI values are frozen
  (like the close snapshot: each close keeps its own values; a reopen and re-close stores new ones, earlier ones
  kept). Reports read frozen values for closed periods and live values for open ones. Built into sections 2.7,
  3.1, 4.2 and 4.6; the item `kpi` flag is removed. Follow-ups: Q24-Q26 (all A).

**Q6. Ratio format.**
- A. **Recommended:** "1.85 : 1".
- B. "1.85x".
- **Owner answer (2026-11-19): A.**

**Q7. What a financial run needs.**
- A. **Recommended:** `report.financial` and `money.view` (no money anywhere without `money.view`); seed
  `money.view` in every level that holds `report.financial` or `report.job_cost`.
- B. `report.financial` alone; `money.view` only for Records money fields.
- **Owner answer (2026-11-19): A.**

**Q8. New permission codes.**
- A. **Recommended:** `report.records` (run Records reports), `report.design` (edit layouts, measures and shared
  saved reports), `report.schedule` (schedules), all not sensitive; `money.view` as decided.
- B. Reuse `report.financial` for everything except `money.view`.
- **Owner answer (2026-11-19): A.** `report.design` also covers KPI definitions (Q5).

**Q9. Cash basis speed.**
- A. **Recommended:** computed at run time from payments and allocations in v1; add a cash summary later if the
  budget (Q10) fails.
- B. Build a cash-basis summary maintained at payment application in v1.
- **Owner answer (2026-11-19): A.**

**Q10. Performance budget for 2.9 tests.**
- A. **Recommended:** a 12-column P&L with a plan comparison on 250,000 posted lines in under 1 second.
- B. Under 3 seconds.
- **Owner answer (2026-11-19): A.**

**Q11. Conditional summaries on Records columns (needed for "won ÷ closed").**
- A. **Recommended:** a column may carry its own `where` filter.
- B. Only report-level filters; win rate built in as a special summary.
- **Owner answer (2026-11-19): A.**

**Q12. Pack dates.**
- A. **Recommended:** a pack may set its own dates that replace each report's dates for that run.
- B. Each report always keeps its own dates.
- **Owner answer (2026-11-19): A.**

**Q13. Compare columns with several periods.**
- A. **Recommended:** beside each period column for `single_period`; beside the total only for `by_period`.
- B. Beside every period column always.
- **Owner answer (2026-11-19): A.**

**Q14. "All companies" (separate company files).**
- A. **Recommended:** not in v1; consolidation within one file (entities) comes with the consolidation work.
- B. A combined run across files in v1.
- **Owner answer (2026-11-19): B, with no automatic consolidation and no eliminations.** Eliminations are written
  as custom formulas. The user picks companies; only files the user can open and is signed in to, holding
  `report.financial` and `money.view` in each; each company's figures are computed by its own file's services,
  then combined. A formula operand for one company's group or account lets an elimination formula reference it.
  Built into section 4.7 and the `company_group` / `company_account` operands (3.1).
  Follow-ups: Q19 (B, amended) and Q20-Q23 (A).

**Q15. A Records report with a money filter run by someone without money.view.**
- A. **Recommended:** the filter, sort, group-by and formulas on money fields are dropped too, with the notice.
- B. Refuse the run: "This report uses money fields your role can't see."
- **Owner answer (2026-11-19): B.** Section 5.4: any use of a money field (column, filter, sort, group-by,
  formula) refuses the run with that sentence.

**Q16. Typed measure values in closed periods.**
- A. **Recommended:** editable and logged (not ledger data).
- B. Locked with the period.
- **Owner answer (2026-11-19): B.** Typed values are locked with their period, editable again only after a
  reopen, changes logged (section 6.2). Derived values are not recomputed while their period is closed either
  (planning's reading, confirmed by the owner in fix mode 2).

**Q17. Row limits on derived measures.**
- A. **Recommended:** derived measures are company figures computed without row limits (only counts or sums, no
  rows shown); the measure's drill applies the viewer's limits.
- B. Computed per viewer.
- **Owner answer (2026-11-19): A.**

**Q18. Email delivery for schedules.**
- A. **Recommended:** optional, only when the company mailbox is connected (area 20); otherwise in-app
  notifications and the outbox.
- B. In-app only in v1.
- **Owner answer (2026-11-19): B.** In-app delivery only in v1 (notification and outbox); no email (section
  7.3).

**Q19. Combined run: matching accounts across different charts.**
- A. **Recommended:** by account number. An account in another company whose number is not in the current
  company's chart is shown in an "Unmatched accounts" section for that company, outside the groups and the
  totals, with a Check notice naming the amount left out.
- B. By account number, and unmatched accounts are added into the group whose auto-include rule their number
  fits (range or type), with only the rest shown as unmatched.
- C. A stored mapping per company (each other company's accounts mapped to this company's, kept and edited on a
  mapping screen).
- **Owner answer (2026-11-19, fix mode 2): B, as amended by the owner.** Accounts are matched by account number.
  An unmatched account shows as its own row under its group (or "Not in any group"), labelled with its company,
  and counts in the group and report totals. The run returns a warning listing the unmatched accounts. The
  combined total always equals the sum of the companies. Built into sections 2.2 and 4.7. "Its group" is read
  as the group whose `auto_include` rule the account's number or type fits.

**Q20. Combined run: companies with different currencies.**
- A. **Recommended:** refused: "These companies use different currencies (USD and PHP). Pick companies with the
  same currency."
- B. Converted to the current company's currency at a rate the user enters for the run (average for P&L,
  closing for balance sheet), labelled on the report.
- C. Converted using stored exchange rates (needs a rates table and a source; later).
- **Owner answer (2026-11-19, fix mode 2): A.**

**Q21. Saving and scheduling a combined report.**
- A. **Recommended:** it can be saved as a report in the current company (its company list kept with it) and
  added to packs; it cannot be scheduled in v1 (a schedule runs under one company sign-in).
- B. Saved and scheduled; a scheduled run that cannot open one of its companies is "partly delivered" with the
  reason.
- C. Neither: a combined report is run on demand only.
- **Owner answer (2026-11-19, fix mode 2): A.**

**Q22. Combined run: companies with different fiscal years or adjustment settings.**
- A. **Recommended:** dates resolve on the current company's calendar and apply to each company by calendar
  date; only calendar-month columns are allowed when fiscal year starts differ, and the basis must be
  pre-adjustment unless every company has adjustment periods on.
- B. Refuse companies whose fiscal year start differs from the current company's.
- **Owner answer (2026-11-19, fix mode 2): A.**

**Q23. Combined run: plan comparisons and filters.**
- A. **Recommended:** not in v1 (plan versions, dimensions, jobs and contacts are per file); prior period and
  prior year comparisons are allowed.
- B. Plan comparison by version name, when each company has a plan version with the same name.
- **Owner answer (2026-11-19, fix mode 2): A.**

**Q24. KPI basis.**
- A. **Recommended:** each KPI stores its own basis (method and adjustments; default accrual and the company's
  default adjustment basis), and its frozen values use it.
- B. One company-wide KPI basis in Company Settings.
- **Owner answer (2026-11-19, fix mode 2): A.**

**Q25. A KPI over several periods (quarter, year, total columns).**
- A. **Recommended:** each KPI sets `range_method`: `sum`, `average` or `last` of the per-period values (frozen
  for closed periods), or `recalculate` from its source over the range (for ratios such as gross margin).
- B. Always recalculated live over the range; frozen values are used only for single-period columns.
- **Owner answer (2026-11-19, fix mode 2): A.**

**Q26. A KPI created after a period closed.**
- A. **Recommended:** that period shows the live value marked "Not frozen: this KPI was added after Sep 2026
  closed."; it is frozen at the next close of that period.
- B. Saving a new KPI freezes values for every closed period at once, from the current figures.
- **Owner answer (2026-11-19, fix mode 2): A.**

---

## 12. For the 2.9 replan

For area 17 unless another area is named. Every editable table gets `row_version` (area 21, g4).

1. `report_layout` (`kind` financial | records, `report_type`, `scope` single | combined, `name`, `built_in`,
   `copied_from_id`, `source_id` for records, `updated_at`/`by`, `row_version`); built-in rows read-only by a
   service rule.
2. `layout_item` (tree: `parent_id`, `sort`, `type` group | formula | chart, name, group options, formula
   `format`, `decimals`, `total_method`, `hide_if_zero`, `over_plan_is`, `positive_when`). No `kpi` flag (Q5).
3. `layout_group_account` (`layout_id`, `group_id`, `account_id`; UNIQUE (`layout_id`, `account_id`)) and
   `layout_auto_include` (range or type rule; overlapping rules refused at save, Q3 A).
4. `layout_formula_token` (item, position, `t`, `kind`, `ref_item_id` or `kpi_id` or `measure_id` or `system`,
   `company_id` and `account_code` for the combined operands, `number`, `op`) rather than JSON text, so
   references to a deleted item or KPI are found by query (11-18 "Done when").
5. `layout_chart` and `layout_chart_series`.
6. Records layout parts: `records_column` (field, summary, `where` (Q11 A), format, formula tokens),
   `records_group_by` (up to 3, bucket), `records_sort`, `records_filter`.
7. `saved_report` (layout, owner, shared, `parameters` with the dynamic date preset or fixed dates,
   `plan_version_id`; for a combined report the chosen `company_id` list, Q21 A), `report_pack`,
   `report_pack_item` (sort), with the usage count and the delete block; `report_pack.pack_dates` (Q12 A).
8. **KPIs (Q5):** `kpi` (`kpi_id`, name, source kind group | formula | measure, `layout_id` + `item_id` or
   `measure_id`, `format`, `decimals`, `over_plan_is`, basis (Q24 A), `range_method` (Q25 A), `is_active`,
   `row_version`) and `kpi_value` (`kpi_id`, `period_id`, `close_event_id` → `period_status_history`, value as
   `value_cents` or `value_decimal` text, `note`, `frozen_at`, `frozen_by`): insert-only, written by the period
   close service in the close transaction for every active KPI, never updated or deleted, audit-logged (AX4).
   Each close of a period adds its own rows (a reopen and re-close keep the earlier ones); the latest close's
   row is the one reports read. Delete blocks: a layout item or layout used by an active KPI; a measure used by
   one. Area 13 (close) gains the freeze step beside the close snapshot.
9. `report_schedule` and `report_schedule_run` (status, message, file handle); `report_delivery` (run,
   recipient user, read at) for the in-app outbox and notifications (Q18 B: no email fields); output file handles
   through `storage.py` (H3).
10. `nonfinancial_measure` (name, unit, decimals, aggregate, source typed | from_jobs, rule) and
    `nonfinancial_value` (measure, period, `typed_value`, `derived_value`, `entered_by`/`at`); a service refuses
    typed changes in a closed period and skips derived recomputation there (Q16 B); import through the standard
    all-or-nothing batch.
11. Operating plan (area 7): `operating_plan_version` and `operating_plan_line` (account, period or month,
    dimension set, amount in cents).
12. **Period balance summary** (area 10 with 17): `ledger_period_balance` (`period_id`, `account_id`,
    `entity_id`, `project_id`, `cost_code_id`, `dimension_set_id`, `debit_cents`, `credit_cents`, `line_count`)
    written only by `ledger.py` at posting; `dimension_set` and `dimension_set_member`; a verify check against
    `journal_line` and a rebuild tool; index `journal_entry (period_id, is_posted)`.
13. Reclass (area 10): `journal_entry.source` gains `'Reclass'`; reclass lines carry the original document and
    line ids and the original's name, date, memo, item and job, and the reason.
14. Permissions (area 18): `money.view` (decided, not sensitive) and the Q8 A codes `report.records`,
    `report.design`, `report.schedule` (not sensitive): permission rows, the role caps and level defaults, and
    `money.view` seeded in every level that holds `report.financial` or `report.job_cost` (Q7 A).
    **Area 18 seed tables (owner, fix mode 2):** in 2.4.2 add `money.view` to Accountant · View only (holds
    `report.financial` and `report.job_cost`), Sales rep · Manager and Operations · Standard (each holds
    `report.job_cost`); levels are cumulative, so the higher levels inherit it. Add `money.view` to the
    Accountant, Sales rep and Operations caps (2.4.1). Shipped templates that add a report code (Payroll, Sales
    manager, Project manager, Estimator, Staff accountant) sit on a level that already gives `money.view` or
    need it added: planning checks each row in area 18. `AGENT_ALLOWED` gains `report.records` only if planning
    wants the Assistant to run Records reports.
15. **Combined runs (Q14 B, Q19 B, Q20-Q23 A):** no new company-file table (Q21 A: the company list lives in
    `saved_report`; no schedule).
    Needs: a master-side service that lists the companies a user may open (exists for the launcher) and builds a
    `ServiceContext` per company; `company_settings.base_currency` and `fiscal_year_start` read per file (exist);
    account matching by `account.code` (exists); unmatched accounts placed by the layout's `auto_include` rules
    (item 3). No account mapping table and no exchange rates table.
16. Records source tables not in the baseline (areas 6, 8, 15): `lead`, lead stage/status history, `activity`,
    job stage history, job cancellation reason, `service_case` and its status history, lead → job link (X4),
    sales rep on the contract.
17. Custom fields (area 16): `custom_field_def.record_type` needs `Lead` (and job type scoping) for Records
    fields.
18. Cash basis and cash flow: a company default for Accrual / Cash (CB1) and an account cash flow category (CF1);
    neither is in `company_settings` or `account` today.
19. `user_list_pref` / `saved_view` are not reused for reports (different shape); say so in area 17.
