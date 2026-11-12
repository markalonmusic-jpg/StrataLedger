---
paths:
  - "modules/services/**/*.py"
  - "tests/test_static_*.py"
---

# Service layer rules (loads when a service file is open)

- Shape of a write service: validate, `authorize(context, permission, ...)`, then
  `with write_transaction(context.company_db_path, context) as conn:`. Authorize BEFORE the transaction so a
  denial is logged in its own transaction (rule 10; the static test checks the order).
- Reads use `read_connection(...)` and close it. Name columns in SQL; read rows by name.
- Inputs and results are plain types and dicts; money is integer cents; errors are the typed exceptions in
  `errors.py`. Never catch a service error to continue silently.
- Take `now` and `today` from the context. Never call the clock.
- A static-test allow-list may only shrink. If a test fails, fix the code, not the list.

The full text of rule 15, unchanged from CLAUDE.md:

15. **Portability (hosted-ready).** Services must port to FastAPI and
    PostgreSQL without a rewrite (docs/decisions_2026-11-11.md H1-H6). In
    `modules/services/`: no UI, dialog or OS-specific imports (H1); no reading
    the system clock, `now` and `today` come from the context (H2); files go
    through `storage.py` (H3); `audit_context` is touched only in `tx.py`, and
    workflow rules live in services, not new triggers (H4); no SQLite-only SQL
    such as `date('now')`, `strftime`, `julianday`, `INSERT OR REPLACE`,
    `GROUP_CONCAT`, and PRAGMAs only in `database.py` (H5); visual values live
    in `config.Theme` (H6). `tests/test_static_portability.py` enforces H1, H2,
    H4 and H5; its allow-lists can only shrink. Hosted target is PostgreSQL, expected on Azure
    Database for PostgreSQL (P5): posted-entry locks and the void trigger are rewritten per dialect,
    numbering and the hash chain use explicit counter-row locking, and secrets sit behind one wrapper
    (`KeyProvider`) so Azure Key Vault can replace DPAPI. The SQLite-only constructs in the baseline that
    the PostgreSQL schema rewrites (GLOB, `typeof`, RAISE triggers, `json_object`, AUTOINCREMENT, `IS`
    comparisons) are listed in docs/audit_readiness_design.md section 16; add new ones there.
