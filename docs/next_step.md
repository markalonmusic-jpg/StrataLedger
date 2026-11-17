# Next step: Phase 2.7 STOP B (hooks, add-ons, add-on migrations), plan

Written 2026-11-17 at STOP A. Overwritten at each STOP (CLAUDE.md section 8). Start a fresh session (MR1).
Status: **Phase 2.7 STOP A (multi-role permissions) is done**: built, reviewed, audited and mutation-checked.
STOP B is not started; no hook or add-on code is written.

**State:** suite **3027 passed, 7 deselected, 0 xfailed** (was 2959 passed at STOP 2). No baseline change in STOP A; the development
databases did not need a rebuild.

## Done in STOP A (2026-11-17)

- **Decisions:** MR1-MR8, HA1-HA6 and FR1, with index rows (docs/decisions_2026-11-11.md, "MR, HA, FR. Phase 2.7").
- **authz** (MR2-MR4): roles come from `user_company_role` for the company of the nearest access row, falling back
  to `role_code`; missing or inactive roles are skipped; permissions are the union; Admin in any role allows
  everything; project scope applies only when every granting role is Assigned; the highest approval limit wins.
  `Access` is `(is_master, role_codes)` with `is_admin`; there is a new `granting_roles`.
- **approvals** (MR5): a slot is matched against any active role; one person, one slot per chain; an any-role slot
  is recorded as Master, Admin, else the first granting role; `ROLES_CHANGED` replaces a raw NOT NULL error.
- **users** (MR2, MR8): the broader-role check uses the union; the Admin guards and last-Admin check read the
  effective roles; `grant_access` and `set_role` replace the role rows in that company, and `deny_access` clears
  them.
- **payments.allocate** (MR6, closes LOW 2): the side is read first; someone with neither payment right gets
  `CANNOT_APPLY` whether the source exists or not; an inactive user, one without access, or the Master in an
  archived company gets their own sentence.
- **Reviews:**
  - **step-reviewer:** approve with changes, all fixed in 4c46ef4. MR8 came from its HIGH finding. The Admin role
    cannot be deactivated (a schema trigger), so its LOW 7 does not apply to Admin.
  - **secrets-auditor:** nothing leaks; LOW 2 is closed. INFO-B (the Master's sentence) is fixed in 9e022b9.
    LOW-A is open, see below.
  - **mutation-tester** (on 9e022b9): 87 mutants. 67 were killed and 6 are equivalent; tests for the other 14 are
    in tests/test_mutation_stop_a_extra.py, and each kills its mutant.

## STOP B plan (to confirm at the start of the session)

1. **Baseline (HA6), tests first:** `addon_schema_version.sha256 TEXT NOT NULL`. Save the current baseline as
   archive/baseline_pre_2_7_b and tag it; rebuild the empty development databases (`Companies/` is empty; the
   development master is rebuilt).
2. **Permission (HA5):** `addon.manage` in permissions.py, held by the Admin and Master templates only, and not in
   AGENT_ALLOWED. Update the role templates and tests/test_permissions_registry.py.
3. **`modules/services/hooks.py` (HA1, HA2):**
   - `EVENTS = {"entry.posted", "entry.voided", "stage.entered", "stage.left"}` (the last two are declared only).
   - `register(event, addon_key, handler)`, and `fire(conn, context, event, payload)` inside the caller's
     transaction. It runs only enabled add-ons' handlers and is refused for an Agent context.
   - `database.py` installs a SQLite authorizer while a handler runs: writes only to `<key>_` tables, and no
     PRAGMA, ATTACH or schema change.
   - A handler error becomes a typed error with one sentence ("The <name> add-on failed: ...; disable it in
     Company Settings > Add-ons and try again"), and the caller's transaction rolls back.
   - `ledger` fires `entry.posted` and `entry.voided`.
4. **Add-on registry (`modules/services/addons.py`, HA3, HA5):**
   - `list_addons`, `enable` and `disable` (`addon.manage`, audit-logged through `company_addon`).
   - Discovery and import only from `RESOURCE_DIR/addons/<key>/` (a manifest plus `register(hooks)`), never from
     `DATA_DIR`, with a test that plants an add-on under DATA_DIR.
   - Core never imports `addons` (a static test). Disabling stops the hooks and drops nothing.
   - Tests use a fixture add-on.
5. **Add-on migration runner (`modules/database.py`, HA4, HA6):**
   - `addons/<key>/migrations/<key>_NNN.sql`, applied in one transaction with a backup first, and recorded with
     their sha256.
   - Refused: an edited applied file, a gap, an object outside the `<key>_` prefix, triggers or indexes on other
     tables, PRAGMA and ATTACH (checked by statement and by comparing `sqlite_master` before and after).
   - Runs on `enable`, and on company open for add-ons that are already enabled.
6. **STOP C plan (FR1):** write the custom fields service plan into docs/next_step.md at STOP B; do not build it.
7. Reviews: step-reviewer, secrets-auditor (code loading) and mutation-tester, one at a time. Then STOP, with
   CLAUDE.md at 200 lines or fewer (MR7).

## Open points for the owner

1. **MR8 (from the step-reviewer's HIGH finding):** the single-role services replace or clear a user's
   `user_company_role` rows. Confirm, or choose to refuse with a typed error when rows exist.
2. **LOW-A (secrets audit, STOP A):** a user holding exactly one payment right can still tell whether an id on the
   other side exists. A missing id says "Choose the payment ..."; an existing other-side id gets that side's role
   denial. Nothing else is disclosed, and it was true before MR6. Closing it means one sentence for "missing" and
   "other side". Accept it, or close it?
3. **FR1 sources:** a search for "field pack" and "15-field" finds only FR1 itself. Point STOP C at the CRM
   decision text for field packs and the 15-field cap, or restate them.
4. Still open from earlier: open question 7 (System context and Import-origin entries in `post_journal_entry`);
   undeposited funds vs matching (Phase 4).

## Deferred (unchanged from STOP 2)

- **Phase 4 posting services:** `clearing_lines` and `NEW_CLEARING`; `next_invoice_number` and
  `next_voucher_number`; the voids call `void_document_entry` and `release_allocations`; AR and AP in the chart
  CSVs.
- Deferral targets in `allocate`; the STOP 1 service checks (two of them, the custom-field ones, move to STOP C).
- **Phase 3 screens:**
  - show the unverified range and the close check's warning;
  - call `App.start_key_store()` after a key replacement;
  - show `KeyReplaced.recovery_code` once;
  - pass `self.app.action_context()` on every post, approval, close, void and correction;
  - show `display_description`;
  - log errors by passing the error object;
  - show `SaveFailedError` like any service error;
  - the import review shows the rounding note;
  - the AQ2 bridge follows RP6 and the token rules in docs/design.md section 1;
  - a screen for several roles per user (only the single-role services exist; MR8).
- **Backlog 21:** "voids and corrections need a second person" (R42). **KS18:** retired installation keys'
  recovery copies.
- `auth._now()` remains the one allowed clock read in services (H2).
