# AI Copilot: connectivity, safety and skills (design draft)

Status: DESIGN ONLY. NOT BUILT. Items marked PROPOSED are not decided.
This revises the submitted "Strata AI Copilot" specification so it fits the
rest of the design (staging, controls, roles, add-ons, UI guide). The changes
are listed in section 10.

Conventions follow CLAUDE.md. The agent only proposes. It never posts, approves,
voids, closes a period or runs raw SQL. A person always saves or posts.

---

## 1. Providers and authentication

**v1 provider: Google Gemini API.** The customer creates their own API key in
Google AI Studio (or Google Cloud) and pays Google for their own usage per
token. A consumer subscription (for example Google AI Pro) is a separate
product and does not provide API access.

**Provider-neutral design.** The product talks to a small internal interface
(send messages with tool definitions, get back text or tool calls, report
token usage, list models, test connection). Gemini is the first adapter.
Other adapters (Claude through the Claude Console API key, a cloud provider, a
local model) can be added later without touching skills, screens or rules.
No skill or screen may import a provider SDK directly; only the adapter does.

**Rules that apply to every provider:**
- Customer-owned API key only. The product never pays for or proxies AI usage
  (that would need a commercial agreement with the provider; not designed).
- No consumer-account logins or tokens. Claude.ai login is not permitted for
  third-party apps by Anthropic's terms
  (https://code.claude.com/docs/en/legal-and-compliance), so the earlier
  "Sign in with Claude" mode stays removed. Do the equivalent check against
  Google's terms before adding any non-key sign-in.
- Re-read the provider's current terms and data-use rules before release.
  PROPOSED: record the terms version reviewed in this document.

**Gemini free tier warning (important for financial data).** As understood
from Google's Gemini API terms
(https://ai.google.dev/gemini-api/terms_preview), content sent on the free
tier may be used to improve Google's products, while paid usage is handled
differently. Verify the current wording. Because the app cannot reliably tell
which tier a key is on:
- The data-sharing screen shows this warning in plain words.
- The opt-in for sending company data requires the Admin to confirm the key is
  on a paid tier / billing-enabled project, and logs the confirmation.
- Without that confirmation only non-company content (column headers, sample
  CSV files) may be sent. PROPOSED.

Rate limits and prices change often. They are never hardcoded; the screen
links to the provider's current pages.

Answers open decision 6 in CLAUDE.md for the desktop version: customers bring
their own key.

---

## 2. Safety rules

1. **Read-only plus proposals.** The agent's own database connection is
   read-only (it can never run a write). It reads role-filtered views and
   service read methods. The only writes in an agent run are the staged rows in
   rule 2, and those are made by a write SERVICE function (which owns its own
   transaction and sets `origin = 'Agent'`, the run id and the human user id in
   `audit_context`). The agent code never holds a write connection. It never calls
   posting, approval, void, reversal, period-close or reopen functions, and it
   is not given them.
2. **Two kinds of proposals (decided here):**
   - *Single-record proposals* (an invoice, a journal entry, an estimate, a
     change order, a return slip, a loan setup, a fixed asset): the agent
     returns structured data and the UI opens the real screen PRE-FILLED and
     UNSAVED, marked "Suggested". Nothing is written until a person saves.
   - *Bulk or queue items* (receipts, CSV batches, staging coding): the agent
     writes staged rows through service functions with `origin = 'Agent'`, each
     with an `agent_suggestion` row (confidence, rationale, rule citations,
     agent version, status) and a run id. They appear in an "Agent proposals"
     queue, separate from human drafts. A person approves.
3. **Untrusted content.** Text from receipts, PDFs, CSVs, vendor names and emails
   is DATA, never instructions. Document text must not be able to trigger tool
   calls on other records. Tool calls in a run are limited to an allow-list for
   that task, with a step limit. No tool sends email, browses the web or writes
   files. The UI shows the source (file, row) behind every suggested value.
4. **Privacy and consent.**
   - A master setting "Allow sending company data to the AI provider" is OFF by
     default and needs an Admin or Master to turn on, with a logged
     acknowledgement. When off, no company data leaves the machine and the
     Copilot works with local tools only.
   - Data minimization: send only the fields a task needs. Never send `.db`
     files, password hashes, API keys, bank account numbers or full tax
     identifiers; the redaction list is configurable (PROPOSED defaults: TIN,
     bank and card numbers, passwords, keys).
   - Per-feature toggles (receipt reading, CSV staging, require rule citations).
   - **Images and PDFs cannot be field-redacted.** A receipt sent as an image
     or file carries whatever is printed on it (tax IDs, card or bank details).
     PROPOSED: accept this for receipts only, behind its own toggle (OFF by
     default) and its own Admin acknowledgement. A later option is extracting
     text locally first and redacting before sending. CSV and structured data
     are always redacted by field.
5. **Roles.** The agent acts as the logged-in user. Tools and read views are
   filtered by that user's role: for example wages and payroll are visible only to
   roles that can see them. (Depends on the roles and permissions design.)
6. **Audit.** Every tool call and every proposal is logged with `origin =
   'Agent'`, the human `user_id`, the run id, the tool, an argument summary, row
   counts and the model. Whether full payloads are stored locally is a setting
   (PROPOSED default: no).
7. **Cost control.** Token usage from each response is stored in `ai_usage`
   (date, user, model, input and output tokens, estimated cost). A monthly cap is
   checked BEFORE a call. Prices are a configurable table, never hardcoded.

---

## 2A. Credentials

- The API key (any provider) lives only in the Windows Credential Manager (or the platform's
  secure store) through the `keyring` package, keyed by company. It is never
  written to `config.py`, any `.db`, logs or exports.
- The submitted idea of an "encrypted local fallback in system_master.db" is
  dropped: a key stored next to the data that protects it is only obfuscation.
  If no secure store is available, the key is entered per session and kept in
  memory only (PROPOSED), or encrypted with a user passphrase (scrypt-derived).
- Where the key lives (PROPOSED): in the secure store of the Windows user on
  that computer. It is NOT shared across users or machines. A user on another
  computer, or another Windows account, enters their own key (the screen shows
  "No key on this computer"). The hosted version stores it server-side per
  tenant instead.
- Set by an Admin or Master. The key is shown masked with Show/Hide while it is
  being entered, and never again after saving.
- Test Connection makes a minimal call and reports Connected, Invalid key or
  Offline.
- Model choice: the list is fetched from the provider's list-models call and
  the Admin picks a default. Model names are not hardcoded in the app.
  Only models that support tool (function) calling are offered. The list-models
  call may report generation methods rather than tool support, so the adapter
  keeps a small capability table and a startup test call (to be verified when
  the adapter is built).
- Hosted version: keys and usage are stored server-side per tenant.

---

## 2B. Where settings live (PROPOSED)

- Per company, in the company file (`company_settings`): the data-sharing
  opt-in and paid-tier confirmation, feature toggles, redaction list, monthly
  cap, and the `ai_usage` log.
- Per computer, outside any database: the API key (section 2A).
- `system_master.db` holds nothing AI-related in v1. An optional per-user cap can
  come later.

## 2C. Schema this needs (not in the committed migrations)

Migrations 003 and 004 are already committed and are NOT changed by this
design. Everything AI-related goes in a later, separate migration ("AI
support", numbered when it is created; PROPOSED 011, never renumbering the
others), added before the Phase 3 screens:
- Audit: `audit_log` exists (created in 001; the audit triggers from 003/004
  write to it). Add `origin` and `agent_run_id` to `audit_log`, and carry them
  in `audit_context` so the triggers can copy them. Confirm the exact column
  names and trigger changes from the live schema before writing the migration.
- `staged_transaction.origin` (confirmed missing).
- New tables: `agent_run`, `agent_suggestion` (confidence, rationale, rule
  citations, agent version, status), `ai_usage`, price table.
- AI keys in `company_settings` (opt-in, paid-tier confirmation, toggles,
  redaction list, monthly cap).
Because the fresh-start rebuild creates databases from migrations, a later
migration costs nothing extra.

---

## 3. Files (one view = one file)

- `modules/views_ai_settings.py`: the settings screen. No SQL, no secrets in
  widgets after save.
- AI services (location decided in the Phase 2 plan, next to other services):
  - credentials and connection service (keyring, key validation, health check),
  - provider adapter interface plus the Gemini adapter (the only code that
    imports a provider SDK or calls a provider endpoint),
  - orchestrator (tool loop, context builder, skill router, audit logging,
    spend cap),
  - `ai_skills/` skill packs, one file per domain.
- Skill packs register typed tools through a registry. Core skill packs never
  import an add-on. An add-on (for example Philippines tax) registers its own
  tools when it is enabled.

---

## 4. Settings screen

Reached from the Copilot header gear or SETTINGS > AI Connectivity (Admin and
Master only). Sections:
1. Provider: Gemini (v1). Other providers appear only when their adapter exists.
2. "How to get a key" help panel: (a) open Google AI Studio and sign in,
   (b) create an API key, (c) turn on billing for the project so usage is on the
   paid tier, (d) paste the key here. A line says a consumer subscription is
   not an API key. Link to the provider's pricing and limits pages.
3. Key entry, Test Connection, status badge, model selector.
4. Data sharing: the master opt-in, the free-tier warning and paid-tier
   confirmation, the redaction list, feature toggles.
5. Budget: monthly cap, usage this month by user, usage log.

Follows docs/CLAUDE_UI.md (theme tokens, states, no raw errors).

---

## 5. Tool design

- **Read tools** (`read_*`): call read-only views and service read methods.
  Row limits, role filtering, and result size caps; no free-form SQL.
- **Proposal tools** (`propose_*`): return structured data for a pre-filled
  screen, or stage rows with `agent_suggestion` records (section 2, rule 2).
  Names use `propose_`, not `draft_`, because a draft is a saved record.
- **Never provided:** post, approve, void, reverse, close or reopen a period,
  delete, change roles or settings, create users, create vendors or customers
  without the duplicate-checked flow.
- Contacts: the agent matches existing contacts and proposes; it never creates
  one silently.
- Each tool declares: inputs, outputs, tables read, roles allowed, whether it
  sends data off the machine.

---

## 6. Skill packs (each ships with its domain)

A skill pack is built only when its underlying service exists and is tested.

| Pack | Example tools | Needs |
|---|---|---|
| AR and billing | customer summary, AR aging, propose invoice, propose payment matches | billing service, v_ar_open_items |
| AP, Ramp and spend | AP aging, staging queue, propose bill from receipt, suggest staging coding | staging, policy rules, vendor service |
| General ledger and close | trial balance, account ledger, close readiness, propose journal entry, suggest bank matches | v_gl_detail, period service, banking design |
| CRM and contracts | pipeline summary, project health, propose estimate, propose change order | CRM design built |
| Pay applications | SOV status, propose pay application | pay application design (not done) |
| Inventory and assets | stock and advances, propose material cost report, propose return, propose fixed asset | inventory and asset designs built |
| Loans and deferrals | loan schedule, deferral schedule, propose loan from agreement | loans design built |
| CSV import | inspect and map a CSV, validate in memory | CSV import service |
| Audit and exceptions | exception scan, policy compliance check, tax summary | exception views, policy_rule |

"Propose a loan from an agreement" reads a PDF; the extracted terms are shown
with page references for a person to confirm.

---

## 7. Phase placement (PROPOSED)

Build the AI work as one stretch, after the core services it reads from exist.
Nothing in Phases 2-5 depends on it, and a settings screen with no working
Copilot behind it has no value.

- Schema: one "AI support" migration (section 2C). Its number is assigned when
  it is created, in build order. Before the first release, unreleased
  migrations may be renumbered freely, because databases are rebuilt from
  scratch; after release, never. If it is built after 010, it is 011.
- Phase 6, step 1: credentials and connection service, provider interface and
  Gemini adapter, `ai_usage`, data-sharing settings, `agent_suggestion`, the
  AI support migration.
- Phase 6, step 2: `modules/views_ai_settings.py`, the gear trigger, the
  "Agent proposals" queue screen, the Copilot drawer behavior from
  docs/CLAUDE_UI.md.
- Phase 6, step 3: the orchestrator, then each skill pack as its domain's
  service is built and tested (CRM pack with CRM, pay apps pack with pay apps,
  and so on).
- Until then the Copilot drawer is a visible placeholder and uses no network.

---

## 8. Tests required

- Skills and screens never import a provider SDK (static test); the adapter can
  be swapped for a fake in all other tests.
- The Gemini adapter maps tool definitions, tool calls and token usage to the
  internal interface (tested with recorded fixtures, no live calls in CI).
- The free-tier confirmation is required before company data is sent.
- The key never appears in config, any `.db`, logs, exports or error messages.
- With the opt-in OFF, no network call is attempted (tested with a blocked
  transport).
- Redaction removes listed fields before a request is built.
- The agent cannot reach posting, approval, void or close functions: skill
  modules may import only read and proposal functions (a static test fails the
  build otherwise).
- Proposals write nothing to the database; staged proposals write only through
  service functions with `origin = 'Agent'` and a run id.
- Injection fixtures: receipts and CSVs containing instructions do not cause
  extra tool calls or changes in the proposal.
- The step limit and the monthly cap stop a run; usage is recorded.
- Role filtering: a role without access to payroll gets no payroll data from any
  tool.
- Controlled accounts are never offered in a proposed journal entry.

---

## 9. Open questions

1. Will the hosted version let customers bring their own key, or will the
   product bill for AI? (The second needs a commercial agreement.)
2. Which second provider, if any: Claude (API key), a cloud provider, or a local
   model?
3. Store full AI payloads in the local audit trail, or summaries only
   (PROPOSED summaries)?
4. Default redaction list: confirm the PROPOSED defaults.
5. Zero data retention or a business associate agreement for any customers?
6. Is the monthly cap per company, per user, or both?

---

## 10. Changes from the submitted spec

0. Provider is Gemini API key (v1) behind a provider-neutral adapter; the
   submitted spec was Claude-only.
1. Removed the Claude account OAuth mode: Anthropic does not permit it for
   third-party apps.
2. Dropped the encrypted fallback in the database; OS secure store only.
3. Added the master data-sharing opt-in (default off), redaction, and data
   minimization.
4. Single-record proposals are pre-filled unsaved forms; only bulk items are
   staged, with `agent_suggestion` records and a separate Agent proposals queue.
   `draft_*` tools became `propose_*`.
5. Added the untrusted-content (prompt injection) rules and tool allow-lists.
6. Model names are fetched from the provider, not hardcoded; prices are a table.
7. Spend cap checked before each call, usage stored in `ai_usage`.
8. Skill packs ship with their domains; add-ons register their own tools.
9. Role filtering applies to every read tool.
10. Phase placement: orchestrator in Phase 6, skills spread over the phases.
