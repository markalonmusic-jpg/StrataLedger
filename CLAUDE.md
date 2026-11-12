# StrataLedger (Accounting LibreBase) - project rules for Claude Code

Desktop accounting app for Windows: Python 3.11, CustomTkinter, SQLite. Subscription-free, local data. A
hosted version (FastAPI + PostgreSQL) comes later, so services stay portable (rule 15).

This file holds what every session needs: the rules, the file map and where the project stands. Keep it
under 200 lines. Dated history goes in docs/status_log.md, plans in docs/roadmap.md, design decisions in
docs/design_decisions.md and docs/decisions_2026-11-11.md. Code comments and tests cite the section and
rule numbers below, so keep the numbering.

Commands (from the repo root):
- Full test suite: `python -m pytest -q`
- Static rules only: `python -m pytest -q tests/test_static_rules.py tests/test_static_portability.py`
- Run the app: `pythonw app_strata.pyw` (or `StrataLedger.bat`)
- Rebuild development databases: `python scripts/create_fresh_databases.py` (dry run; `--apply` writes)

---

## 0. Design principle: graduated controls (top-level rule)

StrataLedger defaults to QuickBooks-level flexibility for a small business; a company switches on stronger
controls as it grows. It is not a NetSuite clone. Source: docs/decisions_2026-11-11.md section 0, which wins
over any design doc.

**Integrity rules: always on, never configurable.**
- Integer cents; balanced double entry checked in the posting transaction.
- Posted records are locked; corrections are reversals or new documents.
- The audit log records every change and cannot be edited or deleted.
- Nothing posts into a closed period (closing periods is optional).
- Registered invoice series (Philippines add-on) stay gapless.
- Permissions are enforced in the service layer (`authorize`); the AI never posts, approves or moves money.
- Agent-origin entries always need a human approval; import-origin batches always need one human review.

**Controls: configurable, OFF or permissive by default**, switched on in Company Settings > Controls by an
Admin or the Master, every change audit-logged: separation of duties, approval per document type, manual
entries to controlled accounts, PO matching and tolerances, compliance holds, close-checklist blocks,
project scope, approval limits and chains, a second approver for imports.

Rule for new features: a check that could reasonably be optional is a setting with a permissive default,
listed on the Controls page and logged. When unsure whether something is integrity or control, ask.

## 0b. Design principle: ease of use (UX/UI)

Simple by default, power one step away: plain language, sensible defaults, progressive disclosure, presets
first, wizards for rare tasks, searchable lists that drill down, safe drafts, and errors that say what to do
next in one sentence. Screens follow docs/CLAUDE_UI.md.

---

## 1. Project vision and history

A desktop, subscription-free accounting platform for businesses and CPAs who want local data ownership:
multi-company, project costing, percentage of completion, construction contracts, deferrals, custom
dimensions, imports from Gusto, Rippling and Ramp. Release order: v1.0 core accounting, v1.1 construction,
v1.2 AI Copilot (docs/roadmap.md).

## 2. Directory and file structure

Paths are defined once in `config.py`: `RESOURCE_DIR` (read-only: migrations, fonts, templates, help) and
`DATA_DIR` (written: databases, `Companies/`, `Backups/`, `Logs/`, `Uploaded_Files/`). Never hardcode a path.

- `app_strata.pyw` - entry point: first-run routing, launcher, login, shell (sidebar, workspace, Copilot
  placeholder).
- `config.py` - paths and `Theme` (every colour, font and size).
- `modules/database.py` - connections, the baseline runner and the pre-release hash guard.
- `modules/services/` - the service layer: every write and every protected read. `tx.py` (write transaction,
  read connection), `context.py` (`ServiceContext`), `authz.py` (`authorize`), `errors.py` (typed
  exceptions), then one module per area.
- `modules/views_*.py`, `sidebar.py`, `ui_components.py` - screens and shared widgets. A screen's checks and
  wording live in a `*_model.py` with no Tk. The pattern to copy: `views_first_run.py` + `first_run_model.py`.
- LEGACY screens (the files in `CONNECT_ALLOW_LIST` in tests/test_static_rules.py) still run their own SQL
  and are rewritten in Phase 3. Do not copy their patterns.
- `migrations/001_company.sql`, `001_master.sql` - the schema baseline (section 5).
- `templates/coa/` - approved chart-of-accounts templates. `tests/` - pytest. `scripts/`, `tools/` -
  developer tools.
- `docs/` - design docs. Read the one for an area before touching it; docs/file_map.md lists each with its
  build status and has the longer notes on individual modules.
- `archive/` - old baselines and prompts. Do not read, search or copy from it unless the task names it;
  never apply anything there.
- `.claude/agents/` - subagents. `.claude/rules/` - rules that load only for matching files.
- `.db` files, `fonts/`, `Backups/` and `Logs/` are not tracked by git.

## 3. Non-negotiable engineering and accounting rules

1. **Integer cents only.** Money is `INTEGER` cents everywhere, never `REAL`/`FLOAT`. (Quantities, hours
   and percentages may be `REAL`.)
2. **Balanced double entry.** Posting checks `SUM(debit_cents) == SUM(credit_cents)` in the posting
   transaction. Unbalanced drafts may be saved.
3. **Two kinds of database.** `system_master.db` (users, company registry, access) and one isolated file
   per company. Never put company accounting tables in the master. Services reach the open company through
   the `ServiceContext`.
4. **Foreign keys on** for every connection.
5. **Separation of concerns.** `database.py` and services never show dialogs. They raise typed exceptions;
   the UI catches and displays them.
6. **Security.** Never commit plaintext credentials or tokens. Passwords: rule 13.
7. **All writes go through `modules/services/`.** The UI and the AI agent never run SQL writes.
   `ledger.py` is the only writer of the journal tables. The agent's own connection will be read-only
   (Phase 6); today no agent code exists, only `authorize`'s `AGENT_ALLOWED` allow-list.
8. **Posted records are locked.** Corrections are reversing entries, never edits or deletes.
9. **Never delete or rewrite a database file without asking.** Back up a file that holds real data before
   any schema change (section 5).
10. **Every service that writes, or reads protected data, calls `authorize(context, permission, project_id)`
    first**, before it opens its write transaction, and raises a typed exception on denial. The UI only hides.
11. **Connections** come only from `modules/database.py`; services reach it through `tx.write_transaction`
    (which sets `audit_context`) and `tx.read_connection`. No `sqlite3.connect` anywhere else, except in
    `tests/`, `scripts/` and `tools/`.
12. **No silent errors.** No `print()` in `modules/`. Services raise typed exceptions, the UI shows a
    dialog, and errors go to the log file (`config.LOG_FILE`).
13. **Auth.** Passwords are hashed with `hashlib.scrypt` through `passwords.py`, never stored or compared as
    plaintext; only `auth.py` and `users.py` touch `password_hash`. Opening a company checks
    `user_company_access`.
14. **Ease of use.** Every screen follows section 0b and docs/CLAUDE_UI.md. New optional checks follow
    section 0.
15. **Portability (hosted-ready).** In `modules/services/`: no UI or OS-specific imports (H1); no clock
    reads, `now` and `today` come from the context (H2); files go through `storage.py` (H3);
    `audit_context` is touched only in `tx.py`, and workflow rules live in services, not new triggers (H4);
    no SQLite-only SQL, PRAGMAs only in `database.py` (H5); visual values live in `config.Theme` (H6).

`tests/test_static_rules.py` and `tests/test_static_portability.py` enforce rules 10-12, 13 (`password_hash`
only; scrypt is tested in tests/test_passwords.py) and 15 (H1, H2, H4, H5). Allow-lists only shrink.

## 4. Key schema conventions

Table names, columns and allowed values are in `migrations/001_company.sql` and `001_master.sql`. Read them
there; do not rely on a list in a doc. `_at` columns written by services are UTC ISO 8601 with an offset.
User ids in a company file are plain integers (the user table is in the master; there is no cross-file FK).

## 5. Source of truth and reference documents

1. The baseline files `migrations/001_company.sql` and `migrations/001_master.sql` are the schema source of
   truth. Until the first release there is ONE baseline per database kind: schema changes edit it directly,
   with failing tests first, and development databases are rebuilt from it. At the first release the
   baseline is frozen and later changes are numbered migrations (002 and up); a released file is never
   edited.
2. The runner stores a SHA-256 of the baseline text in every database it builds and refuses to open a file
   whose hash differs (`SchemaUpgradeBlockedError`). ANY edit to a baseline file, a comment included,
   blocks every existing development database until it is rebuilt.
3. `docs/accounting_schema.txt` is a planning reference; its names may differ from the baseline. Where a
   doc and the baseline differ, the baseline wins. Do not change either to match the other without asking;
   report the difference.

## 6. Design decisions already made

Moved, unchanged, to docs/design_decisions.md. Read the topic before building in its area: Imports;
Deferrals; Construction; AI coworker guardrails; CRM and project lifecycle; Customer codes; Vendor codes;
Schema cleanup; Timestamps; Purchase orders and PO-to-AP matching; Report presets; Fresh start; Country
add-ons. Items marked PROPOSED in a design doc are not decided: do not build them as final.

## 7. Roadmap and status

Plan, phases, backlog and schema plan: docs/roadmap.md. Dated history: docs/status_log.md (append an entry
there at the end of each step, and update the paragraph below).

**Where we are (2026-11-12):** Phase 2 (service layer). Done: 2.1-2.4, 2.6, and 2.5 steps 1, 2, 1b, 3, 3b
(drafts, sealed posting, verification, signed checkpoints at close, logout and exit). Password recovery is
decided (PW1-PW11; build step 2.8 after 2.5). Now: 2.5 step 1c (keystore, KS1-KS11), sub-step 1 done
(`cryptography` pinned); then steps 4-7, 2.7, Phase 3. Until 1c sub-step 6 nothing posts outside tests.

**Known issues (code as it is today):**
- `auth._now()` is the one allowed clock read in services (H2 allow-list) until auth takes `now` as an
  argument.
- The context from `open_company` is kept for the whole session, so its `now` and `today` are the time the
  company was opened. A screen must get a fresh context for each action before it posts, closes a period or
  approves (posted_at is sealed into the chain). Not built yet.
- Nothing calls `logging_setup.configure_logging()` at start-up, so the running app writes no log file.
- `views_billing.py` cannot load or save (its SQL names tables and columns that are not in the baseline);
  `views_wizard.py` inserts a customer without a code, which the baseline rejects. Phase 3.
- The launcher's "Open Existing Ledger File" button cannot work (it passes a path as a company id) and the
  launcher list shows archived companies. Phase 3.
- `ui_components.DataTable` needs `Theme.create_scrollbar`, which does not exist; the modal's badge styles
  hold hex colours. Phase 3.
- `app_user.role` is a legacy free-text column read only by the sidebar's `NAV_ITEMS`; Phase 3 replaces it
  with permission-based visibility and removes it from the baseline.
- Tests share one hidden Tk window (`tk_app` in tests/conftest.py). The live-clipboard tests run only with
  `STRATALEDGER_LIVE_CLIPBOARD=1`.

## 8. Working agreement

This section is for the main Claude Code session. A subagent follows its own file in `.claude/agents/`
where the two differ (subagents never commit or push), and Copilot follows .github/copilot-instructions.md.

- This repo is StrataLedger-clean. C:\Users\marka\StrataLedger is an old archive: never edit, commit or push there.
- Work only on the phase or task named. Start in plan mode: list the files you will change and why.
- Show diffs. Tests first for every rule you enforce. Run the full suite and show the results.
- Commit at the end of each phase or step and push `main` to `origin`. Stage files by explicit path, never
  `git add -A` or `git add .` (the planning chat writes files into this folder). Check `git status` and
  `git diff --cached` before every commit. Never commit `.db` files, credentials or tokens; never
  force-push without asking.
- Only one tool edits this working folder at a time. Copilot works only in its own worktree
  (`git worktree add ..\StrataLedger-copilot -b copilot/<task> origin/main`); copilot-reviewer reviews its
  commits before merge. Commit and push between handoffs, and pull before starting.
- Before reporting a step: run step-reviewer; for auth, keys, recovery, backups, email or feeds also run
  secrets-auditor; run mutation-tester on the committed step. View-only screens may go to screen-builder;
  the main session reviews and commits its work. Run one agent that edits files at a time.
- Finish every task with a summary: files changed, tests run, anything uncertain.
- Planning and review happen in the Claude chat; this tool performs the tasks from the prompts it is given.

## 9. Open decisions and notes for review

docs/roadmap.md, "Open decisions".
