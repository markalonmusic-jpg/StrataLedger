# Step 2.9 schema replan, area 12: bank and reconciliation

Status: **Owner-approved 2026-11-19** (first draft 2026-11-19, d9032ea; owner answers Q1-Q20, all A, 2026-11-19, folded
in below, a837bc1; permission placement revised by the owner, d239f32; section 9). Docs only: nothing here changes
code, a baseline, a migration or a test. Planning has marked area 12 owner-approved in
`Strata_Teams\schema_replan_2026-11-17.md`. Every table, column, code and check below is built only in the 2.9
baseline pass. No questions are open. The amendments this area's answers make to areas 13 and 18 are dated lines in
those docs (section 10).

Sources read (only these, searched by date, title or code):
- `Strata_Teams\schema_replan_2026-11-17.md`, row 12 and the source keys.
- `Strata_Teams\inbox\archive\to_planning_archive_2026-11-17.md`: 2026-11-14 "owner decisions on Pay Run,
  Undeposited funds, cash basis", "Banking, service rules (bank feed, open payments, reconcile)", "mockup account
  numbers are sample data"; 2026-11-15 "Bank feed matching rules, QBO-style" (11:48 AM), "Where unposted bank lines
  live" (11:51 AM), "Reconcile needs source-record links and match detail" (1:58 PM), "QBO-style reconciliation
  model" (2:19 PM).
- `Strata_Teams\shared_decisions.md`: 2026-11-14 "payments model", "banking", "chart of accounts"; 2026-11-15 "Bank
  feed page", "reconcile like QBO", "Bank details page"; 2026-11-18 2:05 PM (reconciliation differences), 9:18 PM
  and 9:20 PM (unmatch), 10:03 PM (bills are paid only through pay runs); 2026-11-19 R38 (Matched badge).
- `StrataLedger_mockups\CODE_CHANGES_NEEDED.md` sections 46, 90, 98 and 99.
- docs/decisions_2026-11-11.md by code: B3, B10, B11, B11a, BF1, B12, B13, C4, CF1, RP1, RP2, R57, R60, AG8 (index
  line), H4.
- docs/replan_2.9/area_13_close_and_locks.md sections 1.3-1.4, 2.3, 4.4, 8 (F12) and 9 (answers, dac81ec).
- docs/replan_2.9/area_18_admin_security_audit.md (permissions, audit, the reasons table, exempt lists).
- docs/contracts/reports.md section 12 items 12 and 18 and the period balance summary notes (cash basis, CF1).
- `migrations/001_company.sql` (the bank, payment, pay run and reconciliation tables and their triggers);
  `modules/services/bank_accounts.py`, `payments.py`, `ledger_chain.py`, `chart_templates.py`;
  `templates/coa/construction.csv` (numbers as examples only).

---

## 0. Summary

| # | Topic | Proposal in one line | Baseline |
|---|-------|----------------------|----------|
| 1 | Bank feed and matching | `bank_statement_line` keeps staging (states For review / Posted / Excluded); a match always points at the bank or card **journal line** of the record (payment, pay-run payment, deposit, transfer, refund, loan or card payment, bank JE) and names the record for R38; one feed line can match several records | company |
| 2 | Unmatch | One `bank_feed.unmatch` for every record type: reason always required (Q4 A), refused in a closed period or a period locked for Bank and card or for that GL account (no override); a finished reconciliation that covered the line is flagged "Changed after finish" with the difference (Q5 A) | company |
| 3 | Reconciliation | Cleared state moves off `journal_line` into `bank_line_clearing` (Q1 A). `bank_reconciliation` gains a state (In progress, Finished, Changed after finish, Reopened, Undone), beginning balance and an append-only event table. Finish only at $0.00; a difference is fixed by a normal "Reconciliation adjustment" JE (Q9 A). Period reopen sets Reopened (Q6 A); undo is latest only and lock-checked (Q7 A) | company |
| 4 | Deposits and transfers | In area 12 (Q20 A). `deposit` + `deposit_line` (Dr bank, Cr the undeposited funds role) and `bank_transfer` (bank or card to bank or card); new journal sources `Deposit`, `Transfer`, `Reconciliation adjustment`; undeposited funds tracks clearing groups (Q11 A); a card payment is a transfer (Q15 A) | company |
| 5 | Bank and card accounts | `bank_account.kind` (Checking, Savings, Money market, Cash, Credit card); cards reconcile on the same screen (B12) and are not cash: ending cash is every kind except Credit card plus undeposited funds (Q12 A; area 13 amended) | company |
| 6 | Lock checks | Every posting action here calls `period_locks.check_open` with area Bank and card and the bank or card account; unmatch and undo use the record's own posting period; matching and ticking are allowed in a closed period (Q3 A) | company |
| 7 | Permissions | `bank.feed`, `bank.reconcile` (not sensitive), `bank.unreconcile` (sensitive), in the Accountant cap and levels; none in AGENT_ALLOWED (Q10 A; area 18 amended) | company |

Master file: no change. Live feeds stay held (B11a, AG8): v1.0 ships the file provider only.

---

## 1. Bank feed: staging, matching, every record type

### 1.1 Current state

- **Staging table exists:** `bank_statement_line` (`migrations/001_company.sql:4032-4044`): `bank_account_id`,
  `source` File / Feed / Manual, `import_batch_id`, `external_id` (unique per account where set, `:4046-4047`),
  `posted_date`, `description`, signed `amount_cents` (+ in, - out), `status` CHECK IN ('Unmatched', 'Matched',
  'Excluded'), `recon_id`, `created_at`. Lines of a completed reconciliation cannot change or be deleted
  (`bank_statement_line_recon_lock`, `:4049`; `_delete`, `:4055`). Audited (`:5027`, `:5051`, `:5086`).
- **Matches exist:** `bank_statement_match` (`:4061-4074`): `statement_line_id`, exactly one of `payment_id` or
  `journal_line_id`, `amount_cents`, `matched_by`/`at`, and a one-time release (`released_at`, `released_by`,
  `release_reason`, all three together). `bank_statement_match_release_only` (`:4076`) and `_no_delete` (`:4090`)
  make it append-only apart from the release. Audited on insert and update (`:5110`, `:5133`).
- **No exclude reason, no "posted as" link, no check number, no duplicate fingerprint** on the staging line.
  `import_batch.batch_type` (`:929-945`) has no bank statement value and no file hash.
- **No service** reads or writes `bank_statement_line` or `bank_statement_match` (grep of `modules/`); only
  `tests/test_schema_replan.py:588` and `:635` touch them.
- **Clearing ID (RP2, R57, R60)** is a different thing: `journal_line.clearing_id` (`:509`) groups AR, AP and other
  open-item lines on accounts with `account.track_clearing_id = 1` (`:587`), sealed in the chain
  (`ledger_chain.py:41-45`). It is not the bank's cleared state (section 3).

### 1.2 Decided

- Feed lines per account, states for review / posted (matched or categorized) / excluded; excluded needs a reason,
  is restorable, logged; Undo moves a posted line back to for review and reverses or unlinks what posting created
  (11-14 banking rules; 11-15 11:48 AM; C90).
- Exact matches (amount, date ±2 days, reference) are **suggested only**; a person confirms (one click or "match
  all suggested"); the assistant proposes, never confirms (11-14; AI guardrails).
- A bank line can match one or more records (combined deposit, a pay run's payments), with an optional adjustment
  line for a difference (11-15 11:48 AM; B3 "many receipts to one bank line").
- Own-account transfers: one transfer matches the line in both accounts' feeds; transfers and card payments are
  detected as pairs (11-14; 11-15).
- Categorize creates a record through the normal services (approval per Approvers); rules can preset payee,
  account, job and cost code; a payment created from a feed line is import-origin and the human post is its review
  (11-14 integrity rules; 11-15 11:51 AM).
- Staging is not the ledger: nothing reaches the GL until a person posts it through the services; one import batch
  per file; Undo import deletes a batch's lines only while none are posted (logged); duplicate check on account,
  date, amount and description or check number (11-15 11:51 AM; C90 preview "Already in the feed").
- Matching sets Date cleared on the matched record and removes it from Open payments (11-14; S 11-14 "payments
  model": every payment has Date paid and Date cleared).
- Bills are paid only through pay runs (S 11-18 10:03 PM); a pay run's payments clear together or one by one
  (11-15 2:19 PM; C99 one row that expands).
- R38: a Matched badge names and opens what it is matched to; several records open a match panel with Unmatch.
- B11a: v1.0 ships the feed seam and the file provider (CSV, OFX/QFX); Ramp in v1.1; aggregators later. BF1: a
  Ramp card charge is never booked twice.

### 1.3 Proposed schema

**`bank_statement_line`** (kept; columns changed or added):

| Column | Change |
|--------|--------|
| `status` | CHECK IN ('For review', 'Posted', 'Excluded') (replaces Unmatched / Matched / Excluded; C90 wording) |
| `check_number` | TEXT (from the file; used in suggestions and the duplicate check) |
| `payee_text` | TEXT (the bank's payee, if the file has one) |
| `fingerprint` | TEXT NOT NULL: a service-computed hash of account, date, amount and normalized description or check number (Q14 A: a repeat warns and is unticked in the preview, never refused). Index (`bank_account_id`, `fingerprint`), not unique: a real repeat can exist |
| `excluded_by`, `excluded_at`, `exclude_reason` | set together when Excluded; cleared together on Restore (audited); CHECK all three set or all NULL, reason 1-1000 characters |
| `posted_by`, `posted_at` | set when the line becomes Posted (match or categorize); cleared by Undo |
| `origin` | TEXT NOT NULL DEFAULT 'Import' CHECK IN ('Import', 'Feed', 'Manual') (area 18's origin vocabulary; `source` stays for the provider) |
| `row_version` | INTEGER NOT NULL DEFAULT 1 (g4) |

- CHECK (`status` = 'Excluded') = (`exclude_reason` IS NOT NULL); CHECK (`status` = 'Posted') = (`posted_at` IS NOT
  NULL). "Posted" means at least one live match row exists; the service keeps this, a test checks it (H4: no new
  workflow trigger).
- The completed-reconciliation lock triggers stay (integrity of a finished reconciliation, section 3).

**`bank_statement_match`** (kept; target generalised, Q2 A):

| Column | Change |
|--------|--------|
| `journal_line_id` | becomes NOT NULL: always the **bank or card account line** of the matched record |
| `payment_id` | dropped; replaced by `record_type` + `record_id` |
| `record_type` | TEXT NOT NULL CHECK IN ('Payment received', 'Bill payment', 'Deposit', 'Transfer', 'Customer refund', 'Vendor refund', 'Loan payment', 'Card payment', 'Journal entry', 'Feed adjustment') (the 9:20 PM list; a pay-run payment is a Bill payment with its pay run shown) |
| `record_id` | INTEGER NOT NULL (polymorphic; the service checks it and that `journal_line_id` belongs to it) |
| `match_kind` | TEXT NOT NULL CHECK IN ('Match', 'Categorize') (categorize: the record was created from this line) |
| `release_reason` | kept; already required with the release (the CHECK at `:4072-4073`) |

- Partial unique index (`journal_line_id`) WHERE `released_at` IS NULL: a book line clears against one live match.
- Index (`statement_line_id`) WHERE `released_at` IS NULL, and (`record_type`, `record_id`) for the R38 badge.
- The sum of a statement line's live match amounts plus a Feed adjustment line equals the line amount: service
  rule, tested.

**`import_batch`**: `batch_type` gains 'Bank statement'; add `file_sha256` TEXT and `storage_key` (the file kept
through `storage.py`, H3), `line_count`. Importing a file whose `file_sha256` already exists for that account is
refused with one sentence (C46 "a re-import of the same file adds nothing twice"). Column mapping per account
reuses `import_mapping` (`:92`).

**Matching rules** ("Playbook rules", C90 Rules): `bank_rule` (name, `bank_account_id` or all, conditions as typed
columns: description contains, amount range, direction; actions: payee, account, job, cost code; `is_active`,
`sort_order`, `row_version`). A rule only fills a suggestion; a person posts. Rules land in this 2.9 pass (Q18 A); they work on file imports.

### 1.4 Services (new module `bank_feed.py`)

`import_statement`, `undo_import`, `suggest_matches` (read; amount, ±2 days, check or reference; service constants, Q19 A),
`match` (one line to one or more records, optional Feed adjustment line), `categorize` (calls the record's own
service with origin Import, then matches), `exclude` / `restore` (reason), `undo_posted` (Q17 A: unmatch a match; void what a categorize created), `unmatch`
(section 2). Every write: authorize first, one write transaction, audited with the reason through `tx.py`.

### 1.5 Lands, effects, tests

- Company baseline: the column changes above, `bank_rule`, the `import_batch` values. Every development database
  is blocked and rebuilt (CLAUDE.md section 5.2; list them and ask first, rule 9).
- `tests/test_schema_replan.py:588` (`test_bank_statement_lines_and_matches`) is rewritten for the new status
  values and match target; `:635` keeps its lock assertions.
- Tests to write later: a suggestion is never posted without a person; match-all-suggested posts only the ticked
  ones; a combined match of three payments plus an adjustment line balances to the bank line or is refused; a
  journal line cannot be in two live matches; a transfer matches its line in both feeds; excluded needs a reason
  and restores; undo import refused once any line is posted; the same file twice is refused; a fingerprint
  repeat is unticked in the preview, not dropped; the agent context can suggest but every match write is refused;
  a Ramp card line and its bill are never both booked (BF1).

---

## 2. Unmatch

### 2.1 Current state

`bank_statement_match` already supports a one-time release with a required reason (`:4061-4090`). No service. No
reconciliation flag. Nothing checks locks.

### 2.2 Decided

- "Unmatch from bank feed" from the record's ⋯ menu; the confirm explains that the record goes back to not cleared
  and the feed line back to for review; if the bank account is reconciled for that period it warns that the
  reconciliation will be off by the amount and must be redone ("Unmatch anyway"). Logged on the record, the feed
  line and the reconciliation (S 11-18 9:18 PM; to_planning 11-18 items 1-3).
- Not available when the period is locked: the Bank area or the bank account is locked in the close; disabled with
  the reason; an Admin unlocks first; no override (9:18 PM). Area 13: a bank account lock is an Account lock on the
  bank account's GL account (area 13 section 1.3).
- One service, dialog and wording for every type the feed can match (9:20 PM).

### 2.3 Proposed rule (service only)

`bank_feed.unmatch(context, match_ids, *, reason, confirm_reconciled=False, row_versions)`:
1. authorize `bank.feed` (Q10 A) before the transaction; the reason is always required (Q4 A);
2. for each match: `period_locks.check_open(conn, period_id=<the matched journal line's entry period>,
   area_code='bank_card', account_ids=[<the bank or card account>], action='unmatch')`: a closed period raises
   `PeriodClosedError`, a lock raises `PeriodLockedError` (area 13 section 1.4);
3. if the matched line is in a **finished** reconciliation and `confirm_reconciled` is False: return the warning
   (account, reconciled-through date, amount) and change nothing;
4. otherwise: release the match (reason), set the clearing row back to Not cleared (section 3), set the feed line
   to For review when it has no live match left, and, for a finished reconciliation, add a `Changed` event with
   the signed difference and set its state to Changed after finish (Q5 A). One transaction.

### 2.4 Tests to write later

- For each of the ten record types: unmatch works, warns when reconciled, and is refused (writing nothing, file
  compare) when the period is closed, the Bank and card area is locked, or the account is locked; a lock on
  another account does not refuse it.
- Without a reason, or with `confirm_reconciled` False on a reconciled line: nothing changes.
- After unmatch the reconciliation shows Changed after finish with the right difference and its report is kept.
- A pay-run payment unmatched alone leaves the other payments of the run matched.

---

## 3. Reconciliation

### 3.1 Current state

- `bank_reconciliation` (`:725-731`): `account_id`, `statement_date`, `statement_balance_cents`, `is_complete`.
  No beginning balance, finished by/at, adjustment link, statement file, state or history. Audited (`:2979`).
- Cleared state: `journal_line.recon_id` (`:495`), the only column a posted line may change
  (`journal_line_lock_update_posted`, `:1817-1840`), left out of the chain hash (`ledger_chain.EXCLUDED_LINE`,
  `ledger_chain.py:46`, B10). `journal_line_recon_lock` (`:1842`) refuses moving a line into or out of a completed
  reconciliation; `bank_reconciliation_lock` (`:1851`) and `_lock_delete` (`:1858`) refuse any change to a
  completed one. `tests/test_controls_004.py:435-463` checks these.
- **No "cleared but not reconciled" state and no Date cleared:** `payment` (`:670-682`) has no `date_cleared`;
  there is nowhere to store a feed-match clearing before a reconciliation exists.
- No service; no `bank.reconcile` or `bank.unreconcile` permission rows (B10 and BF1 name them; seeds at
  `:1177-1215` do not have them).

### 3.2 Decided

- QBO model (11-15 2:19 PM; C99): beginning balance = last finished reconciliation's ending; statement date and
  balance; tick book transactions (feed matches pre-ticked; a pay run is one expandable row); per transaction
  Not cleared / Cleared / Reconciled; Save for later; Finish; report; History by account; Undo by Admin with a
  reason (B10: only the latest per account, `bank.unreconcile`); beginning-balance warning when a reconciled item
  changed ("changes since").
- **Finish only at $0.00 (S 11-18 2:05 PM, replaces 11-15 "finish with a difference"):** Difference = statement
  balance − (cleared balance adjusted by uncleared items); uncleared items are carried to the next statement. A
  real difference is fixed with "Create adjustment entry": a journal entry prefilled as "Reconciliation
  adjustment" (date = statement end, bank line with the difference, memo naming the reconciliation); the user picks
  the offsetting account; posting it brings the difference to $0.00. No "finish with a difference".
- Service charge or interest added from the screen posts normal entries in the statement's period (period open;
  C46), default accounts the `bank_charges` and `interest_income` roles.
- 11-14 integrity rule: Date cleared can be set in a closed period and is audit-logged.
- Unmatch in a finished reconciliation flags it changed after completion with the difference until redone
  (9:18 PM); area 13 F12: a period reopen sends the period's reconciliations to a reopened state that area 12
  owns; area 13 only calls it.
- Close checks (area 13 section 2.3): `bank_reconciled` and `reconciliation_changed`, warn by default (L2).

### 3.3 Proposed schema

**`bank_line_clearing`** (Q1 A; one row per bank or card journal line that has ever been cleared):

| Column | Type and constraint |
|--------|---------------------|
| `journal_line_id` | INTEGER PRIMARY KEY REFERENCES journal_line (must be a posted line on a `bank_account` GL account: service check) |
| `state` | TEXT NOT NULL CHECK IN ('Not cleared', 'Cleared', 'Reconciled') |
| `cleared_date` | TEXT (the Date cleared: the feed line's date for a match, the statement date for a tick); CHECK (state = 'Not cleared') = (cleared_date IS NULL) |
| `cleared_via` | TEXT CHECK IN ('Feed match', 'Tick') |
| `recon_id` | INTEGER REFERENCES bank_reconciliation; CHECK (state = 'Reconciled') = (recon_id IS NOT NULL); also set while Cleared inside an in-progress reconciliation (the tick) |
| `changed_by`, `changed_at` | INTEGER, TEXT NOT NULL |
| `row_version` | INTEGER NOT NULL DEFAULT 1 |

- Index (`recon_id`), and (`state`) for Open payments and uncleared items.
- `journal_line.recon_id` is dropped with its index (`:5861`) and its exception in
  `journal_line_lock_update_posted`, so **a posted journal line has no editable column at all** (rule 8 tighter).
  `ledger_chain.EXCLUDED_LINE` becomes empty; the chain hash does not change (the column was never hashed).
- A payment's Date cleared, Open payments (no Date cleared) and a pay run's cleared status are reads through the
  payment's bank line. `payment` gets no column.
- Integrity backstop (moved from `journal_line_recon_lock`): a trigger refuses changing a `bank_line_clearing` row
  whose `recon_id` names a Finished reconciliation, except the unmatch and undo transitions the service makes
  (Q8 A). This is the existing integrity rule (a finished reconciliation's lines are fixed) moved, not a new
  workflow rule.

**`bank_reconciliation`** (kept; columns added):

| Column | Type and constraint |
|--------|---------------------|
| `bank_account_id` | INTEGER NOT NULL REFERENCES bank_account (replaces `account_id`; the GL account is read through it) |
| `beginning_balance_cents` | INTEGER NOT NULL (the previous Finished reconciliation's ending; 0 or the opening balance for the first) |
| `statement_date`, `statement_balance_cents` | kept |
| `state` | TEXT NOT NULL DEFAULT 'In progress' CHECK IN ('In progress', 'Finished', 'Changed after finish', 'Reopened', 'Undone') (replaces `is_complete`) |
| `finished_by`, `finished_at` | set on each Finish |
| `changed_difference_cents` | INTEGER; set while Changed after finish (the signed amount it is off) |
| `adjustment_entry_id` | INTEGER REFERENCES journal_entry (the latest Reconciliation adjustment, for the report) |
| `statement_storage_key` | TEXT (uploaded statement, `storage.py`, H3) |
| `row_version` | INTEGER NOT NULL DEFAULT 1 |

- Partial unique index (`bank_account_id`) WHERE `state` = 'In progress': one open reconciliation per account.
- UNIQUE (`bank_account_id`, `statement_date`) WHERE `state` <> 'Undone'.
- `bank_reconciliation_lock` (`:1851`) narrows to: once a row has been Finished, `bank_account_id`,
  `beginning_balance_cents`, `statement_date` and `statement_balance_cents` never change; `_lock_delete` stays
  (Q8 A). State moves are service rules.

**`bank_reconciliation_event`** (append-only history; feeds History, the report and "changes since"):
`event_id`, `recon_id`, `event` CHECK IN ('Started', 'Finished', 'Changed', 'Reopened', 'Undone', 'Adjustment
posted'), `difference_cents`, `reason` (required for Changed by unmatch, Reopened, Undone), `user_id`, `acted_at`,
`period_status_history_id` (for Reopened by a period reopen). Triggers refuse UPDATE and DELETE (insert-only
integrity backstop, as `period_status_history`).

**States, in one place:**

| From | Event | To | Who / rule |
|------|-------|----|------------|
| — | Start | In progress | `bank.reconcile`; one open per account |
| In progress | Finish (difference $0.00) | Finished | `bank.reconcile`; the service recomputes the difference inside the transaction and refuses anything but 0; ticked lines become Reconciled |
| Finished | Unmatch or a void of a reconciled line (confirmed) | Changed after finish | section 2; `changed_difference_cents` set |
| Finished or Changed after finish | Period reopen (area 13) | Reopened | Q6 A; lines stay Reconciled |
| Changed after finish or Reopened | Finish again at $0.00 | Finished | `bank.reconcile`; a new Finished event; the earlier report stays in History |
| Finished, Changed after finish or Reopened (latest only, B10) | Undo | Undone | `bank.unreconcile`, reason; its lines go back to Cleared; refused when the statement date's period is closed or locked (Q7 A) |

**Reconciliation adjustment:** a journal entry with `journal_entry.source` 'Reconciliation adjustment' (new
value), posted through `ledger.py` like any manual entry, so manual-entry approval applies if the company turned
it on (Q9 A). The offsetting account is the user's choice; the screen suggests a "reconciliation discrepancies"
role if the company has mapped one (new optional role `reconciliation_discrepancies_acct_id`, Q9 A). No Approvers type for adjustments (Q9 A). The posted
adjustment's bank line is Cleared in the open reconciliation.

**What the close checks read** (area 13 section 2.3):
- `bank_reconciled`: for each active `bank_account` (cards included) with posted activity on or before the period
  end, the latest non-Undone reconciliation has `statement_date` on or after the period end and `state` =
  'Finished'. A Changed after finish or Reopened one fails the check. Warn by default (L2).
- `reconciliation_changed`: any reconciliation with `state` = 'Changed after finish' whose `statement_date` is on
  or before the period end; the message names the account, the date and the difference. Warn by default.

### 3.4 Lands, effects, tests

- Company baseline: `bank_line_clearing`, the `bank_reconciliation` changes, `bank_reconciliation_event`, the
  journal source values, the optional role; drop `journal_line.recon_id`, its index and its trigger exception;
  move `journal_line_recon_lock` to `bank_line_clearing`; narrow `bank_reconciliation_lock`. Permission rows for
  `bank.feed`, `bank.reconcile` and `bank.unreconcile` (Q10 A; placement in 3.5). Rebuild every development database.
- `ledger_chain.EXCLUDED_LINE` becomes `()`; `tests/test_ledger_chain.py` checks the hash is unchanged for a line
  that had a `recon_id`. `tests/test_controls_004.py:435-463` and the `bank_reconciliation` rows at `:28`, `:50`,
  `:71` are rewritten for the new tables. `tests/test_schema_replan.py:257` (a reconciled line cannot move its
  entity or clearing group) becomes "a posted line cannot change at all".
- New module `reconciliation.py`: `start`, `tick` / `untick`, `save_for_later`, `finish`, `report`, `history`,
  `undo`, `reopen_for_period` (called by `periods.reopen_period`, area 13), `prefill_adjustment` (returns a draft
  entry; posting goes through `ledger.py`).
- Tests to write later: finish refused at any difference other than $0.00, including after a concurrent post that
  changes the cleared balance (the difference is recomputed in the transaction); uncleared items carry to the next
  reconciliation; beginning balance equals the previous ending; "changes since" counts a void of a reconciled
  line; a pay run row ticks its payments together and partial ticks work; undo only the latest, with a reason and
  `bank.unreconcile`; period reopen sets Reopened with the history link and the `bank_reconciled` check fails
  until re-finished; the clearing trigger refuses editing a Reconciled row outside unmatch and undo; a
  Reconciliation adjustment goes through manual-entry approval when that control is on and never otherwise.


### 3.5 Permissions (Q10 A)

| Code | Module | Sensitive | Used by |
|------|--------|-----------|---------|
| `bank.feed` | Banking | no | import, suggest, match, categorize, exclude and restore, undo import, undo a posted line, unmatch |
| `bank.reconcile` | Banking | no | start, tick and untick, save, finish, prefill an adjustment (posting it needs `je.post`) |
| `bank.unreconcile` | Banking | yes (B10) | undo the latest reconciliation |

Deposits use `payment.receive`; transfers use `payment.make`. Reading bank pages uses `ledger.view` (as
`bank_accounts.py` does today).

Placement in area 18's seed tables (owner, through Q10 A; area 18 carries the dated amendment):
- **Caps (2.4.1):** all three go in the Accountant cap only (59 → 62 codes). Never in Sales rep or Operations, so
  bank pages stay out of those roles, as area 18 already keeps the ledger and bank details.
- **Level defaults (2.4.2, cumulative, no sensitive code; owner 2026-11-19):** Accountant · Standard adds both
  `bank.feed` and `bank.reconcile`, so Manager inherits them. `bank.unreconcile` is in no level (sensitive).
- **Shipped access template (2.4.3; owner 2026-11-19):** the Controller template adds `bank.unreconcile` in its
  sensitive codes, as it carries `retainage.release` (which is not sensitive, so that one sits in the other
  column). Admin and the Master keep it. Anyone else gets it only by that template or an Add override with a
  reason (area 18 Q7 A). No other template changes.
- **AGENT_ALLOWED:** none of the three. The assistant may suggest matches through reads only; every write is refused
  and logged.
- **Seeds:** three permission rows; the seeded code count grows by three.
- **Area 18 section 2.4 placement check, re-run in words (2026-11-19):** every code is still placed (the three new
  ones are in the Accountant cap, the rest unchanged); Accountant · Standard's cumulative defaults stay inside the
  Accountant cap and hold no sensitive code (`bank.feed` and `bank.reconcile` are not sensitive); View only still
  holds read codes only (no bank code added there); the Controller template stays inside its role's cap, since
  `bank.unreconcile` is in the Accountant cap. No rule fails. It becomes a real test when built (area 18 section 2.6).

---

## 4. Deposits and transfers

### 4.1 Current state

- `company_settings.undeposited_funds_acct_id` (`:771`) exists, filled from the `undeposited_funds` chart role
  (`chart_templates.py:31`; construction example 1050). The account's `control_type` can be 'Undeposited funds'
  (`:580`). Nothing posts to it: no payment service exists yet (area 1), and no deposit table.
- No transfer table; `journal_entry.source` (`:451`) has no 'Transfer', 'Deposit' or 'Reconciliation adjustment'.
- `payment.method` (`:678`) is Cash, Check, Bank Transfer, GCash, Maya: no card, ACH or wire.

### 4.2 Decided

- Undeposited funds stays for checks and cash (Make a deposit); ACH, wire and card post straight to the bank and
  clear by match; undeposited checks clear through their deposit (S 11-14 payments model; 11-14 banking rules).
- B3: receipts go to undeposited funds, a bank, a processor clearing account or any account; a deposit groups
  receipts; processor payouts record fees.
- C46: Make a deposit picks payments in undeposited funds; one number from a sequence (DEP-); Dr bank / Cr
  undeposited funds; void with a reason returns the payments. Transfer between two different own accounts (bank or
  card), one entry with source Transfer; paying the card from checking is a transfer; follows "Payments need
  approval" (off by default).

### 4.3 Proposed schema

**`deposit`**: `deposit_id`, `deposit_number` TEXT NOT NULL UNIQUE (from a `deposit_sequence` counter row, as
`voucher_sequence`; derived and exempt like it), `bank_account_id` NOT NULL (kind not Credit card), `deposit_date`,
`entry_id` UNIQUE REFERENCES journal_entry, `total_cents` INTEGER NOT NULL > 0, `memo`, `created_by`/`at`,
`voided_by`/`at`/`void_reason` (all or none), `row_version`.

**`deposit_line`**: `deposit_id`, `payment_id` REFERENCES payment, `amount_cents` > 0; a payment is in at most one
live deposit, refused by the service (Q11 A; no extra index). Lines in cash or checks only (other lines go straight to the bank).

**Posting:** one entry, source 'Deposit': Dr the bank account, Cr the undeposited funds role, one credit line per
payment carrying that payment's `clearing_id` when the undeposited funds account tracks clearing groups (Q11 A),
so open undeposited items are the open clearing groups (RP2, R60). A void posts the reversal (void rules, R48) and
the payments return to undeposited funds.

**`bank_transfer`**: `transfer_id`, `from_bank_account_id`, `to_bank_account_id` (CHECK differ), `transfer_date`,
`amount_cents` > 0, `entry_id` UNIQUE, `memo`, created and void columns, `row_version`. One entry, source
'Transfer': Cr the from account, Dr the to account. A card payment from checking is a transfer to the card
account (Q15 A). Approval: the existing "Payments need approval" control covers transfers (OFF by default).

**`journal_entry.source`** gains 'Deposit', 'Transfer', 'Reconciliation adjustment' (and area 10 adds 'Reclass').

### 4.4 Lands, effects, tests

- Company baseline: the three tables, the counter, the source values; audit triggers (area 18); `deposit_sequence`
  on area 18's derived exempt list beside `voucher_sequence` (an amendment to area 18; see F9).
- New module `banking.py` (`make_deposit`, `void_deposit`, `transfer`, `void_transfer`). Area 1's payment service
  posts receipts to undeposited funds or the bank (area 1 owns that choice).
- Tests to write later: a deposit's lines equal its total and its entry balances; a payment cannot be in two live
  deposits; void returns the payments and reopens their undeposited groups; a deposit into a card account is
  refused; a transfer between the same account is refused; a transfer matches its line in both feeds; ACH payments
  never appear in Make a deposit.

---

## 5. Bank and card accounts

### 5.1 Current state

- `bank_account` (`:1332-1339`): `account_id` (UNIQUE), `bank_name`, `routing_number`, `account_number`,
  `account_last4`. No kind, no active flag, no feed source. Full numbers stored and masked without
  `view.bank_details` (C4; `modules/services/bank_accounts.py:1-48`, `HOLDER_TYPES` Asset or Liability at `:14`);
  the audit trigger logs only the last four (area 18 table, `:3730`).
- `account_type` has five rows only (`:1166-1171`: Asset, Liability, Equity, Revenue, Expense). **There is no
  "Bank" or "Cash" account type**; the construction chart marks bank accounts only by their parent "Cash and Bank"
  and the `default_bank` role. Cards are Liability accounts (example 2040).
- `pay_run.bank_account_id` (`:3995`) references `bank_account`; `payment.bank_account_id` (`:679`) references
  `account` directly.

### 5.2 Decided

- C46: kind checking, savings, money market, credit card; the chart account; bank; last four; statement file
  format; reconciled-through date (shown); book balance = GL; opening balance only through Opening balances.
- B12: credit cards reconcile on the same screen. Area 13 Q16 B: ending cash includes undeposited funds and
  **card accounts are not cash**; Q12 A here defines the set by `bank_account.kind` (area 13 section 4.4 amended).
- C46: Ramp card charges arrive as vendor bills through the Ramp import; the Ramp program is not a card account.
  BF1: Ramp card lines go to both the holding area and the statement lines; never booked twice.
- C98: a Bank details page per bank or card account (register, statements, reconciliations, details, attachments).

### 5.3 Proposed schema

**`bank_account`** (columns added):

| Column | Type and constraint |
|--------|---------------------|
| `kind` | TEXT NOT NULL CHECK IN ('Checking', 'Savings', 'Money market', 'Cash', 'Credit card') (Q12 A; 'Cash' for petty cash or a cash box with no bank) |
| `is_active` | INTEGER NOT NULL DEFAULT 1 |
| `feed_provider` | TEXT NOT NULL DEFAULT 'File' CHECK IN ('File') (B11a; 'Ramp' and others added with their providers in v1.1, Q18 A) |
| `statement_format` | TEXT CHECK IN ('CSV', 'OFX', 'QFX', 'QBO') |
| `row_version` | INTEGER NOT NULL DEFAULT 1 |

- Service rule (extends `bank_accounts.HOLDER_TYPES`): Credit card requires a Liability account; every other kind an
  Asset account. Reconciled-through is derived (latest Finished reconciliation), never stored.
- `payment.bank_account_id` keeps referencing `account` (area 1 may change it); the service checks it has a
  `bank_account` row.
- **Ending cash (area 13 section 4.4, Q16 B):** the accounts with a `bank_account` row whose `kind` is not
  'Credit card', plus `company_settings.undeposited_funds_acct_id`. This replaces "account types Bank and Cash",
  which do not exist (F6). The cash flow report (CF1) uses the same set. Area 13 sections 0 and 4.4 carry a dated
  amendment line saying so (Q12 A).

**Card reconciliation:** the same screen and tables (B12). The statement balance is the amount owed, entered as a
positive number; the service compares it with the account's credit balance. Charges are payments out of the card,
card payments from checking are transfers in. Feed lines keep their sign from the card's point of view
(+ payment or refund, - charge).

### 5.4 Lands, effects, tests

- Company baseline: the columns above. `bank_accounts.set_bank_details` takes `kind` (or a new
  `set_account_kind`); `tests/test_bank_accounts.py` adds the kind cases. `tests/test_schema_replan.py:304` (no
  table stores third-party bank numbers) stays.
- Tests to write later: a card on an Asset account is refused; a card account never counts in ending cash and the
  undeposited funds account always does; a card reconciles to $0.00 with charges, a refund and a payment from
  checking; making a card account inactive with an open reconciliation is refused.

---

## 6. Lock checks this area makes (area 13 section 1.4)

All through `period_locks.check_open` inside the write transaction. Area code `bank_card` (Bank and card,
area 13 Q1 A). "Accounts" are the GL accounts of the `bank_account` rows involved, found through `bank_account`,
never by number.

| Action | Period checked | Area | Accounts checked |
|--------|----------------|------|------------------|
| Post a categorized feed line (record created through its own service) | the new record's date | the record's own area (a bill: Bills and vendor credits; an expense JE: Journal entries); the creating service makes the call | every line |
| Match a feed line, tick or untick in a reconciliation | none (Q3 A: Date cleared may be set in a closed period, 11-14) | — | — |
| Unmatch (every record type) | the matched journal line's entry period | Bank and card | the bank or card account |
| Undo a posted feed line (Q17 A: unmatch, or void what a categorize created) | the void's date (void rules, R48) and the original's period for the unmatch | the record's area and Bank and card | every line of the reversal, and the bank account |
| Finish a reconciliation | none (no GL change) | — | — |
| Undo a reconciliation (Q7 A) | the statement date's period | Bank and card | the bank or card account |
| Reconciliation adjustment, service charge, interest | the entry date (statement end; period must be open) | Bank and card | every line |
| Make a deposit / void it | the deposit date / the void date | Bank and card | every line (bank and undeposited funds) |
| Transfer / void it | the transfer date / the void date | Bank and card | both accounts |
| A period reopen setting reconciliations to Reopened | none (the reopen itself is the action, area 13) | — | — |

Refused means refused, never moved (R48): the message names the lock ("October is partly closed: Bank and card is
locked. Ask an Admin to unlock it, or date this in November."). The static test in area 13 section 1.4 covers
`bank_feed.py`, `reconciliation.py` and `banking.py`.

Tests to write later: each row above refused in a closed period, a Bank and card lock and an account lock, writing
nothing; the "none" rows succeed in a closed period and write their audit rows.

---

## 7. Row version (rule g4) and audit

| Table | Editable? | `row_version` |
|-------|-----------|---------------|
| `bank_account` | yes | yes |
| `bank_statement_line` | status, exclude, posted fields | yes |
| `bank_statement_match` | release once | no (insert plus one release; the release names the match id) |
| `bank_line_clearing` | state moves | yes |
| `bank_reconciliation` | state, finish fields | yes |
| `bank_reconciliation_event` | insert-only | no |
| `deposit`, `bank_transfer` | void once | yes |
| `deposit_line` | insert with the deposit | no |
| `bank_rule` | yes | yes |
| `deposit_sequence` | counter | no (derived, exempt) |

- Every new table gets audit triggers (area 18 section 1); `bank_statement_match` gains a delete audit trigger for
  completeness (deletes are refused anyway). `bank_line_clearing` is audited: Date cleared changes in a closed
  period are logged (11-14).
- Reasons required (area 18's reasons table, extended here): exclude a feed line, unmatch, undo a posted line,
  undo a reconciliation, reopen (from the period reopen's reason), void a deposit or transfer. Area 18's reasons
  table lists them through its dated amendment (Q10 A, F9).
- Integrity backstops in this area guard only append-only or finished data (`bank_statement_match`,
  `bank_reconciliation_event`, the finished-reconciliation locks, `bank_line_clearing` of a Finished
  reconciliation). Workflow rules (states, one-live-match, the posted-means-matched rule, suggestions) are
  service rules with tests (H4).

---

## 8. Conflicts with decisions (all resolved by the owner's answers, 2026-11-19)

- **F1 Finish with a difference.** 11-15 2:19 PM and C99 let a reconciliation finish with a difference that posts
  to a "reconciliation discrepancies" role through a new Approvers type; S 11-18 2:05 PM says only $0.00, and a real
  difference is a prefilled journal entry with an offset the user picks. **Resolved by Q9 A:** finish only at
  $0.00; a normal Reconciliation adjustment JE; the discrepancies role is only a suggested offset; no Approvers type.
- **F2 Unmatch in a finished reconciliation.** 11-14: "reopens it with a reason"; 11-18 9:18 PM: flagged changed
  after completion until redone. **Resolved by Q5 A:** Changed after finish with the difference, finished again
  after the fix.
- **F3 Clearing in a closed period.** 11-14: Date cleared may be set in a closed period; 9:18 PM: unmatch is refused
  in a locked period. **Resolved by Q3 A:** matching and ticking are allowed and audited in a closed period; only
  unmatch and undo are refused.
- **F4 Period reopen vs B10.** Area 13 F12: a period reopen sends reconciliations back to In progress; B10: undo only
  the latest. **Resolved by Q6 A and Q7 A:** a period reopen sets Reopened (nothing is undone, so B10 holds); undo
  stays latest only, with a reason, refused in a closed or locked period.
- **F5 Bank numbers.** C46: last four digits only; C4 (built): full numbers stored and masked. **Resolved by Q13 A:**
  C4 stands as built; C46's "last four only" is not followed.
- **F6 "Bank and Cash account types".** Area 13 Q16 B named account types that the baseline does not have.
  **Resolved by Q12 A:** ending cash is every `bank_account` kind except Credit card, plus undeposited funds; area 13
  sections 0 and 4.4 carry a dated amendment line.
- **F7 Area 1 boundary.** Working-doc row 1 also names deposits. **Resolved by Q20 A:** deposits and transfers are in
  area 12; area 1 keeps the payment record and the receipt destination.
- **F8 Date cleared on the payment.** S 11-14: every payment has Date cleared; the baseline payment has no column.
  **Resolved by Q1 A:** Date cleared is read from `bank_line_clearing` through the payment's bank line; `payment`
  gets no column.
- **F9 Area 18 amendments.** Area 18's owner-approved seed tables, reasons table and exempt list lacked the bank
  codes, the bank reasons and `deposit_sequence`. **Resolved by Q10 A and the owner's amendment (2026-11-19):** area
  18 carries a dated amendment line (placement in section 3.5).
- **F10 Pay Bills.** S 11-14's single-vendor Pay Bills vs S 11-18 10:03 PM pay runs only. **Resolved as drafted (no
  question):** pay runs only.
- **F11 Ramp lines.** C46 (Ramp charges as bills) vs BF1 (holding area and statement lines). **Resolved as drafted
  (no question):** where Ramp lines land is for the imports area; this area keeps the never-booked-twice test.
- **F12 Role names and numbers.** C46's `bank_fee_account_id`, `interest_income_account_id`, 6950 and 4900 vs the
  baseline's `bank_charges_acct_id` and `interest_income_acct_id` (`:783-784`). **Resolved as drafted (no
  question):** baseline names; numbers are examples only.
- **F13 Statement line states.** Baseline Unmatched / Matched / Excluded vs the decided For review / Posted /
  Excluded. **Resolved as drafted (no question):** the decided states.

---

## 9. Questions for the owner: answers recorded (2026-11-19)

All twenty answered A, one by one. The options as asked are kept in 9.1.

| Q | Answer (A) | Where it lands |
|---|------------|----------------|
| Q1 Cleared state | `bank_line_clearing`; `journal_line.recon_id` dropped | 3.3, 3.4 |
| Q2 Match target | the bank or card journal line plus record type and id | 1.3 |
| Q3 Clearing in a closed period | allowed and audited; only unmatch and undo refused | 2, 6 |
| Q4 Unmatch reason | always required | 0, 2.3 |
| Q5 Unmatch in a finished reconciliation | Changed after finish with the difference | 2.3, 3.3 |
| Q6 Period reopen | Reopened; lines stay reconciled | 3.3 |
| Q7 Undo | latest only, `bank.unreconcile`, reason, lock-checked | 3.3, 6 |
| Q8 Backstop | narrowed finished-reconciliation triggers kept | 3.3 |
| Q9 Adjustments | normal JE; optional discrepancies role as a suggestion; no Approvers type | 3.3 |
| Q10 Permissions | `bank.feed`, `bank.reconcile`, `bank.unreconcile`; placement in 3.5; area 18 amended | 3.5, 7 |
| Q11 Undeposited funds | clearing groups plus `deposit_line`; double deposit refused by the service | 4.3 |
| Q12 Kinds and cash set | `bank_account.kind`; cash = every kind except Credit card plus undeposited funds; area 13 amended | 5.3 |
| Q13 Bank numbers | C4 as built | 5.1 |
| Q14 Duplicates | fingerprint warns and unticks; the same file is refused | 1.3 |
| Q15 Paying the card | a transfer | 4.3 |
| Q16 Open payments limits | area 21 policy records | 10 |
| Q17 Undo a posted line | unmatch, or void what a categorize created | 1.4, 6 |
| Q18 Rules and providers | `bank_rule` now; providers beyond File in v1.1 | 1.3, 5.3 |
| Q19 Tolerances | service constants | 1.4 |
| Q20 Deposits and transfers | area 12 | 4 |

### 9.1 The questions as asked

**Q1. Where the cleared state lives.** (F8)
- A. A new `bank_line_clearing` row per bank or card journal line (Not cleared, Cleared, Reconciled, Date cleared,
  reconciliation); `journal_line.recon_id` is dropped, so a posted journal line has no editable column.
- B. Add `cleared_state` and `cleared_date` to `journal_line` beside `recon_id`, widening the posted-line trigger
  exception and the chain exclusion list.
- C. `date_cleared` on `payment` only (journal entries, deposits and transfers have nowhere to clear).

**Q2. What a match points at.**
- A. Always the record's bank or card journal line, plus `record_type` and `record_id` to name it (R38).
- B. Keep `payment_id` or `journal_line_id`, and add `deposit_id` and `transfer_id` columns.

**Q3. Matching and ticking in a closed or locked period.** (F3)
- A. Allowed and audited (11-14: Date cleared may be set in a closed period), so October can be reconciled after
  October is closed; only unmatch and undo are refused.
- B. Refused like unmatch.

**Q4. Unmatch reason.**
- A. Always required (the baseline's release already requires one).
- B. Required only when the line is in a finished reconciliation.

**Q5. Unmatch in a finished reconciliation.** (F2)
- A. The reconciliation becomes Changed after finish with the difference, keeps its report, and is finished again
  after the fix (9:18 PM).
- B. It goes back to In progress with a reason (11-14).
- C. Unmatch is refused until the reconciliation is undone (B10).

**Q6. Period reopen and reconciliations.** (F4)
- A. Each Finished or Changed reconciliation whose statement date is in the reopened period becomes Reopened (lines
  stay reconciled, the report is kept); it is finished again before the period closes again.
- B. They are undone (lines back to Cleared), which needs an exception to B10's latest-only rule.
- C. No change; only a real change (unmatch, void) flags them.

**Q7. Undo a reconciliation.** (F4)
- A. Latest per account only (B10), `bank.unreconcile`, a reason; refused when the statement date's period is
  closed or locked for Bank and card or the account.
- B. Latest only, allowed in a closed period (it changes no GL).
- C. Any reconciliation, newest first in a chain.

**Q8. Finished-reconciliation backstop.**
- A. Keep a narrowed trigger: a finished reconciliation's account, dates and balances never change, and its
  clearing rows change only by unmatch or undo; states are service rules.
- B. Service only (drop the triggers).

**Q9. Reconciliation adjustments.** (F1)
- A. A normal journal entry, source 'Reconciliation adjustment', through `ledger.py` (manual-entry approval applies
  when on); an optional `reconciliation_discrepancies` role is only the suggested offset; no new Approvers type.
- B. As A, plus the 11-15 Approvers type "Reconciliation adjustments" (OFF by default).
- C. As A, with no role at all.

**Q10. Permissions.** (F9)
- A. New codes `bank.feed` (import, match, categorize, exclude, unmatch; not sensitive), `bank.reconcile` (not
  sensitive), `bank.unreconcile` (sensitive, B10); deposits use `payment.receive`, transfers `payment.make`; area
  18's caps and level defaults amended to place them (in the Accountant cap; planning proposes the levels); none
  in AGENT_ALLOWED.
- B. One code `bank.manage` for everything, plus `bank.unreconcile`.
- C. Reuse `je.post` for all bank writes.

**Q11. Undeposited funds open items.**
- A. The undeposited funds account tracks clearing groups (R60): each receipt opens a group, its deposit line joins
  it; `deposit_line` keeps the document link; a payment in two live deposits is refused by the service.
- B. `deposit_line` only, with a partial unique index on live lines; no clearing groups.

**Q12. Bank account kinds and the cash set.** (F6)
- A. `bank_account.kind` (Checking, Savings, Money market, Cash, Credit card); ending cash = every kind except
  Credit card, plus undeposited funds.
- B. Use `account.subtype` values 'Bank' and 'Cash' instead of a kind on `bank_account`.

**Q13. Bank numbers.** (F5)
- A. Keep C4 as built: full numbers stored, masked without `view.bank_details`, last four in the audit log.
- B. Last four only (C46); drop `routing_number` and `account_number` and change `bank_accounts.py` and C4.

**Q14. Duplicate lines on import.**
- A. A fingerprint warns and unticks the line in the preview (a person can tick it); the same file twice is refused.
- B. Fingerprint duplicates are refused outright.

**Q15. Paying the card.**
- A. A transfer from the bank account to the card account (C46), matched in both feeds.
- B. A bill payment to the card issuer through a pay run.

**Q16. Open payments limits** (30 and 180 days, 11-14).
- A. In area 21's policy records with the other company limits.
- B. Two columns on `company_settings` now.

**Q17. Undo a posted feed line.**
- A. A matched line: unmatch. A categorized line: void the record it created (void rules, R48, never into a closed
  period), then the line returns to For review.
- B. Unlink only; the created record stays posted.

**Q18. Bank rules and feed providers in the 2.9 pass.**
- A. `bank_rule` now (rules work on file imports too); provider columns beyond 'File' (sync time, needs
  reauthorization) only with the Ramp provider in v1.1.
- B. Both now.
- C. Neither now.

**Q19. Suggestion tolerances.**
- A. Service constants (amount exact, date ±2 days, check or reference); suggestions only.
- B. Company settings.

**Q20. Where deposits and transfers belong.** (F7)
- A. Area 12 (this doc); area 1 keeps the payment record and the receipt destination.
- B. Area 1, with this doc only referencing them.

---

## 10. Open items (not decisions)

- Area 1: the payment service (receipt destination: undeposited funds or bank; `payment.method` values for ACH,
  wire, card); `payment.bank_account_id` target.
- Area 2: pay run posting (one entry per vendor payment or one per run) decides how a pay run's bank lines look to
  the matcher; this doc assumes one bank line per payment.
- Area 13: the ending cash amendment is recorded there as a dated line (Q12 A); `reconciliation.reopen_for_period`
  is called from `periods.reopen_period`.
- Area 18: the permission rows, caps, level defaults, reasons rows and `deposit_sequence` are recorded there as a
  dated amendment (Q10 A, F9).
- Area 21: `row_version` mechanics and the open payments limits (30 and 180 days) as policy records (Q16 A).
- Imports (area 19 or the provider step): Ramp lines and the BF1 never-booked-twice rule (F11).
- Contracts: CF1's cash flow category on accounts (reports.md section 12 item 18) uses this area's cash set.
