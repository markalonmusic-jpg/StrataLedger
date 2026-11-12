# Instructions for Claude Code: Phase 2, Step 0 (pre-flight) and Step 1 (foundation)

Read CLAUDE.md first. Stay in plan mode. Show the plan and wait for approval
before editing. Do NOT commit this file (phase2_step0_instructions.md).

## Ground rules

- Do not touch the real .db files. Do not launch the app.
- Do not run scripts/create_fresh_databases.py with --apply.
- No remote, no push (CLAUDE.md section 8).

---

## Step 0. Pre-flight (report first, then act on approval)

### 0.1 Report (read-only)

1. `git status` and `git log --oneline master..phase1-ledger-integrity | wc -l`.
   CLAUDE.md was modified after the last commit; show `git diff CLAUDE.md`
   if it has uncommitted changes.
2. Run the full test suite (`pytest -q`). Report pass / xfail / fail counts.
   Every test in tests/test_service_rules_pending.py must be an xfail.
3. Check whether these root files are exact duplicates of the docs/ copies:
   `claude_md_additions.md` vs `docs/claude_md_additions.md`,
   `crm_pm_design.md` vs `docs/crm_pm_design.md`. Report git-tracked or not.
4. Report on: `app_stratacrm.py` (0 bytes), `modules/_init_.py` (single
   underscores, so it is not a package marker). Do not fix the import
   structure yet; only report what imports would break if it were renamed
   to `__init__.py`.

### 0.2 Act (after I approve the report)

1. Commit any pending CLAUDE.md change alone ("docs: CLAUDE.md status").
2. Fast-forward merge `phase1-ledger-integrity` into `master`
   (`git checkout master && git merge --ff-only phase1-ledger-integrity`).
   Stop if it is not a fast-forward.
3. Create branch `phase2-service-layer` from master.
4. Delete the root duplicates from item 0.1.3 only if they are identical to
   the docs/ copies. Leave `app_stratacrm.py` and `_init_.py` for Phase 5.

### 0.3 CLAUDE.md edits (doc-only commit: "docs: Phase 2 rules and plan")

These were agreed in docs/next_steps_addendum.md Step B but are missing.

Section 3, add rules 11-13:

11. **Connections.** Every connection comes from `database.get_connection()`.
    Every write runs inside the service layer's write transaction, which sets
    `audit_context` (user_id, origin) before any SQL. A static test fails if
    `sqlite3.connect` appears outside `modules/database.py`, `tests/`,
    `scripts/` and `tools/`.
12. **No silent errors.** No `print()` for validation or database errors.
    Services raise typed exceptions; the UI shows a dialog; errors are also
    written to a log file whose path is defined in `config.py`.
13. **Auth.** Passwords are hashed with `hashlib.scrypt`, never stored or
    compared as plaintext. No hardcoded tokens. Opening a company checks
    `user_company_access`.

Section 7, replace the Phase 2 bullet with the step list below
("Phase 2 steps"), keeping the existing sub-bullets' content.

---

## Phase 2 steps (for CLAUDE.md; build one step per prompt)

- **2.1 Foundation:** `modules/services/` package; typed exceptions;
  `ServiceContext`; `write_transaction()` that sets `audit_context`; error
  log path in config; static tests for rule 11 and rule 12 (allow-list of
  current offenders, which shrinks to zero by end of Phase 3).
- **2.2 Permissions core:** permission code registry (Python constant, the
  list in roles_permissions_design.md section 3), `authorize()`,
  `PermissionDeniedError`, denied-attempt audit, and the static test for
  rule 10. Roles tables migration (company) + 003_master.
- **2.3 Auth service:** scrypt hash/verify/change password, first Master
  creation, remove the hardcoded token, open-company service checking
  `user_company_access`.
- **2.4 Company creation and periods:** company creation service (build from
  migrations, `company_settings` row id = 1, chart of accounts template,
  fiscal periods); period service (generate, close with pre-close checks,
  reopen with reason and approver).
- **2.5 Ledger services:** the controls-audit rules; every test in
  tests/test_service_rules_pending.py flips from xfail to pass (strict
  xfail means each one must be un-marked as it is implemented).
- **2.6 Customer codes:** `customer_number` table, `customer_code`, the
  assignment service and duplicate check.
- **2.7 Hooks and add-ons:** hook registry, add-on registry, add-on
  migration runner (`addon_schema_version`).

---

## Step 1 (= 2.1). Foundation (start only after Step 0 is reviewed)

Failing tests first, then code. No schema changes in this step.

1. `modules/services/__init__.py` and `modules/services/errors.py`:
   a `ServiceError` base and typed subclasses (`ValidationError`,
   `NotFoundError`, `PostingError`, `PermissionDeniedError`,
   `PeriodClosedError`). Keep `SchemaUpgradeBlockedError` where it is.
2. `modules/services/context.py`: a frozen dataclass `ServiceContext`
   (user_id, company_id, role_code, origin in {Human, Agent, Import,
   System}, agent_run_id optional). Origin is validated.
3. `modules/services/tx.py`: `write_transaction(db_path, context)` context
   manager: gets a connection from `database.get_connection`, `BEGIN
   IMMEDIATE`, writes `audit_context` for this transaction, commits or rolls
   back, always closes. Check the live audit_context table and triggers in
   migrations 001-004 and use their real column names; report if `origin`
   is missing there (it is planned for 011, so do not add it now).
   Also `read_connection(db_path)` for read-only use.
4. `config.py`: `LOG_DIR` and `LOG_FILE` under the base directory; a
   `modules/services/logging_setup.py` that configures a rotating file log.
5. Tests:
   - `tests/test_service_tx.py`: commit on success, rollback on exception,
     foreign keys ON inside the transaction, audit_context set for the
     transaction's writes (use an audited table from 001-004), invalid
     origin rejected.
   - `tests/test_static_rules.py`: (a) no `sqlite3.connect` outside the
     allowed paths, (b) no `print(` in `modules/` except an allow-list.
     Both allow-lists list today's offenders by file, with a comment that
     each file is removed from the list when Phase 3 rewrites it.
6. Do not change any view in this step.

Finish with the summary from CLAUDE.md section 8: files changed, tests run
(counts), anything uncertain. Commit: "Phase 2.1: service foundation".
