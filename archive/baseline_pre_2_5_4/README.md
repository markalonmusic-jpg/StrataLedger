# Company baseline before Phase 2.5 step 4 (historical, not applied)

`001_company.sql` exactly as it stood at commit 76c027d, before step 4 added `approval_request.document_digest`
(required for a journal entry's request), the audit triggers on `approval_request` (insert, update) and
`approval_action` (insert), and the trigger that stops an `approval_request` row being deleted. The master
baseline did not change in step 4. Kept for reference only; the migration runner never reads this folder.
Git tag `baseline-pre-2.5-4` marks the same commit.
