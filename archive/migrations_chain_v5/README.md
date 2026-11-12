# Migration chain v5 (historical, not applied)

These are the schema migrations as they stood before the pre-release baseline
squash: company 001-005 and master 001-003. They are kept for reference only.

- The migration runner reads only the files named in `modules/database.py`
  from `migrations/`. It never reads this folder.
- Git tag `schema-chain-v5` marks the commit where this chain was last the live
  schema ("Migration chain 001-005 / master 001-003 before baseline squash").
- The current schema is the baseline: `migrations/001_company.sql` and
  `migrations/001_master.sql`. Until the first release, schema changes edit the
  baseline directly (CLAUDE.md section 5).
- `tools/verify_baseline_squash.py` builds a database from this chain and from
  the baseline and compares them.
