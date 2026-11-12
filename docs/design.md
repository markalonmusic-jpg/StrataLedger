# StrataLedger Design System & Look-and-Feel Specification (`docs/design.md`)

**Status:** DRAFT - to be reconciled with docs/CLAUDE_UI.md in Phase 3; CLAUDE_UI.md wins on conflicts  
**Applies To:** `app_strata.pyw`, `config.py`, `modules/ui_components.py`, and all `modules/views_*.py` screens.  
**Rulebook Alignment:** Enforces `docs/CLAUDE_UI.md` (zero raw hex codes in views, zero `tkinter.messagebox`, zero `ttk.Scrollbar`, and strict separation between UI widgets and `services/*.py`).

---

## 1. Visual Philosophy & Aesthetic Direction
- **Identity:** Precision dark-slate financial & construction cockpit. Designed for high-density accounting, job costing, and Schedule of Values (SOV) workflows without visual fatigue.
- **Depth Through Flat Elevation (No Shadows or Blur):** CustomTkinter does not support CSS drop shadows or glass blur. Create clear visual hierarchy strictly through **3 stepped dark-slate surface elevations** paired with crisp **`1px` hairline borders**:
  1. **Canvas (`Theme.bg_color` = `#090D16`):** Deepest obsidian base for the main application window and modal backdrop.
  2. **Chrome / Rail (`Theme.sidebar_bg` = `#0E1320`):** Fixed left navigation rail and right AI Copilot drawer.
  3. **Elevated Card (`Theme.glass_panel` = `#131824`):** Content cards, numbered step sections, KPI tiles, data tables, and modals, framed by `Theme.glass_border` (`#242C3E`).
  4. **Recessed Input (`Theme.input_bg` = `#0F131C`):** Form entries, dropdowns, code/detail boxes, and inactive segmented-control tracks.

---

## 2. Color System & Semantic Tokens (`config.Theme`)

Never hardcode hex colors inside views. Every color must come from `Theme`:

| Role | Token | Hex | Usage Rules |
| :--- | :--- | :--- | :--- |
| **App Background** | `Theme.bg_color` | `#090D16` | Root window background, scrollbar tracks |
| **Sidebar / Drawer** | `Theme.sidebar_bg` | `#0E1320` | Left navigation rail, right AI drawer, table headers |
| **Card Surface** | `Theme.glass_panel` | `#131824` | Cards, step containers, modals, table rows |
| **Input Surface** | `Theme.input_bg` | `#0F131C` | Text inputs, dropdowns, nested sub-cards |
| **Hairline Border** | `Theme.glass_border` | `#242C3E` | `1px` borders on cards, dividers, inputs |
| **Active Focus Ring** | `Theme.focus_border` | `#3B82F6` | `2px` border highlight when AI composer or input is focused |
| **Primary Action** | `Theme.btn_primary` | `#2563EB` | One primary CTA per screen (`Save`, `Post`, `+ New`), active pills |
| **Primary Hover** | `Theme.btn_primary_hover` | `#1D4ED8` | Hover state for primary buttons |
| **Secondary Action** | `Theme.btn_secondary` | `#1E293B` | Cancel, Back, secondary shortcuts, user chat bubbles |
| **Secondary Border** | `Theme.btn_secondary_border` | `#334155` | `1px` outline on secondary buttons |
| **Destructive Fill** | `Theme.btn_danger_bg` | `#2A1519` | Muted dark rose fill for `Logout`, `Void`, `Make Inactive` |
| **Destructive Text** | `Theme.btn_danger_text` | `#FCA5A5` | High-contrast rose text on destructive buttons |
| **Primary Text** | `Theme.text_primary` | `#F8FAFC` | Page titles, card headings, input values, primary figures |
| **Secondary Text** | `Theme.text_secondary` | `#94A3B8` | Subtitles, body copy, table headers, descriptions |
| **Muted Text** | `Theme.text_muted` | `#64748B` | Uppercase field labels, breadcrumbs, timestamps, hints |
| **Success / Posted** | `Theme.success_glow` | `#34D399` | Posted badges, connected status dot, positive deltas |
| **Warning / Review** | `Theme.warning_glow` | `#F59E0B` | Stalled deals, imported batches needing review, near-limit caps |
| **Error / Locked** | `Theme.error_glow` | `#F87171` | Validation errors, void badges, overdue items |

### Strict Color Discipline
- **One Primary Button Per View:** Only the main forward action on a screen uses `Theme.btn_primary` (`#2563EB`). All supporting actions use `Theme.btn_secondary` (`#1E293B`) or ghost/transparent buttons.
- **Status Never Relies on Color Alone:** Every semantic color must accompany an uppercase text pill (`POSTED · LOCKED`, `DRAFT`, `VOID`, `STALLED`, `ACTIVE`) or glyph.

---

## 3. Typography (`Inter` Type Scale)

- **Font Provisioning:** `modules/font_loader.py` ensures **`Inter`** is loaded at startup (downloading and registering privately via Windows GDI if absent, falling back cleanly to `Segoe UI` only if offline).
- **Scale & Hierarchy:**
  - **Page Title (`Theme.title_font`):** `24px Bold` (`#F8FAFC`) — Top of every screen and large KPI values.
  - **Card / Modal Title (`Theme.semi_title_font`):** `16px Regular/Medium` (`#F8FAFC`) — Modal headers, empty-state titles, sidebar brand.
  - **Section Heading (`Theme.section_font`):** `13px Bold` — Uppercase step titles (`CORPORATE ENTITY CLASSIFICATION`), primary button labels.
  - **Body & Inputs (`Theme.body_font`):** `13px Regular` — Form entries, chat messages, table cells, descriptions.
  - **Small / Secondary (`Theme.small_font`):** `12px Regular` — Subtitles, helper text, filter pills, status context lines.
  - **Micro Labels & Breadcrumbs (`Theme.caption_font`):** `11px Regular/Bold` — Uppercase field labels (`CUSTOMER NAME`), top breadcrumbs (`PLATFORM > CUSTOMERS > NEW INTAKE`), semantic pill badges.
- **Number Alignment:** All currency, quantity, and percentage columns in tables align **right** (`anchor="e"`), formatted with thousands separators and two decimals (`$1,250.00` — never raw cents).

---

## 4. Layout Grid, Spacing & Geometry

- **Window Target:** Designed for `1280 × 720` minimum up to widescreen displays (`1920 × 1080+`).
- **3-Column Shell (`app_strata.pyw`):**
  1. **Left Navigation Rail (`width = 240px`):** Brand header -> collapsible tree groups (`Customers ▾`, `Revenue ▾`, `Operations ▾`, `Projects ▾`, `Accounting ▾`, `Imports ▾`, `Settings ▾`) -> active row tinted `#16233F` with `3px` left accent bar -> bottom user card + `Toggle Assistant`.
  2. **Center Workspace (`flex = 1`):**
     - Fixed `36px` top bar with dynamic uppercase breadcrumb on the left (`PLATFORM > SECTION > PAGE`) and persistent **Company & Period Context Pill** (`COMBUZZ · USD · 2026-11`) on the right.
     - Scrollable or full-height content area (`padding = 24px–30px`).
     - Forms cap at `max_width ~ 960px` (or centered step cards); dashboards and data tables stretch full width.
  3. **Right AI Copilot Drawer (`width = 340px`, collapsible):** Minimal header (`Strata AI` + status dot + `+` New Chat + `⚙` Settings) -> scrollable chat feed (right-aligned `#1E293B` user bubbles, left-aligned `#131824` assistant cards) -> unified bottom composer card (`corner_radius = 12`) that highlights its border to `#3B82F6` (`2px`) on focus.
- **Consistent Corner Radii & Spacing:**
  - Cards & Modals: `Theme.radius_lg` (`12px`)
  - Inputs, Buttons & Tables: `Theme.radius` (`8px`)
  - Badges & Pills: `Theme.radius_sm` (`6px`)
  - Internal Card Padding: `20px–24px`
  - Field Vertical Gap: `12px`

---

## 5. Standardized Component Patterns (`modules/ui_components.py`)

Every screen must assemble its layout from these shared widgets rather than building custom one-off frames:

1. **`PageHeader`:** Left-aligned `24px` title + `13px` subtitle, paired with right-aligned cross-page shortcut buttons (secondary) and one `+ New ...` primary CTA button.
2. **Master List Pattern (`DataTable` + Filter Bar):**
   - Live search entry (`height = 38px`) + **Status Filter Pills defaulting to `Active`** (`Active` selected in `Theme.btn_primary`, `Inactive`, `All` in `Theme.btn_secondary`).
   - Contextual row action bar (`Edit`, `New Related Document`, `Make Inactive / Reactivate`).
   - `DataTable` (`rowheight = 36px`, uppercase `11px` headers, `#16233F` selection tint) paired with `Theme.create_scrollbar()`.
3. **Multi-Step Forms (`StepSection`):** Numbered circular blue badges (`1`, `2`, `3`) beside uppercase section headers, 2-column balanced field grids, uppercase `11px` field labels above `38px` inputs, and a pinned `SummaryBar` footer with progress indicators.
4. **Transaction & Billing Screens (`Banner` + Line Grid + `SummaryBar`):**
   - Top semantic `Banner` (`DRAFT`, `POSTED · LOCKED`, `VOID`, `IMPORTED · NEEDS REVIEW`, `AI SUGGESTED`).
   - Full-width line-item grid with inline auto-calculations (`Qty × Price`, `% ↔ $` linked inputs) and disabled `Post` button until balanced (`Difference == $0.00`).
   - Collapsible **GL Posting Impact Preview** above the sticky `SummaryBar`.
5. **Custom Dark Modals (`StrataModal`):**
   - Native `tkinter.messagebox` is banned. All alerts and confirmations use `show_info`, `show_success`, `show_warning`, `show_error` (with collapsible technical details), and `ask_confirm` (using `destructive=True` for irreversible/void/inactive actions).
6. **Slim Dark Scrollbars (`Theme.create_scrollbar` / `Theme.style_scrollable_frame`):**
   - Every scrollable frame and table uses an `8px`-wide, `4px`-radius scrollbar (`#090D16` track, `#2A3446` thumb, `#3B82F6` hover).

---

## 6. Interaction & UX Guardrails

- **Cross-Page Shortcuts:** Every list and detail screen exposes direct buttons to its immediate next workflows (e.g., Customer List -> `+ New Customer`, `Import CSV`, `New Invoice`, `Make Inactive`; Project -> `+ New Pay App`, `Change Order`, `Enter Bill`).
- **All 5 UI States Required:** Every view must cleanly handle **Empty** (`EmptyState` with CTA), **Loading**, **Editable** (inline field errors), **Locked** (`Banner` + read-only fields + `Reverse`/`Void`), and **Error** (`show_error` modal).
- **Keyboard Ergonomics:** `Tab` navigates fields in logical left-to-right, top-to-bottom order; `Enter` submits modals/chat (`Shift+Enter` for newline); `Esc` dismisses open modals.
- **No Emoji Clutter:** Rely on crisp `Inter` labels, semantic badges, and minimal geometric glyphs (`▸`, `▾`, `+`, `↑`, `●`) rather than multi-colored emojis.
