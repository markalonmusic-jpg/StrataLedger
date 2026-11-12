---
paths:
  - "modules/views_*.py"
  - "modules/*_model.py"
  - "modules/ui_components.py"
  - "modules/sidebar.py"
  - "app_strata.pyw"
---

# Screen rules (loads when a view is open)

Read docs/CLAUDE_UI.md before creating or changing a screen. The rules that are checked:

- No SQL, no `sqlite3`, no `print`, no `messagebox` in a view: call services, show the shared dialogs in
  `modules/ui_components.py`.
- No hex colours, fonts or sizes in a view: `config.Theme` tokens only. A token that is not in `config.py`
  does not exist; add it there once.
- Business rules, checks and wording live in services or in the screen's `*_model.py` (no Tk, unit tested).
- Every screen declares `PAGE_KEY`, lowercase snake_case `<area>.<screen_or_action>`, unique across all
  `modules/views_*.py`, with a test that scans them all.
- Errors shown to the user are one sentence with a next step; no codes or stack traces.
- Money is formatted from integer cents; dates follow the company date format; secrets are never logged.
- The legacy screens (the `CONNECT_ALLOW_LIST` in tests/test_static_rules.py) are not a pattern. Copy
  `views_first_run.py` + `first_run_model.py` and their tests.
