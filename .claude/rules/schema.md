---
paths:
  - "migrations/**"
  - "modules/database.py"
  - "scripts/**/*.py"
  - "tests/test_baseline_guard.py"
  - "tests/test_migration_runner.py"
---

# Schema and baseline rules (loads when a migration or the runner is open)

Unchanged from CLAUDE.md section 5:

1. **The baseline files `migrations/001_company.sql` and
   `migrations/001_master.sql` are the schema source of truth** (decided after
   the 2026-11-10 schema audit, `docs/schema_audit.md`). Until the first
   release there is ONE baseline per database kind instead of a migration
   chain (decided 2026-11-11: nothing is released and no real data exists).
   Schema changes edit the baseline directly, with failing tests first, and
   development databases are rebuilt from it with
   `scripts/create_fresh_databases.py`. At the first release the baseline is
   frozen; later changes are numbered migrations 002 and up, and a released
   file is never edited. The chain that preceded the baseline is archived in
   `archive/migrations_chain_v5/`;
   `tools/verify_baseline_squash.py` proved the baseline equal to it (zero
   differences) at the squash commit. `accounting_librebase.db` is a reference
   snapshot generated from the baseline by
   `scripts/build_reference_snapshot.py`, so the two cannot drift. It is not
   read at runtime. Never edit it by hand; regenerate it.
2. The migration runner (`database._apply_migrations`) applies all pending
   migrations in one transaction, runs `PRAGMA foreign_key_check` and
   `PRAGMA integrity_check` before commit, and on any failure rolls back,
   leaves the file unchanged and raises `SchemaUpgradeBlockedError`.
   Migration scripts must not manage transactions or `PRAGMA foreign_keys`.
   **Pre-release guard:** when it builds a database the runner stores a
   SHA-256 of the baseline text in it (table `schema_baseline`, line endings
   ignored). Opening a file whose stored hash differs or is missing, whose
   version is above the baseline's, or that has tables but no
   `schema_version` raises `SchemaUpgradeBlockedError` ("rebuild with
   scripts/create_fresh_databases.py") and leaves the file unchanged. This
   guard is pre-release only: it is replaced by versioned migrations at the
   first release.
3. `docs/accounting_schema.txt` is the planning reference. It records design
   intent, rules and open decisions from the schema planning sessions, and
   marks each rule as enforced by the schema or in the service layer. Table
   and field names there may differ from the live database (for example it
   says `batch_id` where the database uses `source_batch_id`).
4. Where the doc and the baseline schema differ, **the baseline wins**. Do
   not change either to match the other without asking. Report differences
   instead.
