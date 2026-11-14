# Cloud migration design (DESIGN, NOT BUILT)

**Date:** 2026-11-13 · **Status:** design, accepted by the owner. Owner decisions CM1 and CM2, and CM3 (the open
questions in section 10, all answered as proposed; docs/decisions_2026-11-11.md). Nothing here is built, and the
hosted product it moves into (P5) is not designed yet.

**Owner decisions this design follows:**
* **CM1** The desktop app offers "Move to the cloud / Invite your team". It moves one company into the hosted
  version (PostgreSQL on Azure, P5) and keeps every journal entry, contact, job and attachment, with the ledger
  history still verifiable. It is easy to find and never nags (section 0b).
* **CM2** Sign-ins move as seamlessly as possible:
  * accounts, roles, company access and approval limits move automatically;
  * the desktop password keeps working: its scrypt hash moves and is upgraded to the cloud scheme at the first
    cloud sign-in; users sign in with their email address;
  * each user verifies their email once; two-factor sign-in is required for Admins and the Master and offered
    to everyone else;
  * recovery codes, backup codes and temporary passwords do not move; the cloud uses normal account recovery;
  * the pre-flight lists every user without an email address and blocks the move until each has one.

**Inputs read:** P5, H1-H6, K8, KS1-KS21, K14-K18 (checkpoints), backlog 16 (key bundle),
docs/audit_readiness_design.md sections 1, 2.4, 2.7, 3, 9, 10 and 16, docs/password_recovery_design.md.

**Facts from the code that shape this design:**
* The chain seal is `HMAC(key, "SLJ1" | company_code | prev_hash | canonical_entry)` (ledger_chain.py). The
  canonical form holds `entry_id`, `line_id`, `period_id`, `account_id`, `contact_id`, `project_id`, the
  dimension ids and the user ids `created_by`, `posted_by` and `approved_by`. **So the cloud must keep the
  company code and every id exactly as stored.** No row is renumbered and no user id in the company data is
  rewritten (section 7.2).
* The canonical form is defined on values, not on driver output, and the golden vectors in
  `tests/data/ledger_chain_vectors.json` must pass unchanged on the PostgreSQL port (audit design 2.4). That is
  what lets the cloud re-verify the desktop chain.
* Chain keys are 32-byte HMAC keys, wrapped in the master (`company_key`) by the installation key. Retired keys
  are kept forever because verification needs them (2.7). A key retired as `Key lost` has no key to move.
* `export_company` (Master only) today copies the file with no keys and returns `EXPORT_NOT_VERIFIABLE` (KS11).
* `app_user.email` is `NOT NULL` but may be empty, is not unique and is never verified (password design 6).
* `file_attachment` stores a `file_path` and no hash.

---

## 1. The flow, from the user's side

**Where it lives (0b: easy to find, never nagging).** One entry, "Move to the cloud / Invite your team":
* in Company Settings, under the company's name;
* in the launcher's menu for each company row.

There are no pop-ups, timed reminders or badges. Anyone with access sees the entry. Only the Master can start a
move (the keys leave only with the Master, K8). Everyone else sees one sentence: "Only the Master can move this
company to the cloud; ask them to start it here."

**Steps** (a wizard, because this is a rare task; 0b):
1. **Sign in to the cloud.** The Master signs in to an existing StrataLedger cloud account, or creates one, in
   the system browser (never an embedded web view, so the password is never typed into the desktop app). The
   desktop app gets a short-lived, single-use move token scoped to "create one company and upload one package".
   The cloud account's email becomes the Master's cloud login (section 7.1).
2. **Choose the company.** The Master picks one desktop company. The step shows the company's parent and
   subsidiaries, if it has any (10, Q6).
3. **Pre-flight** (section 2). This step shows every result in plain sentences: blocks first, each with its fix,
   then warnings. "Fix and check again" reruns it.
4. **Consent.** One screen that says, in plain words:
   * **What is uploaded:** every record of this company, including contacts' full tax IDs and bank details
     (C4), employees' wages, attachments, the audit trail and the ledger keys; and, for the people who have
     access, their names, email addresses, roles, approval limits and password hashes.
   * **What is not uploaded:** other companies, recovery and backup codes, temporary passwords, the installation
     key, email (SMTP), AI and bank-feed credentials, and log files.
   * **Where it is stored:** the region by name (for example "Microsoft Azure, East US") and the company that runs
     it.
   * **Who can see it:** the people listed, after they verify their email.
   * **How long the upload copy is kept:** until the move is confirmed or cancelled, then deleted (section 8).

   The Master ticks "I have the right to move this data" and types the company code (0b, for a rare and
   far-reaching action).
5. **Progress.** Build the package, upload it (resumable, section 8), then the cloud imports and verifies it.
   Each phase shows its own progress and an estimated time. The window stays responsive (backlog 14). The desktop
   company stays usable until the switch (section 6).
6. **Verification report** (section 5): matched or not, line by line, with both "migrated" checkpoints. "Save
   report" (PDF and the JSON it is built from) and "Open in the cloud".
7. **Confirm the switch** (section 6), or cancel. Only after confirming is the team invited.

---

## 2. Pre-flight

Every check runs before anything leaves the computer. A **block** stops the move and names its fix; a
**warning** is shown and the move can go on.

| Check | Result | Message (one sentence, says what to do) |
|---|---|---|
| Full ledger verification | Broken: **block** | "The ledger check found a changed entry (JE-000123); this must be investigated before the company can move." |
| | Unavailable (a key missing, no epoch): **block** | "The ledger key for this company cannot be opened here; restore it with the recovery code, or start a new key epoch, then try again." |
| | Unverified range (KS12-KS15): **warning** | "Entries JE-000001 to JE-000480 cannot be verified (key lost on 2026-03-02); they move as they are and stay marked unverified in the cloud." |
| Mirror comparison (the master's checkpoints for this company match the file, audit design 3) | Mismatch: **block** | "This company file does not match what this computer recorded earlier; restore the right file or contact support." |
| Schema version | The file's baseline hash or migration version is not one the cloud importer supports: **block** | "Update StrataLedger to the latest version, then try again." |
| App version | Older than the cloud's minimum: **block** | Same sentence as above. |
| Users without an email address (CM2) | **block** | "3 people have no email address: Ana Cruz, B. Lee, R. Tan. Add one for each in Users, then check again." |
| Two users with the same email (ignoring case) | **block** | "Ana Cruz and A. Cruz share ana@example.com; each person needs their own address." |
| An email that is not a valid address | **block** | Names the user and the address. |
| Open drafts | **warning**, with counts by type | "12 drafts (4 invoices, 8 journal entries) move as drafts." |
| Pending or approved-but-not-posted approval requests | **warning** | "5 entries are waiting for approval; they move with their approvals and the same checks apply in the cloud." |
| Unfinished imports (staged batches not approved) | **warning** | Count and source. |
| A period-close or reconciliation in progress | **warning** | Names it. |
| Users with a temporary password or a forced change pending | **warning** | "2 people will set their password from the invitation email instead." (section 7.3) |
| Attachments missing on disk | **block** | Names each missing file; "Find the file or remove the attachment link, then check again." |
| Size estimate | **info** | Database size, attachment count and size, the estimated upload time at the measured speed, and the cloud plan's limit (a block if over it). |
| Parent or subsidiary companies | **info** | Lists them (10, Q6). |

Drafts, pending approvals and staged imports **move as they are**. They are data, the approval digest (R15) is
computed on the same canonical form in both databases, and every posting check runs again in the cloud. The
pre-flight lists them so that people can finish them first if they prefer.

---

## 3. The portable company package (one format, shared with backlog 16)

One format serves **backups, exports and cloud moves**, so it is built once (Phase 5) and tested once. A
**profile** in the manifest says which optional parts a package carries.

**Container.** One file, `<CODE>-<UTC timestamp>.slpkg`: a ZIP archive with stored (uncompressed) members for
the database and deflate for the JSON members. ZIP is readable on every platform and by Python's standard
library on both the desktop and the hosted side (no new dependency). Member names are fixed and relative; the
reader refuses absolute paths, `..`, duplicates and symlinks (zip-slip).

**Members:**

| Member | Backup | Export | Cloud move | Content |
|---|---|---|---|---|
| `manifest.json` | yes | yes | yes | Format version, profile, app version, company code and id, schema baseline hash and version, created at and by, the latest checkpoint string, the verification result with any unverified range, row counts per table, and the SHA-256 and size of every other member. |
| `manifest.mac` | yes | yes | yes | HMAC of the manifest bytes. Backup: under the installation key (audit design 9). Export and cloud move: under the active chain key, so whoever imports the keys can check it. |
| `company.sqlite` | yes | yes | yes | A consistent copy made with the SQLite backup API: all company tables, including `ledger_chain_key`, `ledger_checkpoint`, `audit_log`, `approval_*`, roles and limits. |
| `attachments/<sha256>` | yes | yes | yes | Each attachment file under its hash, read through `storage.py` (H3). An index in the manifest maps `file_id` to hash, size and name. |
| `master_extract.json` | no (see below) | yes | yes | This company's rows from the master: the registry row, its `chain_checkpoint` mirror rows, and its key history (fingerprints, dates and retire reasons; never the keys). |
| `keys.bundle` | optional (K8) | yes (K8) | yes | The encrypted key bundle (section 4). |
| `users.json` | no | no | yes | The people who move, per CM2 (section 7). Only in a cloud-move package. |

A **backup** stays as audit design 9 says: the master travels with every backup as its own SQLite copy (KS10),
not as an extract. So the backup profile adds `master.sqlite` and leaves out `master_extract.json`.

**Versioning.** `format_version` starts at 1. A reader refuses a higher major version with "This file was made
by a newer StrataLedger; update to open it." Adding an optional member is a minor version. The database inside
is versioned by its own baseline hash or migration number, so the package format and the schema version change
independently.

**Why the SQLite file and not a table-by-table dump.** The desktop restores it directly (backups), and the cloud
importer reads it with Python's `sqlite3` module, which needs no SQLite server. The values are what the chain
hashes, so nothing passes through an intermediate text form that could change a value. The importer maps types
table by table (section 5).

**Attachments.** Hashes are recorded when the package is made. Until attachments record their SHA-256 at upload
(audit design 10), a package hash proves the file arrived unchanged; it does not prove the file is unchanged
since it was attached. The verification report says so.

---

## 4. Keys

* **What moves:** every chain key of the company that this installation can open: the active key and every key
  retired by `Rotation`. A key retired as `Key lost` has no key to move; its `ledger_chain_key` row moves (it is
  in the file) so the cloud verifier sees the same history.
* **The key bundle** (backlog 16, K8): a small JSON document listing each key as `{key_id, fingerprint, key}`,
  encrypted with AES-256-GCM (as `key_wrap.py` already does) under a random 32-byte content key. The
  manifest's SHA-256 is in the associated data, so a bundle cannot be moved to another package. The content key
  is wrapped for one or more **recipients**:
  * **passphrase** (K8, export and backup): scrypt from a passphrase the Master types, with its own salt
    (as KS2);
  * **cloud recipient** (cloud move only): wrapped to the public key of a migration key that the cloud creates
    for this move in Azure Key Vault (RSA-OAEP-256). The private half never leaves Key Vault, so no passphrase is
    typed twice and nothing readable travels. The desktop shows the recipient key's fingerprint on the consent
    screen and checks it against the value the cloud sent over TLS.
* **Import into Key Vault.** The cloud unwraps the content key inside Key Vault, decrypts the bundle in the
  import worker's memory, checks each key's fingerprint against `ledger_chain_key` (KS3), and stores each key
  through the hosted `KeyProvider` (`AzureKeyVaultProvider`, audit design 2.7; services do not change, P5). The
  proposed storage is envelope encryption: each chain key wrapped by a per-tenant Key Vault key, with the wrapped
  blob in the tenant's key table, just as the master's `company_key` works today. **Confirm before building:**
  Key Vault's current operations and limits for RSA unwrap, the choice between Key Vault and Managed HSM, and
  whether HMAC keys can or should be held as Key Vault keys rather than wrapped secrets.
* **History stays verifiable** because the keys, the fingerprints and the canonical form are all unchanged
  (section 5).
* **Unverified ranges.** A `Key lost` checkpoint moves as it is. The cloud verifier reports the same range as
  Unverified, never Broken, and the KS15 note ("entries JE-000001 to JE-N cannot be verified") follows those
  periods into every cloud report. The move never turns an unverified range into a verified one (KS18).
* **On the desktop afterwards.** The keys stay in the master, so the read-only desktop company (section 6) can
  still verify itself.

---

## 5. Import and proof

**Import** (a privileged load path in the hosted product, not the services' posting path):
1. Check the package: the ZIP rules, each member's SHA-256 against the manifest, and the manifest MAC once the
   keys are imported.
2. Create the company's schema from the hosted schema version that matches the package's baseline (H5: one
   schema per company).
3. Copy table by table **with every id kept** (PostgreSQL identity columns loaded with `OVERRIDING SYSTEM
   VALUE`, and each sequence set past the highest id afterwards). Types map per audit design 16: integers stay
   integers (a REAL found in a cents column fails the import), 0/1 flags become booleans, ISO timestamps become
   `timestamptz`, BLOBs become `bytea`. Text is copied byte for byte.
4. The posted-entry locks and the append-only triggers exist in the hosted schema before the load. The load
   inserts rows and never updates or deletes, so the locks need no bypass. Copied `audit_log` rows are inserted
   as history; the audit triggers do not write a second row for them. **Confirm before building:** how the
   PostgreSQL audit triggers tell the migration load from a normal write (for example a `SET LOCAL` flag that only
   the migration role may set, H4).
5. Store the attachments in object storage under their hashes, through the hosted `storage.py` backend (H3).
6. Import the keys (section 4).

**Proof.** The cloud computes every item below, the desktop computes the same items from its own file, and each
pair must match:
* **full chain re-verification** in the cloud with the same canonical form (the golden vectors pass on the port),
  with the same result, `through_entry_number`, chain head and unverified range as the desktop pre-flight;
* **the latest checkpoint:** the cloud recomputes the head at that checkpoint's entry number and gets the same
  hash;
* **trial balance per period** (periods 1-14, debits and credits per account in cents);
* **row counts** for every table;
* **a SHA-256 over each table's canonical rows** (sorted by primary key, values as in audit design 2.4), which
  covers `audit_log`, contacts, jobs and drafts, none of which the chain covers;
* **attachment hashes**, every one.

**"Migrated" checkpoints on both sides.** Once everything matches, the cloud writes a checkpoint of a new kind,
`Migration`, signed with the company's active chain key over the same head. The desktop writes the same kind in
its file and its master mirror when the user confirms the switch (section 6). Both checkpoint strings
(`SL1-CODE-JE000123-...`) are printed on the report, so an auditor can check either side later (audit design 3).
The baseline's checkpoint `kind` CHECK has no `Migration` value today (section 9).

**The report the user keeps:** company, both checkpoint strings, the verification results, every comparison
with "matched" or the first difference, the unverified range note, attachment counts, the users who moved and
their status, who ran the move and when (UTC and company time), the region, and the package's SHA-256. It is
saved as a PDF plus its JSON, and the cloud keeps a copy in the company's documents.

**On any mismatch:** the cloud copy is not activated. The report names the first difference in one sentence,
and the only options are "Try again" or "Cancel the move". The desktop company is untouched.

---

## 6. After the move

* **Confirm the switch.** The report screen asks: "Switch this company to the cloud? On this computer it will
  become read-only." Confirming:
  1. checks that the desktop company has not changed since the package was made (the same entry count and head,
     the same highest `audit_log` id). If it has: "Something changed in this company after the copy was made;
     start the move again." The desktop is therefore not locked during the upload and the checks, and a slow
     upload never stops the team working;
  2. in one company transaction on the desktop, writes the `Migration` checkpoint and marks the company **moved**
     (registry and file; section 9), which makes every write service refuse with "This company now lives in the
     cloud; open it there.";
  3. tells the cloud to activate the company and send the invitations. If that call fails, the desktop shows
     "Finishing the move" and retries, and the Master can press "Try again". The desktop never becomes writable
     again on its own. This order means the company can never be writable in both places at once.
* **The read-only desktop company:** it opens normally with a banner: "This company moved to the cloud on 13 Nov
  2026. This copy is read-only." and an "Open in the cloud" button. Reports, verification and exports still work.
  It is not archived (S9): it stays in the launcher with a "Moved to cloud" label.
* **No two-way sync** in this feature (crm_pm_design.md question "desktop to hosted sync" stays open).
* **Undo before confirming:** "Cancel the move" deletes the cloud copy, the uploaded package and the migration
  key in Key Vault (the cloud confirms each deletion), and leaves the desktop exactly as it was. A move that is
  neither confirmed nor cancelled expires after 7 days and is cleaned up the same way (10, Q4).
* **After confirming:** this feature has no undo. Going back is a future "Download to desktop" that builds the
  same package format from the cloud (10, Q5).

---

## 7. Users and roles (CM2)

### 7.1 Who moves, and with what
* **People:** every active user whose effective access to this company is a Grant (the nearest-row rule,
  including access inherited from a parent company; a Deny row holds nothing), plus the Master. Inactive users
  with history in the company move as **deactivated** cloud users, so names still show on old records, and they
  cannot sign in.
* **Roles, approval limits, project scope, approval chains and policies** live in the company file (`role`,
  `role_permission`, `approval_limit`, `user_project_scope`, `approval_policy`, `approval_step`), so they move
  with it unchanged. Each user's role in this company (`user_company_access.role_code`) goes in `users.json`.
* **The Master** becomes the company's **Owner** in the cloud: an Admin of this company plus the cloud account
  that started the move. The desktop's installation-wide Master power has no cloud counterpart (10, Q2).
* **Identity:** users sign in with their email address, compared ignoring case. The desktop username is kept
  only as a display alias in the cloud; it is not a login.
* **An email that already has a cloud account** (the person uses StrataLedger cloud elsewhere): the user is
  linked to that account and keeps its password. The desktop hash is not imported for them, and their first
  cloud sign-in uses their existing cloud password.

### 7.2 User ids in the company data
The company's tables store desktop user ids (`created_by`, `posted_by`, `approved_by`, `audit_log.user_id`,
approval actions), and the chain hashes some of them. They are never rewritten. Each company schema gets a
**company user map** (company-local user id to cloud user id). Moved users keep their desktop id as their local
id, and people invited later get new local ids above the highest one. Screens show names through the map. This
fits section 4 of CLAUDE.md (user ids in a company file are plain integers with no cross-file FK), and it is an
input to the hosted design (10, Q3).

### 7.3 Passwords
* `users.json` carries each moving user's `password_hash` exactly as stored: `scrypt$N$r$p$salt$hash` (N=2^15,
  r=8, p=1, a 16-byte salt). Only `auth.py` and `users.py` read `password_hash` (rule 13), so the package writer
  gets the hashes through a new function in `users.py`, `hashes_for_cloud_move(session, company_id)`, which is
  Master only and audited (an `auth_event` that names the company and the user count, never the hashes).
* **First cloud sign-in:** email plus the desktop password. The cloud verifies the password against the legacy
  scrypt hash, then at once stores it under the cloud scheme and deletes the legacy hash. Every later sign-in
  uses the cloud scheme only.
* **Not moved** (CM2): the Master recovery code, backup codes, and temporary passwords. A user with a temporary
  password or `must_change_password` set does not get their hash moved (the Admin knows that password). They
  get an invitation email with a "set your password" link instead, which also verifies their email.
* **Legacy hashes expire:** a hash not used within 90 days of the switch is deleted; after that the user signs in
  through normal account recovery (10, Q1).
* **Confirm before building:** whether the cloud's identity provider (for example Microsoft Entra External ID) can
  verify an imported scrypt hash, or needs a just-in-time migration hook that calls our own verifier. The design
  needs only "verify the legacy hash once, then replace it", whichever way it is done.

### 7.4 Email verification and two-factor sign-in
* **Verification:** at the first cloud sign-in, after the password, the cloud emails a one-time code to the
  address. The user sees no company data until it is entered. Because both the password and the mailbox are
  needed, a mistyped address does not let a stranger in: the stranger has the mailbox but not the password.
* **An unverified email:** password reset by email ("forgot password") is **off** for that account until it is
  verified, because that path needs only the mailbox. An Admin can resend the code or correct the address (the
  change is audited and needs a new verification). The pre-flight lists who moved and the report shows each
  person's state (Not signed in yet / Verified).
* **Two-factor sign-in:** required for the Owner and every Admin before they see company data, enrolled at the
  first sign-in (an authenticator app or passkey). Everyone else is offered it, with a "Later" button that is
  offered again at most once a month (0b: never nagging). Their recovery is the cloud's normal recovery; desktop
  backup codes do not carry over.

### 7.5 Threat model of moving password hashes
| Risk | Effect | Mitigation |
|---|---|---|
| The package is copied in transit or from cloud staging | Offline guessing against scrypt hashes | The whole package travels over TLS, and `users.json` and `keys.bundle` are inside an encrypted package (section 8); the upload copy is deleted after the move |
| The cloud database leaks before users first sign in | Offline guessing against the legacy hashes | Legacy hashes are stored encrypted under a Key Vault key (decrypted only to verify a sign-in), deleted at first sign-in, and expire after 90 days |
| scrypt at N=2^15 is weaker than the cloud scheme | Weak passwords are cheaper to guess | Upgraded at first sign-in; the 12-character minimum (PW10) applies; at the first sign-in the cloud can check the password against a breached-password list (confirm before building) |
| A desktop Admin set a weak or known password for someone | The cloud inherits it | Temporary-password hashes are never moved (7.3); two-factor sign-in is required for Admins |
| A mistyped email | A stranger receives the invitation or the code | Verification needs the password as well; email reset is off until the address is verified; the Owner reviews the user list on the consent screen |
| The desktop file is stolen later | The same hashes as today | Unchanged; the move adds no new copy on the desktop |

The alternative, making everyone reset, is safer but not seamless. The owner chose seamless (CM2). These
mitigations keep the extra exposure to a single trip and at most 90 days.

---

## 8. Security and privacy

* **Transport:** HTTPS only, TLS 1.2 or newer, with certificates and host names checked against the system's
  trust store (Python `ssl.create_default_context()`), and no option to turn the checks off. The upload is
  chunked and resumable, each chunk carries its SHA-256, and the move token expires after 24 hours.
* **Package encryption:** the cloud-move package is encrypted on the desktop before upload: AES-256-GCM under a
  random content key wrapped to the migration key (section 4). The upload store holds only ciphertext.
* **Retention:** the uploaded package is deleted once the move is confirmed or cancelled (and at the 7-day
  expiry). The verification report is kept with the company.
* **Consent:** section 1 step 4. The consent text, its version and the Master's acceptance are stored in the cloud
  and in the desktop `audit_log`.
* **Data residency:** the region is chosen when the cloud account is created and is shown on the consent screen;
  the company's data, attachments and keys stay in that region.
* **Philippine data-privacy rules (confirm before building):** the Data Privacy Act of 2012 (Republic Act 10173),
  its implementing rules and the National Privacy Commission's guidance on cross-border transfer, processor
  agreements, registration and breach notification. In particular: whether a Philippine company moving
  employees' and customers' personal data to an overseas Azure region needs anything beyond the consent screen;
  whether a Philippine region is required or offered; and what StrataLedger's role is (personal information
  processor for the customer). The same check is needed for any US state rules that apply. None of this is
  decided here.
* **Logs:** the move logs phases, counts and errors, never hashes, keys, the token or row contents (R30-style
  filtering).
* **Not moved:** recovery and backup codes, temporary passwords, SMTP and feed tokens, AI keys and the installation
  key. Each is set up again in the cloud.

---

## 9. What desktop work comes first, and what waits

**Desktop, in Phase 5 (with the backup step, backlog 16):**
1. The package format (section 3): writer, reader, the ZIP safety rules and the manifest MAC, used first by
   backups and exports.
2. The key bundle with the passphrase recipient (K8); then drop `EXPORT_NOT_VERIFIABLE` (KS11).
3. Attachment SHA-256 recorded at upload (audit design 10), so the package's hashes are evidence and not only a
   transfer check.
4. In `users.py`: email required (not empty), valid in form and unique ignoring case for new and changed users,
   with a Users-screen warning for existing users who lack one. Then the pre-flight rarely blocks.
5. The pre-flight checks that need no cloud (section 2), runnable as "Check this company" on the desktop.

**Waits for the hosted product:** the cloud account and sign-in, the move token, the cloud recipient and Key
Vault import, encrypted upload, the importer and hosted schema, cloud verification and the comparisons, the
company user map, legacy-hash sign-in, email verification and two-factor sign-in, the consent screen, the
`Migration` checkpoint, and the desktop "moved" read-only state.

**Baseline gaps (report only; nothing changed):**
* `ledger_checkpoint.kind` and the master `chain_checkpoint.kind` CHECKs have no `Migration` value.
* `company_registry` has no "moved to cloud" state (moved at, cloud address). The company file has no read-only
  flag either. Archive (S9) is a different state and is not reused.
* `file_attachment` has no `sha256` and stores a path, not a storage key (H3).
* `app_user.email` has no uniqueness or format check.
* No table records a move (started, by whom, package hash, consent version, state); an `auth_event` type or a
  master `cloud_move` table is needed.

---

## 10. Tests and open questions

**Tests** (written first, in the build phase; the desktop ones in Phase 5):
* Package: round trip (write, read, every member's hash matches); the reader refuses a tampered member, a wrong
  manifest MAC, a higher major version, absolute paths, `..`, duplicate names and symlinks; a backup package
  restores to an identical file.
* Key bundle: wrong passphrase refused; a bundle moved to another package refused (associated data); each key's
  fingerprint is checked; `Key lost` keys are absent and their rows present; no key bytes in logs, exceptions or
  `repr`.
* Pre-flight: Broken blocks; Unavailable blocks; an unverified range warns with the range in the message; a
  missing, duplicate (case-insensitive) or invalid email blocks and names the user; a newer baseline blocks; a
  missing attachment blocks; drafts and pending approvals are counted.
* Hashes: `hashes_for_cloud_move` is Master only, writes an audit event with no hash, and is the only new reader
  of `password_hash` (the static rule 13 test is extended, not relaxed); temporary-password users are left out.
* Proof (hosted, with the PostgreSQL port): the golden vectors pass; a moved company re-verifies with the same
  head; trial balance per period, row counts and table hashes match; one changed value in any table is found
  and named; ids are kept (spot checks plus the table hashes).
* Switch: confirm is refused if the desktop changed after the package; after confirm every write service refuses
  with the "lives in the cloud" sentence while reads, reports and verification work; a failed activation leaves
  the desktop read-only and retryable; cancel leaves the desktop byte-identical.
* Users: email sign-in; legacy hash verified once and replaced; expired legacy hash refused; email reset refused
  while unverified; Admin and Owner cannot see data before two-factor enrolment.

**Questions, decided (owner, 2026-11-13, CM3): every answer below was accepted as proposed.**
1. **How long do legacy hashes live in the cloud?** Proposed: 90 days after the switch, then deleted; the user
   uses normal account recovery.
2. **What does the desktop Master become?** Proposed: the company's Owner (Admin plus the cloud account that
   moved it, with billing). Installation-wide powers do not carry over.
3. **How does the cloud keep desktop user ids?** Proposed: a company user map in each company schema (7.2);
   moved users keep their desktop id as their local id. To be confirmed when the hosted design is written.
4. **How long can a move wait unconfirmed?** Proposed: 7 days, then it is cleaned up as if cancelled, with an
   email to the Master the day before.
5. **Can a company come back to the desktop?** Proposed: not in this feature; later, "Download to desktop"
   builds the same package from the cloud and opens it as a new desktop company.
6. **Parents and subsidiaries:** proposed: one company per move. The pre-flight lists related companies and
   suggests moving them in a row. Consolidated reports (E5) work only when all of them are in the same place.
7. **Can an Admin start the move?** Proposed: no, only the Master, because the keys leave only with the Master
   (K8). Admins see the entry and the "ask the Master" sentence.
8. **Is the desktop locked during upload?** Proposed: no. The switch is refused if anything changed after the
   package was made (section 6), so the team keeps working during a slow upload.
9. **Breached-password check at first cloud sign-in?** Proposed: yes, if the identity provider offers it (confirm
   before building); a match forces a new password after verification.
10. **Package container:** proposed: ZIP with fixed member names (section 3) rather than a custom format.
    Decide with backlog 16.

---

## Phase placement

* **Phase 5 (desktop, before v1.0):** the package format, the key bundle (passphrase recipient), attachment
  hashes, the email rules in `users.py`, and the desktop-only pre-flight (section 9). These serve backups and
  exports in v1.0 whether or not the cloud exists.
* **With the hosted product (P5; not yet scheduled in the release plan):** everything else in section 9. The hosted product's own design
  (multi-tenancy, identity provider, threat model) comes first. This design is one of its inputs.
