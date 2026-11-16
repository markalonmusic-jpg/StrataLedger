# StrataLedger system and product design

Status: owner rulings of 2026-11-15, recorded here as the authoritative system and product design. CLAUDE.md
holds the rules; this file holds the design they point to. What is BUILT is in the baseline
(`migrations/001_company.sql`, `001_master.sql`) and the services; everything marked PLANNED is target design
and is not in the baseline yet. Where this file and the baseline differ, the baseline describes the code as it
is (CLAUDE.md section 5.3); section 10 lists the differences the consolidated pre-release baseline update
closes. Screen rules stay in docs/CLAUDE_UI.md. The CustomTkinter visual spec that this file used to hold is
archived as archive/design_drafts_2026-11/visual_spec_customtkinter.md.

Decision codes: AQ1 and AQ2 (architecture) and RP1-RP11 (resolutions, 2026-11-16), indexed in
docs/decisions_2026-11-11.md. Earlier decisions that
these rulings amend are named where they apply.

---

## 1. Architecture (AQ1, AQ2)

**AQ1. Data tier.** The desktop edition is a single-machine app on SQLite: one master file and one file per
standalone company (section 2), in `config.DATA_DIR`. The hosted edition runs on Azure with PostgreSQL. The
same services run on both, which is why rule 15 (H1-H6) exists: no UI or OS imports in services, the clock and
"today" from the context, files through `storage.py`, workflow rules in services rather than new triggers, and
portable SQL. Moving a desktop company to the cloud follows CM1-CM3.

**AQ2. Front end.** The UI moves from CustomTkinter to one HTML/CSS/JS front end used by both editions:
- Desktop: `pywebview` hosts the page in a native window (WebView2 on Windows). A local Python API bridge
  listens on `127.0.0.1` only and calls the services with a `ServiceContext` built for the signed-in user.
- Hosted: the same front end is served to the browser; the hosted API calls the same services.
- `modules/services/*` never import UI or HTTP framework modules. The bridge (or the hosted API) catches the
  typed exceptions from `errors.py` and turns them into responses the page shows as one plain sentence
  (rules 5 and 12; R27 wording).
- Permissions stay in `authorize` (rule 10); the page only hides what the user cannot do.
- Until a screen is rebuilt, the existing CustomTkinter screens keep working. CLAUDE_UI.md and section 0b
  govern every screen in either technology.

Decided (RP6): `app_strata.pyw` makes a per-process token (`secrets.token_urlsafe(32)`, never logged or saved)
and passes it to `pywebview`; the endpoints check `X-Strata-Token` in constant time and build a fresh
`action_context()` per change. `config.Theme` serves the CSS custom properties.
Token handling when the bridge is built:
- the token reaches the page through pywebview's `js_api` / `evaluate_js`, never in a URL, argv or an
  environment variable;
- the bridge logs no headers or query strings, and its access log is off or path-only;
- errors never echo request headers;
- WebView2 devtools are off in a release build (`debug=False`);
- the token is held in a redacted-repr wrapper like `keys.SecretKey`, and a test proves it never reaches the
  log file.

## 2. Databases and entities

- `system_master.db`: users, the company registry, access. Never company accounting tables (rule 3).
- One SQLite file per standalone company (BUILT; `company_registry.parent_company_id` already links a
  subsidiary to its parent).
- PLANNED: a parent's subsidiaries may instead live as entities inside the parent's file, for consolidated
  reporting:
  - `company_entity` (one row per legal entity in the file; the parent is an entity too);
  - `journal_line.entity_id` (every line belongs to exactly one entity; a balanced entry balances per entity,
    or posts through intercompany accounts);
  - intercompany due-to / due-from accounts, and elimination entries for consolidated reports.
- A company chooses separate files or entities-in-file per subsidiary. Consolidation across separate files is
  a report over several files; inside one file it is a report over entities.

## 3. Ledger: append-only lines, clearing and open items

- Posted `journal_line` rows are append-only: never updated, never deleted (integrity, section 0). Posted
  entries are sealed into the keyed hash chain (BUILT, audit readiness design section 2).
- PLANNED: a line-level `clearing_id` groups the lines that settle each other (an invoice's AR line with the
  payment lines applied to it, a bill's AP line with its payments, a GRNI receipt with its bill). The chain
  covers `clearing_id`, so a clearing cannot be changed silently.
- PLANNED: per-account open-item tracking. An account marked open-item (AR, AP, GRNI, clearing and
  undeposited accounts) shows each uncleared line or group with its open amount; a group is cleared when its
  lines net to zero.
- Payment allocation (Step 7, `payment_allocation`) is the subledger link between payments, credit memos and
  documents; clearing is its ledger-side mirror.

## 4. Posted documents versus posted journal entries

- **Journal entries** are strictly reverse-only. A posted entry is corrected with `Reverse…` (BUILT in Step 5:
  `void_entry`, `reverse_entry`, a reason and a confirm), never edited.
- **Documents** (invoice, credit memo, bill, vendor credit), PLANNED. While the control
  `Lock documents after posting` is OFF (the default, section 0), a posted document can be edited:
  - Saving the edit runs one atomic reverse-and-repost: the document's current entry is reversed and a new
    entry posts under the same document number, in one write transaction. No `journal_line` row changes.
  - Every save keeps a version (who, when, what changed); the document shows its version history and each
    version links to its entries.
  - Refused, with a one-sentence reason, when the period or area is locked (closed period, books closed
    through, year closed), when the new total is below the amount already paid or applied, or when the
    document sits in a submitted pay app or a pay run.
  - The repost passes the same checks as a first post (approvals when on, controlled accounts, the chain).
  - With the control ON, a posted document is changed only by a void or a credit memo / vendor credit.
- Gapless registered series (Philippines add-on) keep the same number; the edit never consumes a new one.
- This amends decision section 0 "Posted records are locked; corrections are reversals or new documents" for
  documents only.

## 5. Bank: one staging table and tick-off reconciliation

- PLANNED: one `bank_statement_line` table stages every bank and card line, from CSV / OFX / QFX files (B11)
  and from feeds (B11a, BF1). A line is matched to payments, deposits or transfers, or creates one on match
  (an Import-origin record, so a person reviews it, R18/R55).
- Reconciliation is QBO-style: pick the account and statement ending balance and date, tick cleared items, and
  finish when `Difference = $0.00`. A match can be opened and edited in place (change the matched items,
  unmatch) without leaving the screen.
- BUILT today: `bank_reconciliation` and `journal_line.recon_id`, with a completed reconciliation locked;
  B10 allows undoing only the latest. The 2026-11-14 payments message adds `date_cleared` and reopen-with-reason
  for Phase 4 (docs/next_step.md).

## 6. Payables: two-step Pay Run and bank upload

- PLANNED: a Pay Run selects approved bills (B8: approved when approval is on, off compliance hold) across
  vendors.
  1. **Approve the run.** Each bill on it is locked with the status `In pay run`: it cannot be edited (section
     4). Nothing posts.
  2. **Complete each line.** When a line is paid, the user enters `date_paid` and the payment reference; that
     line posts its payment then.
- Vendors carry a `bank_payee_id`: the payee's identifier as registered in the company's online banking. No
  bank routing or account numbers are stored. A run exports a bank upload file listing `bank_payee_id`, amount
  and reference for the lines being paid.
- `date_paid` is the UI word; the baseline column is `payment.payment_date` (rename only if the owner asks).

## 7. Sales and delivery: Service types and Estimate = Contract

- PLANNED: **Service types.** Each service type (for example Remodel, Maintenance contract, SaaS onboarding)
  defines its own sales stages and delivery stages, customizable per company, and automation triggers written
  as `When <event> then <action>` (for example "When the estimate is signed, then create the job and its
  budget"). Triggers run in services (H4, not SQL triggers) and are idempotent: an event handled twice does
  the action once. The AI never fires money actions (section 0).
- PLANNED: **Estimate = Contract.** The estimate is the contract; there is no separate contract record to keep
  in step. A two-pane guided editor (the document on one side, guided steps and checks on the other) builds
  it. Signing it requires uploading the signed PDF; signing locks the signed revision and creates the budget
  and SOV (D9). Estimate Approval follows 1.6 and D9: OFF by default; when on, the Estimate approval chain
  applies before signing.

## 8. Construction and costing

- **Cost codes, 3 levels** (RP5): 1 Division (not postable), 2 Code, 3 Sub-code; postings go to active leaf
  codes (level 2, or level 3 with no active children).
- **Dimensions, depth up to 10** (RP3). Dimension values nest under parents; JD1 (a line's job sets its
  dimensions) is unchanged.
- **Receiving: Direct-to-site vs. Stock** (PLANNED; accounting in docs/po_ap_matching_design.md section 4).
  Stock: Dr Inventory / Cr GRNI at receipt, the job costed later at the pull ticket. Direct-to-site: a
  delivery ticket charges the job at receipt against GRNI. The bill clears GRNI (A5; section 3 open items).
- **Pay applications, Owner and Sub** (PLANNED, v1.1). Owner pay apps bill the customer against the SOV, with
  retainage receivable; Sub pay apps are the subcontractor's applications against a subcontract, with
  retainage payable. A document in a submitted pay app cannot be edited (section 4). Earlier draft:
  archive/design_drafts_2026-11/pay_applications_design.md.

## 9. Controls these rulings add (section 0)

| Control | Default |
|---|---|
| `Lock documents after posting` | OFF |
| Estimate Approval (with every other per-document approval toggle) | OFF |

Each is listed on Company Settings > Controls and every change is audit-logged.

## 10. The consolidated baseline update (STOP 1, 2026-11-16)

One edit of `001_company.sql` and `001_master.sql` with failing tests first (tests/test_schema_replan.py) and one
rebuild; the previous baselines are in archive/baseline_pre_replan/ (tag `baseline-pre-replan`). Services do
not use the new columns yet; STOP 2 (Step 7) and later steps do.

| Design | In the baseline after STOP 1 |
|---|---|
| Entities in one file | `company_entity`; `journal_line.entity_id` (NULL = the file's own company) |
| Clearing and open items (RP2) | `journal_line.clearing_id`, frozen after posting and sealed; `account.track_clearing_id` |
| Editable posted documents | `invoice.revision_no`, `supersedes_id`; `company_settings.lock_documents_after_posting` (0) |
| Period and area locks | `fiscal_period_lock` (period, area) |
| Bank staging and matching | `bank_statement_line`, `bank_statement_match` (released, never deleted) |
| Pay Run (section 6, RP1) | `pay_run`, `pay_run_line`; `invoice.status` 'In pay run'; `contact.bank_payee_id`, `bank_details_on_file` |
| Service types (RP4) | `service_type`, `service_stage`, `stage_trigger`, `stage_trigger_run`; `project.service_type_id`, `service_stage_id` |
| Cost codes (RP5) | `cost_code.level` 1-3, `parent_id`, `is_active` |
| Dimensions (RP3) | depth limit 10 |
| Step 7 allocations (RP11) | `payment_allocation.applied_date`, `credit_memo_id`, who and when, one-time release |
| Contacts, documents, terms, custom fields, close tasks, list preferences | `contact` columns and `contact_site`; `invoice.voucher_number`, `sent_at`, `void_reason`, `is_opening`; `payment_term`; `custom_field_def`/`value`; `close_task`, `close_task_dependency`; `user_list_pref`, `saved_view`, `alert_dismissal` |
| Multi-role (RP10) | master `user_company_role`, schema only |
| Approvals (RP9) | `document_approval_setting` covers every document type, all OFF |
| Not in STOP 1 | Estimate signing with the signed PDF (with the estimate step); intercompany and elimination entries (with consolidation reports) |

## 11. Questions resolved (owner, 2026-11-16)

1. B9 vs `bank_payee_id`: the payee-ID upload replaces NACHA in v1.0 (RP1).
2. `clearing_id` and the chain: set at save or post on both sides, sealed; open items by group (RP2).
3. Dimension depth: a limit of 10 (RP3).
4. Service types replace `pipeline_stage` (RP4).
5. Bridge security and theme tokens: per-process token, `X-Strata-Token`, `config.Theme` as CSS properties (RP6).
6. Pay Run: multi-vendor, two steps (section 6), recorded with RP1.
7. Cost code levels: Division, Code, Sub-code; postings to active leaf codes (RP5).
