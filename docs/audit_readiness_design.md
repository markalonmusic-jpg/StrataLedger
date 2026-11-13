# Audit readiness design (DESIGN, NOT BUILT)

**Date:** 2026-11-12 · **Status:** design approved with changes (decisions K1-K12 and P5 in
`docs/decisions_2026-11-11.md`). Built so far: Step 1b (the chain schema and the pure
`modules/services/ledger_chain.py`), Step 3 (posting seals every entry) and Step 3b (the verify service,
`modules/services/ledger_verify.py`, and the `ledger_integrity` close check). Everything else is design. Build order is in section 12.

Read with: `docs/controls_audit.md`, `docs/roles_permissions_design.md`, decisions A5, L1-L8, B10, E7, H1-H5,
P1-P5, U5, and CLAUDE.md backlog item 11 (issuing a new Master recovery code).

**What the product claims.** StrataLedger is *designed to support audit-ready record keeping*. Its ledger is
*tamper-evident*: changes made outside the app are detected and the first changed entry is named. It is not
tamper-proof, it is not certified, and it does not claim to meet any particular standard or regulation.
Screens, help pages and marketing use only these words.

---

## 1. Threat model

| Who | What they can do | What stops it or reveals it |
|---|---|---|
| **Outsider with a copied company file** (stolen laptop, copied backup, cloud-synced second folder) | Read everything in v1, because files are not encrypted (U5). Edit the copy. | Reading: Windows BitLocker (recommended in the setup guide), and encryption at rest after v1 (section 4). Editing: the chain key is not in the file, so a changed entry cannot be resealed and verification names it (section 2). |
| **Another Windows user on the same computer** | Read and copy files in the shared data folder (P1 puts it in `%PROGRAMDATA%`, shared by every account). Run code as themselves. | Folder permissions set by the installer (**not built yet**: today the data folder keeps the permissions it inherits, which let every local user read it; roadmap backlog 17). **Limit, stated plainly:** the installation key is wrapped with machine-scope DPAPI (K1), so any local user who can run code can unwrap it. DPAPI protects the key from a copied disk or file, not from another account on the same running computer. |
| **Curious staff** (an app user looking at data they should not) | Use screens and reports. | Permissions in services (rule 10), masking of tax IDs, bank details and wages, project scope, denials logged in `access_event`. |
| **A user trying to change history through the app** | Edit or delete posted entries; backdate; reopen periods. | Posted records are locked (baseline triggers); corrections are reversals; closed periods refuse posting; reopening needs a permission, a reason and a confirmation (L7); every change is in `audit_log`. |
| **A user editing the file with an outside tool** (DB Browser, a script) | Drop triggers, edit or delete posted rows, flip `is_void`, renumber entries. | The keyed chain: they do not hold the key, so verification fails at the first changed entry (section 2). The cross-check catches an `is_void` flip. The check runs at every company open and before backups. |
| **An app Admin** | Change controls, users and roles; turn approvals off. | Every change is audit-logged; Audit-ready mode shows what is off (section 8); the chain and checkpoints still cover the ledger. An Admin cannot edit a posted entry through the app. |
| **Who we cannot stop: the machine's owner holding both the key and the code** (Windows administrator plus the Master, or anyone with the recovery code and the file) | Unwrap the key, rewrite history, reseal the whole chain, edit `audit_log`. | **Nothing inside the computer can prevent this.** It is revealed only by **checkpoints held outside the computer**: a chain head printed on a signed close report, sent to an auditor or kept in a backup elsewhere no longer matches (section 3). |

Out of scope for v1: malware running as the user, a modified build of StrataLedger, and hardware attacks.
The hosted product (P5) changes this model; it gets its own threat model when it is designed.

---

## 2. Tamper-evident ledger

### 2.1 What the chain is
Every posted journal entry carries a seal:

    chain_hash(N) = HMAC-SHA256(chain_key, message(N))
    message(N)    = "SLJ1" 0x00 company_code 0x00 chain_prev_hash(N) 0x00 canonical_json(entry N)
    chain_prev_hash(N) = chain_hash(N-1); for entry 1 it is 64 zeros

* Order is `entry_number`, the gapless posting sequence (L4). A missing, inserted or renumbered entry breaks
  the link.
* `company_code` is immutable (S1) and binds the chain to the company, so entries cannot be copied from
  another company's file with their seals.
* `chain_hash` and `chain_prev_hash` are stored as 64 lowercase hex characters (text, portable). Storing
  the previous hash makes the break point local and obvious.
* HMAC-SHA256 comes from Python's standard library (`hmac`, `hashlib`); no new package is needed for the
  chain itself.

### 2.2 What is hashed (owner item a)

**Entry header** (all in `journal_entry`):
`entry_id, entry_number, entry_date, period_id, reference, description, source, origin, created_by,
created_at, posted_by, posted_at, approved_by, approved_at, reverses_entry_id, reversal_reason,
reversal_note, auto_reverse_date, chain_version, chain_key_id`.

`approved_by` and `approved_at` are hashed as stamped at posting (null when the entry needed no approval).
`chain_version` and `chain_key_id` are hashed so a seal cannot be moved to another format or key.

**Every line**, ordered by `line_id`: `line_id, entry_id, account_id, debit_cents, credit_cents, memo, contact_id,
project_id, cost_code_id, deferral_id, batch_id, is_retainage_line, external_ref, is_control_override,
is_rounding_adjustment`, plus its dimensions as a list of `[dimension_type_id, dimension_value_id]` pairs
sorted by type id. Editing, adding, deleting or swapping a line, or changing a dimension, changes the hash.

### 2.3 What is not hashed (owner item b)
Only state that legitimately changes after posting, plus the seal itself:

| Column | Why excluded | How tampering is still caught |
|---|---|---|
| `journal_entry.is_void` | The baseline trigger sets it when a Void reversal posts. | The cross-check (2.6): `is_void = 1` exactly when a posted, chained Void reversal of the entry exists. The void itself is evidenced by the reversal entry's own place in the chain. |
| `journal_entry.is_posted` | Always 1 on a sealed entry. | A sealed entry with `is_posted = 0` fails the baseline CHECK and verification. |
| `journal_line.recon_id` | Bank reconciliation sets it and B10 can undo it. | Reconciliation has its own audit rows. |
| `chain_hash`, `chain_prev_hash` | They are the seal. | Recomputed during verification. |

**Column classification test.** `ledger_chain.py` declares `HASHED_ENTRY`, `EXCLUDED_ENTRY`, `HASHED_LINE`
and `EXCLUDED_LINE`. A static test compares them with the columns of `journal_entry`, `journal_line` and
`journal_line_dimension`, so a new column (for example B13's `source_doc_type` / `source_doc_id`) fails the
build until someone decides which list it belongs in. A newly hashed field bumps `chain_version`. The
verifier keeps every old version, and old entries keep their version.

### 2.4 Canonical serialization, database-agnostic (owner item i)
The bytes that are hashed must be the same in SQLite today and PostgreSQL later (P5), and the same after a
backup and restore. So the canonical form is defined on **values**, never on driver output or row order.

* JSON object with keys sorted, no spaces (`separators=(",", ":")`), UTF-8, `ensure_ascii=False`.
* Integers are JSON integers. There are no floats in the journal tables; a float found there is a
  verification failure, not something to round.
* NULL is `null`. Booleans and flags are the integers 0 or 1.
* Text is exactly as stored (no trimming or Unicode normalisation at hash time; services trim before they
  write).
* Dates are `YYYY-MM-DD`. Timestamps are normalised to `YYYY-MM-DDTHH:MM:SSZ` (UTC, whole seconds) from
  either stored form. This also absorbs the known `CURRENT_TIMESTAMP` versus `utc_now_iso()` format
  difference (CLAUDE.md, Timestamps).
* Lines are sorted by `line_id` in Python, and dimensions by type id; the SQL order is never trusted.
* The entry is `{"entry": {...header...}, "lines": [ {...line..., "dimensions": [[t, v], ...]}, ... ]}`.

**Golden vectors.** `tests/data/ledger_chain_vectors.json` holds fixed inputs: a key, a company code, a
previous hash and an entry with lines. It also holds the exact canonical bytes (hex) and the resulting
`chain_hash`. A test checks them byte for byte. The same file must pass unchanged against the PostgreSQL
port. Changing it means a new `chain_version`, never an edit.

### 2.5 Posting, concurrency and rollback (owner items c and j)
The seal is computed **inside the posting write transaction**, in Python (H4, H5), in this order:

1. **Lock the counter row.** SQLite: `BEGIN IMMEDIATE` (one writer at a time). PostgreSQL:
   `SELECT last_number FROM entry_number_sequence WHERE id = 1 FOR UPDATE`.
2. **Read** `last_number` and the `chain_hash` of that entry (64 zeros when there is none).
3. **Increment** the counter (`last_number + 1`, which the baseline trigger allows only by one).
4. **Write** the entry with `is_posted = 1`, its number, `posted_by` / `posted_at`, the four chain
   columns and the seal, in one UPDATE.
5. Commit.

* A failed post rolls back the counter, the number and the seal together, so numbers stay gapless and the
  chain has no hole. There is no separate "head" row to drift: the head is the entry with the highest
  `entry_number`.
* Two posts at the same time serialise on the counter-row lock; the second one reads the first one's hash.
  The same steps port to PostgreSQL as written (P5).
* **Everything posted is sealed the same way**: manual entries, document entries (invoices, bills,
  payments), import and payroll batches, rounding lines (L8), auto-reversals (L5, sealed right after their
  original in the same transaction), and both halves of a pair void (R4). An unsealed posted entry cannot
  exist (baseline CHECK, section 14).
* **No key, no posting.** If the key provider cannot supply the active chain key, posting is refused:
  "This computer cannot seal ledger entries right now. Ask the Master to sign in and restore the ledger key
  with the recovery code." Drafts can still be saved.
* **No baseline trigger checks the previous hash** (owner decision). The service computes it and
  verification catches any mismatch. The baseline only enforces shape (CHECKs) and immutability (locks).

### 2.6 Verification
`ledger_chain.verify(conn, provider, *, from_entry=1)` walks entries in number order and checks, for each one:

1. the number is the previous number plus one;
2. `chain_prev_hash` equals the previous `chain_hash`;
3. the recomputed HMAC equals `chain_hash`, using the key named by `chain_key_id`;
4. `chain_version` is known and the row has no float values.

It then runs the void cross-check (2.3) and checks that no posted entry is missing its seal. It returns
`{"ok", "through_entry_number", "chain_hash", "first_broken": {"entry_number", "entry_id", "reason"} | None}`.
It stops at the first break, because later entries chain from it.

**Incremental verification (owner item e).** The last successful verification is written as a checkpoint
row of kind `Verify` (section 3). That row carries its own MAC over its fields, so a forged "verified
through N" marker is detected and treated as no marker.

* **At company open:** check the marker's MAC, check that entry N still has the hash recorded in the
  marker, then verify only entries N+1 onward. This is fast however large the ledger is.
* **Full check:** on demand ("Verify ledger integrity"), before every backup, at period and year close,
  and whenever the marker fails.
* **Limit:** an incremental check does not re-read entries 1..N, so an old changed entry is found at the
  next full check.

**Severity (owner item f).**
* A new period-close check, `ledger_integrity`, is a warning by default and a block when the company turns
  on Audit-ready mode (section 8), following L2.
* At company open a failure shows a prominent banner. It never locks anyone out of their books.
* Posting continues by default with a warning, because the break is in history. In Audit-ready mode
  posting is refused until a full verification passes. Posting is never possible without the key (K3).

**Plain-language message**, naming the first broken entry:

> "Ledger check failed at entry JE-000123 (dated 2026-03-15, posted by M. Alon on 2026-03-16). It no longer
> matches the seal recorded when it was posted, so it may have been changed outside StrataLedger. Entries
> before it are intact. Restore a backup made before 2026-03-16, or ask your accountant to review."

**Background work (K17, backlog 14):** a full verification can take tens of seconds on a large ledger (about
26 s for 100,000 entries as measured in Step 3b), so every screen that starts one (Ledger integrity "Verify now",
period close, year close, Books closed through, and later backups) must run it in the background, show progress
(entries checked out of the total) and keep the window responsive; the result arrives when it is done. The
incremental check at company open is short and can stay in the foreground until the ledger is large.

**Screen** (Phase 3): Settings > Ledger integrity. It shows the last check (when, by whom, scope, result)
and the current checkpoint. It has a "Verify now" button, a box to paste an auditor's checkpoint and
compare it, and the history of checks. Running a check needs `ledger.verify` (K7).

### 2.7 Keys (owner items d and k)
* **One chain key per company**: 32 random bytes from the operating system's secure source
  (`ledger_chain.new_key()`, Python `secrets`), never stored in the company file. The company file holds
  only `ledger_chain_key` rows: id, dates, and a public **fingerprint**.
* **The fingerprint is domain-separated:** `HMAC-SHA256(key, "StrataLedger chain key fingerprint v1")`, as 64
  lowercase hex characters (`ledger_chain.fingerprint`). It identifies the key and reveals nothing about it.
  Because the fixed label differs from every seal message, a fingerprint can never equal a seal or be reused
  as one. A test fixes its format and value.
* **Key provider interface** (`modules/services/keys.py`), the one wrapper for secrets (P5):

      class KeyProvider(Protocol):
          def chain_key(self, company_id, key_id) -> SecretKey          # raises KeyUnavailableError
          def active_chain_key(self, company_id) -> tuple[int, SecretKey]
          def create_chain_key(self, company_id) -> tuple[bytes, SecretKey]   # fingerprint, key
          def retire_chain_key(self, company_id, key_id, reason) -> None

  Backends:
  * `FixedTestKeyProvider`: tests only, a constant key. It refuses to load unless the test flag is set.
  * `NullKeyProvider`: the default until Step 1c. It always raises, so posting is refused outside tests.
  * `LocalKeyProvider` (Step 1c): DPAPI plus the recovery code (below).
  * `AzureKeyVaultProvider` (hosted, P5): later; services do not change.
* **SecretKey** wraps the bytes. `__repr__` and `__str__` return `<SecretKey redacted>`, it cannot be
  pickled, its value is reachable only through a method named `use_for_hmac()`, and it is never placed in a
  `ServiceContext` (contexts appear in tracebacks and logs). Exceptions name the key id, never the key.
* **Local key hierarchy (Step 1c):**
  * An **installation key** (32 random bytes) is created at first-run, when the Master and the recovery code
    are created (S10). Two wrapped copies go in the master database (`installation_key`):
    * one wrapped with **DPAPI, machine scope** (`CryptProtectData` with `CRYPTPROTECT_LOCAL_MACHINE`,
      through `platform_support.py`, the one module for OS calls, P3/H1), so every Windows account on the
      computer can open the app (P1);
    * one wrapped with the **Master recovery code**: scrypt (its own salt, never the login hash's) gives a
      key-encryption key, used with AES-256-GCM from the `cryptography` package (K2). Confirmed 2026-11-12:
      `cryptography` 50.0.2 (Apache-2.0 OR BSD-3-Clause; cffi MIT-0, pycparser BSD-3-Clause), OpenSSL 4.0.3
      built into its own extension; a PyInstaller 6.22.3 one-file build runs AES-GCM and scrypt and adds about
      3.7 MB (`tools/check_frozen_crypto.py`).
  * **Company chain keys** (and later encryption keys) are random and stored in the master (`company_key`),
    wrapped by the installation key with AES-GCM.
  * The recovery code is in clear only at first-run, at Master recovery and when backlog item 11 issues a
    new code; at each of those moments the recovery-wrapped copy is rewritten. **Backlog item 11 must
    re-wrap the installation key**, or a new code would not open it.
  * **Moving to a new computer:** DPAPI fails there, so the Master signs in with the recovery code; the
    installation key is unwrapped with it and re-wrapped with the new machine's DPAPI.
* **Export with a company** (K8): the company's chain keys travel only inside the passphrase-protected
  company bundle (AES-GCM; the key comes from a passphrase the Master types). Only the Master can export or
  import one. A plain `export_company` copy carries no keys: it can still be read, but its chain can be
  verified only on the source installation. Until the bundle is built, `export_company` returns the warning
  `EXPORT_NOT_VERIFIABLE` with its path, and the export screen must show it (KS11).
* **Master tables (built in Step 1c sub-step 4):** `installation_key` (one row: the public `fingerprint`,
  `machine_blob` + `machine_wrapped_at`, both NULL while this computer has no DPAPI copy, `recovery_salt` (16
  bytes), `recovery_blob` (61 bytes), `recovery_wrapped_at`, `created_at`; the blobs may be re-wrapped, the
  fingerprint, `created_at` and id never change, and the row is never deleted) and `company_key` (`company_id`,
  `purpose` `chain` or `encryption`, `fingerprint`, `wrapped_key` (61 bytes), `created_at`; append-only, unique
  per company, purpose and fingerprint, and no ON DELETE, so a company with keys cannot leave the registry).
  Neither is audited (KS9); `auth_event` gained the event types `Installation key created`, `Installation key
  rewrapped`, `Recovery code issued`, `Ledger key created`, `Ledger key rotated`, `Ledger key lost` and an
  optional `company_id`. A wrapped key is `version | nonce | ciphertext | tag` (`key_wrap.py`); its associated
  data names the row (`associated_data("company_key", company_id, purpose, fingerprint)`), so a blob copied to
  another row does not open.
* **As built in Step 1c sub-steps 5-6:**
  * The installation key's fingerprint is `HMAC-SHA256(key, "StrataLedger installation key fingerprint v1")`;
    the recovery copy's associated data is `("installation_key", 1, "recovery", fingerprint)`.
  * `auth.create_first_master(..., machine_wrap=)` makes the key in the Master's transaction. The first-run screen
    passes `platform_support.DPAPI`. Without a DPAPI copy the Master is created and `ledger_key_locked` is True;
    without a recovery copy nothing is created. An installation that already has a key refuses a second first run.
  * `LocalKeyProvider` is set by `App.start_key_store()` before the launcher and after first-run sign-in. It
    holds the installation key in memory for the life of the process and caches unwrapped chain keys.
  * `create_company` gets the chain key from the provider before building anything (KS6), then writes the file's
    key row and, in the registry's master transaction, the `company_key` row and a `Ledger key created`
    auth_event.
  * The first-run code screen says "The ledger key could not be saved for this computer. ..." when the DPAPI
    copy was not made (sub-step 7).
* **As built in Step 1c sub-step 7 (every new recovery code re-wraps the installation key):**
  * `auth.recover_master(path, code, new_password, machine_wrap=)` opens the key with the old code and, in the
    same transaction, re-wraps the recovery copy with the new code and the DPAPI copy for this computer (a new
    computer, or a key locked since first run, is restored this way). A failed DPAPI wrap keeps the old copy.
  * `auth.change_master_password(session, password, code, new_password)` (PW9) and `auth.issue_recovery_code(
    session, password, machine_wrap=)` (backlog 11: the DPAPI copy opens the key; refused while it is locked).
  * Each returns `CodeIssued(recovery_code, ledger_key_restored, message)`. A valid code whose copy does not open
    still resets the password, with `LEDGER_KEY_NOT_RESTORED` (KS5). Events: `Installation key rewrapped`,
    `Recovery code issued`, `Password changed`, `Master recovered`.
  * Not changed: `auth.change_password` still lets the Master change the password without the code (no PW9
    screen exists yet); step 2.8 switches the Master's screen to `change_master_password`.
* **As built in Step 1c sub-step 8 (rotation):** `ledger_keys.rotate_chain_key(session, company_id)`, Master only
  (no new company permission, so the company baseline is unchanged). Order: the key store must be able to make a
  key; a full check under the current key (refused with `ROTATION_NEEDS_KEY` when that key is not available here);
  the new wrapped key and a `Ledger key rotated` auth_event in the master; the old key retired (`Rotation`) and the
  new one active in the company file; then the check signed as a `Key rotation` checkpoint with the NEW key
  (`ref_type` `ledger_chain_key`, `ref_id` the retired key), in the file and the mirror. A rotation over a Broken
  ledger is allowed and its checkpoint says Broken. A checkpoint that cannot be saved never undoes the rotation
  (`checkpoint_error`).
* **As built in Step 1c sub-step 9 (key lost):** `ledger_keys.start_new_key_epoch(session, company_id,
  confirm_company_code=)`, Master only, the company code typed. For a company whose active key cannot be opened
  here while the installation key can (refused with `KEY_STILL_AVAILABLE` when the key still opens: rotate it).
  The old key is retired as `Key lost`, a new key becomes active (wrapped in the master, `Ledger key lost`
  auth_event; the company file's audit trigger records the retirement), and posting goes on: the next entry
  chains to the last stored hash. A full check stays Unavailable (never Broken) because the old entries need the
  lost key; the result names the last entry sealed before the epoch. **Two open points (owner decision):**
  1. **No epoch checkpoint is signed.** `ledger_checkpoint.result` allows only OK and Broken, and signing
     unverified history as OK would claim a check that did not happen; the incremental verifier would also
     re-check the anchor entry with the lost key. An honest epoch needs a new result or kind (for example
     `Key lost` with result `Unverified`) and a verifier that starts after the epoch's entry. Both change the
     company baseline.
  2. **A lost installation key** (DPAPI unusable and the recovery code lost, or KS5's damaged copy) loses every
     company key at once, and no new company key can be stored, because `installation_key` can never be replaced.
     Recovering needs a new installation key epoch (replace the row, recorded, with every company then starting
     a new key), which changes the master baseline's `installation_key_same_key` trigger.
* **Changed after the Step 1c review:**
  * Rotation needs only the CURRENT key to open here (not the whole history): after a key-lost epoch the full
    check is Unavailable, the rotation goes on and signs no checkpoint, and its result says why. This removes a
    loop in which rotation sent the user to the epoch and the epoch sent them back to rotation.
  * KS5: when the recovery copy is damaged but this computer's DPAPI copy opens, `recover_master` and
    `change_master_password(..., machine_wrap=)` rebuild the recovery copy from it with the new code.
    `LEDGER_KEY_NOT_RESTORED` now means both copies failed (open point 2 above).
  * `LocalKeyProvider` reads the company file's fingerprint on every `get_key` and caches by fingerprint, so a
    company file replaced in the same session (restore, Phase 5) never gets the key cached for the file it
    replaced.
  * `FirstMaster` and `CodeIssued` show `<redacted>` for the code and cannot be pickled or copied.
  * `scripts/create_fresh_databases.py --sample-company` sets the `LocalKeyProvider` itself.
  * For step 2.8: after a recovery restores the key, the running app must call `App.start_key_store()` again,
    or it stays locked until the next start.
* **The master holds every company's keys** (KS10): `system_master.db` stores each company's wrapped chain keys,
  so losing it makes every company's ledger unverifiable, though the data stays readable. Every company backup
  must therefore also back up the master (section 9).
* **Rotation:** "Rotate ledger key" (Master) creates a new key, retires the old one (`Rotation`) and writes
  a checkpoint. The next entry is sealed with the new key and chains to the old key's last hash. Old keys
  are kept, wrapped, forever, because verification needs them.
* **Key lost** (DPAPI unusable and recovery code lost): the ledger data is still readable (the chain is not
  encryption). Entries sealed with the lost key can no longer be verified. The Master starts a new key epoch
  (`Key lost`, recorded with a checkpoint and a sensitive audit entry); Audit-ready mode shows "history
  before entry N cannot be verified" until the next year close.

---

## 3. Checkpoints
A checkpoint is the chain head at a moment, in a form people can keep:

    SL1-ACME-JE000123-3f9a1c2e...(64 hex)

Screens show the first 16 hex characters in groups (`3f9a-1c2e-77b0-41d5`); exports show all 64.

**Where checkpoints are written:**
* the `ledger_checkpoint` table in the company file (append-only, each row MACed, audit-logged by its
  insert trigger, so the head is also in `audit_log`);
* a mirror row in the master (`chain_checkpoint`), so restoring an old file cannot erase what this
  computer saw;
* every backup's manifest (section 9);
* the footer of the period-close report and of every report export (the export design adds the footer
  hook).

**Kinds:** Verify, Period close, Year close, Report export, Backup, Restore, Key rotation, Manual.

**Close checkpoints (built):** a successful period close, Books closed through (one for the last month it
closes) and year close each sign the full verification they ran as their close check, as a `Period close` or
`Year close` checkpoint (scope empty, `ref_type` `fiscal_period` / `fiscal_year`, `ref_id` the period or year),
in the file and the master mirror, after the close commits. The ledger is checked once per close. A close that
is refused records nothing; Unavailable records nothing (K16); a close past an acknowledged broken ledger
records a Broken checkpoint. A checkpoint that cannot be written never undoes the close: it is logged and the
close's result says so in one sentence.

**Auditor workflow:**
1. At year end the client sends the signed period-close or year-close report. The auditor records the
   checkpoint printed on it (in working papers, outside the client's computer).
2. Next year the auditor signs in with the Auditor role (section 6), opens Ledger integrity and pastes the
   recorded checkpoint.
3. The app runs a full verification and recomputes the hash at that entry number.
   * **Match:** entries 1..N are the same as when the report was printed.
   * **No match:** the app names the first entry at or before N whose seal differs from the chain the
     auditor recorded.
4. This is the only defence against the "owner with key and code" in section 1: rewriting and resealing
   history changes the head at N.

The app also compares itself with its own mirrors: at open and at restore, every master checkpoint for this
company with number at most the current head must match the file's chain.

---

## 4. Encryption at rest

**Decision unchanged: U5 stands** (standard SQLite in v1.0; optional encryption after v1; BitLocker
recommended). This section prepares for it, so v1.0 ships nothing that would block it.

### 4.1 Options for this repository (all facts here: "confirm before building")

| Option | Python on Windows | Licence | PyInstaller | Notes |
|---|---|---|---|---|
| **SQLite3 Multiple Ciphers DLL** in place of `sqlite3.dll`; keep the standard `sqlite3` module | Python's `_sqlite3.pyd` loads `sqlite3.dll` dynamically on Windows, so a drop-in DLL may work with no code change. *Confirm* ABI compatibility with Python 3.11 and the SQLite version (the baseline needs `RETURNING`, 3.35+). | MIT (*confirm*) | Ship the DLL in the bundle under the expected name; *confirm* PyInstaller picks it over the system DLL. | Can read and write the SQLCipher format (*confirm* the cipher settings). Least code change; preferred if it works. |
| **sqlcipher3** (DB-API module modelled on `sqlite3`) | Official wheels may be Linux-only; third-party Windows wheels may exist (*confirm* for cp311-win_amd64). Building needs MSVC and OpenSSL. | SQLCipher Community Edition: BSD-style (*confirm*); commercial editions from Zetetic. | Normal native extension. | `import sqlite3` becomes `import sqlcipher3` in `database.py` only, which needs the single connection point (section 5). |
| **pysqlcipher3** | Unmaintained (*confirm*). | | | Not recommended. |

* **Speed:** page-level AES-256 typically costs a modest overhead (*confirm* by running the full test suite
  and a 100k-entry verify, encrypted and not). Open with a raw 32-byte key (`PRAGMA key = "x'..'"`) to skip
  the slow passphrase KDF; the key is random, so stretching adds nothing.
* **Outside tools:** DB Browser for SQLite (the repository keeps a `.sqbpro` project) cannot open an
  encrypted file. Its SQLCipher build can, with the raw key, which a developer export tool would have to
  reveal on purpose. The reference snapshot `accounting_librebase.db` stays unencrypted (it holds no data).
* **Tests:** the suite runs unencrypted by default, plus one encrypted job running the database, backup and
  ledger tests.

### 4.2 Keys and lifecycle
* One random encryption key per company file, wrapped exactly like the chain key (2.7), purpose
  `encryption` in `company_key`.
* **Rekey/rotation:** `PRAGMA rekey` on a copy, verify the copy (integrity check and full chain verify),
  swap the files, keep a backup. The PRAGMA lives in `database.py` only (H5).
* **Backups** are copies of the encrypted file, so they are encrypted with the same key. A backup made
  before encryption was turned on stays readable; the setup screen offers to delete or re-make old
  unencrypted backups.
* **Key lost = data lost**, including every backup. This is why the installation key has two wraps and why
  backlog item 11 is a hard prerequisite.

### 4.3 Recommendation and go/no-go checklist
Recommendation: **no-go for v1.0** (U5). Build the key hierarchy (Step 1c) and the single connection point
(Phase 3) in v1.0, then add encryption as an opt-in in v1.1 when every item below is green.

- [ ] Backlog item 11 built; it re-wraps the installation key.
- [ ] Every connection goes through `database.py`, the static test has an empty allow-list, and scripts and
      tools use it too (section 5).
- [ ] The chosen library verified on Windows 10 and 11 in the PyInstaller build, its licence reviewed.
- [ ] Full test suite green against the encrypted build; speed measured and acceptable.
- [ ] Backup and restore (section 9) built, and they round-trip an encrypted file.
- [ ] Rekey on a copy, with rollback, tested.
- [ ] Key-loss recovery flow (recovery code, new computer) tested end to end.
- [ ] The support bundle (U4) never includes keys; the opt-in company file is described as encrypted.
- [ ] The setup guide explains BitLocker and the recovery sheet.

---

## 5. Single connection point
**Finding (today):** not yet. All production opens in `modules/` go through `database.get_connection`,
`get_readonly_connection` (`mode=ro`) or the migration runner, except:

* `app_strata.pyw` and five Phase 3 screens (`views_billing.py`, `views_payroll.py`, `views_registry.py`,
  `views_user_profile.py`, `views_wizard.py`), which call `sqlite3.connect` directly. They are already
  named in the rule-11 allow-list of `tests/test_static_rules.py`, which must be empty by the end of
  Phase 3.
* `scripts/` and `tools/`, which are exempt by prefix.

**Proposal** (extend the existing test; no new mechanism):
1. Also catch aliases: `from sqlite3 import connect`, `import sqlite3 as x` followed by `x.connect`,
   `sqlite3.dbapi2.connect`, and any import of `apsw`, `sqlcipher3` or `pysqlcipher3` outside `database.py`.
2. Catch `.backup(` on connections and `shutil.copy*` of `.db` paths outside `database.py` and the future
   backup service (an encrypted file must be copied by code that understands it).
3. Before encryption ships, remove the `scripts/` and `tools/` exemption: they open files through
   `database.py` helpers too (an encrypted file cannot be opened by a plain `sqlite3.connect`).
4. A test that `database.get_connection` is the only place `PRAGMA key` / `rekey` appears (H5 already
   keeps PRAGMAs in `database.py`).

---

## 6. Auditor role
* **A 12th starter role, "Auditor"** (K9), added to `docs/role_templates.md` and `role_templates.py`.
  * It holds every non-sensitive `*.view` code, `report.financial`, `report.job_cost`, `report.export`,
    `audit.view` and `ledger.verify`.
  * Sensitive views (`view.tax_ids`, `view.bank_details`, `payroll.view`) only if an Admin grants them
    (K4).
  * It holds no create, post, approve, void, settings or user code. A test checks the template against a
    read-only list, so a write code cannot slip in.
* **Read-only open.** `companies.open_company(session, company_id, read_only=True)` returns a context with
  `read_only=True`, and opening as an Auditor always sets it.
  * `tx.write_transaction` refuses a read-only context before it opens a connection (one sentence: "This
    company is open read-only.").
  * All reads already use `database.get_readonly_connection` (`mode=ro`).
  * Defence in depth: even a permission mistake cannot write.
  * *Confirm before building* that `mode=ro` works with the file's journal mode.
* **Verification by the Auditor** runs read-only. It writes no checkpoint into the company file; it records
  its result in the master (`chain_checkpoint`, kind `Verify`, by the Auditor's user id) and shows it.

---

## 7. Audit trail reports
All of them are exportable through the export design (not written yet); every export carries a checkpoint
footer. All need `audit.view` except the journal listing (`report.financial`).

| Report | Source | Notes |
|---|---|---|
| Full journal listing | `journal_entry`, `journal_line`, dimensions | Number, dates, who created / posted / approved, origin, reversal links, seal status per entry. |
| User activity and logins | master `auth_event`, company `access_event`, `audit_log` by user | Logins, failures, lockouts, company opens, denials, writes per user. |
| Permission and role changes | company audit rows on `role`, `role_permission`, `approval_limit`, `user_project_scope`; master `audit_log` on `user_company_access`, `app_user` | Who changed which role or grant, before and after. |
| Period reopens | `period_status_history` | Reason, who, when; year reopens included. |
| Control overrides | `journal_line.is_control_override`; later match and compliance overrides with reasons | The same data as the `control_overrides` close check. |
| Voids and reversals | `journal_entry.reverses_entry_id`, `reversal_reason`, `reversal_note` | Includes auto-reversals and pair voids. |
| Self-approved items | `self_approved` flags (R3, roles design section 5) | The banner when separate approver is off. |
| Settings changes | audit rows on `company_settings`, `document_approval_setting`, `period_close_check` | Every control change. |
| Backup, restore and verification events | master `backup_event`, `chain_checkpoint` | Checksums, results, Master overrides (K5). |

---

## 8. Audit-ready mode
Settings > Controls > **Audit readiness**, a checklist with a status per line (on / off / attention).
* **Opt-in.** Controls stay off by default (section 0 of CLAUDE.md); a small company never sees this
  unless it opens the page.
* **No hidden flag.** The status is worked out from the settings themselves. "Audit-ready" means every
  recommended line is on.

| Line | Setting it reads or sets |
|---|---|
| Separate approver | `require_separate_approver = 1` |
| Journal entry approval | `manual_entry_approval = 1` (threshold as chosen) |
| Document approvals | `document_approval_setting` for Bill and Payment |
| Manual entries to controlled accounts | `allow_manual_control_je = 0` |
| Close checks as blocks | `period_close_check` mode `block` for every check, including `ledger_integrity` and `control_overrides` |
| Ledger verified | a full verification passed in the last 31 days |
| Backups | nightly backups on, a second folder set (E7) |
| Recovery code | the Master confirmed it is saved (backlog item 11) |
| Restores with mismatched checksum | none, or each one reviewed (K5) |
| Disk encryption | BitLocker status, for information only (*confirm* it can be detected without admin rights) |

**"Turn on the recommended set"** (needs `company.settings`; Admin or Master):
1. A preview lists exactly what will change.
2. The user confirms.
3. Each change goes through the existing `company_settings` / `periods.set_close_check_mode` services, so
   each is audit-logged as usual.

Turning lines off again is done one at a time, and each change is logged.

---

## 9. Backups
The E7 backup service (`modules/services/backups.py`, through `storage.py`, H3) is not built yet. When it
is:
* **Before a backup:** a full chain verification. A failure is shown and recorded, but the backup is still
  made, because a backup of a damaged file is still worth keeping. The failure is flagged in the manifest.
* **At backup time:** a consistent copy with the SQLite backup API, then **SHA-256** of the file. A
  manifest (`<file>.manifest.json`) records:
  * company code and id, size, sha256;
  * chain checkpoint, schema baseline hash, app version;
  * who made it and when, and the verification result.

  The manifest is MACed with the installation key. A row in the master `backup_event` table (append-only)
  holds the same data. The backup also writes a `Backup` checkpoint.
* **On restore** (`company.restore`, sensitive, typed confirmation per 0b):
  1. Check the file's SHA-256 against the master record and the manifest.
  2. Make a safety backup of the current file (E7).
  3. Run a full chain verification on the restored copy.
  4. Compare it with the master's mirrored checkpoints.
  5. Swap the files.
  6. Write a `Restore` checkpoint.
* **Checksum mismatch** (K5): refused, except for the Master with a typed confirmation and a reason. A
  safety backup is made first, the event is logged as sensitive, and it is flagged on the Audit-ready
  checklist until reviewed.
* **Logged as sensitive:** every backup, restore, refusal and override is written to `backup_event` and the
  audit trail.
* **The master travels with every backup** (KS10): it holds the wrapped chain keys of every company, so a
  company backup without a matching master backup cannot be verified after the master is lost.

---

## 10. Attachments as audit evidence (hook only)
When the attachments design exists (the `attachment` table is sketched in `docs/crm_pm_design.md`; the AI
design's `document` table stores a file hash), it must:
* record each file's SHA-256 at upload;
* write an audit row naming the record it supports;
* never delete or replace an attachment of a posted record (a new version is added instead);
* show attachments in the journal listing.

The chain covers entries, not files. A later "evidence seal" can chain attachment hashes the same way. The
hook is a single function in `ledger_chain.py`, `record_evidence(conn, record_type, record_id, sha256)`, to
be designed with that work.

---

## 11. Test plan (tests are written first in each build step)

**Chain and verification (Steps 1b and 3):**
1. Golden vectors: canonical bytes and hashes match the fixture byte for byte (2.4).
2. Every hashed field, changed by direct SQL in the file (triggers dropped first), breaks verification at
   that entry. The test is parametrized over the full `HASHED_ENTRY` and `HASHED_LINE` lists, dimensions
   included, so a line edit always breaks the chain.
3. Excluded fields (`recon_id`, and `is_void` alone) do not change the hash. An `is_void` flip without a
   Void reversal is caught by the cross-check.
4. **Delete a row:** delete entry N (or one of its lines) with triggers dropped; verification names N
   (or N+1 for a deleted entry).
5. **Reorder rows:** swap the `entry_number` of two entries; swap two `line_id`s; verification names the
   first affected entry.
6. **Reseal without the key:** recompute hashes with a wrong key; verification fails at entry 1.
7. **Rollback:** a post that fails after its hash is computed (forced error) leaves the counter, the head
   and every hash unchanged; the next post chains correctly.
8. **Concurrency:** two or more writers started together with a `threading.Barrier`. Assert the
   invariants, never timing:
   * entry numbers 1..N with no gap;
   * each `chain_prev_hash` equals the previous `chain_hash`;
   * full verification passes.

   Run 20 times in a loop once, and report.
9. Auto-reversal, pair void, document entries and rounding entries are sealed in number order and verify.
10. No key: posting is refused with the one-sentence message and nothing is written; drafts still save.
11. Incremental verification:
    * a valid marker verifies only N+1 onward (spy);
    * a forged marker (MAC wrong, or the hash at N changed) forces a full check;
    * an old edit is found by the full check, not by the incremental one (documents the limit).
12. Messages: the failure text names the entry number, date and poster, and contains no hash or key.
13. **Speed (benchmark, not a pass/fail test; K12):** measure and report full verification of 100k
    entries with 3 lines each (target 10 seconds) and incremental verification of 100 new entries (target
    0.2 seconds) on the development machine, in the step that builds the verify service.

**Keys (Steps 3 and 1c):**
14. A known key (bytes, hex and base64) never appears in log files, `audit_log`, `access_event`,
    exception messages, `repr(context)` or `repr(SecretKey)`.
15. `SecretKey` cannot be pickled.
16. `FixedTestKeyProvider` refuses to load outside tests; `NullKeyProvider` always raises.
17. DPAPI round trip; the recovery-code wrap round trips; a wrong code fails cleanly; Master recovery
    re-wraps for a new machine (DPAPI simulated); backlog item 11 re-wraps.
18. Rotation: entries across two key epochs verify; a retired key cannot seal.

**Checkpoints and backups (later phases):**
19. A checkpoint row is append-only; its MAC detects a change; the master mirror matches.
20. **Restore with a matching checkpoint:** succeeds and verifies.
21. **Restore with a non-matching checkpoint:** warns and names the entry.
22. **Restore with a checksum mismatch:** refused, except the Master path with typed confirmation and
    reason, which makes a safety backup and writes a sensitive log entry.
23. Auditor:
    * the template holds only read codes;
    * a read-only context cannot open a write transaction;
    * a verification run as the Auditor writes nothing to the company file.

---

## 12. Phase placement and build order

| What | When | Release |
|---|---|---|
| **Step 1b:** chain columns, `ledger_chain_key`, `ledger_checkpoint`, locks, close check code `ledger_integrity`; pure `ledger_chain.py` (canonical form, seal, verify) with golden vectors; test helpers seal with a fixed test key | Phase 2.5, now, before Step 3 | v1.0 |
| **Step 3:** posting seals inside the transaction through the `KeyProvider` interface (`FixedTestKeyProvider` in tests, `NullKeyProvider` otherwise, so posting is refused without a real key); the `ledger_integrity` close check; incremental verification at open | Phase 2.5 | v1.0 |
| **Step 1c:** keystore (`keys.py` `LocalKeyProvider`, master `installation_key` and `company_key`, DPAPI in `platform_support.py`, recovery-code wrap; the `cryptography` decision K2). **Must land before any screen can post, and before 2.5 is declared done.** The keystore must **retain every retired key** (wrapped, never deleted), so entries sealed under an old key stay verifiable; it mirrors `ledger_chain_key`, which already keeps retired rows. | Phase 2.5, after Step 3 | v1.0 |
| Steps 4-7 (approvals, reversals, rounding, billing) seal through the same path; `create_document_entry` (section 13) lands with billing | Phase 2.5 | v1.0 |
| Verify service, checkpoints table writes, master mirror, `ledger.verify` permission | Phase 2.5 (with Step 3 / 1c) | v1.0 |
| Ledger integrity screen, banner at open, Audit-ready checklist screen | Phase 3 | v1.0 |
| Single connection point: allow-list emptied, test extended (section 5) | Phase 3 | v1.0 |
| Auditor role template and read-only context | Phase 3 (role editor) | v1.0 |
| Backup service with checksums, manifests, restore checks (E7) | Phase 5 (cleanup and security) | v1.0 |
| Backlog item 11, re-wrapping the installation key | Before v1.0 (already required) | v1.0 |
| Audit trail reports and checkpoint footers on exports | Reports (backlog item 6) | v1.0 |
| Encryption at rest | After v1.0, when the checklist in 4.3 is green | v1.1+ (U5) |
| `audit_log` chaining | Backlog (K6) | later |
| Attachment evidence seal | With the attachments design | later |
| Azure Key Vault provider and hosted threat model | Hosted product (P5) | hosted |

---

## 13. Document-source entries: one narrow entry point (owner item g)
Step 2 already refuses document sources (`Invoice`, `Bill`, `Payment`, `Payroll`, `Import`, `Deferral`,
`Completion`, `Conversion`) on Human and Agent drafts. The services that legitimately make such entries
get one narrow function:

    ledger.create_document_entry(conn, context, *, source, entry_date, lines, description=None,
                                 reference=None, post=False)

* **It runs inside the caller's write transaction** (`conn`), so the document and its entry are written
  together or not at all. It does not authorize: the calling service has already authorized the human for
  its own permission (`invoice.send`, `bill.approve`, `payroll.import`, ...), so an AR clerk does not need
  `je.create`.
* **It requires origin System or Import.** The caller builds that context with `context.as_system()` (or
  `as_import()`), which keeps the human's `user_id`, so the audit trail still names the person.
* **Allowed callers and their sources** are fixed in a static test (AST scan of `modules/`):

  | Module | Sources it may pass (literal) |
  |---|---|
  | `billing.py` | Invoice, Payment |
  | `bills.py` | Bill |
  | `payments.py` | Payment |
  | `payroll_import.py` | Payroll |
  | `imports.py` | Import |
  | `conversion.py` | Conversion |
  | `deferrals.py` | Deferral |
  | `poc.py` | Completion |
  | `ledger.py` | (auto-reversal and rounding paths only) |

  The test fails if any other module calls `create_document_entry`, `as_system` or `as_import`, or passes a
  source outside its row, or passes a non-literal source.
* **When it lands** (with billing, Step 7), `create_entry` (the public draft function) accepts only the
  manual sources for every origin, Import and System included. That closes the remaining path. Until then
  Step 2's rule stands.
* The same lines go through `check_lines`, the same posting path and the same seal (2.5).

---

## 14. Step 1b prompt (ready to paste)

> **Phase 2.5 Step 1b: baseline schema for the tamper-evident ledger chain** (docs/audit_readiness_design.md
> sections 2, 3, 12). Design decisions K1-K10 and P5 apply. Tests first; each step green; commit by
> explicit path; push.
>
> **0. Save the previous baseline first** (no migrations): copy `migrations/001_company.sql` to
> `archive/baseline_pre_2_5_1b/001_company.sql` with a README naming the commit, and tag that commit
> `baseline-pre-2.5-1b`. The master baseline does not change in 1b.
>
> **1. Tests to write first** (they must fail before the baseline edit):
> - `tests/test_schema_ledger_chain.py`:
>   - drafts have all four chain columns NULL;
>   - posting with any chain column missing is refused;
>   - a posted entry with a draft-style NULL seal is refused;
>   - hex CHECKs reject uppercase, 63 or 65 characters and non-hex;
>   - `chain_version` other than 1 is refused;
>   - `chain_key_id` must reference `ledger_chain_key`;
>   - duplicate `chain_hash` is refused (partial unique);
>   - each chain column is locked once posted (parametrized update);
>   - the Void reversal still sets `is_void` on a sealed original;
>   - `ledger_chain_key`: one active key, no delete, a key can be retired once (is_active 1 to 0 with
>     `retired_at` and `retire_reason`), other columns are locked, a retired key cannot be reactivated;
>   - `ledger_checkpoint`: insert allowed; no update; no delete;
>     `(result = 'Broken') = (first_broken_entry_number IS NOT NULL)`;
>     `(through_entry_number = 0) = (chain_hash IS NULL)`; scope required exactly for kind Verify; MAC
>     format; the insert writes an audit row;
>   - the `journal_entry` audit JSON (insert, update and delete triggers, including the post snapshot)
>     carries the four chain columns;
>   - `period_close_check` has `ledger_integrity` seeded as a warning.
> - `tests/test_ledger_chain.py` (pure module, no database for most tests):
>   - golden vectors in `tests/data/ledger_chain_vectors.json`;
>   - canonical form rules (sorted keys, timestamp normalisation, line and dimension order, float
>     refused);
>   - each hashed field changes the hash; excluded fields do not;
>   - the column classification test against `PRAGMA table_info` of `journal_entry`, `journal_line` and
>     `journal_line_dimension`.
>
> **2. Baseline edits** (`migrations/001_company.sql`):
> - `journal_entry` new columns:
>   - `chain_version INTEGER CHECK (chain_version IS NULL OR chain_version = 1)`
>   - `chain_key_id INTEGER REFERENCES ledger_chain_key(key_id)`
>   - `chain_prev_hash TEXT CHECK (chain_prev_hash IS NULL OR (length(chain_prev_hash) = 64 AND chain_prev_hash NOT GLOB '*[^0-9a-f]*'))`
>   - `chain_hash TEXT CHECK (chain_hash IS NULL OR (length(chain_hash) = 64 AND chain_hash NOT GLOB '*[^0-9a-f]*'))`
>   - `CHECK (is_posted = 1 OR (chain_version IS NULL AND chain_key_id IS NULL AND chain_prev_hash IS NULL AND chain_hash IS NULL))`
>   - `CHECK (is_posted = 0 OR (chain_version IS NOT NULL AND chain_key_id IS NOT NULL AND chain_prev_hash IS NOT NULL AND chain_hash IS NOT NULL))`
> - `CREATE UNIQUE INDEX journal_entry_chain_hash_unique ON journal_entry (chain_hash) WHERE chain_hash IS NOT NULL;`
> - New table `ledger_chain_key`: `key_id INTEGER PRIMARY KEY AUTOINCREMENT`,
>   `fingerprint TEXT NOT NULL UNIQUE` (64 lowercase hex, CHECK), `created_at TEXT NOT NULL`,
>   `created_by INTEGER`, `is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))`,
>   `retired_at TEXT`, `retire_reason TEXT CHECK (retire_reason IN ('Rotation', 'Key lost', 'Compromised'))`,
>   `CHECK ((is_active = 1) = (retired_at IS NULL))`, `CHECK ((retired_at IS NULL) = (retire_reason IS NULL))`.
>   Constraints:
>   - `CREATE UNIQUE INDEX ledger_chain_key_one_active ON ledger_chain_key (is_active) WHERE is_active = 1;`
>   - trigger `ledger_chain_key_no_delete`;
>   - trigger `ledger_chain_key_retire_only`: an update may only move `is_active` from 1 to 0 and set
>     `retired_at` / `retire_reason`; every other column stays.
>   - audit insert and update triggers.
> - New table `ledger_checkpoint`: `checkpoint_id INTEGER PRIMARY KEY AUTOINCREMENT`,
>   `created_at TEXT NOT NULL`, `created_by INTEGER`,
>   `kind TEXT NOT NULL CHECK (kind IN ('Verify', 'Period close', 'Year close', 'Report export', 'Backup', 'Restore', 'Key rotation', 'Manual'))`,
>   `scope TEXT CHECK (scope IN ('Incremental', 'Full'))`,
>   `result TEXT NOT NULL CHECK (result IN ('OK', 'Broken'))`,
>   `through_entry_number INTEGER NOT NULL CHECK (typeof(through_entry_number) = 'integer' AND through_entry_number >= 0)`,
>   `chain_hash TEXT` (hex CHECK), `first_broken_entry_number INTEGER`,
>   `key_id INTEGER REFERENCES ledger_chain_key(key_id)`, `ref_type TEXT`, `ref_id INTEGER`,
>   `mac TEXT NOT NULL` (hex CHECK), plus:
>   - `CHECK ((kind = 'Verify') = (scope IS NOT NULL))`
>   - `CHECK ((result = 'Broken') = (first_broken_entry_number IS NOT NULL))`
>   - `CHECK ((through_entry_number = 0) = (chain_hash IS NULL))`
>
>   Triggers `ledger_checkpoint_no_update`, `ledger_checkpoint_no_delete`, and the audit insert trigger.
> - `journal_entry_lock_posted`: add `NEW.chain_version IS OLD.chain_version`, the same for `chain_key_id`,
>   `chain_prev_hash` and `chain_hash`.
> - The `journal_entry` audit triggers (insert, update both branches, delete): add the four chain columns.
> - `period_close_check`: add `'ledger_integrity'` to the CHECK and seed it (mode `warn`).
> - **No trigger checks the previous hash or the active key** (owner decision): the service computes the
>   chain and verification catches mismatches.
>
> **3. Pure module** `modules/services/ledger_chain.py` (no database writes, no keys stored):
> `HASHED_ENTRY`, `EXCLUDED_ENTRY`, `HASHED_LINE`, `EXCLUDED_LINE`, `canonical_entry(header, lines, dims)`,
> `seal(key_bytes, company_code, prev_hash, canonical) -> hex`, `GENESIS = "0" * 64`.
>
> **4. Test helpers:** `tests/ledger_helpers.post` seals with a fixed test key (insert one active
> `ledger_chain_key` row with that key's fingerprint on first use) and writes the four chain columns in the
> posting UPDATE. Route the three raw posting UPDATEs in `tests/test_controls_004.py` through it, or give
> them the chain columns. Adapt any other test that posts by raw SQL.
>
> **5. Verify:** full suite green (state counts), the new tests failed before the edit, `git status` clean
> after the commit. Update CLAUDE.md (status entry, the Step 1b line in the 2.5 roadmap). **STOP after
> Step 1b and report:** what changed in the baseline, the tests adapted, counts and the commit hash. Do not
> start Step 3.

---

## 15. Questions answered (recorded as decisions K1-K12)
These were the open questions; the owner's answers are recorded in `docs/decisions_2026-11-11.md` section K.

1. DPAPI scope → **machine scope**, with the limit stated in section 1 (K1).
2. Wrapping library → **add `cryptography`** after confirming its licence and PyInstaller build (K2).
3. Posting on a broken chain → **warn and allow by default; block in Audit-ready mode; never post without
   the key** (K3).
4. Auditor and sensitive fields → **only if granted** (K4).
5. Restore with checksum mismatch → **Master only, typed confirmation and reason, safety backup first,
   flagged on the Audit-ready checklist** (K5).
6. `audit_log` chaining → **backlog** (K6).
7. Who may run verification → **`ledger.verify` for Admin, Controller and Auditor** (K7).
8. Exporting the chain key → **only inside the passphrase-protected company bundle, Master only** (K8).
9. Auditor → **a 12th starter role** (K9).
10. Encryption → **keep U5, SQLCipher-type encryption after v1** (K10).

11. Accountant and `ledger.verify` → **no**; the Accountant sees the result on the close checklist (K11).
12. Speed targets → **benchmarks to measure and report** when the verify service is built, not pass/fail
    tests (K12).

---

## 16. Per-dialect constructs (P5)
P5 says the PostgreSQL version rewrites dialect-specific parts rather than porting them. This list names the
SQLite-only constructs in the baseline that the PostgreSQL schema must rewrite. Services hold none of these
(H5). Add to this list whenever the baseline gains a new one.

| Construct | Where (company baseline) | PostgreSQL rewrite |
|---|---|---|
| `GLOB` (64-hex checks; account code digits) | Step 1b hex CHECKs on `journal_entry.chain_prev_hash` / `chain_hash`, `ledger_chain_key.fingerprint`, `ledger_checkpoint.chain_hash` / `mac`; `account.code` | A regular-expression CHECK (`x ~ '^[0-9a-f]{64}$'`) |
| `typeof(x) = 'integer'` | Step 1b `ledger_checkpoint.through_entry_number`; every integer-cents and counter CHECK | Not needed: a typed `INTEGER` / `BIGINT` column refuses other types; drop the CHECK |
| `RAISE(ABORT, ...)` triggers with `WHEN` | posted-entry and posted-line locks, `journal_entry_void_on_reversal`, Step 1b `ledger_chain_key_no_delete` / `ledger_chain_key_retire_only`, `ledger_checkpoint_no_update` / `ledger_checkpoint_no_delete` | PL/pgSQL trigger functions (`RAISE EXCEPTION`), one per lock |
| `json_object(...)` in audit triggers | every `audit_*` trigger, including Step 1b's `audit_ledger_chain_key_*` and `audit_ledger_checkpoint_insert` | `jsonb_build_object(...)` |
| `INTEGER PRIMARY KEY AUTOINCREMENT` | every table, including `ledger_chain_key`, `ledger_checkpoint` | `GENERATED ALWAYS AS IDENTITY` |
| `IS` / `IS NOT` comparing values | lock triggers (`NEW.x IS OLD.x`) | `IS NOT DISTINCT FROM` |
| Partial unique indexes (`WHERE ...`) | `journal_entry_chain_hash_unique`, `ledger_chain_key_one_active`, the reversal slots | Supported as is |
| `BLOB` with `typeof(x) = 'blob'` and `length(x)` | Step 1c master `installation_key` (`machine_blob`, `recovery_salt`, `recovery_blob`) and `company_key.wrapped_key`; their `GLOB` fingerprints and RAISE triggers are as above | `bytea` with `octet_length(x)`; drop the `typeof` CHECK |

The chain itself is unaffected: the canonical form (2.4) is defined on values, the golden vectors must pass
unchanged, and posting uses the counter-row lock described in 2.5.

### As built in Step 1b (differences from section 14)
* `journal_line.entry_id` is hashed too (the line list in 2.2 now says so), so a line moved to another entry
  breaks both entries. `journal_line_dimension.line_id` is classified as excluded because it only groups
  dimensions under their hashed line.
* Date fields (`entry_date`, `auto_reverse_date`) must be text; an integer date is refused.
* The test helper that adds the fixed test key is `ensure_test_chain_key` (a `test_` name would be collected
  by pytest).
* SQLite's integer affinity turns the text '1' into the integer 1, so the schema tests do not treat a numeric
  string as a wrong type.

### As built in Step 3b (verification)
* **Service:** `ledger_verify.verify_ledger(context, mode="incremental" | "full")`, permission `ledger.verify`
  (K7, K13). It reads through a read-only connection, then records in two short writes: a `ledger_checkpoint`
  row (kind Verify, scope, result, through, first broken, key_id, MAC) and its mirror in the master's new
  `chain_checkpoint` table. A read-only context (`ServiceContext.read_only`, the Auditor's open, section 6)
  records in the master only; `tx.write_transaction` refuses a company-file write from such a context.
* **Result:** status `OK`, `Broken` or `Unavailable`. Broken names the first broken entry: number, JE number,
  date, who posted it (name from the master), and a reason code: `Link`, `Hash`, `Gap`, `Void mismatch`,
  `Key fingerprint`, `Truncated`, `Marker`. The message is plain language, names that entry and a next step,
  and contains no hash or key. Unavailable (the key provider cannot supply a needed key) is never recorded as
  a checkpoint and the message says plainly it is not a sign of tampering.
* **Checkpoint MAC** (`ledger_chain.checkpoint_mac`): HMAC-SHA256 under the chain key named by the row's
  key_id, over the tag `SLCP1`, the company code and the canonical JSON of the checkpoint fields. The latest OK
  checkpoint in the file and the latest OK mirror in the master are both checked; a bad MAC is `Marker`.
* **Incremental (K15):** it starts at the last OK checkpoint. It checks that the checkpointed entry still has
  the recorded hash, re-checks that entry's link and recomputes its seal, then checks every entry after it.
  It does not re-read the entries before the checkpoint: an edit inside the already-verified range is found
  only by a **full** check, which is what re-proves older entries (run at every period and year close, on
  demand, and before backups once the backup service exists). With no OK checkpoint, incremental runs full.
* **Whole-ledger checks in both modes:** the void cross-check, and truncation against the latest OK
  checkpoints (file and master) and the entry counter. Restoring an older copy of the file is caught by the
  master's mirror ("this looks like an older copy of the company file").
* **Automatic checkpoints:** `ledger_verify.checkpoint_on_close(context)` signs a checkpoint (company file
  and master mirror) whenever a company is closed in the app (logout) and when the app exits. It is system
  upkeep (no permission), runs an incremental check (full when there is no checkpoint yet), records OK or
  Broken like `verify_ledger`, records nothing when no key is available, and never raises (a failure is
  logged).
* **Documented limit:** if the last entries are cut, the counter is rolled back as well, and no checkpoint
  exists in the file or the master, the shorter chain is consistent and verifies. Because a checkpoint is now
  written at every company close and app exit, this gap exists only before a ledger's first close (or when no
  key was available at every close). The master's mirror catches a cut tail afterwards even if the file's own
  checkpoints are deleted too. Printed checkpoints in an auditor's hands cover the rest (section 3).
* **Close check:** `ledger_integrity` runs one full verification per close action (period close, Books
  closed through, year close, and the close-check preview), over the caller's connection, not recorded.
  Broken follows the check's mode (warning by default, block when set, L2); Unavailable is always a warning
  that says the check could not run.
* **Keys:** the provider interface is now `get_key(company_id, key_id)`; the test provider can hold several
  keys. **Step 1c:** the local provider must keep every retired key (wrapped, never deleted), because
  verification asks for the key named by each entry's `chain_key_id`; a missing retired key makes
  verification Unavailable, not Broken.
* **Benchmarks (K12, measured 2026-11-12 on the development machine, `tools/benchmark_ledger_verify.py`):**
  full verification of 100,000 entries with 3 lines each took 25.4 s and 28.0 s (two runs; target 10 s);
  incremental verification of 100 new entries after a checkpoint at 100,000 took 0.34 s and 0.37 s (target
  0.2 s). Both miss the targets. A profile shows about half of the full check is building the canonical form
  in Python and a sixth is JSON encoding, so the seal itself is not the cost; the incremental check's fixed cost
  is the whole-ledger SQL (mainly the void cross-check), which grows with the ledger. Follow-up: backlog
  item 14. Whatever the speed, screens run full verification in the background with progress (2.6).
