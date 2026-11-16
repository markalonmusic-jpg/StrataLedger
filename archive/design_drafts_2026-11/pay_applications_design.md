# Pay applications and retainage receivable: design draft

Status: DESIGN ONLY. NOT BUILT. Items marked PROPOSED are not decided.
Replaces the archived alternate draft `pay_app.md`, which is not guidance.
Names of existing columns come from the report on migrations 001-004; confirm
against the live schema before writing the migration.

Conventions follow CLAUDE.md: integer cents, double-entry, posted records
locked, corrections by reversing entries or credit memos, writes only through
service functions, controlled accounts fed only by their subledger service.

---

## 1. Scope

In v1:
- Pay applications (progress billing) against a contract's schedule of values.
- Retainage receivable: withheld at billing, invoiced later on release.
- Approved change orders feeding the schedule of values.

Out of v1 (decided):
- Stored materials. Materials delivered to a job are expensed and count toward
  percent complete (inventory design), so there is no separate stored-materials
  billing column. The existing `stored_materials_cents` columns stay unused.
- Subcontractor pay applications and retainage payable. Subcontractors go
  through a PO-to-AP matching process, which is its own design (purchase
  orders with lines and `project_id`, receipts, bill matching).
- Retainage rate reductions (for example after 50% complete). One rate per
  contract. Later add-on.

---

## 2. Concepts

- **Schedule of values (SOV):** the `contract_line` rows of a contract. Each has
  a scheduled value. Revised scheduled value = original + approved change order
  amounts for that line.
- **Billing percent:** to-date billed / revised scheduled value. It is a
  billing figure only. It is NOT the cost-to-cost percent complete that drives
  earned revenue (CLAUDE.md POC rule). Billing never sets earned revenue.
- **Retainage:** `contract.retainage_pct`, one rate per contract. Withheld from
  each application, held in **Retainage Receivable**, moved to regular
  **Accounts Receivable** only when a release is invoiced.

---

## 3. Data model (PROPOSED)

**`progress_billing_application`** (exists, header only). Add or confirm:
- `contract_id`, `project_id`, `application_number`, `period_id`,
  `period_to_date`, `invoice_id` (set when approved), `status`, approval fields.
- Unique `(contract_id, application_number)`.
- Totals are derived from lines and must equal them (check at approval).
- `status`: Draft, Submitted, Approved. Paid is derived from the invoice, not
  stored twice. Approval is by a person only.

**`progress_billing_line`** (new), one row per SOV line per application:
- `application_id`, `contract_line_id`, `sort_order`.
- `scheduled_value_cents` (revised, as of this application, copied for the
  record).
- `completed_to_date_cents` (the stored basis).
- `previous_to_date_cents` (copied from the previous approved application at
  creation, for display; the check below enforces it).
- `this_period_cents` = completed to date - previous to date (derived, stored
  for reporting, checked).
- `retainage_to_date_cents`, `retainage_this_period_cents`.
- Checks: `completed_to_date_cents` >= previous; <= revised scheduled value;
  all integers.

**Input in the screen:** the user may type a percent or an amount. Only cents
are stored. Percent converts as `round half up(percent x scheduled value)`.

**Retainage rounding (no drift):** cumulative retainage =
`round half up(completed_to_date x rate)`; this period's retainage = cumulative
- previous cumulative. Per line, then summed.

**Rate lock:** the contract's rate cannot change after the first approved
application. A change goes through a contract amendment (PROPOSED).

**`retainage_release`** (new): `contract_id`, `release_date`, `amount_cents`,
`invoice_id`, status, approval fields. Partial releases allowed. The amount
cannot exceed the contract's retainage held (sum retained - sum released).

---

## 4. Accounting

Approving an application generates a **Draft invoice** through the normal
billing service (invoice lines mirror the SOV lines at this-period amounts).
The invoice gets its series number when it is sent, never before; sales tax
follows the normal rules. Posting happens only through the normal posting path.

When the invoice is sent/posted:
- Dr Accounts Receivable (gross this period - retainage this period)
- Dr Retainage Receivable (retainage this period)
- Cr Contract Revenue / billings (gross this period)

The period-end POC entry then adjusts revenue to earned revenue with the
offset to underbilled/overbilled (existing design). The application's billed
to date feeds `poc_snapshot.billed_to_date_cents`.

**Releasing retainage:** an approved release generates an invoice (a real,
numbered document the customer receives) with a retainage release line
(`is_retainage_line`). Posting it:
- Dr Accounts Receivable
- Cr Retainage Receivable
No revenue is touched. The customer's payment then applies to that invoice as
normal.

**Control account:** Retainage Receivable is a controlled account. Only the
pay-application and release services post to it, and every line carries
`contract_id` and `project_id`. Subledger tie-out: per contract, retainage
held = retained - released; the total must equal the GL balance.
`account.control_type` needs separate values for retainage receivable and
retainage payable (a single "Retainage" value cannot tell them apart); only
receivable is used in v1. Add the receivable account to `company_settings`.

---

## 5. Controls

1. An approved application locks (lines, amounts, application number). Fixes
   use a credit memo or the next application, never an edit.
2. Completed to date can never go below the previous approved application or
   above the revised scheduled value.
3. Only approved change orders change a scheduled value; the approval locks the
   SOV change. Pending change orders are excluded.
4. The generated invoice cannot be edited into a different amount; a mismatch
   with the application is blocked at posting.
5. The project must allow billing (`allows_billing`) and the period must be
   open.
6. Voiding a posted pay-app invoice reverses it and reopens the application for
   a corrected one (existing void-as-reversal rule). Retainage balances follow
   the reversal.
7. AI Copilot: may propose a pay application from posted job costs and the POC
   snapshot as a pre-filled, unsaved screen. It never approves or posts.

---

## 6. Screens (Phase 3, one view per file)

- `modules/views_pay_apps.py`: the application list per contract and the SOV
  entry grid (scheduled value, previous, this period as % or $, to date,
  balance to finish, retainage). Summary panel: gross, retainage, net due,
  retainage held. Buttons: Save draft, Submit, Approve (role-limited).
- Retainage release: a small form on the contract showing retainage held and
  the amount to release.
- Follows `docs/CLAUDE_UI.md`.

---

## 7. Tests required

Cumulative basis: this-period derived correctly across 3 applications; cannot
go below previous or above revised value; percent entry rounds half up to
cents; retainage rounding does not drift over many applications; approval
requires lines to sum to the header; approved application is locked; rate
locked after first approval; change order raises the cap only when approved;
invoice generated as Draft with no number, number assigned at send; posting
entry balances and uses the right accounts; release cannot exceed retainage
held; release posts no revenue; retainage control account only accepts the
service's entries; void reverses retainage correctly; per-contract tie-out
equals the GL; closed period rejected; non-billable project rejected;
`poc_snapshot.billed_to_date_cents` matches.

---

## 8. Migration placement

Part of the CRM/PM construction migration (005) or its own migration right
after it: `progress_billing_line`, `retainage_release`, new constraints on the
application header, `counts_toward_progress` on `cost_code` (needed by the POC
rule), the FK from `contract_line.change_order_id` to `change_order` (005
drops `crm_change_order`, so `change_order` is the single table), the
retainage control types, and the settings account.

---

## 9. Open questions

1. Does the customer's contract ever require a final "retainage release at
   substantial completion" separate from a normal release? (Same mechanism;
   only the label differs.)
2. Should the application print/export the AIA G702/G703 layout? PROPOSED later
   (report layout, not a data-model change).
3. Is the rate lock too strict (contracts renegotiated mid-job)? PROPOSED:
   allow only via amendment.
4. Do any customers require retainage on only part of the lines (for example
   not on mobilization)? Needs a per-line flag; not in v1.
