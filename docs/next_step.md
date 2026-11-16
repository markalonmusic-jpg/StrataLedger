# Next step: Phase 2.7 (hooks and add-ons), plan for the owner's approval

Written 2026-11-16 at the STOP after Phase 2.5 Step 7. Overwritten at each STOP (CLAUDE.md section 8).
Status: **Phase 2.5 is done** (Step 7 committed, reviewed and mutation-checked). 2.7 is not started; no 2.7 code
is written.

**State:** suite **2933 passed, 7 deselected, 0 xfailed** (was 2821 passed and 5 xfailed). No xfails remain: tests/test_service_rules_pending.py is gone, and its five rules
are real tests. The development master was rebuilt on the Step 7 baseline. `Companies/` is empty: the old
COMBUZZ.db is in Backups/20261116-112133/.

## Done in Step 7 (2026-11-16)

- **Decisions:**
  - R56: payment.receive for the Sales side, payment.make for the Purchase side.
  - R57: clearing ids are set when a document's entry is saved or posted, and a group's id is its opening
    line's id.
  - R58: an application entry for a posted source.
  - R59: application entries and their release need no document approval; a release is a ledger Void.
  - R60: only accounts with `track_clearing_id` keep groups, and AR and AP accounts are marked automatically; a
    group is joined only after its opening entry has posted, for the same contact.
- **Baseline:**
  - `payment_allocation.application_entry_id`, saved first as archive/baseline_pre_2_5_7, tag
    `baseline-pre-2.5-7`;
  - the credit-memo source triggers accept either side, so vendor credits apply to bills.
- **Services:**
  - `payments.allocate`:
    - a Human or an Agent without permission is refused before the amounts are checked, and an Agent before
      any read;
    - the checks: open amounts (B2), side, contact, statuses, void, the applied date against both documents,
      the closed period and the area lock;
    - the application entry (R58), and Paid marking.
  - `payments.release_allocations` (after the void, RP11): voids each application entry and reopens Paid
    targets.
  - `payments.open_item` and `clearing_lines` (R57).
  - `ledger`: `NEW_CLEARING` and clearing groups in `create_document_entry` (R57, R60), `exempt_from_approval`
    (R59, payments only), `void_document_entry`, and leaf cost codes at save and at post (RP5).
  - `sequences.next_invoice_number(..., issue_date=)`: the R6 default series, ph_tax needs a registered series,
    the registered range, `valid_until` against the issue date, the first usable series, gapless.
  - `accounts`: AR and AP accounts get `track_clearing_id = 1` (R60).
- **Static tests:**
  - `DOCUMENT_ENTRY_CALLERS["services/billing.py"]` is `{"Invoice"}`;
  - only payments.py passes `exempt_from_approval`;
  - only payments.py calls `void_document_entry`, and nothing calls `release_allocations` yet.
- **Hand check:** tools/hand_check_step7.py passes every step.
- **Reviews:**
  - **step-reviewer:** approve with changes, all fixed: R59 (approval never blocks an application or a
    release), rule 10 (authorize before validating), a test for each rule that had none, refused paths
    snapshot-checked, the release date and area lock, the stricter group joins (R60), ph_tax and valid_until,
    the first usable series, and the docs.
  - **secrets-auditor:** nothing leaks. Fixed: the wrong-side refusal no longer names the other side's
    document, and the static caller check for the two helpers. Open: LOW 2 below.
  - **mutation-tester:** MUTATION_HERE

## Step 2.7 plan (to detail and approve)

From docs/roadmap.md: the hook registry, the add-on registry, and the add-on migration runner
(`addon_schema_version`, `company_addon`).
- **Hook registry:** named service events that an add-on may subscribe to (for example after a document posts),
  run inside the caller's transaction, refused for an Agent. The first user is the RP4 stage triggers
  (`stage_trigger_run` is idempotent per event).
- **Add-on registry:** `company_addon` (`addon_key`, enabled, version), switched by an Admin, logged. The
  Philippines add-on (`ph_tax`) is the first; `sequences.next_invoice_number` already reads it.
- **Add-on migrations:** numbered `ph_001`, `ph_002`, ...; applied in one transaction, recorded in
  `addon_schema_version`, with the same refusal rules as the baseline runner.
- Then 2.8, password recovery (PW1-PW11), then Phase 3 screens.

## Deferred from Step 7 (each with its phase)

- **Phase 4 posting services** (invoice, bill, credit memo, payment):
  - call `payments.clearing_lines` and `ledger.NEW_CLEARING`;
  - call `next_invoice_number` when sending, and `next_voucher_number` for bills and vendor credits (filling
    `invoice.voucher_number`);
  - the voids call `ledger.void_document_entry` and `payments.release_allocations`;
  - mark AR and AP accounts in the chart templates' CSVs (`accounts.tracks_open_items` already does it from
    `control_type`).
- **Deferral targets** (`("deferral", id)`) are refused by `allocate` in Step 7; they come with the deferrals
  service.
- **Service checks the schema leaves open** (STOP 1 list):
  - `void_reason` only on a voided document;
  - ISO format for the new `_at` columns;
  - a custom field's `data_type` is fixed while values exist;
  - no cycles in `close_task_dependency`;
  - a bill in at most one open pay run;
  - a contact custom field named like a bank number is refused.

  Each comes with the service that writes those tables (Phase 3/4).
- **Open question 7** (from STOP 1): should `post_journal_entry` also refuse a System context for an
  Import-origin entry? Still open.

## Open points for the owner

1. **LOW 2 (secrets audit):** before the permission check, a person with neither permission can tell whether a
   payment or credit memo id exists (a missing id says "Choose the payment ..."; an existing one is a denial).
   No amounts, numbers or contacts are disclosed. To close it, refuse before the read when the caller holds
   neither permission. That needs a non-raising permission check in authz (a small 2.7 item).
2. **`authz` and `user_company_role` (RP10):** authz still reads only `user_company_access.role_code`.
3. **Undeposited funds vs matching:** still open; not needed before Phase 4.

## Carried forward

- **Phase 3 screens:**
  - show the unverified range and the close check's warning;
  - call `App.start_key_store()` after a key replacement;
  - show `KeyReplaced.recovery_code` once;
  - pass `self.app.action_context()` on every post, approval, close, void and correction;
  - show `display_description`;
  - log errors by passing the error object;
  - show `SaveFailedError` like any service error;
  - the import review shows the rounding note;
  - the AQ2 bridge follows RP6 and the token rules in docs/design.md section 1.
- **Backlog 21:** "voids and corrections need a second person" (R42). **KS18:** retired installation keys'
  recovery copies.
- `auth._now()` remains the one allowed clock read in services (H2).
