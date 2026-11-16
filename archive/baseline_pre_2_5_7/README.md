# Company baseline before Phase 2.5 step 7 (historical, not applied)

`001_company.sql` exactly as it stood at commit 5411d7e, before step 7 added
`payment_allocation.application_entry_id` (decision R58: the application entry an allocation of a posted
payment or credit memo posts, so a release can post its opposite). The master baseline did not change in step 7.
Kept for reference only; the migration runner never reads this folder. Git tag `baseline-pre-2.5-7` marks the
same commit.
