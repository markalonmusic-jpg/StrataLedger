# Company and master baselines before the consolidated replan update (historical, not applied)

`001_company.sql` and `001_master.sql` exactly as they stood at commit 499c8d5, before STOP 1 of the
consolidated baseline update (decisions RP1-RP11, docs/design.md section 10) added entities, line clearing,
contact, document and payment-allocation columns, service types, pay runs, bank statement lines, close tasks,
custom fields, list preferences, multi-role access and an index on every foreign key. Kept for reference only;
the migration runner never reads this folder. Git tag `baseline-pre-replan` marks the same commit.
