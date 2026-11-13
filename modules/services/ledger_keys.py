"""Changing a company's ledger chain key: rotation (Step 1c sub-step 8) and a new key epoch when the key is lost
(sub-step 9, `start_new_key_epoch`, below); docs/audit_readiness_design.md 2.7.

Master only (a key change is an installation-level act, like export; no company permission is added, so the
company baseline does not change). Old keys are never deleted: they stay wrapped in the master and retired in
the company file, because verification needs them for the entries they sealed.

rotate_chain_key, in order:
1. the key store must be able to make a key (KeyStoreLockedError while locked, KS6);
2. the CURRENT key must open here, else rotation is refused (ROTATION_NEEDS_KEY): a lost key takes the key-lost
   path instead. Then a full ledger check; after a key-lost epoch it is OK with the unverified range (Step 1d,
   KS16), so the rotation signs its checkpoint as usual;
3. the new key, wrapped, into the master with a 'Ledger key rotated' auth_event (one master transaction);
4. the company file: the old key retired ('Rotation'), the new one active (one company transaction). A failure
   between 3 and 4 leaves an unused wrapped key in the master, never an active key that cannot be found;
5. the check from step 2 signed as a 'Key rotation' checkpoint with the new key (ledger_verify).
The next entry is sealed with the new key and chains to the old key's last hash.
"""
from modules.services import auth, companies, keys, ledger_chain, ledger_verify
from modules.services.errors import KeyUnavailableError, ValidationError
from modules.services.tx import read_connection, write_transaction

ROTATION_NEEDS_KEY = ("The ledger key cannot be rotated: the current key is not available on this computer. "
                      "Restore it with the recovery code first, or start a new ledger key if it is lost.")
NO_ACTIVE_KEY = "This company has no active ledger key to rotate."


def _active_key_id(context):
    conn = read_connection(context.company_db_path)
    try:
        row = conn.execute("SELECT key_id FROM ledger_chain_key WHERE is_active = 1").fetchone()
    finally:
        conn.close()
    return row["key_id"] if row else None


def _switch_keys(session, context, provider, new_key, old_key_id, *, event, retire_reason, in_company_tx=None):
    """Steps 3 and 4: store the new key in the master, then retire the old one and activate the new one in the
    company file. `in_company_tx(conn, new_key_id)`, when given, runs inside that same company transaction (the
    key-lost checkpoint, so an epoch never exists without it). Returns (new key_id, what in_company_tx returned).
    Checks the Master again itself, so no caller can skip it (rule 10)."""
    auth.require_master(session, "ledger.rotate_key")
    with write_transaction(context.master_db_path, context) as conn:
        provider.store_chain_key(conn, context.company_id, new_key, context.now)
        auth._insert_event(conn, event, user_id=context.user_id, actor_user_id=context.user_id,
                           company_id=context.company_id)
    with write_transaction(context.company_db_path, context) as conn:
        if old_key_id is not None:
            conn.execute("UPDATE ledger_chain_key SET is_active = 0, retired_at = ?, retire_reason = ? "
                         "WHERE key_id = ?", (context.now, retire_reason, old_key_id))
        new_key_id = conn.execute("INSERT INTO ledger_chain_key (fingerprint, created_at, created_by) "
                                  "VALUES (?, ?, ?) RETURNING key_id",
                                  (ledger_chain.fingerprint(new_key.use_for_hmac()), context.now,
                                   context.user_id)).fetchone()[0]
        return new_key_id, (in_company_tx(conn, new_key_id) if in_company_tx is not None else None)


def rotate_chain_key(session, company_id):
    """Rotate the company's ledger key (Master only). Returns {'old_key_id', 'new_key_id', 'checkpoint'}, where
    'checkpoint' is the signed 'Key rotation' result (status, through_entry_number, recorded_in, and
    'checkpoint_error' if it could not be saved)."""
    auth.require_master(session, "ledger.rotate_key")
    context = companies.open_company(session, company_id)
    provider = keys.get_provider()
    new_key = provider.new_chain_key()                               # KeyStoreLockedError while locked
    old_key_id = _active_key_id(context)
    if old_key_id is None:
        raise ValidationError(NO_ACTIVE_KEY)
    try:
        provider.get_key(company_id, old_key_id)                     # rotation needs the CURRENT key only
    except KeyUnavailableError:
        raise KeyUnavailableError(ROTATION_NEEDS_KEY) from None
    verification = ledger_verify.check_before_key_change(context)   # OK with its unverified range after an epoch
    new_key_id, _ = _switch_keys(session, context, provider, new_key, old_key_id, event="Ledger key rotated",
                                 retire_reason="Rotation")
    checkpoint = ledger_verify.record_key_checkpoint(context, verification, old_key_id=old_key_id)
    return {"old_key_id": old_key_id, "new_key_id": new_key_id, "checkpoint": checkpoint}


# --- Key lost: a new key epoch (sub-step 9, KS8) -------------------------------------------------------------------

KEY_STILL_AVAILABLE = ("This company's ledger key is still available on this computer, so it is not lost. Rotate "
                       "the key instead if it needs replacing.")


def _typed_code_matches(session, company_id, confirm_company_code):
    conn = read_connection(session.master_db_path)
    try:
        row = conn.execute("SELECT company_code FROM company_registry WHERE company_id = ?",
                           (company_id,)).fetchone()
    finally:
        conn.close()
    if row is None:
        raise ValidationError("No such company")
    if not isinstance(confirm_company_code, str) or confirm_company_code != row["company_code"]:
        raise ValidationError(f"Type the company code exactly as shown ({row['company_code']}) to continue")


def start_new_key_epoch(session, company_id, *, confirm_company_code):
    """Start a new ledger key for a company whose active key is lost on this computer (Master only; the company
    code must be typed). The old key is retired as 'Key lost' and a new one becomes active, so posting can go on.
    Entries sealed with the lost key stay readable but can no longer be verified. Returns {'old_key_id',
    'new_key_id', 'unverifiable_through', 'message', 'checkpoint_id', 'recorded_in'} plus 'checkpoint_error' when
    the master's copy of the checkpoint could not be saved.

    Needs the installation key (KeyStoreLockedError while it is locked). Refused while the active key can still
    be opened here (KEY_STILL_AVAILABLE): that key is rotated instead. In the same company transaction as the key
    switch it signs a 'Key lost' checkpoint (result 'Unverified') through the last sealed entry with the new key
    (Step 1d, KS12); the verifier then reports entries up to it as unverified and checks the ones after it. The
    master's copy is written afterwards: if it fails, the epoch stands and 'checkpoint_error' says so."""
    auth.require_master(session, "ledger.rotate_key")
    _typed_code_matches(session, company_id, confirm_company_code)
    context = companies.open_company(session, company_id)
    provider = keys.get_provider()
    new_key = provider.new_chain_key()                               # KeyStoreLockedError while locked
    old_key_id = _active_key_id(context)
    if old_key_id is not None:
        try:
            provider.get_key(company_id, old_key_id)
        except KeyUnavailableError:
            pass
        else:
            raise ValidationError(KEY_STILL_AVAILABLE)
    def key_lost_checkpoint(conn, new_key_id):
        if old_key_id is None:                                       # no key was lost: nothing to record
            return None
        return ledger_verify.insert_key_lost_checkpoint(conn, context, new_key=new_key, new_key_id=new_key_id,
                                                        lost_key_id=old_key_id)

    new_key_id, row = _switch_keys(session, context, provider, new_key, old_key_id, event="Ledger key lost",
                                   retire_reason="Key lost", in_company_tx=key_lost_checkpoint)
    recorded = (ledger_verify.mirror_key_lost_checkpoint(session, context, row) if row is not None
                else {"checkpoint_id": None, "recorded_in": []})
    through = row["through_entry_number"] if row is not None else 0
    if through:
        message = (f"A new ledger key was started. Entries up to {ledger_verify.je_number(through)} were sealed "
                   "with the lost key and can no longer be verified; their data is unchanged.")
    else:
        message = "A new ledger key was started. No entries were sealed with the lost key."
    return {"old_key_id": old_key_id, "new_key_id": new_key_id, "unverifiable_through": through,
            "message": message, **recorded}
