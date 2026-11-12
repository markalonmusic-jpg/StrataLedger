# Instructions: update CLAUDE.md for the CRM / project lifecycle design

Apply the edits below to CLAUDE.md. Change nothing else. Do not build
anything: this is documentation only, and the Phase 1 plan is unchanged.
Show me the diff before committing. Do NOT commit this instruction file.

Commit message: "Update CLAUDE.md: CRM and project lifecycle design"

---

## Edit 1: section 2 (directory and file structure)

Add this line next to the other docs/ entry:

- `docs/crm_pm_design.md` - design draft for the CRM, project lifecycle,
  service cases, customer/vendor codes and throughput tracking. NOT BUILT.
  Read it before touching anything in these areas.

---

## Edit 2: section 6 (design decisions already made)

Add a new subsection at the end of section 6:

**CRM and project lifecycle (summary; full design in docs/crm_pm_design.md)**
- Internal-use CRM and project tool. Desktop version has no subscription;
  a hosted version is planned. Same schema and service layer; one database
  per company in both.
- A lead is a project from day one: one `project` record moves through one
  list of stages (Sales, signing milestone, Delivery, Closeout, Closed).
  There is no separate opportunity table.
- Signing the contract runs one service function: confirm the customer,
  assign the customer code, assign the job number, create the contract and
  original budget.
- No costs before signing (stage flag `allows_costs`). Invoices only to
  contacts that have a customer code.
- Closed projects are LOCKED and never reopen. Lost leads can be reopened.
- Repairs after closing are new service cases (`project.kind = 'Service
  case'`, `parent_project_id` = the closed job) in a separate Customer
  Support pipeline. Warranty cost is charged to the case, never to the
  closed job.
- Stage history tables are append-only. Every stage move or block change
  writes history in the same transaction, through one service function.
- All timestamps (`_at` fields) are UTC ISO 8601 text. Throughput measures
  (time in stage, conversion, aging, sales velocity, planned vs actual) are
  views over the history tables, not stored fields.
- `comment`, `attachment` and `notification` point at records by
  (record_type, record_id) and are validated in the service layer. Every
  other relationship uses a real foreign key.
- Items marked PROPOSED in docs/crm_pm_design.md are not decided. Do not
  build them as final.

**Customer codes**
- Automatic only; no manual entry or editing.
- customer_code = first 2 letters of the customer name (uppercase, accents
  removed, skip a leading The/A/An, ignore digits and punctuation, pad with
  X) + seq, zero-padded to at least 4 digits (AC0001). The number may grow
  beyond 4 digits. Sort by seq, not by the code text.
- The number comes from the database: insert a row into customer_number
  (seq INTEGER PRIMARY KEY AUTOINCREMENT, contact_id UNIQUE) in the same
  transaction that sets the code, and use seq. Keep a unique index on
  customer_code as a second safeguard. Never compute the number with MAX+1.
- Assigned once, when a contact first becomes a customer: saving a new
  customer in the Create New Customer wizard, or signing a contract for a
  prospect. Both call the same service function. The UI never builds codes.
- Never changed and never reused. A customer with a code can only be made
  inactive, never deleted. A merged customer's code stays reserved.
- A contact with is_customer = 1 must have a customer_code (CHECK, added
  after the backfill).
- Run a duplicate check (name, tax_id, email) before creating a customer.
- Job number = customer_code + '-' + project_code, stored in
  project.project_number (AC0001-001). A service case's project_code is the
  parent job's project_code + '-S' + a 2-digit sequence (AC0001-001-S01).

**Vendor codes (PROPOSED: the V prefix is not confirmed yet)**
- Same method with a separate vendor_number sequence table.
- vendor_code = 'V' + 2-letter prefix + seq, 4+ digits (VAC0001). Customer
  codes never match this pattern, so the formats cannot collide.
- Assigned once, when a contact first becomes a vendor. Imports (Ramp, etc.)
  never create vendors directly: the staging approval step matches existing
  vendors (name, tax_id, email) and creates a new one only on approval.
- A contact can hold both a customer_code and a vendor_code.

---

## Edit 3: section 7 (roadmap), backlog list

Add these items to the backlog (not scheduled, proposed order):
8. Customer code sequence table, customer_code field and the assignment
   service function (proposed for Phase 2); wizard shows the code
   (proposed for Phase 3).
9. After Phase 4, unscheduled: (a) pipeline, stages, stage history and the
   signing function; (b) CRM basics and collaboration; (c) service cases and
   the Customer Support pipeline; (d) throughput and profit views.
See docs/crm_pm_design.md section 11.

---

## Edit 4: section 9 (open decisions)

Add:
7. CRM / project design open questions: see docs/crm_pm_design.md section
   12 (vendor code V prefix, optional case fields, linear stages, warranty
   length, pausing cases, prospect in the wizard, closing checklist, desktop
   to hosted sync).

---

## Edit 5: status line (section 7)

Append to the status: "2026-11-10: CRM / project lifecycle design written
(docs/crm_pm_design.md). No schema or code changes."
