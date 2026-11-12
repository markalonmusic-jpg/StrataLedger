# StrataLedger UI design principles (docs/CLAUDE_UI.md)

Read this before creating or changing any view in `modules/`. It applies to
every screen. The root CLAUDE.md still governs: if this file and the root
CLAUDE.md disagree, the root CLAUDE.md wins.

Source: three mockups (Command Center, Customer Intake Form, New Transaction
Posting). The mockups are the VISUAL DIRECTION only. They contain mock data
and a few patterns that break our accounting rules; section 11 lists what NOT
to copy. Where a mockup and an accounting rule conflict, the rule wins.

---

## 1. Rules that apply to every view

1. One view = one file. A view builds widgets and calls service functions. It
   contains NO SQL and NO business rules.
2. Views never import `sqlite3`. All data comes from service functions and
   read-only query functions. All writes go through the service layer.
3. No hardcoded colors, fonts, sizes or paddings in a view. Use `config.Theme`.
   Read `config.py` first and extend `Theme`; do not create a second theme.
4. No hardcoded numbers or text standing in for data. No mock KPIs, names or
   alerts in a shipped screen. A screen with no data shows an empty state.
5. No `print()` for errors. Services raise typed exceptions; the view catches
   them and shows a dialog (section 8). Never navigate away after a failed save.
6. Money is always shown formatted (`$1,500.00`), never as raw cents. Input is
   parsed with `Decimal` and converted to integer cents by one shared helper.
7. Dates follow the company date format (`company_settings.date_format`) for
   display and entry; storage is strict ISO. Use the shared formatter.
8. Long operations never block the UI thread.
9. Anything the AI Copilot suggests is shown as a suggestion that a person must
   accept. The UI never labels an AI action as done unless a person approved it.

---

## 2. Application shell

Three columns plus a top bar:
- **Left sidebar (fixed width):**
  - Logo and app name ("StrataLedger") at the top.
  - A user card: avatar or initials, username, role.
  - Grouped navigation with small uppercase group labels. Groups follow the
    modules, for example: MAIN, CUSTOMERS (CRM), REVENUE (billing, payments),
    OPERATIONS AND COST (bills, payroll, inventory, assets, loans), PROJECTS,
    ACCOUNTING (ledger, periods, reports), IMPORTS AND TOOLS, SETTINGS.
  - The active item is highlighted (accent text on a tinted background).
  - Items a role cannot use are hidden. Add-on items (for example Philippines
    tax) appear only when that add-on is enabled for the open company.
  - A "Toggle assistant" control at the bottom.
- **Top bar:** breadcrumb (PLATFORM > section > page) with the current page in
  the accent color; on the right a search box, notifications and settings.
  Show the open company name and the date format/currency context somewhere
  persistent (top bar or user card).
- **Center:** the page. Content is centered with a maximum width on forms; data
  tables and dashboards use the full width.
- **Right drawer (AI Copilot):** fixed width, collapsible (section 6).

When no company is open, show the "No Company Open" launcher, not the shell.

---

## 3. Visual language

Dark theme by default; a light theme is a planned option (PROPOSED), so every
color is a token, never a literal. Approximate values from the mockups; put the
exact ones in `Theme` once:

| Token | Approx. value | Use |
|---|---|---|
| bg_app | #0B0F19 | window background |
| bg_panel | #111827 | sidebar, drawer, top bar |
| bg_card | #151B2B | cards and form sections |
| border | #1F2937 | card and input borders |
| text_primary | #F3F4F6 | headings, values |
| text_secondary | #9CA3AF | labels, captions |
| accent | #2563EB | primary buttons, active nav, links |
| success | #22C55E | won, posted, paid |
| warning | #F59E0B | stalled, due soon, needs review |
| danger | #EF4444 | errors, void, overdue |
| neutral | #6B7280 | draft, inactive (decoration only, never for text) |

- **Typography:** one sans family. Page title large and bold; section titles
  small, bold, uppercase, letter-spaced, accent colored; field labels small
  uppercase in `text_secondary`; values in `text_primary`. Numbers in tables
  use a monospaced or tabular style and align right.
- **Shape:** rounded corners on cards, inputs and buttons (consistent radius from
  `Theme`), 1 px borders, generous padding. No heavy shadows.
- **Status is never color alone.** Every colored status also has a text label
  or icon (INBOUND LEAD, STALLED, CLOSED-WON, DRAFT, POSTED, VOID).
- **Status colors are semantic:** blue = info or primary, green = success,
  amber = warning, red = error or void, gray = draft or inactive.

---

## 4. Components

- **Quick-action card:** icon in a tinted square, bold title, one-line
  description; the whole card is clickable and keyboard-focusable.
- **KPI card:** small uppercase label, large value, one line of context (for
  example "weighted value" or "vs target"). Values come from queries. Show a
  delta with an arrow and a color plus text (+12%).
- **Alert row (activity feed):** a colored tag, a source label, relative time,
  one sentence. Each row opens the record it refers to.
- **Numbered step section (forms):** a section card with a numbered square (1, 2,
  3) and an uppercase title. Group fields by meaning. The footer shows progress.
- **Segmented control:** for a small fixed set (entity type, contract type).
  Options come from the database list, not literals.
- **Inputs:** uppercase small label above; placeholder text is an example, not a
  value; error text appears under the field in `danger`.
- **Data table:** header row in `text_secondary` uppercase; zebra or divider
  lines; right-aligned numbers; sticky header; keyboard row navigation; the
  row count and totals shown.
- **Buttons:** one primary per screen (accent, uppercase label). Secondary is a
  bordered or text button. Destructive actions are red and ask for
  confirmation. Cancel is always available.
- **Summary bar (bottom of a transaction screen):** shows the impact of the
  action (section 5.3) with Cancel and the primary button.
- **Banners:** a thin colored banner under the title for state: DRAFT, POSTED
  (LOCKED), VOID, IMPORTED (NEEDS REVIEW).

---

## 5. Screen patterns

### 5.1 Dashboard (Command Center)
- Title and one-line description; "real-time" indicators only if data really
  refreshes.
- Quick actions row, KPI row, alert feed.
- The default dashboard is built for construction: open jobs by stage, WIP and
  over/under billing, AR and AP aging, cash, approvals waiting, period status.
  SaaS metrics (ARR, MRR) appear only for companies that have subscriptions.
- Every KPI and alert is a link to its detail.

### 5.2 Intake and edit forms (Customer Intake)
- Numbered sections, "Draft save" and a primary "Complete" button in a footer
  with a progress indicator.
- The customer code is shown read-only ("Assigned on save"); never editable.
- Entity types and other lists come from the database.
- Run the duplicate check (name, tax id, email) before creating, and show
  matches in the form.
- Validation runs per section and on submit; errors appear inline; the first
  error receives focus.
- Money fields show formatted amounts and accept typed amounts with a currency
  symbol or separators; they never ask the user for cents.

### 5.3 Transaction entry (Invoice, Bill, Credit Memo, Journal Entry)
- Header fields in a two-column grid: type, contact, project/job, terms, date.
- The reference field shows "Assigned on posting" for sales documents (numbers
  come from the numbering series at post, never at Draft). Vendor bill numbers
  are typed by the user.
- The contact picker offers only contacts that can be used (a customer needs a
  customer code; a vendor needs a vendor code). A missing contact opens the
  duplicate-checked create flow.
- Line items table with an "Add row" action and keyboard entry (Tab moves
  across, Enter on the last cell adds a row). Columns: account, project, cost
  code or item, dimension values, description, quantity, unit price, amount.
  Control accounts are not offered.
- The summary bar shows subtotal, tax, total and, for journal entries, total
  debits, total credits and the DIFFERENCE. The primary "Post" button is
  disabled until the entry is valid (balanced, open period, valid accounts).
- A "Posting impact" preview lists the accounts that will be debited and
  credited before posting.
- Actions: Save draft, Post, Cancel. Posting is a person's explicit action and
  asks for confirmation if the setting requires it. After posting, the screen
  becomes read-only with a POSTED banner and the entry number; corrections use
  Reverse or Void, which open their own flow.
- Entries made by an import or the AI show an IMPORTED or SUGGESTED banner until
  a person approves.

### 5.4 Lists and registers
- Live search and filters at the top, sortable columns, paging or virtual
  scrolling for large tables, a row action menu, and a count.
- Inactive records are hidden by default and shown with a toggle. Records with
  history are never deleted from the UI, only made inactive.

### 5.5 Imports
- The CSV import page follows docs/csv_import_design.md (five steps, preview
  grid, error list, all-or-nothing commit).

---

## 6. AI Copilot drawer

- Header: "Strata AI Assistant" and a status (Ready, Working, Offline).
- A status card at the top shows which company is connected.
- Messages: the assistant's messages are plain bubbles; the user's are accent
  bubbles. Highlighted terms (a job name, a probability) are links to records.
- Input area: multi-line box, Send (Enter) and a new line (Shift+Enter), an
  "Attach CSV" button and an optional microphone button.
- The send button says "Send", never "Execute". The assistant only proposes.
  Proposals appear as cards with the proposed values and two buttons: "Review
  and apply" (opens the real screen, pre-filled, for a person to confirm) and
  "Dismiss".
- Any value the assistant pre-fills in a form is marked "Suggested" and stays
  editable. A person must save or post.
- Claims such as a win probability or a discount recommendation must show their
  basis (the data used) or be labeled an estimate. Do not invent numbers.
- Sending financial data to the AI provider requires the explicit opt-in setting;
  when it is off, the drawer says so and works only with local tools.
- "Attach CSV" opens the import page with a preview; the assistant never commits
  a batch.
- Everything the assistant does is recorded with `origin = 'Agent'`.

---

## 7. Money, dates and numbers

- Money: company base currency symbol, thousands separators from the company
  number format, two decimals, right-aligned. Negative amounts show a minus sign
  or parentheses consistently (one choice in `Theme`/settings) and also use
  `danger` color only where appropriate.
- Totals and balances never use floats; use integer cents and the shared
  formatter.
- Dates: company date format everywhere. Typed dates are parsed with that
  format (ISO also accepted); an ambiguous or invalid date is an error.
- Percentages and quantities show only the precision they need.

---

## 8. States and feedback

- **Empty state:** an icon, one sentence, and the action that fills it ("No
  customers yet. Create the first one.").
- **Loading:** skeleton rows or a spinner; the UI stays responsive.
- **Validation error:** inline under the field plus a summary at the top for
  long forms.
- **Service or database error:** a dialog with a plain-language message and, in
  a details section, the technical text. The error is also written to the log
  file. No silent failure and no `print()`.
- **Locked data:** read-only fields, a banner saying why, and the allowed next
  action (Reverse, Void, New service case).
- **Success:** a brief confirmation (toast) that names what happened and links to
  the record.
- **Destructive or irreversible actions** (post, void, close period, close job,
  reopen period): confirmation with a summary of the effect; reopen and void
  ask for a reason that is logged.

---

## 9. Accessibility and keyboard

- Text contrast of at least 4.5:1 against its background. Labels use
  `text_secondary`, never the dim neutral color. The mockups' faint labels fail
  this; do not copy them.
- Minimum text size is set in `Theme` (PROPOSED 11 pt for labels, 12 pt for
  values). Do not go below it for decoration.
- Everything reachable and operable by keyboard; visible focus ring; logical Tab
  order; Enter submits the focused form section; Escape closes dialogs.
- Shortcuts (PROPOSED): Ctrl+S save draft, Ctrl+Enter post, Ctrl+N new row or
  record, Ctrl+F search, Ctrl+K command palette (later).
- Status uses text and icons as well as color.

---

## 9A. Roles and visibility

- Hide navigation and buttons a role cannot use, and also enforce the rule in the
  service layer; the UI is never the only guard.
- A Viewer sees data and reports with no create, edit or post controls.
- Approval actions (approve batch, post agent entries, approve manual entries)
  show who approved and when.

---

## 10. CustomTkinter implementation notes

- The mockups were drawn for the web: glow effects, blur, gradients and
  semi-transparent layers are NOT available. Approximate them with flat tinted
  fills, borders and the `Theme` tokens. Do not add image assets for effects.
- Build screens from small reusable widgets kept in one shared file
  (`modules/ui_components.py`, PROPOSED): StepSection, KpiCard, AlertRow,
  QuickActionCard, DataTable, MoneyEntry, DateEntry, SegmentedControl,
  SummaryBar, Banner, ConfirmDialog, ErrorDialog, EmptyState. A view assembles
  them; it does not restyle them.
- Destroy or reuse widgets when navigating; do not leak frames or bindings.
- Run queries and imports off the UI thread; update widgets only on the UI
  thread.
- Window sizing: the layout must work from a 1280 x 720 window to large
  screens; the right drawer collapses first on narrow windows.
- No external fonts or assets that need the network. The desktop version works
  offline.

---

## 11. Do NOT copy from the mockups

1. Mock data: "142 clients", "$142,500", "$685,000", "Acme Corp", "Highway 101
   Expansion", "Mark Aglugub", the "65% probability" message.
2. The prefilled "INV-2026-001" reference: sales numbers are assigned at
   posting.
3. A raw cents field ("MRR value (cents): 150000"): always formatted money.
4. "Execute Instruction" on the AI input: the assistant proposes; use Send.
5. Faint, low-contrast labels and very small text.
6. A hardcoded SaaS-first dashboard: the default is construction (jobs, WIP,
   billing, aging).
7. Entity type values (LLC / Corp / LLP): use the live `contact.entity_type`
   list.
8. "Consolidated Balance" as the only figure: show totals and, for journal
   entries, debits, credits and the difference.
9. The "Contract type" fork as a hard split of customers: customers move through
   one lifecycle (see docs/crm_pm_design.md); a customer can have jobs and
   subscriptions.
10. Any control that lets a person type a customer code, an invoice number for a
    sales document, or a period id.

---

## 12. Checklist before a screen is done

- [ ] No SQL, no `sqlite3`, no business rules in the view; services only.
- [ ] Colors, fonts and spacing come from `Theme`.
- [ ] Money, dates and numbers use the shared formatters and company settings.
- [ ] Empty, loading, error, locked and success states exist.
- [ ] Errors show a dialog and are logged; nothing is swallowed or printed.
- [ ] Contrast, focus order, keyboard use and text-plus-color status verified.
- [ ] Hidden or disabled for roles that cannot use it; enforced in the service.
- [ ] Works with the Copilot drawer open and closed, at 1280 x 720.
- [ ] Tests exist for the service functions the screen calls; the view has a
      smoke test (builds and tears down without errors).
- [ ] Screenshots of the screen in the dark theme added to docs/ui/ (PROPOSED).
