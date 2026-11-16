# Next step: STOP 2, Phase 2.5 Step 7 (plan for the owner's approval)

Written 2026-11-16 at the end of STOP 1 (the consolidated baseline update). Overwritten at each STOP (CLAUDE.md
section 8).
Status: **STOP 1 is committed: both baselines carry the replan schema (RP1-RP11, docs/design.md section 10),
the previous baselines are in archive/baseline_pre_replan/ (tag `baseline-pre-replan`), and the development
master was rebuilt. Step 7 is not started.**

**State:** suite **2798 passed, 7 deselected, 5 xfailed** (was 2745; 53 new). The 5 xfails in tests/test_service_rules_pending.py are the Step 7 work below.
Rebuild needed before running the app on an older development file: `python scripts/create_fresh_databases.py
--apply`. `Companies/COMBUZZ.db` predates this baseline, and the hash guard refuses it.

## Done in STOP 1 (2026-11-16)

- **Decisions:** RP1-RP11 recorded in docs/decisions_2026-11-11.md, with B9, D7 and H6 amended.
- **Baselines:** schema only, with no service using the new columns yet:
  - `company_entity`; `journal_line.entity_id` and `clearing_id`, frozen after posting and sealed (RP2, RP8),
    plus the open-item index; `account.track_clearing_id`;
  - the contact columns and `contact_site`;
  - the invoice columns (`voucher_number`, `revision_no`, `supersedes_id`, `sent_at` / `sent_to` /
    `void_reason` set once, `memo`, `is_opening`, `payment_term_id`; status `In pay run`, Sent <-> In pay run
    -> Paid);
  - `fiscal_period_lock`, `audit_log.reason`, `company_settings.lock_documents_after_posting`;
  - `document_approval_setting` with Invoice, Credit Memo, Vendor credit and Pay run (all 0);
  - `payment_allocation.applied_date` (NOT NULL), `credit_memo_id` (a sales Credit Memo), `created_by/_at`, and
    the release fields; exactly one source; a posted source's rows released once, never deleted (RP11);
  - 3-level `cost_code` (RP5); dimension depth 10 (RP3);
  - `service_type`, `service_stage`, `stage_trigger`, `stage_trigger_run` (idempotent, append-only), with
    `project.service_type_id` / `service_stage_id` (RP4);
  - `pay_run`, `pay_run_line`; `bank_statement_line` (recon lock), `bank_statement_match` (release once);
  - `close_task`, `close_task_dependency`; `payment_term`; `custom_field_def` / `custom_field_value`;
    `user_list_pref`, `saved_view`, `alert_dismissal`;
  - master `user_company_role` (RP10);
  - audit triggers on every new table and column;
  - a full index on every foreign key column in both files (static test).
- **Code:** `MAX_DIMENSION_DEPTH = 10`; `ledger_chain.HASHED_LINE` gains `entity_id` and `clearing_id` (v1
  vectors regenerated, RP8); `ledger.MIRRORED_LINE_FIELDS` gains both, so a reversal stays in its original's
  entity and clearing group.
- **Tests:** tests/test_schema_replan.py (new); tests/test_ledger_chain.py and tests/test_database.py (depth 10
  allowed, 11 rejected, and a subtree move past 10); allocation fixtures in test_controls_003 and
  test_schema_ledger_2_5. `test_allocations_of_posted_payment` now asserts release-not-delete (RP11).
- **Reviews:** REVIEWS_HERE

## STOP 2 plan: Step 7

Step 7 closes Phase 2.5. It needs no baseline change: STOP 1 added every column it uses.

### Part 1. The five strict xfails (tests/test_service_rules_pending.py)

| xfail | Step 7 work |
|---|---|
| Reopening a period needs a logged reason | Covered by `periods.reopen_period` and `period_status_history` (tests/test_period_close.py). Delete the xfail; no code. |
| Period set from the entry date | Covered by `ledger.create_entry` / `periods.resolve_entry_period`. Delete the xfail; no code. |
| Numbering assigns the next number | New `modules/services/sequences.py`: `next_invoice_number(conn, context, document_type)`, run inside the caller's write transaction. It uses the R6 default series (`INV-` / `CM-`, created on first use, not with `ph_tax`), checks the registered range and `valid_until`, stays gapless, and refuses a missing series under `ph_tax` with a sentence. Also `next_voucher_number(conn, context)` for bills and vendor credits (`VCH-`, from `voucher_sequence`, decision 1.3; fills `invoice.voucher_number`). Rewrite the xfail against it. |
| A payment cannot be over-allocated | Part 2. |
| An allocation names exactly one target | Part 2: the service refuses it with a sentence before the CHECK is reached. |

### Part 2. `modules/services/payments.py`

Each function follows rule 10: validate, `authorize`, then the write transaction.
- `allocate(context, *, source, target, amount_cents, applied_date)`:
  - `source` is `("payment", id)` or `("credit_memo", id)`; `target` is `("invoice", id)` or
    `("deferral", id)`.
  - Never more than the target's open amount (total − retainage − live allocations, B2).
  - Never more than the source's unapplied amount (amount, or credit memo total, − live allocations).
  - Same contact; Received payment or sales credit memo → Sales invoice; Made payment or vendor credit → Bill
    (R7).
  - Source and target posted and not void; the target is not Draft, Void or Paid.
  - `applied_date` is on or after both documents' dates and in an open period (closed-period integrity; it uses
    `fiscal_period_lock` area `Sales` / `Purchases` too).
  - The invoice is marked Paid when its net due reaches zero (B2), in the same transaction.
  - Sets `created_by` / `created_at` from the context (H2).
- `release_allocations(conn, context, *, source, reason)`: stamps `released_*` once on every live allocation of
  the source and reopens Paid invoices. It is called by the payment and credit-memo void (Phase 4); Step 7 builds
  and tests it.
- Permissions: reuse the receive / pay permissions (`payment.receive`, `payment.make` or the existing names) or add
  `payment.allocate` (open question 4). Agent never (section 0).
- `clearing_id`: when an allocation's payment entry and the invoice entry exist, the service sets the same
  clearing id on the AR/AP line of each at save or post time (RP2). In Step 7 only `allocate` and the release
  touch it; the document posting services set it in Phase 4. Open question 8.

### Part 3. Smaller items found in STOP 1

- `DOCUMENT_ENTRY_CALLERS`: payments are made only by `services/payments.py`, so the billing row shrinks to
  `{"Invoice"}` (allow-lists only shrink).
- Postings target active leaf cost codes (RP5): a check in the ledger's line validation (where accounts are checked postable and active), with a sentence ("Post to a
  cost code or sub-code, not the division").
- The four new approval toggles (Invoice, Credit Memo, Vendor credit, Pay run) exist at 0, but
  `company_settings.set_document_approval` refuses them, because `permissions.DOCUMENT_TYPES` and the approval
  chain CHECKs do not list them yet. They join when their posting services exist (Phase 4). Not Step 7.

### Part 4. Close Phase 2.5

Roadmap 2.5 marked done, a status log entry, the Step 7 hand-check script, step-reviewer and mutation-tester.

## Open questions for the owner

1. **$0.00 payments.** Recommendation (unchanged): a credit-only application is allocation rows from the credit
   memo with their own `applied_date`, shown on screen as a $0.00 payment; no CHECK change.
2. **Pay Run:** answered by RP1 and docs/design.md section 6 (multi-vendor, two steps). Closed.
3. **Releasing allocations:** answered by RP11. Closed.
4. **Permission for allocating:** reuse receive/pay, or add `payment.allocate`?
5. **Vendor credit numbering:** STOP 1 gives vendor credits a `voucher_number` (`VCH-`, gaps allowed, decision
   1.3) beside the vendor's own number. Confirm that this answers the gapless-series request in the payments
   message.
6. **Undeposited funds vs matching:** still open; not needed for Step 7.
7. **Who may post a reviewed import:** should `post_journal_entry` also refuse a System context for an
   Import-origin entry? Small; it could go into Step 7 with a test.
8. **When is `clearing_id` set?** Proposal: the open item's line (the invoice's AR line) gets a new clearing id
   when the invoice posts, and each settling line copies it when its payment posts or is allocated. Lines
   already posted cannot be changed (RP2), so the open item's id must exist from its own posting. The
   allocation then only links documents. Confirm.

## Carried forward

- **Known issue (RP10):** `user_company_role` exists, but `authz` reads only `user_company_access.role_code`; a
  later step switches it.
- **Phase 3 screens:**
  - show the unverified range and the close check's warning;
  - after a key replacement, call `App.start_key_store()` again;
  - show `KeyReplaced.recovery_code` once;
  - every post, approval, close, void and correction passes `self.app.action_context()`;
  - show `display_description`;
  - log an error by passing the error object;
  - show `SaveFailedError` like any service error;
  - the import review screen shows the rounding note;
  - the AQ2 bridge follows RP6.
- **Backlog 21:** the "voids and corrections need a second person" control (R42).
- **KS18:** whether retired installation keys keep their recovery copies.
- `auth._now()` is the one allowed clock read in services (H2).
