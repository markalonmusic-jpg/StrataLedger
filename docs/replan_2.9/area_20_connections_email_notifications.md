# Step 2.9 schema replan, area 20: Connections, company email, capture inbox, company calendar, notifications and Playbook

Status: **DRAFT 2026-11-25, awaiting owner approval; revised for the owner answers A20-Q1 to Q4 (12:50 AM) and the serial-number answer (12:53 AM), section 17.** Docs only: nothing here changes code, a baseline, a migration
or a test. Every table, column, code and check below would be built only in the 2.9 baseline pass, after the replan
is approved. **Only the lines marked "owner" are owner rules.** Everything else is a **planning proposal, owner may
revise**. PROPOSED items in the sources are not built as final.

**Nothing in this area posts to the ledger, approves anything or moves money.** It sends mail, files drafts that a
person confirms, writes notices and stores settings. A static test checks that no service in this area imports
`ledger` or writes a journal table (§13).

Sources read (only these, searched by section, date or code):
- Owner answers 2026-11-25 12:37 AM (Strata_Teams `inbox/to_owner.md`, read-only): Q3 notices, Q4 weather; and the
  planning calls Q1 (the feed is Area 20's) and Q2 (the company's own mailbox).
- docs/next_step.md: "Area 20, Capture inbox" (item 23, CAP-04), "Area 20, Connections" (the weather forecast), "Area 20
  (Connections; CONN-01 to CONN-03)", the Area 20 proposal-email line, the Area 21 notification lines; docs/roadmap.md;
  `Strata_Teams/schema_replan_2026-11-17.md` row 20 (Connections: AI key, company SMTP; Playbook; A 11-13, C 18, 41, 42, 77;
  AG1-AG8; L SMTP).
- Approved areas, by section: 2 (§5 remittance), 3 (O6, vendor documents, duplicate warning), 6 (§8 sending, §16 item 10 the email log
  id), 8 (§12.2 weather, `final_bill_request.email_ref`, share-schedule emails), 9 (§8, §17 late deliveries), 14 (§14 notifications),
  15 (§6 appointments and `.ics`, notification feed text), 18 (§3 attachments, Q15 reasons), 13 (§1.4 locks), 12/21 (row version).
- Live mockups (read-only, StrataLedger_mockups): `connections.html`, `capture-inbox.html`, `crm-alerts.html`,
  `job-calendar.html`, `field-daily-log.html` (weather); `CODE_CHANGES_NEEDED.md` §18 (Connections), §19.2 (Capture inbox), §41, §42
  and §77 (Playbook).
- `docs/decisions_2026-11-11.md` AG1-AG8, HA rules, H1 to H5; `modules/services/key_store.py`, `storage.py`, `clock.py` (read for the
  patterns only); `migrations/001_company.sql` (checked: no connection, email, capture, calendar or notification table exists;
  `file_attachment` holds only three `target_type` values).

---

## 0. Summary

| # | Item | Proposal in one line |
|---|------|----------------------|
| 1 | Notices | **Every notice shows in the user's in-app list, always. Email is opt-in per user and per kind of notice (owner).** Documents (invoices, remittances, estimates) still send by email as their own action. One `notification` feed in this area (planning call; Area 21 points here). |
| 2 | Company mailbox | One company mailbox sends and receives, as live Settings > Connections shows (Microsoft 365, Google Workspace, or IMAP and SMTP; "Sending as" the company address; no password stored by the app for the OAuth methods). |
| 3 | Email log | One insert-only `email_log` for every send: documents, notices, capture replies, calendar items. Other areas store its id (`email_ref`). |
| 4 | Capture inbox | Mailbox addresses (receiving@, pulls@, ap@, docs@) become drafts in a tray; every draft needs one human confirmation; rejected and deleted messages are kept 30 days. |
| 5 | Company calendar | **Off by default, Admin only (live mockup and the planning call).** One company calendar address receives every calendar item as an `.ics` event; stable UID and SEQUENCE; a downloadable `.ics` when there is no mailbox. |
| 6 | Weather | **OFF until an Admin turns it on (owner 12:37 AM, Q4).** One setting, owned here (planning call); Area 8 points to it. Sends job addresses to a weather service. |
| 7 | AI assistant connection | Connection settings, spending cap and an `ai_usage` log only; the assistant itself is Phase 6. Off until an Admin or the Master turns it on (AG3); a saved key and a passed test come first (planning proposal). |
| 8 | Secrets | Passwords, tokens and keys are never in the company file, a backup or the audit log (mockup rule; AG1 superseded by the owner's A20-Q1 answer: the Windows credential store, section 17). |
| 9 | Playbook | Tables for pages, versions and rules (C41, C42, C77), built in the baseline pass; services later (stage 3 waits for Phase 5). |

---

## 1. Current state

- **Baseline:** no table for connections, a mailbox, an email log, a capture inbox, calendar events, notifications, the Playbook
  or AI usage. `file_attachment` exists with a three-value `target_type` (Area 18 §3 widens it). `modules/services/` has
  `key_store.py` (installation key, DPAPI, company chain keys), `storage.py` and `clock.py`; nothing sends mail.
- **Mockups:** `connections.html` shows the AI assistant (provider, model, key last 4, cap, who may use it, "Let the assistant
  read company records"), the company email (Microsoft 365, Google Workspace, Other IMAP and SMTP; "Sending as"; Check every 5 or
  15 minutes or manually; capture addresses with allowed senders; who reviews each type; "Give each job its own address", marked
  Hosted), sending (From name, From address, Reply-to) and the company calendar (Off by default; only an Admin can change it).
  It has **no weather setting** (the daily log has a typed Weather field and a link to the National Weather Service; no fetched forecast is shown, so the fetch is new work). `capture-inbox.html` shows the tray, the reviewed
  draft from a photo, the serial list read from a pallet label, and the states "Rejected sender", "Possible duplicate", "Needs a
  job" and "Mail not checked".
- **Approved areas hand this area:** the remittance email (Area 2, Area 3 O6), the vendor document request email (Area 3 O6),
  the proposal email and its log id (Area 6), final bill requests and share-schedule emails with `final_bill_request.email_ref`
  (Area 8), the weather fetch (Area 8 §12.2), the `.ics` event and the company calendar address (Area 15), approver and other
  notices (Areas 14, 9, 15).

## 2. Decided (owner) and carried forward

- **Notices (owner 12:37 AM, Q3):** every notice (approval waiting, "moved to Admin", a recoded request line, an estimate
  expiring in 3 days) shows in the user's in-app notification list. A user can also turn on email for a kind of notice. Example:
  Dana sees "$22,000.00 bill waiting for your approval" in the app and gets an email too only if she turned that on. **Documents
  (invoices, remittances, estimates) still send by email as their own action.**
- **Weather (owner 12:37 AM, Q4):** the job-site weather forecast is **OFF until an Admin turns it on**; it sends job addresses to a
  weather service, so it follows the controls-off rule. Example: after an Admin turns it on in Connections, the job's daily log
  and crew board show the forecast for the job's address. This clarifies "the weather forecast stays on" (owner 11/22) in next_step
  and Area 8 §12.2, which already say a company setting turns it on: the feature stays in scope, and the default is OFF.
- **Capture inbox (owner, item 23, CAP-04):** "Allow sender" covers that sender for that capture address only; an already rejected
  message needs a one-click Reprocess to enter review; rejected and deleted messages are kept 30 days, then purged (company setting
  `capture_rejected_retention_days`, default 30).
- **Planning calls (owner may revise, 12:37 AM note):** the notification feed lives in this area (Area 21 points here); email sends
  from the company's own mailbox as live Settings > Connections shows (Microsoft 365, Google Workspace or IMAP and SMTP, "Sending as" the
  company address; the token never stores a password; the company calendar is Off by default, Admin only).
- **Carried forward:** the AI never posts, approves or moves money; every agent-origin draft needs one human confirmation (integrity,
  CLAUDE.md section 0); only an Admin or the Master changes connections, each change with a reason and audit-logged without the
  secret; no printed or emailed document contains its memo (Area 18); mail from a sender an address does not allow is held as
  Rejected sender and nothing is read; desktop team features work between turns on one PC while hosted is real time (planning log
  3b), so the desktop sends and checks mail only while the app is open.

---

## 3. Connections: the settings, never the secrets

- **`connection`** (one row per kind; planning proposal): `connection_id`; `kind` CHECK IN ('Company mailbox', 'AI assistant',
  'Weather forecast'); `method` TEXT (for the mailbox 'Microsoft 365', 'Google Workspace' or 'IMAP and SMTP'; for AI the provider); `status`
  CHECK IN ('Not set up', 'Connected', 'Failed', 'Disconnected'); `account_label` TEXT (the connected address or provider name; no
  secret); `secret_ref` TEXT (the name of the entry in the key store; never the secret); `secret_last4` TEXT NULL (AI key only, AG8
  style); `last_tested_at`, `last_test_result`, `connected_by`, `connected_at`; `row_version`. One row per kind (UNIQUE `kind`).
- **Company mailbox settings** (`company_mailbox`, one row): `sending_name`, `sending_address` (the "Sending as" identity), `reply_to`;
  for Other: `imap_host`, `imap_port`, `imap_security`, `smtp_host`, `smtp_port`, `smtp_security`, `user_name` (no password); `check_every_minutes`
  CHECK IN (5, 15, 0) DEFAULT 15 (owner A20-Q2: every 15 minutes, an Admin may choose 5, plus Check now; 0 = manual) (0 = manual; **the desktop app checks only while it is open**); `capture_allowed_senders` per address (§5).
- **AI assistant settings** (`ai_setting`, one row): `provider` (Google Gemini in v1; others later, AG2 includes a local model),
  `model_tier` CHECK IN ('Recommended', 'Higher quality'), `paid_plan_confirmed`, `read_company_records` DEFAULT 0, `monthly_cap_cents`
  DEFAULT 2500 ($25.00, C18.1), `who_may_use` CHECK IN ('Everyone', 'Admins and Controllers', 'Chosen roles') DEFAULT 'Everyone' (the mockup's first option), `enabled` DEFAULT 0.
  **AI is OFF per company until an Admin or the Master turns it on, with a warning before the first send (AG3);** planning proposal: it also
  needs a saved key and a passed test first. **`ai_usage`** (insert-only, AG8): `usage_id`,
  `used_at`, `user_id`, `provider`, `form_code`, `cost_cents` (estimated), `outcome`; never the content or the key.
- **Weather settings:** `company_settings.weather_forecast_on` INTEGER NOT NULL DEFAULT 0 (**owner: OFF**), Admin or Master, a reason,
  audit-logged; forecasts in `weather_forecast` (§8).
- **Secrets (owner 12:50 AM, A20-Q1: the Windows credential store on the desktop, locked to the Windows user; a server secret store when hosted; AG1's "DATA_DIR\Secrets" is superseded for connection secrets):** the key store holds every password, app password, refresh token and API
  key; the company file, backups, logs and the audit log never do. The audit log records that a key was added, replaced or removed,
  by whom, and (AI key only) its last 4 characters. The hosted version uses a key vault. Services reach the key store and the
  mail and weather clients only through injected provider objects (like `clock`), so `modules/services/` imports no OS, network or
  mail library (H1).
- **Rules:** connecting, replacing and disconnecting the **mailbox**, and changing the **calendar** and **weather** settings, need `connection.manage`
  (planning proposal, sensitive, Admin and the Master only, none in `AGENT_ALLOWED`); the **AI rows** keep the existing `ai.settings` (baseline, "Change AI keys,
  data sharing and budget", not sensitive); Area 18 may place both, a reason (Area 18 Q15 A: controls), and are audit-logged. **Test connection** reports the actual
  sending identity and the real result; a saved setting alone never shows "Connected" (§6). Disconnect needs a reason; mail already
  received stays in the Capture inbox.
- Tests (planning proposals): `test_connection_change_needs_connection_manage_a_reason_and_is_audit_logged`,
  `test_connection_rows_never_hold_a_secret_and_audit_log_has_last4_only`,
  `test_company_file_and_backups_contain_no_password_token_or_key`,
  `test_mailbox_test_reports_actual_sending_identity`, `test_mailbox_reconnect_records_connection_outcome`,
  `test_mailbox_disconnect_records_state_and_keeps_ics_fallback` (next_step), `test_mailbox_disconnect_keeps_received_mail`, `test_ai_off_until_key_saved_and_test_passes`,
  `test_ai_usage_logs_who_when_provider_form_never_content_or_key`, `test_ai_monthly_cap_stops_calls`,
  `test_services_import_no_mail_network_or_keyring_library` (static, H1).

## 4. The email log and sending

- **`email_log`** (insert-only, no update or delete trigger; one row per send **result**, planning proposal): `email_id`; `kind` CHECK IN ('Document', 'Notice',
  'Capture reply', 'Calendar item', 'Reminder'); `document_type` TEXT NULL (invoice, remittance, estimate, statement, final bill request,
  share schedule, vendor document request); `record_type`, `record_id`; `to_addresses`, `cc_addresses` (lists, no body); `subject`;
  `attachment_file_id` NULL (the retained copy of what was sent, through `storage.py`; Area 5's statement copy uses it); `status` CHECK IN
  ('Sent', 'Failed', 'Not sent (no mailbox)'); `error_text`; `provider_message_id`; `sent_by`; `sent_at`; `retry_of_email_id` NULL (a new attempt after a
  failure is a new row);
  `operation_id` UNIQUE (a retry with the same ID returns the first row and sends nothing twice). There is no 'Queued' row: a notice waiting to be emailed is a
  `notification` with no `email_id` yet (§7).
- **Audit and purge:** the audit trigger for `capture_message` redacts `from_address` and the subject (Area 18 AX4's shared redaction list), so purging the message leaves no copy of the sender in `audit_log`.
- **Sending rules:** a document is sent by its own action (Send, Email) and authorized by its own permission (for example `invoice.send`);
  the send runs after the record is saved; **delivery status comes from the recorded send result, never from a saved setting
  alone**. With no connected mailbox every document keeps its non-email routes: Save PDF, Print, Mark as sent, and Download .ics
  (Areas 2, 6, 15). No email carries a memo, a password or a secret; a document email is built from the same allow-list as print
  (Area 18). Other areas store `email_log.email_id` as `email_ref` (Area 8 `final_bill_request`, Area 6's revision, Area 3's
  vendor document request); the FK is added in the same baseline pass.
- **Reminders** (a final bill request's `remind_after_days`, the 3-day estimate expiry, activity reminders) are written as notices
  (§7) and, only when the user opted in, as email; the desktop sends them while the app runs, the hosted version on time.
- Tests: `test_email_send_writes_one_log_row_and_status_comes_from_the_send_result`,
  `test_email_retry_with_same_operation_id_sends_once`, `test_no_mailbox_leaves_document_unsent_and_offers_other_routes`,
  `test_email_log_is_insert_only`, `test_no_document_email_contains_the_memo`,
  `test_sent_document_keeps_a_retained_copy_through_storage`, `test_email_ref_in_other_areas_points_to_email_log`.

## 5. Capture inbox

- **Addresses:** **`capture_address`**: `address_id`, `address` (an alias of the connected mailbox: receiving@, pulls@, ap@, docs@),
  `item_type` CHECK IN ('Delivery ticket', 'Pull ticket', 'Vendor bill', 'Supporting document', 'Job photo'), `allowed_senders` CHECK IN
  ('Users and vendor addresses on file', 'Users only', 'Anyone') DEFAULT 'Users and vendor addresses on file' (C18.2), `is_active`, `row_version`.
  **`capture_review_setting`** (`item_type` PK, `reviewer` TEXT NOT NULL, `row_version`; the CHECK allows only the options below per type; each defaults to its first
  option; planning proposals): delivery tickets by the job's project manager or superintendent; pull tickets by the warehouse lead or the job's PM; vendor bills by
  accounts payable or the job's PM; job photos filed by the job's PM or the sender (live Connections; the first option listed is the default). The per-job address (plus
  addressing, "Give each job its own address") is **hosted only** (M5; live marks it Hosted).
- **`capture_message`:** `message_id`; `address_id`; `provider_message_id` with UNIQUE (`address_id`, `provider_message_id`) (a message is never booked twice for one address; the same mail sent to two addresses is two rows, and the second is flagged Possible duplicate); `from_address`;
  `from_user_id` NULL / `from_contact_id` NULL; `received_at`; `item_type`; `project_id` NULL; `match_method` CHECK IN ('Per-job address',
  'PO number', 'Vendor or address', "Sender's jobs", 'Unsorted'); `status` CHECK IN ('Draft ready', 'Needs a job', 'Possible duplicate',
  'Needs review', 'Rejected sender', 'Reviewed', 'Discarded', 'Purged'); `discard_reason_code`, `discard_reason_text` (OD-31,
  conditional CHECK); `content_fingerprint` TEXT (a hash of the message content, kept by the stub); `purge_after` (received or discarded date + `capture_rejected_retention_days`); `reprocess_count`; `row_version`.
  Files are `file_attachment` rows (Area 18 §3 adds a 'Capture message' target type), through `storage.py`.
- **`capture_draft`** (what the assistant or a person typed): `draft_id`; `message_id`; `target_type` CHECK IN ('Goods receipt', 'Pull ticket',
  'Vendor bill', 'Vendor document', 'Job attachment'); `fields_json` (each value with where it was read and a confidence mark: Matches,
  Check this, Changed by you); `origin` CHECK IN ('Agent', 'Person'), `run_id` NULL (CHECK: origin 'Agent' requires `run_id`); `confirmed_by`, `confirmed_at` (CHECK: both set or both NULL), `target_id` NULL,
  `question_for_user_id` NULL. **Integrity:** an Agent draft needs one human confirmation, saved with the source attached (AG6);
  exceptions are asked as a question to the PM, never resolved; a draft changes nothing until confirmed (Area 9 receipts, Area 3 bills and
  vendor documents are created by their own services, which post nothing for a draft).
- **Rules (planning proposals unless marked owner):**
  - Job matching order: per-job address, then the ticket's PO number, vendor or address, then the sender's jobs; otherwise **Unsorted**;
    **the system never guesses** (live).
  - **Sender not allowed:** nothing is read and no AI cost is incurred; status Rejected sender. **Allow sender** covers that sender for that
    address only (owner CAP-04) and offers **Reprocess** (one click) to enter review (owner).
  - **Possible duplicate:** same vendor and bill number as an existing bill (Area 3's duplicate warning): the tray offers Discard
    duplicate (a reason, OD-31) or Keep as a different bill (a note).
  - Discard needs a reason (OD-31). Rejected and deleted messages are kept `capture_rejected_retention_days` (default 30, owner) and then
    **purged**: the files and sender text are deleted and a stub row stays (status Purged, content fingerprint, sender, dates) so a repeat of the same
    message is still recognized (owner A20-Q4: the stub keeps only a content fingerprint, the sender and the dates; a re-sent bill photo is flagged "already received 01/12, rejected").
  - **Assistant off:** the photo still arrives; the person types the delivery beside it (live). The reading is Phase 6; the tray works
    without it.
  - On Confirm the reply to the sender is previewed and, with a mailbox, sent and logged (`email_log` kind 'Capture reply'); with
    none, nothing is sent.
  - The desktop app reads mail only while open (owner A20-Q2: every 15 minutes, an Admin may choose 5, plus Check now; mail waits in the mailbox while the app is closed); the interval lives in §3.
- **Serial numbers:** serial tracking is in (owner 12:53 AM; Area 9 §8.3). A delivery-ticket draft may carry typed serials into the Area 9 receipt, which a person
  confirms; reading a serial list from a pallet label by the assistant is Phase 6.
- Tests: `test_capture_message_never_booked_twice_same_provider_id`, `test_capture_unsorted_when_no_match_never_guessed`,
  `test_capture_sender_not_allowed_is_rejected_nothing_read_no_ai_cost`,
  `test_allow_sender_covers_only_that_address_and_reprocess_enters_review`,
  `test_capture_possible_duplicate_offers_discard_with_reason_or_keep_with_note`,
  `test_agent_draft_needs_one_human_confirmation_and_changes_nothing_before`,
  `test_capture_discard_needs_reason_or_10_character_other`, `test_rejected_and_discarded_kept_30_days_then_purged_to_a_stub`,
  `test_capture_retention_days_setting_default_30`, `test_capture_works_with_assistant_off_by_typing`,
  `test_capture_reply_sent_and_logged_only_with_a_mailbox`, `test_capture_files_go_through_storage`.

## 6. Company calendar and `.ics`

- **Settings:** `company_settings.company_calendar_on` INTEGER NOT NULL DEFAULT 0 (**Off by default, Admin only**; live), and
  `company_calendar_address` TEXT NULL, changed by `connection.manage`. It needs a connected mailbox first. **The address must differ from the company's actual
  sending mailbox** (some providers do not add invites a mailbox sends to itself); a change goes through **Review changes**, asks
  for a reason, **Cancel discards it, Apply saves it, reload keeps it, and the next event uses that destination** (CONN-01 to CONN-03).
- **One-way:** the app sends items, updates and cancellations; changes made in Google or Outlook do not come back. People get no
  invites of their own: attendees, assignees, the job and a link back are written in each event's details (live).
- **`calendar_event`** (planning proposal): `event_id`; `source_type` CHECK IN ('Activity', 'Job task', 'Job milestone', 'Calendar item',
  'Close task'); `source_id`; **`event_uid`** TEXT UNIQUE (stable for life: `<source_type>-<source_id>@<company domain>`); **`sequence`**
  INTEGER NOT NULL DEFAULT 0; **`destination_address`** TEXT NOT NULL (the company calendar address in force when the event was first sent); `status` CHECK IN ('Active', 'Cancelled'); `last_email_id` NULL; `last_send_result`; `row_version`.
  **Events already sent keep their original destination for updates and cancellations; only new events use a new address (owner 2026-11-22, item 24, CONN-03; Area 8's schedule notifications follow the same rule).** **Create starts at SEQUENCE 0; each successful update or cancellation increments it once; a retry does not duplicate or increment
  twice.** The sequence is this table's, not the source row's `row_version` (flagged: Area 15 says "SEQUENCE = row_version"; a send that
  fails or is skipped, or an edit unrelated to the calendar, would leave gaps or repeat numbers; Area 15 gets a pointer).
- **Who raises events:** Area 15 appointments (create, reschedule, cancel), Area 8 job tasks and milestones, Area 8 calendar items and Area
  13 close tasks call `calendar_events.raise(conn, context, source_type, source_id, change)`; it writes the `calendar_event` row **in the caller's transaction** (so a failure rolls back with its cause, as `notify` does) and sends
  the mail and writes its `email_log` row **after commit**, and only while `company_calendar_on`. With no mailbox the reply offers **Download .ics**
  (always available).
- **Delivery status** shown on the calendar settings and the source record comes from `last_send_result` (the recorded send), never
  from the setting alone. A failed send writes an in-app notice to the Admin and the record's owner (§7).
- Tests: `test_calendar_address_only_review_reason_cancel_apply_reload_and_next_event_destination` (CONN-01),
  `test_calendar_address_must_differ_from_actual_sending_mailbox` (CONN-03), `test_company_calendar_off_by_default_admin_only`,
  `test_calendar_invite_create_uses_stable_uid_sequence_zero`, `test_calendar_invite_update_keeps_uid_and_increments_sequence`,
  `test_calendar_invite_cancel_keeps_uid_and_increments_sequence`,
  `test_calendar_invite_retry_does_not_duplicate_or_increment_sequence_twice`,
  `test_calendar_delivery_status_comes_from_recorded_send_result`,
  `test_calendar_address_change_keeps_sent_event_destination_for_updates_and_cancels` (owner item 24), `test_ics_download_fallback_available_without_connected_mailbox`,
  `test_calendar_event_raised_only_while_company_calendar_on`, `test_sequence_is_not_the_source_row_version`.

## 7. Notifications (the feed)

- **`notification_kind`** (seeded list; each row owned by an area; planning proposal): `kind_code` TEXT PK, `label`, `owner_area`,
  `sort_order`, `is_active`, `row_version`. Seeded kinds (each written by the service of the area named, or by the routing that area owns: Area 14's approvals service calls `notify`; it owns no feed): approval waiting, approval decided
  (to the submitter), approval moved to the backup or Admin (Area 14), no eligible approver (Area 14), request line recoded (Area 9), late or
  short delivery (Area 9), a mention or a comment on your record (Area 15), activity reminder, lead auto-lost warning, the Resolve prompt for a
  case, assignment (PM assigned, Ask the rep), estimate sent back, **estimate expires in 3 days** (Areas 6 and 15), final bill request
  reminder (Area 8), calendar send failed, capture message needs review, mailbox disconnected. Owning areas add rows through their
  own baseline seed.
- **`notification`** (planning proposal): `notification_id`; `user_id`; `kind_code`; `title`; `body` (a sentence, no memo, no secret);
  `record_type`, `record_id`; `project_id` NULL; `created_at`; `read_at` NULL; `dedupe_key` TEXT NULL with UNIQUE (`user_id`, `kind_code`,
  `dedupe_key`) (an activity reminder or auto-lost warning is written once, even if the run repeats); `email_id` NULL (set when an email
  was sent for it); `source` (the service).
- **`notification_state`** (`user_id` PK, `last_seen_at`): the badge count is notices newer than it.
- **`user_notice_preference`** (`user_id`, `kind_code`, `email_on`, PK both): **absent means off**. **There is no preference that turns
  a notice's in-app copy off (owner: in-app always).** Email is also sent only when a mailbox is connected; without one the preference
  page says so and the notice stays in-app.
- **Writing a notice:** `notifications.notify(conn, context, kind_code, recipients, record, ...)` runs inside the **caller's write
  transaction**, so the notice and its cause commit together (H4: a service rule, not a trigger). It resolves recipients through the
  record's own access (MR3, project scope): a person never receives a notice about a record they may not see. A notice never carries
  the memo, a secret or another company's data.
- **Email for a notice (opt-in, owner):** after commit, for each recipient with `email_on`, one `email_log` row (kind 'Notice') is queued and
  sent by the mailbox; the desktop app sends queued notices while it is open, the hosted version on time. A failed email never loses the
  in-app notice.
- **Reading:** `notifications.list_for(context, unread_only=False)` (read-only, scoped to the user); mark read, mark all read, and open the
  record the notice links to. Notices are never deleted by a service (they are old messages, not records of money).
- **Boundary with Area 21 (flagged):** earlier approved text (Area 15 §6, lines 66, 68, 406, 558, 686 and 981; next_step lines 645 and
  687, and line 580's "area 17's general notification feed") says "Area 21's notification feed"; per the planning call (12:37 AM) the feed and `last_seen_at` live here, and Area 21 keeps the
  company calendar **query** (`activities.calendar_rows`) and `row_version`. Pointers amend those lines.
- Tests: `test_notice_always_shows_in_app_and_cannot_be_turned_off`, `test_email_for_a_notice_is_off_until_the_user_turns_that_kind_on`,
  `test_notice_email_needs_a_connected_mailbox_else_stays_in_app_only`, `test_notify_commits_with_its_cause_and_rolls_back_with_it`,
  `test_notice_dedupe_key_writes_one_per_user_kind_and_key`, `test_notice_goes_only_to_people_who_may_see_the_record`,
  `test_notice_has_no_memo_or_secret`, `test_failed_notice_email_keeps_the_in_app_notice`, `test_last_seen_at_drives_the_badge_count`,
  `test_documents_still_send_by_email_without_a_preference` (invoices, remittances and estimates are their own action),
  `test_every_seeded_notice_kind_has_an_owner_area`.

## 8. Weather forecast

- **Setting (owner 12:37 AM, Q4):** `company_settings.weather_forecast_on` DEFAULT 0, Admin or Master, a reason, audit-logged, shown on
  Connections. **One setting, owned here (planning call); Area 8 points to it** (pointer in Area 8 §12.2; the next_step line "the weather forecast stays on" is clarified by marker). The mockup's Connections page has no weather row (the daily log has only a typed Weather field and an NWS link): design-queue work order.
- **What is sent (owner 12:50 AM, A20-Q3):** only the job site address of jobs with an active schedule, and nothing else (no customer name, no job number, no
  amount). **`weather_forecast`** (`project_id`, `forecast_date`, `summary`, `high_c`, `low_c`, `precip_pct`, `fetched_at`, `source`; UNIQUE
  (`project_id`, `forecast_date`)); fetched **twice a day, read-only**, only while the setting is on and only while the app runs.
- **Failure and offline:** a failed fetch writes nothing over the last good forecast, shows "Forecast not updated since <time>" and writes
  one in-app notice to the Admin per day (dedupe); offline the screens show the last forecast with its age, or "No forecast yet".
  Turning the setting off stops fetches and hides the forecast; stored forecasts stay (history).
- Tests: `test_weather_off_by_default_and_admin_only_with_a_reason`, `test_weather_sends_only_the_job_site_address`,
  `test_weather_fetch_twice_a_day_only_while_on`, `test_weather_failure_keeps_last_forecast_and_notifies_admin_once_a_day`,
  `test_weather_offline_shows_last_forecast_with_its_age`, `test_turning_weather_off_stops_fetches_and_hides_the_forecast`.

## 9. AI assistant connection, usage and the capture draft path

- Section 3 holds the settings and `ai_usage`. **Phase 6** builds the assistant; this area only makes the tray, the drafts and the
  setting. `AGENT_ALLOWED` is unchanged; the assistant stays Agent origin with a run id; it never approves, posts or moves money; matching is
  local (AG6); extraction sends only the chosen file or pasted text (AG4); the model returns only that form's fields (AG5); every call is
  logged without content or key (AG8).
- **Conflict flagged, not resolved here (next_step, 2026-11-24 mockup audit item 10):** the mockup's "Let the assistant read company
  records" conflicts with AG4 and AG7 (the 11/17 AI privacy rule). `ai_setting.read_company_records` is stored, default 0, and is **not
  used** until Phase 5 resolves it with the Playbook items.
- Tests: `test_read_company_records_defaults_off_and_is_not_read_by_any_service_yet`,
  `test_ai_call_log_never_stores_content_or_key`, `test_ai_cannot_confirm_its_own_capture_draft`.

## 10. Playbook (tables only; services in Phases 3 and 5)

- **Placement:** Playbook stage 3 waits for Phase 5 (owner 2026-11-22 item 3; "propose page edits from evidence" and "Playbook text is
  sent to the AI provider" conflict with the 11/17 AI privacy rule). Stages 1 and 2 are tables and an editor in the HTML front end
  (AQ2), the same editor on desktop and hosted (the planning answer to C41's Q3).
- **Tables (planning proposals; names from C41, C42, C77):** `playbook_area` (company list, per console ERP, CRM, PM); `playbook_page`
  (area, title, `owner_user_id`, `reviewed_on`, `status` Draft or Published, `used_by_assistant`, `current_version_id`);
  `playbook_page_version` (append-only; page, version, `content_json` of blocks, created, published; restore copies an old version as
  a new one); `playbook_rule` (area, `conditions_json`, `actions_json`, `created_by`, `is_active`, `times_used`, `times_overridden`);
  `playbook_rule_order` (which rule wins, or "ask"). Files go through `storage.py`.
- **Rules (C42):** rules fill form defaults **whether or not the assistant is on**; a rule never overrides a control or an integrity rule;
  the person can always change the value; "Remember this" needs the permission; at 5 overrides in the last 8 uses a rule shows in "need
  attention" (Update, Keep, Turn off); two rules that fill one field are shown and the person chooses, never a silent pick; a rule never
  used is deleted, a used one is turned off (history kept). Pages older than 6 months since `reviewed_on` show in "need attention". The
  assistant reads only the **published** version and only while `used_by_assistant` is on. A save-time warning for card-like or
  account-like numbers (planning proposal).
- Tests: `test_playbook_page_versions_are_append_only_and_restore_makes_a_new_version`,
  `test_playbook_rule_fills_defaults_with_assistant_off`, `test_playbook_rule_never_overrides_a_control_or_integrity_rule`,
  `test_playbook_conflicting_rules_are_shown_never_silently_picked`, `test_used_rule_is_turned_off_not_deleted`,
  `test_playbook_assistant_reads_only_published_pages_marked_for_it`.

## 11. Permissions, locks, row version and audit

- **Permissions (planning proposals; none in `AGENT_ALLOWED`; Area 18's seeded count grows):** `connection.manage` (sensitive; Admin
  and the Master), `capture.review` (the reviewers named in §5; scoped by job, MR3), `capture.manage` (addresses and allowed senders).
  A user edits only their own notice preferences. Sending a document uses that document's own permission.
- **Locks:** Area 13's shared lock check does not apply (no posting). Sending a document does not change its period; a calendar event
  for a close task is read-only information.
- **Row version** (Area 21): `connection`, `capture_address`, `capture_message`, `notification_kind`, `calendar_event`, `playbook_page`,
  `playbook_rule`. **Audit:** every table above is audited by the trigger pattern (Area 18 §1.2), without secrets; `email_log`,
  `ai_usage`, `playbook_page_version` and approved changes are insert-only.
- Tests: `test_connection_manage_is_sensitive_and_not_in_agent_allowed`, `test_capture_review_is_scoped_by_job`,
  `test_audit_rows_for_connections_hold_no_secret`.

## 12. How it lands in the baselines and code

- **Baseline (planning):** new tables `connection`, `company_mailbox`, `ai_setting`, `ai_usage`, `email_log`, `capture_address`,
  `capture_review_setting`, `capture_message`, `capture_draft`, `calendar_event`, `notification_kind`, `notification`, `notification_state`,
  `user_notice_preference`, `weather_forecast`, `playbook_area`, `playbook_page`, `playbook_page_version`, `playbook_rule`,
  `playbook_rule_order`; `company_settings` gains `company_calendar_on`, `company_calendar_address`, `weather_forecast_on`,
  `capture_rejected_retention_days` (DEFAULT 30); `file_attachment.target_type` gains 'Capture message' (Area 18 §3); FKs from
  `final_bill_request.email_ref` (existing column) and a new `estimate_revision.sent_email_id` (Area 6; planning proposal) to `email_log`; Area 3's vendor document
  request has no table, its record is the `email_log` row.
- **Code:** services `connections.py`, `emails.py`, `capture.py`, `calendar_events.py`, `notifications.py`, `weather.py`, `playbook.py`;
  the mail, key-store and weather clients are provider objects injected through `ServiceContext` (no `smtplib`, `imaplib`, `keyring` or
  `requests` import in `modules/services/`, H1); no clock reads (H2); files through `storage.py` (H3); workflow rules are services, not
  triggers (H4); no SQLite-only SQL (H5). **Static test:** nothing in these modules imports `ledger` or writes `journal_line`.
- **Existing tests change:** none known; the baseline has no such tables.
- **Handoffs out:** Area 2 and Area 3 (remittance and vendor document emails); Area 5 (statement and invoice send, retained copy); Area
  6 (proposal email, log id, Cc the rep, expiry reminder); Area 8 (final bill request send, share-schedule email, weather pointer,
  calendar events); Area 9 (late delivery notice, request recoded notice, capture drafts for receipts and pull tickets); Area 14 (approval
  notices); Area 15 (events, notices); Area 17 (reports on email log and capture, if wanted); Area 18 (permissions, attachment
  target type, reasons); Area 21 (the calendar query, `row_version`, setup of connections at company setup).

## 13. Integrity checks kept (always on)

Nothing here posts, approves or moves money; an agent-origin draft needs one human confirmation; a capture message is never booked twice;
a mail from a sender not allowed is never read; secrets are never in the company file, a backup, a log or the audit log (owner A20-Q1); the email log,
AI usage log and page versions are insert-only; a notice or email never carries a memo or a secret; only an Admin or the Master changes
connections, with a reason; a document is marked sent only by a recorded send result.

## 14. Conflicts with decisions, the baseline or the mockups (flagged)

1. **Notification feed placement:** approved Area 15 (and next_step lines 645 and 687) say Area 21; the planning call puts it here
   (pointers amend them).
2. **SEQUENCE:** Area 15 says "SEQUENCE = `row_version`"; the CONN tests say create at 0 and one increment per successful change. This area
   uses its own counter (§6).
3. **Secrets (resolved, owner 12:50 AM A20-Q1):** AG1 (decisions file) says "stored under `DATA_DIR\Secrets`"; the owner chose the Windows credential store on the
   desktop (a server secret store when hosted), so AG1 is superseded for the mailbox token and the AI key (amendment in the decisions file).
4. **Weather:** "the weather forecast stays on (owner 11/22)" in next_step is clarified by the owner's 12:37 AM Q4 (the feature stays, the default is OFF until
   an Admin turns it on; Area 8 already says a company setting turns it on); the mockup Connections page has no weather row.
5. **"Let the assistant read company records"** conflicts with AG4 and AG7; stored, unused until Phase 5.
6. **Serial numbers (resolved, owner 12:53 AM):** serial tracking is in, per material code, OFF by default (Area 9 §8.3); reading serials from a pallet label stays Phase 6.
7. **`file_attachment`** has a three-value `target_type`; Area 18 §3 widens it for 'Capture message'.
8. **Live captures that "skip the PM on a matched bill"** (C19.1) follow Area 9's "Hold bills that do not match the receipt" control (OFF); no
   conflict, noted so the tray and the control share one rule.
9. **The planning log (3b):** real time is hosted; on the desktop, notices and mail checks run only while the app is open (§2).

## 15. Questions for the owner (recommended option first, with an example; **all answered 2026-11-25 12:50 AM, section 17**)

- **A20-Q1. Where do passwords, tokens and the AI key live on the desktop?** (A) The Windows credential store, never in the company file or a
  backup, as the Connections mockup says; the hosted version uses a key vault (recommended). (B) A `DATA_DIR\Secrets` folder, as AG1 says.
  (C) Wrapped in the master database with the installation key, like the company chain keys. Example: an IMAP app password; under A it is
  not in any backup, so restoring a backup on a new computer asks for it again.
- **A20-Q2. How does the desktop app read the company mailbox?** (A) It checks while the app is open, every 5 or 15 minutes or on Check now, over
  Microsoft 365 or Google sign-in or IMAP (recommended; matches the mockup; open question M4). (B) Hosted only. Example: photos sent
  overnight to receiving@ appear when the app opens in the morning.
- **A20-Q3. What does the weather service receive?** (A) Only the job site address (recommended). (B) Rounded coordinates made from it by us, so
  the service never sees the street. Example: "4410 Harbor Way, Mesa, AZ" versus 33.4, -111.8.
- **A20-Q4. After the 30 days, what stays of a purged capture message?** (A) A stub row (address, received date, status Purged) so a repeat of
  the same message is still recognized (recommended). (B) Nothing; the row is deleted. Example: a sender replays the same vendor bill email
  on day 40.

## 16. Open items (not decisions)

- Delivery of notices to a phone, push or SMS; read receipts; mention emails to people without a user.
- Bank feed connections and the payee-ID upload layout (Area 2 O1, "Area 20 or the bank connection"); not designed here.
- Reading serial numbers from labels, and reading delivery photos and bills (Phase 6).
- Sending a statement or invoice by email as a bulk run; email templates and a company signature; bounce handling beyond "Failed".
- Remittance advice format and the vendor document request wording (Area 3 owns the content; this area sends).
- Hosted multi-mailbox and per-job capture addresses (M5).
- The Playbook editor's rich-text toolkit in the HTML front end (Phase 3).

## 17. Owner answers 2026-11-25 12:50 and 12:53 AM (dated amendment; §15 stays as asked)

- **A20-Q1 secrets (owner):** on the desktop the mailbox sign-in token and the AI key live in the Windows credential store, locked to the Windows user, never in the
  company file or its backups; the hosted edition uses a server secret store. Example: copying the company file to another PC does not copy the token; the user signs in
  again there. §3, §13, §14 item 3.
- **A20-Q2 reading mail (owner):** the desktop reads the company mailbox while the app is open, every 15 minutes (an Admin may choose 5), plus Check now; mail waits in
  the mailbox while the app is closed (a bill photo sent Saturday is picked up Monday). §3, §5.
- **A20-Q3 weather (owner):** the weather service receives only the job site address; no customer name, job number or amounts (example: "1420 Mesa Rd"). §8.
- **A20-Q4 purge (owner):** a purged capture message leaves a stub with no content: a fingerprint, the sender and the dates, so a repeat is still recognized. §5.
- **Serial tracking (owner 12:53 AM):** in the plan, per material code, OFF by default, only while stock tracking is on; serials are recorded at receipt, picked at pull, and
  kept on the job's record for warranty (Area 9 §8.3). Live already has "Track serial numbers" and the String inverter 12 kW with 14 serials. §5, §14 item 6.
