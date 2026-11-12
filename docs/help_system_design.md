# Help system design

Status: DESIGN (decided 2026-11-11). Content is DEFERRED: no `help/*.md`
articles are written until their modules are finalized and tested. Writing
the full guide set is one of the final tasks before release (roadmap step
"Conversion, backup, ship").

Related decisions: 0b (ease of use), U "Built-in help" (offline Markdown,
`?` / F1), H1 (services free of UI), H3 (resources and storage), H6 (theme
tokens), P2a (resource folder), and the AI guardrails (section 6 of
CLAUDE.md).

---

## 1. Storage and offline architecture

- Articles are UTF-8 Markdown files in `help/` inside the resource folder
  (P2a), read-only, bundled into the installer (PyInstaller
  `--add-data "help;help"`). Help works 100% offline: no network calls,
  no web links required to read any article.
- Each file starts with YAML-style frontmatter:

  ```
  ---
  title: Reconciling a bank account
  category: Banking
  page_keys: [banking.reconcile, banking.statement_import]
  permissions: [bank.reconcile]
  order: 20
  ---
  ```

  - `page_keys`: the screen identifiers the article explains (one screen
    may have several articles; one article may serve several screens).
  - `permissions`: permission codes from the registry. An article is shown
    to a user who holds at least one of them; an empty list means everyone.
    Help is filtered by permission, never by role name (roles are
    per-company and customizable).
  - `category` and `order`: grouping and sort order in the help index.
- Images used by articles live in `help/images/` and are referenced with
  relative paths. Screenshots are taken from the sample companies, never
  from real client data.

## 2. Service layer: `modules/services/help.py` (no UI code)

- Loads and indexes `help/*.md` once per run through the resource loader
  (H3), validating frontmatter. A malformed article is logged and skipped,
  never crashes the app.
- `search_help(context, query) -> list[dict]`: case-insensitive full-text
  search over titles and bodies, ranked (title matches first), returning
  title, category, a short snippet with the match, and the article key.
  Filtered by the user's permissions (via the same permission check the
  services use).
- `get_context_help(context, page_key) -> list[dict]`: the articles for
  the screen the user is on, in `order`.
- `get_article(context, key) -> dict`: title and Markdown body.
- Returns plain dicts (H1); no tkinter imports; usable unchanged by the
  hosted web version.
- Tests: index builds from a fixture help folder; search ranking and
  snippets; permission filtering; unknown page key returns an empty list;
  malformed frontmatter is skipped and logged; a static test that every
  `page_key` used by a screen has at least one article (enabled only when
  the content task starts).

## 3. UI and UX integration (`modules/views_help.py`, `app_strata.pyw`)

- Opened by F1, the top-bar `?` button, or inline "Learn more" links on
  empty states and complex controls. F1 opens the articles for the current
  screen (its `page_key`); with none, it opens the help home with search.
- A slide-over drawer on the right, about 480 px wide, styled only with
  `config.Theme` tokens (glass panel, slim scrollbar); no literal colors
  (H6). A "Pop out" button opens the same view in its own window for a
  second monitor.
- Contents: search box (permission-filtered results with snippets),
  the current screen's articles, a category index, and the rendered
  article. Links inside an article can be in-app navigation buttons
  ("Open Bank Reconciliation") that take the user to that screen if they
  have permission.
- Every screen declares a stable `page_key`; screens are not finished in
  Phase 3 without one.
- AI Copilot (v1.2): when the Copilot answers a how-to question, it may cite
  help articles by key and the drawer opens them. The AI reads help articles
  only; help content never includes company data.

## 4. Deferred content rule

- No article is written before its module passes final testing, so help
  never describes behaviour that later changes.
- Planned guides (one or more articles each):
  `getting_started`, `customers_and_projects`, `billing_and_pay_apps`,
  `purchasing_and_ap`, `banking_and_reconciliation`,
  `general_ledger_and_deferrals`, `periods_and_closing`,
  `inventory_assets_loans`, `fpa_and_reporting`, `ai_copilot_and_csv`.
  Guides for modules that ship after v1.0 (construction, FP&A, AI) are
  written with their release.
- Every guide has three parts:
  1. Step-by-step instructions for each task on the screen.
  2. Workflow best practices (how a small business and a growing one
     would each use it, matching graduated controls).
  3. Accounting guardrails (what the system enforces and why, what needs
     care, and which controls a company can turn on).
- Plain language (0b); each article opens with what the screen is for in
  one sentence.

## 5. Final task (roadmap)

"Help content": write the guide set, take screenshots from the sample
companies, enable the page_key coverage test, and review every article
against the finished screens. Runs after all v1.0 modules are finalized
and tested, before the installer build.
