# Instructions for Copilot (StrataLedger)

Read CLAUDE.md sections 0, 0b, 2, 3 and the "Known issues" list in section 7, docs/CLAUDE_UI.md, and the design doc your task names. Do not read the other design docs or anything under archive/. If a rule here and CLAUDE.md differ, CLAUDE.md wins, except for git: CLAUDE.md section 8 (commit, push main) is for Claude Code, and the branch rules below are yours.

- Tests first. The full suite and tests/test_static_rules.py must pass before you say a task is done. Report the pass counts.
- Views: Theme tokens only (no hex colours), shared dialogs only (no messagebox), no SQL, no print. Business rules live in services, never in views.
- Page keys: every screen declares a stable PAGE_KEY, lowercase snake_case, "<area>.<screen_or_action>" (for example setup.first_run, banking.reconcile, customers.create). Keys must be unique across all views.
- Never edit: CLAUDE.md, docs/decisions_*.md, migrations/ or the baseline, modules/services/ledger.py, periods.py, auth.py, keys.py, or anything about keys, hashing, posting, approvals or passwords. If a task seems to need one of these, stop and say so.
- Work on a branch named copilot/<task>, never on main. Do not push to main.
- Stage files by explicit path. Never "git add ." or "git add -A".
- Money is whole cents. Dates are ISO text. Never log or print passwords, codes or keys.
- One task at a time, only the files named in the task. Report: files changed, tests added, counts.
