# Baselines before Phase 2.5 step 3b (historical, not applied)

`001_company.sql` and `001_master.sql` exactly as they stood at commit ea91a5f, before step 3b added the
`ledger.verify` permission (company) and the `chain_checkpoint` mirror table (master). Kept for reference only;
the migration runner never reads this folder. Git tag `baseline-pre-2.5-3b` marks the same commit.
