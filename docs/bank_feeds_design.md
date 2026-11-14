# Bank feeds design (DESIGN, NOT BUILT)

**Date:** 2026-11-13 · **Status:** design, accepted by the owner. Owner decision B11a (docs/decisions_2026-11-11.md),
which amends B11, and BF1 (the questions in section 14, all answered as proposed). Nothing here is built.

**Owner decision this design follows (B11a, owner-approved 2026-11-11, recorded 2026-11-13):**
* v1.0 ships the feed **seam** only: a provider interface, one shared staging path, and file import (CSV,
  OFX/QFX) as the first provider. No live connection ships in v1.0.
* v1.1 ships the **Ramp** provider (card and payables data, with an API credential the customer supplies).
* Aggregators (Plaid-style) come later, as an optional add-on where the customer supplies their own
  credentials. A hosted relay belongs to the hosted product, where it becomes natural (P5).
* Reason: a desktop installer cannot safely hold a vendor-wide secret.

**Inputs read:** B3, B10-B14, E5, E6, F1-F6, G7, H3, H4, K1, KS1-KS21, the Imports topic in
docs/design_decisions.md (the Ramp holding area), docs/csv_import_design.md, docs/roles_permissions_design.md,
C11 in docs/controls_audit.md, docs/password_recovery_design.md section 6 (the keystore secret pattern),
`modules/services/storage.py`, `keys.py` and `permissions.py`, and Ramp's developer documentation (section 8).

**What exists today:** statement import and bank matching are **not built**. There is no service, screen or
staging table for statement lines. The baseline has `bank_reconciliation` (account, statement date and
balance, complete flag), `journal_line.recon_id` (an FK, but not locked after completion, C11), `bank_account`
(masked bank details, C4), and the import holding area (`import_batch`, `staged_transaction`, `staged_line`).
The permission registry has no `bank.*` codes yet (B10 names `bank.unreconcile`). So this design also defines
the statement-line staging table that the file import will use.

---

## 1. Provider interface (`modules/services/feeds/`)

The package follows the style of `keys.py` and `storage.py`: a Protocol, a small registry, one module per
backend, and a fake for tests. It has no Tk and no OS calls (H1), takes `now` from the caller (H2), and reads
files only through `storage.py` (H3).

    class FeedProvider(Protocol):
        key: str                       # "file_csv", "file_ofx", "ramp", ...
        display_name: str
        def connect(self, settings: dict, secret: SecretRef | None) -> ConnectResult
        def test_connection(self, connection: ConnectionInfo, secret: SecretRef | None) -> TestResult
        def list_accounts(self, connection: ConnectionInfo, secret: SecretRef | None) -> list[ExternalAccount]
        def fetch_since(self, connection: ConnectionInfo, secret: SecretRef | None,
                        cursor: str | None, now: str) -> FetchResult
        def disconnect(self, connection: ConnectionInfo, secret: SecretRef | None) -> None

* `FetchResult` holds `lines: list[NormalizedLine]`, `next_cursor: str | None` and `more: bool`.
* `NormalizedLine` holds `external_account_id`, `external_id`, `txn_date`, `posted_date` (None while
  pending), `amount_cents` (int, signed: money in is positive), `description`, `payee`, `reference` (check
  number or similar), `is_pending`, and `raw` (a dict with secrets removed, section 4).
* **A provider returns normalized lines and nothing else.** It never opens a database connection, never calls a
  service that writes, and never sees the ledger. A static test checks that `modules/services/feeds/providers/`
  imports neither `tx`, `database` nor `ledger`.
* The **feed service** (`feeds/service.py`) is the only caller of providers. It authorizes (rule 10), calls the
  provider outside any write transaction (network calls never hold the database), then writes the results in one
  `write_transaction`.
* Money: a provider converts to integer cents itself and raises `FeedDataError` for any amount it cannot convert
  exactly (rule 1). A currency other than the company's base currency is refused with a plain sentence (E6).

**Backends:**

| Key | Release | Notes |
|---|---|---|
| `file_csv` | v1.0 | Column layout saved per company and source (F6); the parsing rules of csv_import_design.md section 4. |
| `file_ofx` | v1.0 | OFX and QFX. `FITID` is the `external_id`. |
| `ramp` | v1.1 | Section 8. |
| `fake` | tests | Scripted lines, failures and cursors. |
| aggregator add-on | later | Customer-supplied credentials (B11a). |
| `relay` | hosted | Section 11. |

For the file providers, `connect` records the GL account and the layout, `test_connection` parses a sample,
`list_accounts` returns the one account the file is for (or the accounts named in an OFX file), `fetch_since`
parses one chosen file (the cursor is unused), and `disconnect` only marks the connection disconnected.

---

## 2. One staging path

Feed lines and file imports land in the **same** statement-line staging table and appear on the **same**
matching screen. Matching does not know or care where a line came from (a test proves identical results,
section 12).

**`bank_statement_line`** (new; company file):

| Column | Notes |
|---|---|
| `line_id` | PK |
| `account_id` | FK `account`: the GL bank or card account (through `feed_account_map` for feeds, chosen at upload for files) |
| `source` | `File` or `Feed` |
| `provider` | the provider key |
| `connection_id` | FK `feed_connection` (files get a connection too, section 3) |
| `import_batch_id` | FK `import_batch`, one per file upload or per sync run |
| `external_id` | the provider's id (OFX `FITID`, a Ramp transaction id). For a CSV with no id column, a SHA-256 of (account, date, amount, normalized description, and the occurrence number of that combination in the file), so two identical coffees on the same day stay two lines |
| `txn_date`, `posted_date` | ISO dates; `posted_date` is NULL while pending |
| `amount_cents` | INTEGER, signed |
| `description`, `payee`, `reference` | text as received, trimmed |
| `is_pending` | 0/1 |
| `status` | `New`, `Matched`, `Excluded`, `Removed` (a pending line the provider later dropped), `Before cutoff` |
| `matched_entry_id` | FK `journal_entry`, when matched (many-to-one is allowed, B3) |
| `recon_id` | FK `bank_reconciliation`, set when the reconciliation is completed, then locked (C11) |
| `raw_json` | the provider's record for audit, secrets removed (section 4) |
| `created_at`, `updated_at` | UTC ISO |

* **Unique** (`connection_id`, `external_id`): re-importing a file or re-syncing never makes a duplicate.
* **No deletes** (an append-and-update table, with an audit trigger like the other tables). A line is excluded
  or marked removed, never deleted, so a dropped pending charge stays visible.
* **Pending lines** are stored but stay out of matching and out of reconciliation until posted (section 5).
* The **holding area is separate.** `staged_transaction` holds source documents that become entries (Ramp card
  purchases, bills, payroll; the Imports topic). `bank_statement_line` holds what the bank or card says
  happened, and it is matched against posted entries. Ramp feeds both of them (section 8).

---

## 3. Tables

**`feed_connection`** (company file; no secrets):

| Column | Notes |
|---|---|
| `connection_id` | PK |
| `provider` | the provider key |
| `display_name` | "Chase operating (CSV)", "Ramp" |
| `status` | `Active`, `Needs attention`, `Disconnected` |
| `start_date` | the cutoff (section 6); ISO date, required |
| `last_sync_at` | UTC ISO; NULL until the first sync |
| `cursor` | provider-opaque text; never a secret (a test checks the Ramp cursor holds no token) |
| `secret_ref` | an opaque name for the secret in the secret store (section 4), never the secret; NULL for file providers |
| `last_error_code` | the code of the last failure, for the screen's sentence (section 9) |
| `created_by`, `created_at`, `disconnected_by`, `disconnected_at` | user ids are plain integers (CLAUDE.md section 4) |

**`feed_account_map`**: `map_id`, `connection_id` (FK), `external_account_id`, `external_account_name`, `last4`
(digits only, like `bank_account.account_last4`), `account_id` (FK `account`, a bank or card account), and
`is_active`. **Unique** (`connection_id`, `external_account_id`): one external account maps to one GL account.
**Unique** active `account_id` per provider, so two connections cannot feed the same GL account from the same
provider. An unmapped external account's lines are not fetched (or are dropped before staging), and the screen
lists it as "not mapped".

**`feed_sync_run`** (append-only): `run_id`, `connection_id`, `started_at`, `finished_at`, `trigger`
(`Manual`, `Timer`, `File`), `result` (`OK`, `Partial`, `Failed`), `lines_new`, `lines_updated`,
`lines_unchanged`, `lines_before_cutoff`, `error_code`, `run_by`. It holds counts and codes only, never row
contents.

---

## 4. Secrets

* **What is a secret:** Ramp's client ID and client secret (section 8), any short-lived access token, and later
  an aggregator's credentials. Nothing else.
* **Where it lives:** behind a `SecretStore` wrapper in the KeyProvider style (audit design 2.7; the same
  `get_secret(name)` idea the email design uses for the SMTP password):

      class SecretStore(Protocol):
          def put_secret(self, name: str, value: SecretKey) -> None
          def get_secret(self, name: str) -> SecretKey          # raises SecretUnavailableError
          def delete_secret(self, name: str) -> None

  * **Desktop backend:** one file per secret under `DATA_DIR/Secrets/` (written through a storage function),
    encrypted with AES-256-GCM under a key derived from the installation key (HKDF with the label
    "StrataLedger feed secret v1"). The associated data is the secret's name and the company id, so a copied
    file opens for no other connection. The installation key is DPAPI-held (K1), so the K1 limit applies and is
    stated on the connect screen: another Windows account on the same computer that can run code could read the
    secret.
  * **Hosted backend:** Azure Key Vault (P5). Services do not change.
* **Outside** the company database, `system_master.db`, every backup, every export and cloud-move package
  (docs/cloud_migration_design.md lists feed credentials as not moved), and every support bundle (backlog 19).
  The backup and support-bundle writers exclude `Secrets/` by name, and a test proves it.
* **Never** logged, never in an exception message or `repr` (a `SecretKey` is redacted and cannot be pickled,
  KS4), never in `raw_json` (providers drop known secret fields, and a redaction pass removes any value that
  equals a stored secret or looks like a bearer token before the line is staged), and never in the audit log.
* **Access tokens** that a provider obtains (Ramp's 10-day client-credentials token) are held in memory only
  and fetched again when needed. They are never written to disk.
* **Read-only scopes only:** the connect screen asks for read scopes and refuses a credential that the provider
  reports as holding write scopes, where the provider can tell (section 8).
* **Replacing a credential** ("Replace key") writes the new secret, tests it, then deletes the old one. The
  audit entry records that it was replaced, never either value.

---

## 5. Sync

* **Polling only on desktop.** Webhooks need a public address, which a desktop app does not have. "Sync now" is
  on the Bank feeds screen and the matching screen. A timer syncs every active connection while the app is open
  (default every 60 minutes, set per company, off allowed). There is no background service when the app is
  closed.
* **Cursor-based and idempotent:** a sync fetches from the stored cursor, upserts by (`connection_id`,
  `external_id`), and advances the cursor in the same write transaction as the lines. A crash before the commit
  leaves the old cursor, so the next sync fetches the same lines again and the unique key absorbs them. Providers
  that cannot fetch by "changed since" use an overlapping date window, and the upsert removes the overlap
  (section 8).
* **Updates:** a line already staged is updated only while it is `New` or pending. A matched or reconciled line
  never changes. If the provider sends a different amount for a matched line, the sync records the difference on
  the run (`lines_updated` stays 0 for it) and flags the line "Changed at the bank" for a person to review.
* **Pending to posted:** a pending line stays out of matching. When the provider reports it posted, the same
  row (same `external_id`) gets its `posted_date` and final amount and becomes matchable. When the provider no
  longer returns a pending line (a reversed authorization), it becomes `Removed` after the provider's settle
  window (Ramp: section 8).
* **One sync at a time per connection** (a running sync makes a second request wait or say "A sync is already
  running").
* **Failure:** a provider error or a parse error leaves staging and the cursor untouched; the run is recorded
  as `Failed` with its code, and the connection becomes `Needs attention` after 3 failures in a row.

---

## 6. Cutoff

* Every connection has a `start_date`, required at connect, defaulting to the day after the GL account's last
  completed reconciliation (or the first day of the current month when there is none).
* Lines dated before it are not staged (or, for files, staged as `Before cutoff` and shown greyed, so the user
  sees why they were skipped), and are counted on the run.
* **No overlap with completed reconciliations:** a start date on or before the statement date of a completed
  `bank_reconciliation` for any mapped account is refused: "This account is reconciled through 31 Oct 2026; pick
  a start date after that." The same check guards each line at staging. Completed reconciliations lock
  `recon_id` on their journal lines (C11) and on their statement lines.
* **Undo** (B10, only the latest reconciliation per account, `bank.unreconcile`) reopens that window. Lines
  from it already staged stay as they are; earlier skipped lines are not fetched again unless the user moves the
  start date back (an audited change).

---

## 7. Ramp in the holding area (v1.1)

* **Card transactions** go into the Ramp holding area: an `import_batch` per sync run (`import_source` Ramp) and
  one `staged_transaction` per cleared transaction, `txn_type = 'Card purchase'`, with `staged_line` rows from
  its line items (amount, memo, Ramp accounting selections translated through `import_mapping`, F1-F5). It is
  non-posting until every row is coded and approved by a person, under the existing Imports rules: one human
  review, R18 and integrity. `external_ref` is the Ramp transaction id, unique per source.
* **The card account's statement lines:** the same cleared transactions also land in `bank_statement_line` for
  the Ramp card GL account, so the card reconciliation (B12) uses the one matching screen and matches them to the
  entries the holding area posted (14, Q3).
* **Bills (payables):** Ramp bills land as staged `Bill` rows and their payments as `Bill payment` rows, matched
  to their bill before posting (the existing rule: post bills first, then payments).
* **Pending** Ramp transactions are not staged in the holding area. They go to the statement-line table as
  pending only.

---

## 8. Ramp provider (v1.1)

**From Ramp's developer documentation, read 2026-11-13** (docs.ramp.com, the `llms-guides/authorization`,
`getting-started`, `pagination`, `rate-limiting` and `webhooks` pages and the `llms-api` reference):
* **Credential the customer supplies:** a Ramp admin creates an app under Company → Developer with the **Client
  Credentials** grant and read scopes, then pastes the client ID and client secret into StrataLedger. We store
  those two values (section 4); there is no StrataLedger-wide secret, which is the reason for B11a.
* **Token:** `POST {base}/developer/v1/token` with HTTP Basic (client_id:client_secret) and a `scope` field (a
  token without scopes has none). Client-credentials access tokens last 10 days (`expires_in`), with no refresh
  token. Revoke: `POST /developer/v1/token/revoke`. Requests send `Authorization: Bearer <token>`. Base URLs:
  production `https://api.ramp.com`, sandbox `https://demo-api.ramp.com` (tokens work only in the environment that
  issued them).
* **Scopes** (read and write are separate): `transactions:read`, `bills:read`, `cards:read`, `users:read`,
  `accounting:read`, `business:read`. We request only read scopes. `cards:read_vault` (card numbers) is never
  requested.
* **Pagination:** keyset; responses carry `page.next` (a full URL to call unchanged, null at the end); the cursor
  is the opaque `start` parameter; `page_size` defaults to 20, maximum 100.
* **Rate limits:** 200 requests per 10 seconds per source IP (token endpoint 100 per 10 seconds); over the limit
  returns 429 and can block for 60 seconds. Honour `Retry-After` when present; otherwise exponential backoff with
  jitter. 504 means a timeout; retry reads with backoff.
* **Transactions:** `GET /developer/v1/transactions` and `GET /developer/v1/transactions/{transaction_id}`.
  States: `ALL`, `CLEARED`, `COMPLETION`, `DECLINED`, `ERROR`, `PENDING`, `PENDING_INITIATION`. Fields used: `id`,
  `entity_amount.value` (signed, in minor units, with `minor_unit_conversion_rate`; the top-level `amount` is
  deprecated and not used), `currency_code`, `user_transaction_time`, `settlement_date`, `accounting_date`,
  `merchant_name`, `card_id`, `card_holder`, `line_items` (each in minor units), `accounting_categories` /
  `accounting_field_selections`, `receipts`, `updated_at`, `statement_id`.
* **Amounts:** cents = `entity_amount.value` when `minor_unit_conversion_rate` is 100 and the currency is the
  base currency; anything else raises `FeedDataError` (E6, rule 1).
* **Incremental sync:** `synced_after` returns only transactions with an accounting-sync commit, and the docs say
  it is "not a general updated-at filter". Using it would mean writing sync status back to Ramp
  (`/developer/v1/accounting/syncs`, `accounting:write`), which the read-only rule forbids. So the provider uses an
  **overlapping window** (section 5): each sync re-reads from `start_date` or from 45 days before the last sync,
  whichever is later, and the upsert removes the overlap. The cursor stores that watermark date, not a token.
* **Bills:** `GET /developer/v1/bills` (filter `from_created_at`, new records only) and `GET
  /developer/v1/bills/{bill_id}`; `status` `OPEN` or `PAID`, `status_summary`, `approval_status`, `amount`,
  `due_at`, `issued_at`, `paid_at`, `vendor`, `payment`, `line_items`.
* **Webhooks** exist (signed with `X-Ramp-Signature`, HMAC-SHA256), but a desktop app cannot receive them. They
  are for the hosted relay (section 11).
* **Who can connect:** creating the app needs Ramp admin access, and whole-business apps need an Admin or
  Business Owner's approval.

**Unverified, confirm before building:**
* the transaction list's filter parameter names (date range, state, card): the reference lists none by name, so
  the window in section 5 may have to be applied client-side over the full list;
* the units of the bill `amount` (minor units, as for transactions, or not);
* whether bill payments are fully represented in the bill's `payment` object, or need `/developer/v1/payments`,
  and which scope that needs;
* how long a `PENDING` transaction can stay pending before it clears or disappears (the settle window used in
  section 5);
* whether a customer-created client-credentials app can be restricted so it cannot hold write scopes, and whether
  the token response lists the granted scopes (so `test_connection` can refuse a write-scoped credential);
* the error response body and codes for an expired or revoked credential;
* any terms of use that apply to a third-party desktop app using a customer's own credential, and whether a
  partner listing is needed (the partner pages were not read).

---

## 9. Permissions and audit

* **New permission `bank.feed.manage`** (module "Banking", sensitive), seeded to Admin. The Master holds it
  through universal access. It covers connect, test, map accounts, set the start date, replace the credential,
  sync now and disconnect.
* Running the matching screen and completing a reconciliation need their own codes (`bank.reconcile`, and
  `bank.unreconcile` from B10), which are **not in the registry yet**. They are added with the bank
  reconciliation step, not here.
* `bank.feed.manage` is **never** in `AGENT_ALLOWED` (section 10).
* **Audit entries** (company `audit_log` through the table triggers, plus the run rows): connect, disconnect,
  start-date change, account map change, credential replaced (that it happened, never a value), and every sync
  with its counts (`feed_sync_run`). A file upload is a run with `trigger = 'File'`, the file name and its
  SHA-256.
* **Disconnect** (confirm in one step: "Disconnect Ramp? Lines already brought in stay; nothing new will
  arrive."): deletes the secret, calls the provider's `disconnect` (Ramp: revoke the token if one is in memory),
  sets the status to `Disconnected`, and keeps every staged line, map row and run. Reconnecting makes a new
  connection whose start date defaults to the day after the old one's last line.

**Errors** (one sentence each, saying what to do next; codes go to the log only, R27):

| Situation | Message |
|---|---|
| Credential rejected or expired | "Ramp no longer accepts this key; create a new one in Ramp and choose Replace key." |
| Access revoked or app removed in Ramp | "Ramp access was removed for StrataLedger; ask a Ramp admin to approve the app again, then choose Replace key." |
| Rate limited | "Ramp asked us to slow down; the sync will try again in a minute." |
| Offline or timeout | "Ramp could not be reached; check the internet connection and choose Sync now." |
| Ramp server error | "Ramp had a problem on its side; nothing was changed here, and the sync will try again later." |
| Unknown external account | "Ramp sent a new card account (ending 1234); map it to a GL account to bring in its lines." |
| Write scopes on the key | "This key can change data in Ramp; create one with read access only." |
| Non-base currency | "This transaction is in EUR, and this company uses USD only; record it by hand." |
| File not readable | "This file is not a CSV or OFX statement we can read; check the format or choose a column layout." |
| Start date overlaps a reconciliation | Section 6. |

---

## 10. The AI

The AI never reads a secret, never sees `secret_ref` values or the `Secrets/` folder, and never calls a
provider. No feed or secret function is reachable from an agent context: `bank.feed.manage` is not in
`AGENT_ALLOWED`, the feed service refuses `origin = 'Agent'` before anything else (a test), and the Copilot's
tools have no feed tool. The AI may later read staged statement lines through the ordinary read services (to
suggest matches), with the same masking as everyone else.

---

## 11. Hosted note

In the hosted product, a **relay** is one more `FeedProvider`. It holds the vendor-wide secrets that a desktop
installer cannot (aggregator keys, Ramp partner credentials) in Key Vault, receives webhooks (Ramp's signed
`X-Ramp-Signature` events, aggregator callbacks), and keeps normalized lines per tenant connection. Its
`fetch_since(cursor)` returns them with the same `NormalizedLine` shape and a relay cursor. Staging, matching,
cutoff, permissions and audit do not change, because they are all above the interface. A desktop installation
could later use the relay as a client of the hosted service (an option, not decided here).

---

## 12. Test plan (tests first, in the build phase)

* **De-duplication:** the same OFX file imported twice stages each line once; a CSV with two identical rows on the
  same day stages two lines (occurrence number); the same Ramp transaction from two syncs stages once.
* **Idempotent re-sync:** a crash injected after fetch and before commit leaves the cursor and staging unchanged,
  and the next sync produces the same rows as a clean run.
* **Cutoff:** lines before `start_date` are not staged (feeds) or are staged as `Before cutoff` (files) and
  counted; a start date on or before a completed reconciliation is refused; a line dated inside a completed
  reconciliation is refused at staging.
* **Pending to posted:** a pending line is not offered for matching; the same `external_id` arriving posted
  updates the row, not a new one; a pending line that disappears becomes `Removed`, never deleted; a matched
  line never changes on a later sync.
* **Secrets:** after connect, sync, failure and disconnect, the secret's value appears in no log file, exception
  text, `repr`, `raw_json`, `audit_log` row, company or master database, backup, export, cloud-move package or
  support bundle (a test scans each for the value); `SecretKey` cannot be pickled.
* **Disconnect:** the secret is deleted; staged lines, maps and runs remain; status `Disconnected`; a sync on it is
  refused.
* **Provider failure:** each provider error (expired credential, revoked, 429, timeout, 5xx, bad data) leaves
  staging and the cursor unchanged, records a `Failed` run with its code, and gives the sentence in section 9.
* **Matching is identical for file and feed lines:** the same statement through `file_ofx` and through `fake`
  produces the same match suggestions and the same reconciliation.
* **Boundaries:** a provider module cannot import `tx`, `database` or `ledger` (static test); the feed service
  authorizes before its write transaction (the existing rule 10 static test); `bank.feed.manage` is not in
  `AGENT_ALLOWED`; an Agent context is refused.
* **A Ramp card charge is never booked twice (owner, 2026-11-13, BF1):** one cleared Ramp transaction reaches both
  the holding area (`staged_transaction`, which makes the entry) and `bank_statement_line` (which reconciles the card
  account), and the ledger gets exactly one expense for it. Tests: after the holding-area row is posted and the
  statement line synced, the card account and the expense account each move once by the charge's amount; the
  matching screen offers no "Create entry" for a Ramp statement line whose `external_id` has a holding-area row (it
  offers the match to that row's entry, or "waiting for review" while the row is unposted); matching that line to a
  second entry is refused; re-syncing, a pending-to-posted change, and syncing before or after the holding-area post
  all leave one entry; a statement line and a holding-area row are tied by provider, connection and `external_id`,
  never by amount and date alone.
* **Money:** amounts become integer cents exactly; a conversion rate other than 100, or a non-base currency, is
  refused.
* **Ramp (v1.1, against recorded responses, never the live API in the suite):** pagination follows `page.next` to
  null; `Retry-After` is honoured; the overlapping window plus upsert stages each line once.

---

## 13. Phase placement and screens

**v1.0** (with the bank reconciliation step, Phase 4 or the Phase 3 screen work that builds it):
`bank_statement_line`, `feed_connection`, `feed_account_map`, `feed_sync_run`; the provider interface and
registry; `file_csv` and `file_ofx`; the feed service; the `SecretStore` interface with its desktop backend (no
secret is stored in v1.0, but the backup and support-bundle exclusions and their tests land with it);
`bank.feed.manage`; the matching screen. **v1.1:** the `ramp` provider and its holding-area committer. **Later:**
the aggregator add-on. **Hosted:** the relay.

**Screens (described, not built; docs/CLAUDE_UI.md, 0b):**
* **Bank feeds** (Banking): a list of connections, with the provider, GL accounts, status, last sync, and the
  last run's counts; buttons "Import a statement file", "Connect Ramp" (v1.1) and "Sync now". Empty state: "Import
  your first bank statement (CSV or OFX)".
* **Import a statement file** (a short wizard): choose the GL account, choose the file, choose or save a column
  layout for a CSV (F6), preview with counts (new, already imported, before cutoff), then import.
* **Connect Ramp** (wizard): what you need in Ramp (an admin creates an app with read access), paste the client ID
  and secret, test, map each Ramp card account to a GL account, choose the start date, and the K1 limit sentence.
* **Connection details:** account map, start date, run history, Replace key, Disconnect.
* **Matching** (the one screen for every source): unmatched lines beside suggested entries, many-to-one matches
  (B3), "Create entry" for a line with no entry (a draft through the normal services), Exclude, and a Pending
  section that is shown but not matchable.

---

## 14. Questions, decided (owner, 2026-11-13, BF1): every answer below was accepted as proposed

1. **Where do desktop secrets live?** Proposed: files under `DATA_DIR/Secrets/`, encrypted under a key derived
   from the installation key (section 4), rather than Windows Credential Manager, which is per Windows user (P1
   needs every account to open the app). Replacing the installation key (KS13) makes them unreadable, and the
   connections then show "Replace key".
2. **Default sync timer:** proposed every 60 minutes while the app is open, set per company, off allowed.
3. **Ramp card lines in both places:** proposed yes (section 7): the holding area makes the entries, and the
   statement-line table reconciles the card account on the one matching screen.
4. **Write back "synced" to Ramp?** Proposed: not in v1.1 (read-only scopes only). Revisit if the overlapping
   window proves too slow.
5. **Window size for Ramp re-reads:** proposed 45 days, to be confirmed against how long Ramp transactions stay
   pending or change (section 8).
6. **The `bank.reconcile` and `bank.unreconcile` codes:** proposed: add them with the bank reconciliation step,
   seeded to Admin, Controller and Accountant (to be confirmed against docs/role_templates.md then).

**Baseline gaps (report only; nothing changed):** `bank_statement_line`, `feed_connection`, `feed_account_map`
and `feed_sync_run` do not exist; `bank_reconciliation` has no lock on `recon_id` after completion (C11) and no
`completed_by` or `completed_at`; there is no `bank.*` permission; `import_source` has no Ramp row seeded (check
when the Imports step is built).
