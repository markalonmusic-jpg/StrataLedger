# Addendum for Claude Code: code review findings

Stay in plan mode. Show the plan before editing. Do NOT commit this file.
This adds to next_steps_instructions.md; it does not replace it.

## Step A. Verify first (read-only, no edits)

An outside review of the uploaded code made the claims below. Check each one
against the repo and report TRUE, FALSE or PARTLY, with file and line.
Only act on the ones that are true.

1. Passwords are stored and compared as plaintext (app_strata.pyw,
   views_new_user.py, views_user_profile.py, database.py).
2. A hardcoded master token (removed in Phase 2.3) was in app_strata.pyw.
3. user_company_access is never checked when a company is opened.
4. views_new_user.py offers roles that the master CHECK constraint rejects
   (for example Viewer).
5. These files call sqlite3.connect directly instead of get_connection():
   app_strata.pyw, views_billing, views_new_company, views_new_user,
   views_payroll, views_registry, views_user_profile, views_wizard.
6. views_new_company.py writes company_profile and never creates the
   company_settings row with id = 1.
7. views_wizard.py save action only print()s errors, still navigates away,
   and writes contacts without a customer_code.
8. views_dashboard.py shows hardcoded numbers.
9. views_payroll.py inserts raw text into wage_cents and burden_cents.
10. 001_company.sql still contains crm_opportunity, crm_change_order,
    crm_activity_stream, saas_subscription and company_profile, and also
    progress_billing_application and purchase_order_subcontract.
11. Duplicate copies of any view file exist in the repo (git ls-files).

For item 10, also list the columns of saas_subscription and say how it
relates to the deferral tables.

## Step B. CLAUDE.md edits (doc-only commit, after Step A is reviewed)

Rules (section 3), new:
- Connections: every connection comes from database.get_connection(). Every
  write goes through the service layer's write transaction, which sets
  audit_context (user_id, origin) before any SQL. A test fails if
  sqlite3.connect appears outside database.py, tests and tool scripts.
- No silent errors: no print() for validation or database errors. Services
  raise typed exceptions; the UI shows a dialog; errors are also logged to a
  log file whose path is defined in config.py.
- Auth: passwords are hashed with hashlib.scrypt, never stored or compared as
  plaintext. No hardcoded tokens. Opening a company checks
  user_company_access. The role list is defined only by the master migration.

Phase 2 (service layer), add:
- Auth service (hash, verify, change password), remove the hardcoded token,
  enforce user_company_access in the open-company service.
- Company creation service: builds the database from migrations, creates the
  company_settings row (id = 1), seeds a chart of accounts from a template,
  and generates fiscal periods.
- Period service: generate periods, close with pre-close checks, reopen with a
  logged reason and approver.
- Write-transaction helper that sets audit_context.

Phase 3 (screens), add:
- Live queries on the dashboard, real error dialogs and customer codes in the
  customer wizard, validated money fields in payroll, a new-company screen
  that calls the service, chart of accounts screen, fiscal period screen,
  trial balance and account ledger, manual journal entry with void and
  reverse, payments and bank reconciliation, backup and restore screen.

Backlog, add "DESIGN NEEDED" items (none designed yet), in this order:
1. Pay applications and subcontracts / purchase orders, with retainage
   (tables already exist in 001_company.sql).
2. Chart of accounts templates (construction contractor first) and the
   mapping of system roles to accounts (AR, AP, retainage, sales tax, and so
   on).
3. Opening balance and conversion workflow for existing businesses.
4. Banking and bank reconciliation.
5. Roles and permissions (what each role can do, approvals).
6. Backup, restore and export, with a retention policy for Backups/.

Schema cleanup decision: migration 005 drops the superseded crm_opportunity,
crm_change_order and crm_activity_stream tables and the legacy company_profile
table. saas_subscription stays until its relationship to the deferral
subledger is decided.

## Step C. Master migration

Add the role Viewer (read-only) to the app_user role CHECK in a new master
migration, 003_master.sql, with a failing test first. Do not apply it to the
real master file.
