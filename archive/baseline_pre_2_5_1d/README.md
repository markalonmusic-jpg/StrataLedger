# Baselines before Phase 2.5 step 1d (historical, not applied)

`001_company.sql` and `001_master.sql` exactly as they stood at commit 21282a4, before step 1d added the
`Key lost` / `Unverified` checkpoint (company `ledger_checkpoint` and master `chain_checkpoint`), made the master's
`installation_key` an append-only history with one active row, added `company_key.installation_key_id` and the
`Installation key replaced` auth event. Kept for reference only; the migration runner never reads this folder.
Git tag `baseline-pre-2.5-1d` marks the same commit.
