# Instructions for Claude Code: Phase 2.2 (permissions core)

Read CLAUDE.md and docs/roles_permissions_design.md (sections 1-12) first.
Stay in plan mode. Do 2.2a, stop for review, then 2.2b. Do NOT commit this
file (phase2_step2_instructions.md).

Ground rules: no real .db files, no app launch, no views changed. Failing
tests first in each part. Migrations are applied only to test copies.

---

## Decision: migration numbering (DECIDED 2026-11-11)

Migrations are numbered in build order. 001-004 keep their numbers. Every
unbuilt migration is named, not numbered, until it is built. Roles and
permissions is 005_company / 003_master.

---

## Decision: multiple approvers (DECIDED 2026-11-11, added after first draft)

Some companies need more than one approver. Approval is a chain of steps,
configured per company as data. A company that sets nothing gets today's
behavior: one approver who holds the permission and a high enough limit.

Rules:
- A policy applies to one document type and an amount band (min, max).
  Bands for a document type must not overlap (service check + test).
- A policy has steps. Steps run in order of step_no. Rows with the same
  step_no are parallel: all must be met before the next step opens.
- Each step names a role and required_count (default 1): that many
  DIFFERENT people holding that role (and the document's permission, and
  an approval_limit covering the amount) must approve.
- One person fills at most one slot in the whole chain, whatever roles
  they hold. Master and Admin follow the same rule.
- When require_separate_approver = 1 the creator can fill no slot. When 0,
  the creator may approve and the action is flagged self_approved.
- Any rejection ends the request (status Rejected, reason required).
- The chain is copied onto the request at submit time. Editing the policy
  later never changes requests already in progress.
- Editing the document (amount, lines, accounts, vendor) after submit
  cancels the request; it must be resubmitted and approved from step 1.
- The document can be posted / paid only when its request is Approved.
  The existing approved_by / approved_at columns hold the LAST approver
  and keep their CHECK (approver is not the creator when the setting is on).
- Agents never approve (AGENT_NEVER), and no step can name an agent.

These tables replace crm_approval_rule / crm_approval_instance (keyed on
job title, contract/estimate/change order only). Do not drop those two in
005; record in CLAUDE.md section 6 "Schema cleanup" that the CRM / project
lifecycle migration drops them, since the new tables replace them.

Add to 005_company.sql:
- `approval_policy` (policy_id PK, document_type same CHECK list as
  approval_limit plus 'Estimate', 'Change order', 'Contract';
  min_amount_cents INTEGER NOT NULL DEFAULT 0, max_amount_cents INTEGER
  NULL = no upper bound, is_active, name).
- `approval_step` (step_id PK, policy_id FK ON DELETE CASCADE, step_no
  INTEGER >= 1, role_code FK role, required_count INTEGER NOT NULL DEFAULT 1
  CHECK >= 1; UNIQUE (policy_id, step_no, role_code)).
- `approval_request` (request_id PK, document_type, record_type, record_id,
  amount_cents INTEGER NOT NULL, policy_id FK NULL (NULL = default single
  approval), chain_json TEXT NOT NULL (the copied steps), status CHECK IN
  ('Pending','Approved','Rejected','Cancelled'), submitted_by INTEGER,
  submitted_at TEXT, completed_at TEXT). At most one Pending request per
  (record_type, record_id) (partial unique index).
- `approval_action` (action_id PK, request_id FK, step_no, role_code,
  user_id INTEGER NOT NULL, decision CHECK IN ('Approve','Reject'), reason
  TEXT (required for Reject), self_approved INTEGER CHECK 0/1, acted_at
  TEXT NOT NULL; UNIQUE (request_id, user_id)). Append-only (triggers).
- Audit triggers on approval_policy and approval_step.

In the 2.2a docs commit, also add a section "5A. Multiple approvers" to
docs/roles_permissions_design.md with the rules above.

In 2.2b, `check_separate_approver` becomes part of an approval module,
`modules/services/approvals.py`: submit_for_approval(context, document_type,
record_type, record_id, amount_cents), approve(context, request_id),
reject(context, request_id, reason), cancel_on_edit(context, record_type,
record_id), is_approved(conn, record_type, record_id). Each calls authorize.
Tests: default single approval; two-step chain; parallel steps; 2-of-N in
one step; same person twice blocked (also across steps and roles);
creator blocked when ON and flagged when OFF; reject ends it; band
selection at the boundaries; policy edit does not affect a pending request;
edit after submit cancels; overlapping bands rejected; agent cannot approve.

---

## 2.2a. Schema (one commit for docs, one for the migrations)

### CLAUDE.md edits (doc-only commit: "docs: migrations numbered in build order")

- Section 7 "Core migration plan": keep 001-004 as they are. Make 005 =
  "Roles and permissions (company) + 003_master". Turn the rest into an
  ordered list of NAMES with no numbers, in this order: customer numbers
  (Phase 2.6); CRM / project lifecycle (with its full existing text: schema
  cleanup, pay applications, the Retainage split); ledger line keys and
  controlled accounts; inventory; PO / subcontract / receiving / matching;
  fixed assets; vendor refunds; loans; AI support. Add the rule: "A
  migration gets its number when it is built. Unreleased migrations may be
  renumbered before the first release, never after."
- Replace every other fixed reference to an unbuilt number (for example
  "migration 011", "011, proposed", "005 drops ...", "005 must handle")
  with the migration's name. Search the whole file; list each change.
- Section 6 or 3, add: "Service timestamps are UTC ISO 8601 with an explicit
  offset, written by one helper (`modules/services/clock.utc_now_iso()`).
  Columns that default to CURRENT_TIMESTAMP (`audit_log.logged_at`, etc.)
  use SQLite's format; this is a known inconsistency, not fixed now."
- Do not edit the design docs; section 7 already wins over them.

### 005_company.sql (company database)

1. `permission` (permission_code TEXT PK, module TEXT NOT NULL, description
   TEXT NOT NULL, is_sensitive INTEGER NOT NULL CHECK 0/1). Seeded with
   every code in design section 3. Sensitive = wages, tax IDs, bank
   details, every *.approve, overrides, period.reopen, payment.release_hold.
2. `role` (role_code TEXT PK, name TEXT NOT NULL UNIQUE, is_system INTEGER
   NOT NULL CHECK 0/1, is_active INTEGER NOT NULL DEFAULT 1 CHECK 0/1,
   project_scope TEXT NOT NULL DEFAULT 'All' CHECK IN ('All','Assigned'),
   created_at TEXT NOT NULL). Seed only `Admin` (is_system = 1, scope All).
   Starter templates are seeded by the company creation service (2.4), not
   here.
3. `role_permission` (role_code FK role, permission_code FK permission,
   PK both). Seed Admin with every permission.
4. `approval_limit` (role_code FK role, document_type TEXT CHECK IN ('Bill',
   'Journal entry', 'Payment', 'Purchase order', 'Subcontract',
   'Pay application', 'Import batch', 'Asset disposal'), max_amount_cents
   INTEGER NOT NULL CHECK >= 0, PK both).
5. `user_project_scope` (user_id INTEGER NOT NULL, no FK: it is a master
   user id, CLAUDE.md section 9 item 4; project_id FK project; PK both).
6. `access_event` (event_id PK, occurred_at TEXT NOT NULL, user_id INTEGER,
   actor_type TEXT CHECK IN ('Master','User','Agent'), event_type TEXT CHECK
   IN ('Denied','Open company'), permission_code TEXT, record_type TEXT,
   record_id INTEGER, origin TEXT). Append-only: triggers block UPDATE and
   DELETE. No field values are ever stored in it.
7. `company_settings.require_separate_approver` INTEGER NOT NULL DEFAULT 1
   CHECK 0/1 (setup wizard asks; default is the safe setting).
8. Protect Admin: triggers block UPDATE or DELETE of the `Admin` role row and
   DELETE of Admin's role_permission rows. Inserts stay allowed so later
   migrations can grant Admin new permissions.
9. A role in use cannot be deleted: that check needs the master database,
   so it is a service rule (2.2b), not a trigger. Say so in a comment.
10. Audit triggers (same pattern as 003/004, reading audit_context) on
    role, role_permission, approval_limit and user_project_scope.

### 003_master.sql (master database)

1. `app_user.is_master` INTEGER NOT NULL DEFAULT 0 CHECK 0/1, with a partial
   unique index so at most one row has is_master = 1.
2. Rebuild `app_user` to DROP the role CHECK but KEEP the `role` column for
   now: login, NAV_ITEMS and views_new_user.py still read it. Backfill
   is_master = 1 where role = 'Master' (if more than one, the upgrade must
   fail with a clear message). The column itself is dropped in a later
   master migration once Phase 3 rewrites those screens; add that to the
   Known issues list in CLAUDE.md.
3. `user_company_access.role_code` TEXT (no FK across files) and
   `access_mode` TEXT NOT NULL DEFAULT 'Grant' CHECK IN ('Grant','Deny').
   'Deny' on a child company narrows access inherited from a parent
   (design section 9, "Subsidiaries").
4. Before writing it, report every reader of `app_user.role` in code and
   tests (including database.create_initial_master_user) and confirm none
   breaks.

### Tests (first) and checks

- Schema tests for every item above, on fresh and on upgraded (v4 company,
  v2 master) test copies: the CHECKs, the Admin protection, append-only
  access_event, one-Master index, backfill failure on two Masters.
- Test: `permission` table rows == the Python registry (the registry itself
  is built in 2.2b; for now compare against the list in the migration test,
  and 2.2b replaces it with the registry).
- Test: Admin holds every permission in `permission`.
- Drift guard in tests/test_ledger_rules.py: version-5 INTENDED_CHANGES entry.
- Regenerate accounting_librebase.db with scripts/build_reference_snapshot.py.
- Full pytest. Commit: "Add migration 005 and 003_master: roles and
  permissions". Stop and send the summary.

---

## 2.2b. authorize() and helpers (after 2.2a is reviewed)

Files: `modules/services/permissions.py`, `modules/services/authz.py`,
`modules/services/clock.py`. No schema changes.

1. `permissions.py`: `PERMISSIONS` registry (code -> module, description,
   is_sensitive), the single source the 005 seed is tested against. Also
   `AGENT_NEVER` (design section 8: approve, post, void, reverse, close,
   reopen, override, release hold, settings, roles, users).
2. `ServiceContext` gains `company_db_path` and `master_db_path` (tests
   updated).
3. `authorize(context, permission, project_id=None)`:
   - Unknown permission code -> raise ValueError (programming error, not a
     denial).
   - origin 'Agent' and permission in AGENT_NEVER -> deny, even for Admin
     and Master.
   - Read the user from the master DB on EVERY call (never cached):
     inactive -> deny; is_master -> allow.
   - Find the access row for context.company_id; if none, walk up
     parent_company_id. The nearest row wins; 'Deny' blocks. No row -> deny.
   - role_code 'Admin' or a role holding the permission in the company DB
     -> allow, if the role is active. Otherwise deny.
   - Project scope: if the role's project_scope is 'Assigned' and
     project_id is given, the user must be in user_project_scope; if
     project_id is None for a scoped role on a project permission, deny.
   - Every denial raises PermissionDeniedError (no values in the message)
     and writes an access_event in its OWN short transaction, committed
     independently, so the log survives the caller's rollback.
   - Master opening a company: `record_company_open(context)` writes an
     'Open company' access_event (actor_type 'Master').
4. Helpers for 2.5 (tests now, used later):
   - `check_approval_limit(context, document_type, amount_cents)`: Admin and
     Master unlimited; no limit row -> deny; amount > limit -> deny.
   - `check_separate_approver(context, created_by_user_id)`: returns
     self_approved = True/False; raises when require_separate_approver = 1
     and the approver is the creator (applies to Master and Admin too).
5. `clock.utc_now_iso()`; tx.py uses it for set_at.
6. Static test for rule 10 (ast): every function in modules/services/ that
   uses write_transaction must call authorize (or a check_* helper that
   calls it) before its first execute. Exclude authz.py's own denial log
   writer, by name, with a comment.
7. Tests from design section 10 that apply now: allowed/denied per
   permission; role change effective on the next call; same user, two
   companies, two roles; subsidiary inheritance and 'Deny' narrowing;
   Master universal; Admin cannot reach a company outside its tree; agent
   blocked from AGENT_NEVER as Admin and as Master; denial logged without
   values and survives rollback; approval limit boundary (= limit allowed,
   limit + 1 denied); self-approval blocked when ON, flagged when OFF.
   Use test copies of both databases.

Full pytest. Commit: "Phase 2.2: authorize and permission registry". Send
the section 8 summary, and say what the 5 skipped tests are.
