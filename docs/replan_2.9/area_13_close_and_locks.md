# Step 2.9 schema replan, area 13: close and locks

Status: **Owner-approved 2026-11-19** (first draft 2026-11-19, dfb26b6; owner answers Q1-Q24, the F13 approval and the
KS15 fix 2026-11-19, folded in below, dac81ec; amendment line from area 12 Q12 A, a837bc1, and from area 10 F11,
77938bc; section 9). Docs only: nothing here changes code, a baseline, a migration or a test. Planning has marked
area 13 owner-approved in `Strata_Teams\schema_replan_2026-11-17.md`. Every table, column, code and check below is
built only in the 2.9 baseline pass. No questions are open.

Sources read (only these, searched by date, title or code):
- `Strata_Teams\schema_replan_2026-11-17.md`, row 13 and the source keys.
- `Strata_Teams\inbox\archive\to_planning_archive_2026-11-17.md`: 2026-11-14 "month-end close rules" (12:50 PM),
  "Partial close" (1:00 PM); 2026-11-15 "Close checklist model with custom dependencies" (1:31 PM).
- `Strata_Teams\inbox\to_planning.md`: 2026-11-17 "company calendar, close due dates, reviewed by" (6:03 PM) and
  "close reviewed-by fields" (6:08 PM); 2026-11-18 "close snapshot of five figures per period close" (11:32 PM),
  "prepaid bills, deferral schedules and auto-posting" (11:55 PM), "unmatch a cleared payment" and "unmatch
  service covers every bank-matched record type".
- `Strata_Teams\shared_decisions.md`: 2026-11-18 9:18 PM and 9:20 PM (unmatch, Bank lock area), 11:32 PM (close
  snapshot), 11:55 PM (prepaid on the Close checklist); 2026-11-19 12:40 AM and 12:45 AM (reclass, prepaid catch-up),
  1:21 AM (prepaid void and job cost), 2:29 AM (build rule g).
- `Strata_Teams\StrataLedger_planning_log_2026-11-12.md` section 3b, 2026-11-18 16:27 (partial locks).
- `StrataLedger_mockups\CODE_CHANGES_NEEDED.md` sections 56 and 97; `StrataLedger_mockups\close.html` (the
  partial-close, unlock, close, reopen dialogs and the checklist only).
- `Strata_Teams\codex_reports\schema_gaps_vs_mockups_2026-11-18.md` item 7.
- docs/contracts/reports.md section 2.7 and section 12 (items 8, 10 and 12; see conflict F9 on the numbering).
- docs/replan_2.9/area_18_admin_security_audit.md (audit, reasons, access, attachments, O6).
- docs/decisions_2026-11-11.md by code: L1, L2, L6, L7 (and its two amendments), B1, C4, A1, S3, S4, R26, R48,
  K18, KS15, AX4.
- `migrations/001_company.sql` (the close tables), and the services that read or write them: `periods.py`,
  `ledger.py`, `payments.py`, `custom_fields.py`, `ledger_verify.py`; `app_strata.pyw` for R26.

---

## 0. Summary

| # | Item | Proposal in one line | Baseline |
|---|------|----------------------|----------|
| 1 | Locks | Full period and year stay as they are (integrity once set). `fiscal_period_lock` is replaced by `period_lock`: one row per locked area (11, Q1 A) or account, with a reason to lock and to unlock (Q4 B), relocked as a new row. One check in a new `period_locks.py`, called by every action that posts or changes a posted record | company |
| 2 | Close checklist | Template and period tasks, system and custom, steps, dependencies with built-in edges guarded by the service only (Q12 B), done/skip records. `period_close_check` stays as the system-check registry with per-check warn/block (L2, Q2 A); `ledger_integrity`'s unverified range never blocks in any mode (KS15); its code list grows | company |
| 3 | Calendar items | `due_type`/`due_n` on tasks, `close_target_bd`, a work week and a holiday list; reviewed-by is the period's closer (`closed_by`/`closed_at`). Reopen clears it and every task's done record, logged (Q15 B) | company |
| 4 | Close snapshot and freezes | `period_close_snapshot`: five figures per close event, insert-only, audited; ending cash is Bank and Cash plus undeposited funds, cards excluded (Q16 B). KPI freeze (area 17's `kpi_value`) in the same transaction. Typed measures refused and derived ones skipped in a closed period | company |
| 5 | Checkpoints | R26/K18 are the company-file close (sign-out), not the period close. The period close already signs a `Period close` checkpoint; the snapshot records the entry number it was verified through | company |
| 6 | Period balance summary | Written only by `ledger.py` at posting; correct across reopen and re-close by construction (append-only lines); a tie-out check and a rebuild tool; on area 18's derived exempt list (F13, owner) | company (area 10 with 17) |

Master file: no change (snapshots are per company; no "All companies" view in v1, 11-18 item 4).

Amendment 2026-11-19 (owner, area 12 Q12 A), row 4: ending cash is the `bank_account` rows of every kind except
Credit card, plus `company_settings.undeposited_funds_acct_id`; this replaces "Bank and Cash account types" (section 4.4).

---

## 1. Locks

### 1.1 Current state

- **Full period close.** `fiscal_period.is_closed`, `closed_at`, `closed_by` (`migrations/001_company.sql:394-409`).
  Two ways to set it, one mechanism (L1): `periods.close_period` (`modules/services/periods.py:356`) and
  `periods.set_books_closed_through` (`periods.py:390`, the setting `company_settings.books_closed_through`,
  `001_company.sql:761`). Every close and reopen is a row in the append-only `period_status_history`
  (`001_company.sql:426-437`; `via` is Period close, Books closed through, Year close or Year reopen).
- **Integrity backstop.** The trigger `journal_entry_require_balance_on_post` (`001_company.sql:1696`) refuses a post
  into a closed period, and a post whose date falls in a closed month (adjustment periods excepted).
- **Year end (B1).** `fiscal_year.is_year_closed` (`001_company.sql:413-423`); `periods.close_year`
  (`periods.py:484`) needs months 1-12 closed, closes 13 and 14 with their checks, and creates the next year.
  `reopen_year` (`periods.py:519`, `year.reopen`, typed year name and reason, L7 amended). The trigger
  `fiscal_period_reopen_in_closed_year` (`001_company.sql:1635-1641`) refuses reopening a period of a closed year.
- **Reopen (L7).** `periods.reopen_period` (`periods.py:371`): `period.reopen`, `confirm=True`, a reason, logged;
  moves `books_closed_through` back before the period when needed. Permissions seeded at `001_company.sql:1186-1189`
  (`period.close` not sensitive; `period.reopen` and `year.reopen` sensitive).
- **Area locks.** `fiscal_period_lock` (`001_company.sql:3911-3921`): `period_id`, `area` CHECK IN ('Sales',
  'Purchases', 'Banking', 'Payroll', 'Inventory', 'Journal'), `is_locked`, `locked_by`, `locked_at`, `reason`,
  UNIQUE (`period_id`, `area`). Audited (area 18 table: triggers at 4509, 4529, 4556). **No service writes it.**
  Only one reader: `payments._check_period` (`modules/services/payments.py:123-132`), which refuses an allocation
  in a locked Sales or Purchases area with a `ValidationError` (not `PeriodClosedError`). Tests insert lock rows
  by hand (`tests/test_payments.py:267`, `:577`; schema tests `tests/test_schema_replan.py:436-444`).
- **Account locks.** None in the schema (Codex X 7).
- **Where the closed-period check is today** (each its own query, no shared function):
  `ledger._open_period` (`ledger.py:312-318`, drafts), `ledger` post (`ledger.py:728-731`), the auto-reversal
  date (`ledger.py:982-984`), void and correction (`ledger.py:1187-1203`, R48), `payments._check_period`
  (`payments.py:123`), `custom_fields._check_posted` (`custom_fields.py:479-493`, closed period and
  `lock_documents_after_posting`; area locks deferred, next_step input 4). None of them reads area locks except
  payments.

### 1.2 Decided

- Partial locks as in close.html: full period (L1, B1) plus area locks plus account locks (planning log 16:27).
- Nothing is locked unless a person sets it; who, when and why audited; checked by every posting service; a post,
  void or reversal touching a locked account or area is refused, never moved to another period (R48 style).
- Posting rule (11-14 1:00 PM; C56): a transaction dated in the period is refused if its document area is
  locked OR any line hits a locked account; the message names the lock. Enforced in the service, not only the UI.
- No posting override: an Admin or the Master unlocks first, with a reason, logged; posts; locks again.
- Full close still locks everything. Partial close is a tool on the Close screen, always available. Completing
  a checklist step may offer to lock its areas; it never locks automatically.

Amendment 2026-11-21 (owner 2:05 AM, close audit): Ordinary books close by whole fiscal months. Refuse an
entered mid-month date in the ordinary close flow with "Pick a month end". Use the fiscal month-end date in
the UI and History.
A user must choose **Special cutoff** explicitly to close through a custom date. As confirmed at 2:08 AM, the
cutoff uses the exact user-entered event date, including any day of the fiscal month. Require a selection from
the Reasons list with kind "Special cutoff" (for example, "Sale of business") and a note. The cutoff locks every
posting dated on or before that day. The remainder of the fiscal month stays open until its normal month-end close.
Show `Closed through <date> (special cutoff)` in the Close screen and History.

- Bank is a lock area, and a bank account can be locked (S 11-18 9:18 PM): unmatch is refused when the
  payment's period is locked for Bank or for that bank account, with no override; 9:20 PM extends this to every
  record type the bank feed can match.
- Custom-field edits on posted invoices and bills honour the area locks (next_step input 4; area 18 O6 asks the
  same for attachment removal).
- Reclass, prepaid catch-up and prepaid void never date anything into a closed period (S 11-19 12:45 AM, 1:21 AM).

### 1.3 Proposed schema

**`lock_area`** (seeded reference table, replaces the CHECK list so a new area is a seed row, not a CHECK edit):

| Column | Type and constraint |
|--------|---------------------|
| `area_code` | TEXT PRIMARY KEY (slug, e.g. `bills_vendor_credits`) |
| `label` | TEXT NOT NULL UNIQUE (the close.html wording) |
| `sort_order` | INTEGER NOT NULL |

Seed (Q1 A): close.html's ten areas plus Bank: Billing (owner pay apps); Invoices and credit memos; Payments
received; Bills and vendor credits; Bill payments; Payroll; Inventory and receipts; Fixed assets and depreciation;
Loans; Journal entries; Bank and card (11). Design adds Bank and card to close.html. Locks live on the Close screen
only, not on the Controls page (Q1 A). Which document or action belongs to which area is a service registry in
`period_locks.py` (section 1.4), not a column, so each area's own service registers its record types.

**`period_lock`** (replaces `fiscal_period_lock`; one row per lock, append-only apart from one unlock):

| Column | Type and constraint |
|--------|---------------------|
| `lock_id` | INTEGER PRIMARY KEY |
| `period_id` | INTEGER NOT NULL REFERENCES fiscal_period |
| `kind` | TEXT NOT NULL CHECK IN ('Area', 'Account') |
| `area_code` | TEXT REFERENCES lock_area; CHECK (kind = 'Area') = (area_code IS NOT NULL) |
| `account_id` | INTEGER REFERENCES account; CHECK (kind = 'Account') = (account_id IS NOT NULL) |
| `locked_by` | INTEGER NOT NULL |
| `locked_at` | TEXT NOT NULL (from `context.now`, UTC with offset) |
| `lock_reason` | TEXT NOT NULL CHECK (length(trim(lock_reason)) BETWEEN 1 AND 1000) (Q4 B: a reason is required to lock, as area 18 says; close.html gains a reason field on the lock dialog) **Withdrawn 2026-11-22 (owner, OD-31): minimum of 1 replaced by at least 10 characters after trimming; Area 18 §8.6** |
| `unlocked_by`, `unlocked_at`, `unlock_reason` | NULL until unlocked; CHECK all three set or all NULL, and `length(trim(unlock_reason)) BETWEEN 1 AND 1000` (Q4 B: required to unlock) **Withdrawn 2026-11-22 (owner, OD-31): minimum of 1 replaced by at least 10 characters after trimming; Area 18 §8.6** |
| `row_version` | INTEGER NOT NULL DEFAULT 1 (rule g4; the unlock dialog sends it back) |

- Partial unique indexes: `(period_id, area_code) WHERE kind = 'Area' AND unlocked_at IS NULL` and
  `(period_id, account_id) WHERE kind = 'Account' AND unlocked_at IS NULL` (one live lock per target; both SQLite
  and PostgreSQL support partial indexes, H5).
- Index `(period_id) WHERE unlocked_at IS NULL` for the posting check.
- Integrity triggers (append-only backstop, as `attachment` in area 18): DELETE refused; UPDATE refused unless it
  only sets the three unlock columns and `row_version`, once, from NULL. Relocking inserts a new row, so the table
  itself is the lock history (C56's "plus history rows"); `period_status_history` is not used for partial locks.
- A **bank account lock** is an Account lock on the bank account's GL account (one account per bank account), so it
  needs no third kind. The unmatch service checks the Bank and card area and the account of the matched line.
- Audit triggers on insert and update (area 18 section 1); the service passes the reason through `tx.py`.
- Period status shown on the Periods list is derived, never stored: Open; Partly closed (x of 11 areas, y of z
  accounts) when live lock rows exist; Closed when `is_closed = 1`.

**`fiscal_period`, `fiscal_year`:** add `row_version` (the close and reopen buttons send it, g4). No other column
(reviewed-by is section 3).

Amendment 2026-11-21 (owner 2:05 AM, close audit): Proposed record for the rebuild. Add `Special cutoff` to
`action` and `via` in the append-only `period_status_history`. Link the event to the fiscal period that
contains the event date. Store the exact
`cutoff_date`, the selected reason ID and its label at the time of the event, the note, and the existing
actor and timestamp. Require the date, reason and note for this event kind. A Special cutoff leaves the
containing month's full-close flag to the ordinary month-end close. Retain the cutoff event in History after
that month closes.

**Permissions** (Q3 A): locking uses `period.close`; unlocking uses `period.reopen` (sensitive; Admin, the Master and
the Controller template per area 18). Code checks permissions, never role names (L7).

### 1.4 One check for every action

New module `modules/services/period_locks.py` (H1-H5 clean):

- `check_open(conn, *, on_date=None, period_id=None, area_code, account_ids, action)`: inside the caller's
  write transaction. Resolves the period (`periods.resolve_entry_period`), then refuses in this order:
  1. the period is closed (or the year is closed): `PeriodClosedError` (integrity, always on);
  2. a live Area lock on `area_code`: `PeriodLockedError` (new, a subclass of `PeriodClosedError` so existing
     callers that catch the closed case still catch it), naming the area;
  3. a live Account lock on any of `account_ids`: `PeriodLockedError`, naming up to three accounts.
  The message is C56's one sentence: "October is partly closed: Bills and vendor credits is locked. Ask an Admin
  to unlock it, or date this in November." For a Void or Correction dated in a locked period 13 or 14 it keeps
  R48's wording: refused, never moved.

Amendment 2026-11-21 (owner 2:05 AM, close audit): Check the effective posting date of every new entry
against the Special cutoff inside the write transaction as part of the closed-date checks. Refuse dates on or before the cutoff,
regardless of area or account. Extend the closed-period posting integrity backstop to cover the cutoff.
Dates after the cutoff follow the existing full-period, area and account rules.

- `set_locks(context, period_id, *, areas, account_ids, reason, row_versions)` and
  `unlock(context, lock_ids, *, reason, row_versions)`: authorize first, then one write transaction. Locking a
  closed period is refused (it is already locked). `preview_locks` returns close.html's summary ("Locks 8 of 11
  areas and 44 of 47 accounts. Left open: ...").
- `lock_status(context, period_id)` for the Periods list and the banner.

Which period the check runs on (one rule for every action):
- **Actions that post new lines** (post a document or entry, void, reverse, correction, reclass, auto-reversal,
  prepaid entry or catch-up, rule 8 reverse-and-repost, recalculate WIP, depreciation): the period the new lines
  are dated in, with the area of the source document and every account the new lines hit. A rule 8 repost checks
  both its reversal and its repost.
- **Actions that change a posted record in place without new lines** (allocate and release a payment, unmatch,
  clearing ID, custom-field edits, attachment removal, a posted document's memo where allowed): the record's own
  posting period, its area, and the accounts of its posted lines that the action touches (unmatch: the bank line;
  allocate: the AR or AP line; custom fields and attachments: none, only the area, Q6 A). For custom fields and
  attachment removal the closed period and `lock_documents_after_posting` also apply, as today.

Callers and their area (registry in `period_locks.py`; each area's own service adds its types later):

| Caller (today or planned) | Area | Accounts checked |
|---------------------------|------|------------------|
| `ledger` post, void, reverse, correction (manual JE) | Journal entries | every line |
| `ledger` post of a document's entry (invoice, credit memo) | Invoices and credit memos | every line |
| bill, vendor credit (area 3) | Bills and vendor credits | every line |
| `payments.allocate` / release (Sales / Purchase) | Payments received / Bill payments | the AR or AP line |
| pay run (area 2) | Bill payments | every line |
| unmatch, reconciliation adjustment, deposits, transfers (area 12) | Bank and card | the bank or card line |
| reclass (area 10) | Journal entries (Q5 A) | both lines of each pair |
| prepaid recognition and catch-up (area 10) | Journal entries (Q5 A) | every line |
| depreciation, disposals (area 11) / loans (area 11) | Fixed assets and depreciation / Loans | every line |
| payroll import (area 19) / receipts, inventory (area 9) / owner pay apps (area 4) | Payroll / Inventory and receipts / Billing | every line |
| `custom_fields.set_value` on a posted invoice or bill | Invoices and credit memos / Bills and vendor credits | none (Q6 A) |
| attachment removal on a posted document (area 18 O6) | the document's area | none (Q6 A) |

No trigger backstop for partial locks (H4: workflow rules in services). The closed-period trigger stays as the
integrity backstop. A static test lists every service function that writes `journal_line` or changes a posted
record and fails if it does not call `period_locks.check_open` (Q7 A).

### 1.5 Reopen (L7) and locks

- `reopen_period` keeps what it does today (permission, confirm, reason, history row, `books_closed_through`
  moved back) and, in the same transaction, clears every close task's done record (section 3, Q15 B). The
  Close dialog lists the effect on entries, reconciliations, and close checks. Reports return to Preliminary
  (derived from `is_closed`).

Corrected 2026-11-21 (close audit): Call Area 12's `reconciliation.reopen_for_period` in the period reopen transaction.
Affected Finished or Changed after finish reconciliations become **Reopened**. They keep their cleared lines
and prior report, and they fail the bank reconciliation close check until finished again. Use this wording in the Close dialog.
"Affected reconciliations move to Reopened. Cleared lines and the prior report are kept. Finish them
again to pass the bank reconciliation close check."
  [Area 12 §§3.3–3.4](area_12_bank_and_reconciliation.md#33-proposed-schema)

- Partial locks set before the full close (Q8 A): stay as they were; the reopened period shows Partly closed, and
  the reopen dialog lists them with an "Unlock these too" option (an unlock with the same reason).
- Reopen clears the period's reviewed-by, which is `fiscal_period.closed_by`/`closed_at` (Q9 A; it already does,
  `periods.py:345-352`), logged; `period_status_history` keeps each closer. It leaves snapshots and frozen KPI
  values in place (section 4).

### 1.6 How it lands in the baselines

Company only: add `lock_area` (seeded) and `period_lock` with their indexes, integrity and audit triggers; drop
`fiscal_period_lock` and its three audit triggers; `close_task.area` (section 2) points at `lock_area`. Add
`row_version` to `fiscal_period` and `fiscal_year`. No permission row is added under Q3 A. Every development
database is blocked and rebuilt (CLAUDE.md section 5.2; list them and ask first, rule 9).

### 1.7 Effect on existing services and tests

- `payments._check_period` calls `period_locks.check_open`; its lock refusal becomes `PeriodLockedError`
  (`tests/test_payments.py:267`, `:577` change their inserts to `period_lock` and their expected error).
- `ledger.py`: the four closed-period sites (`:312`, `:728`, `:982`, `:1187-1203`) call the shared check with the
  Journal entries area (or the document's area) and the line accounts. The R48 messages stay word for word.
- `custom_fields._check_posted` adds the area check (next_step input 4).
- `tests/test_schema_replan.py:436-444` is rewritten for `period_lock`; its audit list (`:733`) renames the table.
- No screen exists for locks today; nothing in `modules/views_*.py` changes.

### 1.8 Tests to write later

- Each action in the 1.4 table is refused in a locked area and in a period with a locked account, writes nothing
  (file compare, prevention rule), and succeeds after unlock.
- An Account lock refuses a JE with only one line on the locked account; an unrelated account passes.
- The bank account lock refuses unmatch for that account only; Bank and card area refuses every type in the
  9:20 PM list.
- R48: a Void dated in a locked period 13 is refused with the R48 sentence, never moved to period 12 or 14.
- Lock without a reason (or a blank one), or without `period.close`, is refused and writes nothing; the CHECK
  refuses a row with no `lock_reason`.
- Unlock without a reason, without `period.reopen`, or with a stale `row_version` is refused; the row is unlocked
  once only (trigger); DELETE refused; relock inserts a new row; the partial unique index refuses two live locks.
- Locking a closed period is refused; `PeriodLockedError` is caught by `except PeriodClosedError`.
- Static: every journal-writing or posted-record-changing service calls the check.
- Agent context: locking and unlocking refused (not in AGENT_ALLOWED).

Amendment 2026-11-21 (owner 2:05 AM, close audit): Rebuild tests for close dates and the Special cutoff record.

- Replace `tests/test_period_close.py:189`, `test_moving_books_closed_through_forward_closes_whole_periods`.
  Its March 15 case currently accepts and stores a mid-month ordinary cutoff. Test that an ordinary March 15
  close returns "Pick a month end" without writing a period flag, settings change or history row. Test that an
  ordinary March 31 close closes whole months and records a month-end date.
- Test an explicit Special cutoff on an exact event date, including first-day, mid-month and month-end
  examples. Require a valid "Special cutoff" reason and a nonblank note. Verify the saved date, actor, time,
  reason, note and audit history, and the label `Closed through <date> (special cutoff)`.
- For a Special cutoff on March 15, refuse new posting on March 14 and March 15, including a reversal or
  correction dated on the cutoff. Allow March 16 in the still-open month when the other checks pass. Verify
  that an ordinary March 31 close retains the cutoff event and closes the rest of March.

---

## 2. Close checklist

### 2.1 Current state

- `period_close_check` (`001_company.sql:440-443`): `check_code` CHECK IN ('draft_entries', 'earlier_period_open',
  'pending_approvals', 'control_overrides', 'ledger_integrity'), `mode` warn (default) or block. Run by
  `periods._run_checks` (`periods.py:274-299`) and `_integrity` (`periods.py:302-310`); judged by `_judge`
  (`periods.py:324-331`: any block stops the close; warnings need `acknowledge_warnings=True`). Changed by
  `set_close_check_mode` (`periods.py:539`, `company.settings`, audited). `ledger_integrity`: Broken follows the mode,
  Unavailable and the unverified range are always warnings (`ledger_verify.py:641-658`, KS15).
- `close_task` (`001_company.sql:4095-4107`: `period_id`, `title`, `area` in the old six, `assignee_user_id`,
  `due_date`, `status` Open/Done/Skipped, `is_blocking` default 0, `completed_by`, `completed_at`, `sort_order`) and
  `close_task_dependency` (`:4109-4114`, PK and no self-edge). Audited. **No service and no screen**; only
  `tests/test_schema_replan.py:651` touches them.
- No template, no step, no system/custom kind, no cycle check, no due-date rule, no skip reason, no "tasks wait"
  setting.

### 2.2 Decided

- 11-14 12:50 PM and C56: ordered steps Costs → PM estimates to complete → WIP → Reconciliations → Review → Close;
  the WIP check fails when a cost or estimate to complete changed after the WIP entry, and passes only when WIP is
  current and its review task is done; reconciliations of the listed accounts against their subledger or
  schedule; manual % complete listed by the close checks; role tasks from templates.
- 11-15 1:31 PM and C97: system tasks (made by the app, complete themselves when their check passes; name, step,
  check and built-in dependencies locked; Owner and Due editable) and custom tasks (completed by a person, optional
  required attachment, Skip needs a reason). Dependencies are a directed graph across both kinds; cycles refused;
  built-in edges cannot be removed. A company template, copied to a period checklist at period start; a task can
  go in the template, this period only, or both. Completion records who, when, a note and an attachment.
  Everything audited. The automatic checks become system tasks.
- Blocking (rule 0): ERP setting **Tasks wait for their dependencies**, off by default (warn and confirm), audited.
  L2: every check warns by default and can block (amends C4). Q2 A: the per-check warn/block modes on the Controls
  page are the only blocking switch for checks; no global "Block closing a period when checks fail" switch;
  close.html's wording becomes "Some checks are set to block in Controls".
- **KS15 (always, whatever the mode):** a per-check block mode never turns `ledger_integrity`'s unverified-range
  finding into a block. With `ledger_integrity` set to block, only a Broken chain blocks; the unverified range
  (entries JE-000001 to JE-N cannot be verified) and Unavailable stay warnings in every mode. This is how
  `ledger_verify.integrity_check` behaves today (`ledger_verify.py:641-658`) and the replan keeps it.
- C4 as amended by L2 and S 11-19 12:45 AM: the deferral close check ships with the prepaid schedule service.
  Prepaid entries due in the period show on the checklist; an entry dated in a closed period is Blocked and shows
  there; caught-up entries are marked "caught up" (S 11-18 11:55 PM, 11-19 12:45 AM).
- close.html close dialog: lists warnings, then open tasks, then what is still dated in the period; closing with
  warnings asks for a reason. Q23 A: the reason is required when any warning is acknowledged and is stored on the
  Close row of `period_status_history` (its CHECK allows a reason on Close; required only on Reopen as today).

Corrected 2026-11-21 (close audit): The current service accepts warning acknowledgement and stores a `NULL` reason.
In the rebuild, validate and store the trimmed reason on the applicable Close history rows in the same transaction as the close.
The dialog must use each check's configured Warn or Block mode. Use the existing per-check controls and retain
the KS15 treatment of ledger-integrity warnings.

### 2.3 Every check: exists today and asked for

| Check (`check_code`) | Step | Source | State | Ships with |
|----------------------|------|--------|-------|------------|
| `draft_entries` | Review | built | exists (`periods.py:276`) | now |
| `earlier_period_open` | Close | built | exists | now |
| `pending_approvals` | Review | built | exists (JE approvals only) | widen with area 14 |
| `control_overrides` | Review | built (R-rules) | exists | now |
| `ledger_integrity`: Broken follows the mode; the unverified range and Unavailable are warnings in every mode, never a block (KS15) | Close | KS15 | exists | now |
| `deferral_entries_posted`: scheduled prepaid/deferral entries for the period posted; Blocked entries listed; caught-up entries listed (info) | Costs | C4, L2, S 11-18 11:55 PM, 11-19 12:45 AM | asked | prepaid service (area 10) |
| `deferral_tie_out`: prepaid and deferral subledger ties to the GL (1400 Prepaid and the unearned revenue account) | Reconciliations | C4 | asked | prepaid service |
| `wip_current`: WIP entry later than every cost and estimate-to-complete change | WIP | 11-14, C56 | asked | WIP service (area 8 or 10) |
| `manual_pct_complete`: jobs with manual % complete (listed with who and why) | WIP | 11-14, C56 | asked | `project.manual_*` columns (area 7/8) |
| `controlled_entry_reviewed`: the WIP adjustment and other controlled-account entries reviewed | Review | close.html | asked | approvals (area 14) |
| `ar_tie_out`, `ap_tie_out`: AR and AP subledgers tie to the control accounts | Reconciliations | close.html | asked | areas 1, 3, 5 |
| `subledger_reconciliations`: retainage receivable and payable, GRNI (Received, not billed), customer deposits, payroll clearing, sales and use tax, and the others in 11-14's list, each against its subledger or schedule | Reconciliations | 11-14 (account numbers: F11) | asked | each owning area |
| `bank_reconciled`: each bank and card account reconciled through the period end at $0.00 difference | Reconciliations | close.html, area 12 | asked | area 12 |
| `reconciliation_changed`: a completed reconciliation flagged "changed after completion" by an unmatch | Reconciliations | S 11-18 9:18 PM, to_planning 11-18 item 3 | asked | area 12 |
| `staged_lines_dated`: import lines still unposted and dated in the period (the Ramp lines) | Review | close.html | asked | imports |
| `depreciation_run`: depreciation posted for the period | Costs | close.html (Go to Run depreciation) | asked | area 11 |
| `received_not_billed_aged`: receipts not billed after 30 days | Costs | C56 (Warehouse role task) | asked | area 9 |
| `material_advances_open` | Costs | C56 | asked | area 9 |
| `stock_count` (only when inventory is on) | Costs | C56 | asked | area 9 |
| `estimates_to_complete_updated` (all open jobs), PM role task, due before WIP | PM estimates | C56 | asked | area 8 |
| `completed_job_review` (keep open or close out), per Completed job | PM estimates | C56 | asked | area 8 |
| `kpi_freeze_note`: KPIs whose value will fail at close (stored as null with a note; never blocks) | Close | contracts 2.7 | asked | area 17 |

Amendment 2026-11-19 (owner, area 10 F11): `deferral_tie_out` finds the prepaid and unearned revenue accounts by flag
(`account.is_deferral_account`) and role (`company_settings.prepaid_expenses_acct_id`, `unearned_revenue_acct_id`),
not by number; "1400" in the row above is an example (docs/replan_2.9/area_10_prepaid_deferrals_reclass.md section 3).

Codes not yet buildable are seeded only when their service ships (each adds its seed row and its CHECK value in
the same baseline edit as long as the baseline is unreleased; a numbered migration after release). The C56 "role
tasks" are shipped template rows of kind System when a check backs them, otherwise shipped Custom rows, owners by
role (Q11 A).

Amendment 2026-11-20 (owner 11-14 7:16 PM, decision audit; answered 1:50 AM): section 2.3 gains the check
`clearing_open_items` (step Reconciliations). It lists open Clearing ID items, with their age, on accounts with
`track_clearing_id = 1` other than AR and AP, which `ar_tie_out` and `ap_tie_out` cover. It warns by default (L2) and
ships now.

Amendment 2026-11-20 (owner 2:25 AM, from area 7 Q18 A): `wip_current` compares `poc_snapshot.computed_at` with the
latest posting carrying the job and the latest `job_forecast_revision` (area 7 section 8.3); `manual_pct_complete`
reads `project.manual_pct_complete`, `manual_pct_reason`, `manual_pct_by` and `manual_pct_at` (area 7 section 1.3).
The columns land in the 2.9 baseline; the WIP service (`wip.py`) ships with the v1.1 construction work, and
`wip_current` is seeded when it does.

### 2.4 Proposed schema

**`period_close_check`** (kept; the system-check registry): keep `check_code`, `mode`; add `step_code`
REFERENCES `close_step`, `name` TEXT NOT NULL, `row_version`. The CHECK list grows only with built checks (above).

**`close_step`**: `step_code` TEXT PRIMARY KEY, `name` TEXT NOT NULL UNIQUE, `sort_order` INTEGER NOT NULL,
`is_system` INTEGER NOT NULL (the six seeded steps are system and cannot be removed or renamed; custom steps can,
"Step (or new)" in C97), `row_version`.

**`close_task_template`** (the company template):

| Column | Type and constraint |
|--------|---------------------|
| `template_task_id` | INTEGER PRIMARY KEY |
| `kind` | TEXT NOT NULL CHECK IN ('System', 'Custom') |
| `check_code` | TEXT REFERENCES period_close_check; CHECK (kind = 'System') = (check_code IS NOT NULL); UNIQUE where not NULL |
| `name` | TEXT NOT NULL CHECK (length BETWEEN 1 AND 200) (fixed for System by the service) |
| `step_code` | TEXT NOT NULL REFERENCES close_step |
| `owner_user_id` / `owner_role_code` | one or neither (C97 "Owner (person or role)"); role codes from area 18 |
| `due_type`, `due_n` | section 3 |
| `how_to` | TEXT (max 4,000) |
| `needs_attachment` | INTEGER NOT NULL DEFAULT 0 (Custom only) |
| `is_active` | INTEGER NOT NULL DEFAULT 1 (Remove is deactivate; history keeps the row) |
| `sort_order` | INTEGER NOT NULL |
| `row_version` | INTEGER NOT NULL DEFAULT 1 |

**`close_task_template_dependency`**: `task_id`, `depends_on_task_id` (both → template), `is_builtin` INTEGER NOT NULL
DEFAULT 0; PK both ids; CHECK no self-edge. Built-in rows cannot be removed: the service refuses it, with a test
(Q12 B; H4: no new trigger for a workflow rule). Cycles are refused by the service (a graph walk inside the write
transaction); a CHECK cannot see a path.

**`close_task`** (the period checklist; replaces the current columns):

| Column | Type and constraint |
|--------|---------------------|
| `task_id` | INTEGER PRIMARY KEY |
| `period_id` | INTEGER NOT NULL REFERENCES fiscal_period |
| `template_task_id` | INTEGER REFERENCES close_task_template (NULL: "this period only") |
| `kind`, `check_code`, `name`, `step_code`, `owner_user_id`, `owner_role_code`, `due_type`, `due_n`, `how_to`, `needs_attachment`, `sort_order` | copied from the template at period start, editable for this period as C97 allows |
| `area_code` | TEXT REFERENCES lock_area (the area the "offer to lock" uses, C56) |
| `status` | TEXT NOT NULL DEFAULT 'Open' CHECK IN ('Open', 'Done', 'Skipped') |
| `done_by`, `done_at` | set together when Done (for System, the user whose action made the check pass, 11-17 6:08 PM); cleared by a reopen (Q15 B) |
| `done_note` | TEXT (max 1,000) |
| `skip_reason`, `skipped_by`, `skipped_at` | set together when Skipped; Custom only (CHECK kind = 'Custom' OR status <> 'Skipped') |
| `row_version` | INTEGER NOT NULL DEFAULT 1 |

- UNIQUE (`period_id`, `template_task_id`) where `template_task_id` is not NULL; UNIQUE (`period_id`, `check_code`)
  where not NULL. Index (`period_id`, `step_code`, `sort_order`).
- `is_blocking`, `assignee_user_id`, `due_date`, `title`, `completed_*` are dropped (renamed or replaced). The
  required attachment uses area 18's `attachment` with `record_type` 'Close task' added to its CHECK.
- **`close_task_dependency`**: add `is_builtin`; dependencies only within one period and built-in edges not
  removable, both by the service only (Q12 B, H4), each with a test.

**`company_settings`**: `tasks_wait_for_dependencies` INTEGER NOT NULL DEFAULT 0 (control, OFF; listed on the
Controls page, audited with a reason as area 18 requires for controls). No global block switch for checks (Q2 A).

When the period checklist is made: at the period's start, by the same upkeep that creates years (S3,
`ensure_upcoming_years`), or on first open of the period's checklist, whichever is first (Q10 A).

### 2.5 How it lands in the baselines

Company only: add `close_step` (6 seed rows), `close_task_template` and its dependency table (seeded with the
system tasks of the built checks and their built-in edges), rebuild `close_task` and `close_task_dependency`,
extend `period_close_check`, add the setting. Audit triggers on every new table (area 18 rule). Blocks every
development database (section 5.2).

### 2.6 Effect on existing services and tests

- `periods.close_checks` returns the period's tasks with their check results (system tasks completing when
  their check passes; done records written then). `_judge` also considers open tasks when
  `tasks_wait_for_dependencies` is on (Close disabled with the reason) and keeps L2 for checks.
- `close_period` and the close dialog: open tasks are a warning by default, like checks.
- `tests/test_schema_replan.py:651` rewritten; `tests/test_period_close.py` and `tests/test_periods.py` keep their
  check assertions (codes unchanged) and gain task assertions.
- A new service module `close_tasks.py` (template edits, period copy, done, skip, dependencies).

### 2.7 Tests to write later

- Template copy at period start is exact and idempotent; "this period only" does not reach the template; "also
  apply to 2026-10" does both.
- Cycles refused across kinds (custom → system → custom); the service refuses removing a built-in edge, in the
  template and in a period, and writes nothing (Q12 B: the only guard, so this test is required); a dependency
  across two periods is refused; a System task's name, step and check cannot change; Owner and Due can.
- **KS15:** with `ledger_integrity` set to block, a ledger with an unverified range (and no break) closes after
  the warning is acknowledged; Unavailable likewise; a Broken chain blocks. With the mode warn, all three warn.
- Skip refused for System tasks and without a reason; Done refused for a custom task needing an attachment until
  one is added.
- `tasks_wait_for_dependencies` off: done out of order warns; on: refused with one sentence; Close blocked while a
  task waits.
- Each check in 2.3 when built: passing, failing, warn vs block.

Corrected 2026-11-21 (close audit): Add a rebuild regression for acknowledged warnings. Missing or blank reasons
leave period state and history untouched when warnings are present. A valid acknowledgement records the trimmed reason on the
Close history row. Cover period close, Books closed through, and year close when they close periods with
warnings. A clean close needs no warning reason. A failing Block check refuses the close even when the user
supplies a reason. Verify the dialog respects both modes when two checks have different modes.

- The prepaid check lists Blocked and caught-up entries and passes once due entries are posted.
- A stale `row_version` on any task save is refused (g4).

---

## 3. Company calendar items for close

### 3.1 Current state

`close_task.due_date` (a stored date) only. No work week, holidays, `close_target_bd` or reviewed-by columns.
`fiscal_period.closed_by` and `closed_at` hold the closer; `reopen_period` clears them (`periods.py:345-352`).

### 3.2 Decided (11-17 6:03 PM and 6:08 PM)

- Close tasks feed one calendar query (with job tasks, calendar items and CRM activities), filtered by the user's
  permissions; a read view, edits through each source's service. Accounting deadlines outside the close: out of
  scope.
- Due: `due_type` business_day | fixed_day and `due_n`. Business days use the work week and holidays; a fixed day
  on a non-business day moves to the business day before. Worked out per period, not stored as text. Company
  setting `close_target_bd`.
- `done_by`/`done_at` per close task; `reviewed_by`/`reviewed_at` on the period (the closer). No self-review check.
  Reopening clears each record, logged.

### 3.3 Proposed schema

- `close_task_template` and `close_task`: `due_type` TEXT CHECK IN ('business_day', 'fixed_day') or NULL (no due),
  `due_n` INTEGER CHECK (business_day: 1-23; fixed_day: 1-31; NULL with `due_type` NULL). Business day N counts
  after the period end (BD1 = the first working day after); fixed day N is that day of the month after the
  period, and a day past that month's end becomes its last day (Q13 A). The due date is computed by the service per period and returned as an ISO date
  (g2); never stored.
- `company_settings.close_target_bd` INTEGER CHECK (NULL or 1-23): the business day the close should finish;
  shown as the Close task's due.
- Work week and holidays (Q14 A: in area 13; area 8's calendar and schedules reuse them): `company_settings.work_week` TEXT
  (seven 0/1 characters, Monday first, default `1111100`, CHECK length 7 and only 0/1) and `company_holiday`
  (`holiday_date` TEXT PRIMARY KEY, `name` TEXT NOT NULL, `row_version`), audited.
- Reviewed-by (Q9 A): the period's existing `closed_by`/`closed_at` are the reviewer and the time; the service and
  screens label them "Reviewed by". No new columns. Reopen clears `closed_by`/`closed_at` on `fiscal_period`
  (logged by its audit trigger, as today); `period_status_history` keeps each closer, so every past review stays
  readable.
- Reopen and done records (Q15 B, owner 11-17 6:08 PM): reopen clears every task's `done_by` and `done_at`, and
  each Done task goes back to Open (System and Custom), in the reopen's transaction. Each cleared task is an
  audited update carrying the reopen's reason; the old values stay in the audit log. Skipped tasks keep their skip
  record (the answer names done records only).

### 3.4 Lands, effects, tests

- Company baseline: the columns and `company_holiday` above. No master change.
- `periods.py`: a `due_date_for(period, due_type, due_n)` helper (pure, takes the work week and holidays) used by
  `close_tasks.py` and the calendar read. No clock read (H2): "overdue" compares with `context.today`.
- Tests: business-day counting across weekends and a holiday; a fixed day on a Saturday moves to Friday; a fixed
  day 31 in a 30-day month becomes the 30th (Q13 A); `close_target_bd` shown; reopen clears `closed_by`/`closed_at`
  and every task's `done_by`/`done_at` (System and Custom back to Open), with one audit row each carrying the
  reason, while `period_status_history` still shows the earlier closer; a reopen that fails leaves every task as
  it was; calendar read refuses tasks a user may not see (`period.view`).

---

## 4. Close snapshot, KPI freeze, measures

### 4.1 Current state

No snapshot table. `period_status_history` is the close event (`history_id`, `acted_at`, `user_id`). No KPI or
non-financial measure tables (area 17). `poc_snapshot` (`001_company.sql:697`) is a job estimate, not a close
snapshot.

### 4.2 Decided

- S 11-18 11:32 PM and to_planning 11-18: on every period close save Ending cash, Net income, Total assets, Total
  liabilities, Total equity as of the period end, at the moment of closing. Insert-only, never edited, in the
  audit log. Each close (after a reopen too) saves a new one; earlier ones kept. History shows each Closed event
  with its five figures and, where today's value differs, today's value and the difference. History only (no
  flag on the Periods list). Per company.
- Definitions (to_planning 11-18 item 3): ending cash = bank and cash accounts (the cash flow report's set); net
  income = the period's income statement; totals from the balance sheet as of period end.
- Contracts 2.7 and section 12 item 8: every active KPI's value frozen in the close transaction, insert-only,
  audited; each close keeps its own rows; reports read the latest close's row; a failed value is stored as null
  with a note and never blocks.
- Contracts section 12 item 10 (the contracts' own Q16 B, not this doc's Q16): typed non-financial values refused in a closed period; derived
  recomputation skipped there.
- S 11-19 12:45 AM: "As reclassed" applies from the reclass date, so closed figures and the snapshot never change.

### 4.3 Proposed schema: `period_close_snapshot`

| Column | Type and constraint |
|--------|---------------------|
| `snapshot_id` | INTEGER PRIMARY KEY |
| `period_id` | INTEGER NOT NULL REFERENCES fiscal_period |
| `close_event_id` | INTEGER NOT NULL UNIQUE REFERENCES period_status_history(history_id) (the Close row) |
| `closed_at`, `closed_by` | TEXT NOT NULL, INTEGER NOT NULL (copied from the event) |
| `as_of_date` | TEXT NOT NULL (the period end) |
| `basis` | TEXT NOT NULL CHECK IN ('pre_adjustment', 'gaap', 'tax') (section 4.4) |
| `ending_cash_cents`, `net_income_cents`, `total_assets_cents`, `total_liabilities_cents`, `total_equity_cents` | INTEGER NOT NULL, CHECK typeof integer (rule 1) |
| `through_entry_number` | INTEGER NOT NULL (the last posted entry number at the close; ties the snapshot to the checkpoint, section 5) |

- CHECK `total_assets_cents = total_liabilities_cents + total_equity_cents` (equity includes the unclosed current
  earnings, B1: no closing entries), so a snapshot that does not balance cannot be stored.
- Integrity triggers: UPDATE and DELETE refused (insert-only). Audit trigger on insert (area 18).
- Index (`period_id`, `closed_at`).
- Written by `periods._close` in the close's own transaction for **every** path that closes a period: Period
  close, Books closed through (one per month it closes), Year close (periods 13 and 14 it closes).

### 4.4 The five definitions (owner answers Q16 B, Q17 A, Q18 A)

All accrual (B1 reports compute retained earnings; cash basis is a report view, not stored). Signs: assets and
cash as debit-positive balances; liabilities and equity as credit-positive; net income income-positive.
- **Basis by period:** months 1-12 use pre-adjustment (entries in periods 13 and 14 are excluded, though dated the
  same last day); period 13 uses GAAP (1-13); period 14 uses tax (1-14) (A1).
- **Ending cash (Q16 B):** the balance as of the period end of the accounts whose account type is Bank or Cash,
  plus the undeposited funds account (`company_settings.undeposited_funds_acct_id`). Card accounts are excluded.
  The cash flow report uses the same set.
  Amendment 2026-11-19 (owner, area 12 Q12 A): ending cash is the GL accounts of the `bank_account` rows of every
  kind except Credit card, plus `company_settings.undeposited_funds_acct_id`. This replaces the "Bank and Cash account
  types" wording above (the baseline has no such account types; docs/replan_2.9/area_12_bank_and_reconciliation.md
  section 5.3).
- **Net income:** income minus expenses of entries in that period only (not year to date).
- **Total assets / liabilities:** balances as of the period end, all periods to date under the basis.
- **Total equity:** equity accounts plus all net income not yet in retained earnings (prior years and current
  year to date), so the balance check above holds.
- Computed from `journal_line` in the close transaction (Q18 A), not from the period balance summary.

**Reading:** `periods.close_history(context, period_id)` (`period.view`) returns each Close and Reopen event; each
Close with its snapshot, today's five values and per figure `differs` and `difference_cents` (pages never compare,
g2). Today's values can differ only after a reopen and a repost, or after an account changes type or class
(the snapshot stores totals, not accounts); History shows both cases the same way.

### 4.5 KPI freeze and measures

- The close transaction also inserts area 17's `kpi_value` rows (contracts section 12 item 8) with the same
  `close_event_id`; area 13 owns the call order: checks → close flag → history row → snapshot → KPI values →
  commit → checkpoint (section 5). A KPI failure is a null value with a note and never blocks.
  Amendment 2026-11-19 (owner, area 17 Q13 B): the KPI freeze also runs when periods 13 and 14 close, through
  `periods._close` (so through `close_period` on either, and through `close_year`), for each KPI whose basis includes
  the period: period 13 for the gaap, tax and management bases, period 14 for the tax basis; a measure-sourced KPI
  freezes months 1-12 only (docs/replan_2.9/area_17_fields_layouts_reports.md section 6.4).
- Non-financial measures (area 17, item 10): typed values refused with `PeriodClosedError` in a closed period;
  derived recomputation skips closed periods. Partial locks do not apply to measures (Q19 A).
- Reopen: snapshots and KPI values are kept; reports show live values again while the period is open
  (contracts 2.7); the next close adds new rows.

### 4.6 Lands, effects, tests

- Company baseline: `period_close_snapshot`; `kpi_value` comes with area 17 and references the same history row.
- `periods._close` gains the snapshot (and the KPI hook once area 17 exists); `set_books_closed_through` and
  `close_year` get it through `_close`. Close takes longer by one balance query per period.
- Tests: one snapshot per close path; reopen + repost + re-close keeps the first and adds the second, and History
  shows the difference; UPDATE/DELETE refused; the balance CHECK refuses a bad row; a rolled-back close leaves
  no snapshot; periods 13/14 use their bases; a reclass dated later never changes a closed snapshot; an
  account type change shows a difference; ending cash includes Bank, Cash and undeposited funds and excludes a
  card account's balance (Q16 B).

---

## 5. Checkpoints: R26, K18 and the period close

### 5.1 Current state

- **R26/K18 are about closing the company file**, not a period: `App.close_company_ledger` (`app_strata.pyw:288`)
  calls `ledger_verify.checkpoint_on_close` at sign-out and exit with a fresh context; it never blocks and logs a
  failure.
- **The period close already signs its own checkpoint:** `close_period`, `close_year` and
  `set_books_closed_through` (forward) return `ledger_verify.record_close_checkpoint` (`ledger_verify.py:487`),
  kind 'Period close' or 'Year close', `ref_type` fiscal_period or fiscal_year, after the commit; a failure is
  reported, never raised. Books closed through signs one checkpoint for the last month it closes.
- `ledger_checkpoint` (`001_company.sql:535-556`) kinds include 'Period close' and 'Year close'.

### 5.2 How they relate to the snapshot

- The two answer different questions: the checkpoint says "the posted ledger rows were not altered outside the
  app" (the R15 chain, signed); the snapshot says "these five figures were the books at the close". The
  snapshot cannot replace the checkpoint (it is not signed) and the checkpoint cannot show what moved.
- They are written at different times: the snapshot inside the close transaction (it must exist when the period
  is closed), the checkpoint after the commit (it may fail and the close stands). So the snapshot cannot hold the
  checkpoint's id. The link is `through_entry_number`: History shows "Ledger verified through JE-N at this close"
  when a Period close checkpoint for that period has the same `through_entry_number`.
- Q20 A: the checkpoint keeps `ref_type` fiscal_period or fiscal_year and its `ref_id`; no change to
  `ledger_verify`. The snapshot's `through_entry_number` is the link.
- K18's sign-out checkpoint is unrelated to the snapshot and stays as it is. Naming (F10): the screens should say
  "sign-out checkpoint" for R26/K18 so "close" means the period close.

### 5.3 Tests to write later

- A period close writes the snapshot even when the checkpoint cannot be signed (key missing): the snapshot exists,
  `checkpoint_error` is reported.
- `through_entry_number` equals the close's verification `through_entry_number`.
- Books closed through over three months: three snapshots, one checkpoint (today's behaviour), History shows the
  verified line only for the month the checkpoint names (Q20 A).

---

## 6. Period balance summary

### 6.1 Current state

None in the baseline. Proposed by docs/contracts/reports.md section 12 item 12 (area 10 with 17):
`ledger_period_balance` (`period_id`, `account_id`, `entity_id`, `project_id`, `cost_code_id`,
`dimension_set_id`, `debit_cents`, `credit_cents`, `line_count`) written only by `ledger.py` at posting;
`dimension_set` and `dimension_set_member`; a verify check against `journal_line` and a rebuild tool; index
`journal_entry (period_id, is_posted)`.

### 6.2 Who writes it and how it stays right across reopen and re-close

- **Writer:** only `ledger.py`, in the posting transaction, after the lines are final and the entry is posted
  (post, void, reversal, correction, auto-reversal, every document posting, every system entry). One upsert per
  key (`INSERT ... ON CONFLICT ... DO UPDATE`, portable to PostgreSQL; not `INSERT OR REPLACE`, H5). A static test
  (like rule 7's writer test) allows no other writer.
- **Keys with no value:** NULL is distinct in a UNIQUE index, so the unique key is an expression index on
  `COALESCE(x, 0)` for each nullable key (portable; Q21 A). The keys stay nullable.
- **Why reopen and re-close need nothing:** posted `journal_line` rows are append-only and posted entries change
  only by new reversing entries (rule 8). The summary is a sum of posted lines by the period the line's entry is
  in, so: a close or reopen changes no line and no row of the summary; posting into a reopened period adds to that
  period's rows in the same transaction; a void or correction adds to the period it is dated in (R48), never the
  original's; a reclass adds to the reclass date's period. Account type changes do not touch it (keyed by
  `account_id`). A rolled-back post leaves no change (same transaction).
- **Things that could make it wrong** and their guard: a write outside `ledger.py` (static test; trigger-level
  guard not added, H4); a bug in the upsert (the tie-out check); a database edited outside the app (the chain and
  the tie-out check).
- **Tie-out check:** a new close check `period_balance_tie_out` (step Close; warn by default, L2) compares the
  period's summary rows with the `journal_line` sums for that period; also run by `ledger_verify` full
  verification. The rebuild tool lives in `tools/` (rule 11 lets tools connect) and is run on request; a service
  wrapper needs `ledger.verify` and is audited (Q22 A).
- **Snapshot vs summary:** the snapshot reads `journal_line` (Q18 A) so a damaged summary cannot enter a stored
  figure; reports read the summary.
- **Audit (area 18):** the summary is derived and is on area 18's derived-table exempt list beside the counters
  (owner 2026-11-19, F13; recorded as a dated amendment in docs/replan_2.9/area_18_admin_security_audit.md
  section 1.2). The schema test that holds the exempt list names it.

### 6.3 Tests to write later

- Summary equals `journal_line` sums after: post, void, correction, auto-reversal pair, posting into a reopened
  period, re-close; a rolled-back post leaves it unchanged; two writers in parallel both counted.
- The tie-out check fails on a hand-edited summary row and passes after the rebuild tool.
- Static: no writer outside `ledger.py`; the upsert has no SQLite-only syntax.

---

## 7. Row version (rule g4) and audit in this area

| Table | Editable? | `row_version` |
|-------|-----------|---------------|
| `fiscal_period`, `fiscal_year` | closed and reopened by services | yes |
| `period_lock` | unlock once | yes |
| `period_close_check` (mode), `close_step`, `close_task_template`, `close_task` | yes | yes |
| `company_holiday` | yes | yes |
| `company_settings` (new columns) | yes | area 21 adds it to the row |
| `close_task_template_dependency`, `close_task_dependency` | insert and delete only | no (a delete names both ids) |
| `period_status_history`, `period_close_snapshot`, `kpi_value` | insert-only | no |
| `lock_area` | seeded | no |
| `ledger_period_balance` | derived, written by `ledger.py` only | no |

Every new table gets audit triggers (area 18), except `ledger_period_balance` (derived, exempt). Reasons required
(area 18 table "Which actions require a reason"): lock and unlock (Q4 B), reopen (which also clears the tasks'
done records, Q15 B), skip, and closing with warnings (Q23 A). Integrity triggers in this area guard append-only
and insert-only rows only (`period_lock`, `period_close_snapshot`); no trigger enforces a workflow rule (Q12 B, H4).

---

## 8. Conflicts with decisions (all resolved by the owner's answers, 2026-11-19)

- **F1 Area names.** The baseline has six areas (Sales, Purchases, Banking, Payroll, Inventory, Journal;
  `001_company.sql:3914`, also on `close_task.area`); close.html and C56 show ten (Billing, Invoices and credit
  memos, ... Journal entries); the planning log 16:27 says "area locks (Sales/Purchases)"; S 11-18 9:18 PM adds
  Bank, which close.html does not show yet. **Resolved by Q1 A:** close.html's ten areas plus Bank and card (11)
  in `lock_area`; design adds Bank and card to close.html.
- **F2 Control or tool.** Planning log 16:27: "All are controls (nothing locked unless set)". 11-14 1:00 PM:
  partial close "is a tool on the Close screen, always available, not a Company control". Both mean nothing is
  locked by default; they differ on whether locks appear on the Controls page. **Resolved by Q1 A:** locks live on
  the Close screen only, audited; nothing on the Controls page.
- **F3 One switch or per-check modes.** L2 and the baseline give each check its own warn/block mode; 11-15 and
  close.html speak of one switch. **Resolved by Q2 A:** per-check modes on the Controls page, no global switch;
  close.html's wording changes. KS15 holds in every mode (section 2.2).
- **F4 Unlock by role.** C56 and close.html: "Only an Admin or the Master can unlock"; L7: code checks
  permissions, never role names. **Resolved by Q3 A:** lock `period.close`, unlock `period.reopen`.
- **F5 Reason on lock.** Area 18's table lists "Set or remove a period lock" as needing a reason; close.html's
  lock dialog had no reason field. **Resolved by Q4 B:** a reason is required to lock and to unlock
  (`lock_reason` NOT NULL); close.html gains a reason field on the lock dialog. Area 18's table stands as written.
- **F6 Reviewed-by.** 11-17 asks for `reviewed_by`/`reviewed_at` on the period "(the closer)"; the period already
  stores `closed_by`/`closed_at`. **Resolved by Q9 A:** no new columns; reopen clears `closed_by`/`closed_at`
  (logged) and `period_status_history` keeps each closer.
- **F7 Reopen clears done records.** 11-17 6:08 PM "Reopening clears each record". **Resolved by Q15 B:** reopen
  clears every task's `done_by`/`done_at` and the period's reviewed-by, each logged.
- **F8 "Mark step done".** C56 offers to lock a step's areas when the step is marked done; C97 removes "Mark step
  done". **Resolved by Q24 A:** the offer comes when a step's last task is done, never automatic.
- **F9 Contracts numbering.** The task named "section 12 item 11 (period balance summary)"; in
  docs/contracts/reports.md it is item 12 (item 11 is the operating plan). **Resolved as drafted (no question):**
  this doc cites item 12; the contracts doc is unchanged.
- **F10 "Close checkpoint".** R26 and K18 call the sign-out checkpoint a "close checkpoint". **Resolved by Q20 A:**
  the code and `ledger_checkpoint` stay as they are; screens say "sign-out checkpoint" for R26/K18 (section 5).
- **F11 Account numbers.** 11-14's reconciliation list numbers do not match the construction chart (S 11-19:
  account numbers follow the repo construction chart). **Resolved as drafted (no question):** checks find accounts
  by role (`company_settings.*_acct_id`), never by number.
- **F12 Reopen and reconciliations.** Area 12 owns the transition. Area 13 calls it when the period reopens.

  Corrected 2026-11-21 (close audit): The approved Area 12 transition is **Reopened**. Use the Close dialog wording
  and state behavior in §1.5.
- **F13 Area 18 exempt list.** Area 18's derived-table exempt list did not name `ledger_period_balance`.
  **Resolved (owner 2026-11-19):** the owner approved adding it; a dated amendment line is in
  docs/replan_2.9/area_18_admin_security_audit.md section 1.2. Nothing else in area 18 changes.
- **F14 Prepaid area.** Prepaid recognition and catch-up are system journal entries from a bill line. **Resolved
  by Q5 A:** prepaid entries and reclasses are Journal entries; account locks still apply.

---

## 9. Questions for the owner: answers recorded (2026-11-19)

The options as asked are kept below each answer for the record.

| Q | Answer | Where it lands |
|---|--------|----------------|
| Q1 Lock areas | A: close.html's ten plus Bank and card (11), in `lock_area`; Close screen only | 1.3 |
| Q2 Blocking failed checks | A: per-check warn/block modes, no global switch; KS15 unchanged in every mode | 2.2, 2.3, 2.4 |
| Q3 Who locks and unlocks | A: lock `period.close`, unlock `period.reopen` | 1.3 |
| Q4 Reason when locking | **B:** required to lock and to unlock; close.html gains a reason field on the lock dialog | 1.3, 1.8, 7 |
| Q5 Area of prepaid and reclass | A: both Journal entries; account locks apply | 1.4 |
| Q6 Locks on non-GL edits | A: closed period, `lock_documents_after_posting` and the document's area lock; no account locks | 1.4 |
| Q7 Enforcement | A: service only plus a static test | 1.4 |
| Q8 Partial locks after reopen | A: kept; reopen dialog offers "Unlock these too" | 1.5 |
| Q9 Reviewed-by | A: `closed_by`/`closed_at`, labelled Reviewed by; reopen clears them (logged); `period_status_history` keeps each closer | 1.5, 3.3 |
| Q10 Checklist creation | A: at period start or first open, whichever is first | 2.4 |
| Q11 C56 role tasks | A: shipped template rows, System where a check backs them, Custom otherwise | 2.3 |
| Q12 Built-in edges | **B:** service only, plus a test; the proposed trigger is removed (H4) | 2.4, 2.7, 7 |
| Q13 Due dates | A: BD1 = first working day after the period end; fixed day in the next month, clamped to its last day | 3.3 |
| Q14 Work week and holidays | A: in area 13; area 8 reuses them | 3.3 |
| Q15 Reopen and tasks | **B:** reopen clears every task's `done_by`/`done_at` and the period's reviewed-by, each logged | 1.5, 2.4, 3.3, 3.4 |
| Q16 Ending cash | **B:** Bank and Cash account types plus undeposited funds; card accounts excluded | 4.4, 4.6 |
| Q17 Snapshot basis | A: accrual; 1-12 pre-adjustment, 13 GAAP, 14 tax | 4.4 |
| Q18 Snapshot source | A: `journal_line` in the close transaction | 4.4, 6.2 |
| Q19 Measures and partial locks | A: only a full close freezes measures | 4.5 |
| Q20 Checkpoint reference | A: unchanged; linked by `through_entry_number` | 5.2, 5.3 |
| Q21 Summary keys | A: nullable keys, unique expression index on `COALESCE(key, 0)` | 6.2 |
| Q22 Summary rebuild | A: tool in `tools/` plus an audited service wrapper needing `ledger.verify` | 6.2 |
| Q23 Reason when closing with warnings | A: required; stored on the Close history row | 2.2, 7 |
| Q24 Offer to lock after a step | A: when a step's last task is done, never automatic | 8 (F8) |

Also from the owner (2026-11-19): F13 approved (section 8); required fix KS15 (sections 2.2, 2.3, 2.7).

### 9.1 The questions as asked

**Q1. Lock areas.** (F1, F2)
- A. close.html's ten areas plus "Bank and card" (11), stored in a `lock_area` table; design adds Bank and card to
  close.html. Locks live on the Close screen only, not on the Controls page.
- B. The baseline's six (Sales, Purchases, Banking, Payroll, Inventory, Journal); close.html changes to match.
- C. Only Sales, Purchases and Bank, plus account locks.

**Q2. Blocking failed checks.** (F3)
- A. Keep per-check warn/block modes (L2) on the Controls page; no extra global switch; close.html's wording
  changes to "Some checks are set to block in Controls".
- B. One global switch "Block closing a period when checks fail" (off), and drop per-check modes.
- C. Both: the global switch and per-check modes (a check blocks when either is on).

**Q3. Who locks and unlocks.** (F4)
- A. Lock: `period.close`. Unlock: `period.reopen` (sensitive; Admin, Master, Controller template).
- B. A new sensitive code `period.unlock`, seeded to Admin only.
- C. Lock and unlock both `period.reopen`.

**Q4. Reason when locking.** (F5)
- A. Optional when locking, required when unlocking (close.html as drawn); area 18's table amended.
- B. Required both ways (area 18 as written); close.html gains a reason field on the lock dialog.

**Q5. Area of prepaid entries and reclasses.** (F14)
- A. Both are Journal entries (they are system or reclass journal entries); account locks still apply.
- B. Prepaid entries under Bills and vendor credits (their source); reclass under Journal entries.
- C. Each line pair checks the area of its original document.

**Q6. Which locks block non-GL edits on posted documents** (custom fields, attachment removal; next_step input 4,
area 18 O6)?
- A. Closed period, `lock_documents_after_posting`, and the document's area lock; account locks do not apply.
- B. Closed period and `lock_documents_after_posting` only (area locks are for postings).
- C. All locks, accounts included (any locked account on the document's lines blocks).

**Q7. Enforcement of partial locks.**
- A. Service only (`period_locks.check_open`), plus a static test that every journal-writing or posted-record
  service calls it (H4).
- B. Also a trigger backstop on posting that refuses lines on a locked account (area cannot be seen there).

**Q8. Partial locks after a full close and reopen.**
- A. Kept as they were; the reopen dialog lists them with "Unlock these too".
- B. Cleared by the reopen (each an audited unlock with the reopen's reason).
- C. A full close turns every live partial lock into history (unlocked by the close), so a reopen opens everything.

**Q9. Reviewed-by on the period.** (F6)
- A. Use the existing `closed_by`/`closed_at`, labelled "Reviewed by"; no new columns.
- B. Add `reviewed_by`/`reviewed_at` beside them (same values today, separable later).

**Q10. When the period checklist is created.**
- A. When the period starts (the upkeep that creates years), or on first open of its checklist, whichever is first.
- B. When the period is created (a year's periods all get checklists at once).
- C. Only when someone opens the period's checklist.

**Q11. C56 role tasks** (PM estimates to complete, Completed-job review, Warehouse tasks).
- A. Shipped template rows: System where a check backs them (2.3), Custom otherwise; owners by role.
- B. All Custom shipped rows; checks only list problems.
- C. Not shipped; the company adds them.

**Q12. Built-in dependency edges.**
- A. Refused by a trigger on delete (integrity of the shipped graph) and by the service.
- B. Service only (H4).

**Q13. Business-day and fixed-day due dates.**
- A. Business day N counts working days after the period end (BD1 = first working day after); fixed day N is that
  day of the month after the period, and a day past the month's end becomes the last day.
- B. Business day N counts from the period end itself (BD0 = the last day).
- C. Fixed day N refers to the period's own month.

**Q14. Work week and holidays.**
- A. In area 13 now (`company_settings.work_week`, `company_holiday`); the calendar and schedules (area 8) reuse
  them.
- B. Owned by area 8 (job schedules); area 13 waits for it.

**Q15. What reopen does to tasks.** (F7)
- A. System tasks go back to Open and rerun; Custom tasks keep their done record unless the reopener unticks them.
- B. Every task's done record is cleared (logged), as 6:08 PM reads literally.
- C. Nothing changes on tasks; only reviewed-by clears.

**Q16. Ending cash set.**
- A. Bank and Cash account types; card accounts and undeposited funds excluded.
- B. Bank, Cash and undeposited funds; cards excluded.
- C. Bank, Cash and card accounts (net cash position).

**Q17. Snapshot basis.**
- A. Accrual; months 1-12 pre-adjustment, period 13 GAAP, period 14 tax.
- B. Accrual and the GAAP basis for every period.
- C. Store both accrual and cash basis figures (ten numbers).

**Q18. Snapshot source.**
- A. From `journal_line` in the close transaction (source of truth); reports use the summary.
- B. From the period balance summary, after the tie-out check passes in the same transaction.

**Q19. Measures and partial locks.**
- A. Only a full close freezes typed and derived measures; partial locks do not.
- B. Partial locks freeze typed values too.

**Q20. Checkpoint reference.**
- A. Keep `ref_type` fiscal_period/fiscal_year; the snapshot's `through_entry_number` links them.
- B. The checkpoint names the close event (`period_status_history`), and Books closed through signs one checkpoint
  per month it closes.

**Q21. Summary keys with no value.**
- A. Nullable keys with a unique expression index on `COALESCE(key, 0)`.
- B. NOT NULL keys with a seeded "none" row per key table.

**Q22. Summary rebuild.**
- A. A tool in `tools/` plus a service wrapper needing `ledger.verify`, audited.
- B. Tool only, run by a developer.

**Q23. Reason when closing with warnings** (close.html dialog).
- A. Required when any warning is acknowledged; stored on the Close history row (`period_status_history.reason`
  allowed on Close).
- B. Optional.

**Q24. Offer to lock after a step.** (F8)
- A. When a step's last task is done, offer to lock its areas (never automatic).
- B. No offer; locks only from Partial close.

---

## 10. Open items (not decisions)

- Area 12 adds the reconciliation "reopened" and "changed after completion" states the reopen and
  `reconciliation_changed` check use.
- Area 17 adds `kpi`, `kpi_value` and the measures; area 13 calls the freeze.
- Area 10 adds the prepaid schedule service; the deferral checks ship with it. Area 10 also owns
  `ledger_period_balance` with area 17.
- Area 21 adds `row_version` to `company_settings` and the stale-save refusal shared by every service.
- Area 14 widens `pending_approvals` beyond journal entries.
