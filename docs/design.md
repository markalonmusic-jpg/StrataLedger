# StrataLedger system and product design

Status: owner rulings of 2026-11-15, recorded here as the authoritative system and product design. CLAUDE.md
holds the rules; this file holds the design they point to. What is BUILT is in the baseline
(`migrations/001_company.sql`, `001_master.sql`) and the services; everything marked PLANNED is target design
and is not in the baseline yet. Where this file and the baseline differ, the baseline describes the code as it
is (CLAUDE.md section 5.3); section 10 lists the differences the consolidated pre-release baseline update
closes. Screen rules stay in docs/CLAUDE_UI.md. The CustomTkinter visual spec that this file used to hold is
archived as archive/design_drafts_2026-11/visual_spec_customtkinter.md.

Decision codes: AQ1 and AQ2 (architecture, indexed in docs/decisions_2026-11-11.md). Earlier decisions that
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

Open (section 11): how the bridge authenticates the page (a per-launch token), and how `config.Theme` (H6)
becomes the front end's CSS tokens.

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

- **Cost codes, 3 levels** (PLANNED). Level names and which level a line posts to are decided with the
  baseline update (section 11).
- **Dimensions, unlimited depth** (PLANNED). Dimension values nest under parents; JD1 (a line's job sets its
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

## 10. Baseline today versus this design

The consolidated pre-release baseline update (docs/roadmap.md, docs/next_step.md) adds these, with failing tests
first, in one edit of `001_company.sql` and `001_master.sql` and one rebuild:

| Design | Baseline today |
|---|---|
| `company_entity`, `journal_line.entity_id`, intercompany and elimination support | Not there; one company per file |
| `journal_line.clearing_id`, open-item account marker | Not there; `journal_line.recon_id` only |
| Document versions for reverse-and-repost; `Lock documents after posting` setting | Not there |
| `bank_statement_line` and match records | Not there (already a Phase 4 gap) |
| Pay run tables; `In pay run` status; `contact.bank_payee_id` | Not there (`invoice.status` has no pay-run state) |
| Service types, their stages and triggers | Not there; `pipeline_stage` exists (D7) |
| Estimate signing with the signed PDF | Not there |
| 3-level cost codes | `cost_code` is flat (`code`, `name`, `cost_type_label`, `account_id`) |
| Unlimited-depth dimensions | `dimension_value.parent_value_id` exists, capped at `database.MAX_DIMENSION_DEPTH = 3` (tested in tests/test_database.py) |
| Step 7 `payment_allocation` columns (`applied_date`, `credit_memo_id`, who and when) | Planned in docs/next_step.md |

## 11. Open questions for the owner

1. **B9 vs `bank_payee_id`.** B9 promises a NACHA ACH export, which needs the payee's routing and account
   numbers. This design stores none. Does the bank upload replace NACHA (B9 amended), or does NACHA stay as a
   later option with its own stored numbers?
2. **`clearing_id` and the chain.** Posted lines are append-only and sealed, but clearing happens after the
   cleared line posted. Is the id fixed at posting (the clearing entry's lines carry it and name the open item
   they settle) or kept in a separate append-only clearing record that the chain also seals? This decides the
   column's shape in the baseline update.
3. **Dimension depth.** Unlimited depth means removing the cap of 3 and its tests, or keeping a high safety cap
   (for example 10) for the recursive checks?
4. **Service types and `pipeline_stage`.** Do service type stages replace `pipeline_stage` (D7's
   `allows_costs` / `allows_billing` carried over), or sit beside it?
5. **Bridge security and theme tokens** (section 1).
6. **Pay Run** answers next_step open question 2 (multi-vendor Pay Run) if the owner confirms.
7. **Cost code levels.** The names of the three levels, and whether lines may post to any level or only the
   lowest. Today `cost_code` is flat.
