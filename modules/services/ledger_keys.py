"""Changing a company's ledger chain key: rotation (Step 1c sub-step 8; docs/audit_readiness_design.md 2.7).

Master only (a key change is an installation-level act, like export; no company permission is added, so the
company baseline does not change). Old keys are never deleted: they stay wrapped in the master and retired in
the company file, because verification needs them for the entries they sealed.

rotate_chain_key, in order:
1. the key store must be able to make a key (KeyStoreLockedError while locked, KS6);
2. a full ledger check under the current key; if that key is not available here, rotation is refused
   (ROTATION_NEEDS_KEY) because a lost key takes the key-lost path instead;
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


def _switch_keys(session, context, provider, new_key, old_key_id, *, event, retire_reason):
    """Steps 3 and 4: store the new key in the master, then retire the old one and activate the new one in the
    company file. Returns the new key_id. Checks the Master again itself, so no caller can skip it (rule 10)."""
    auth.require_master(session, "ledger.rotate_key")
    with write_transaction(context.master_db_path, context) as conn:
        provider.store_chain_key(conn, context.company_id, new_key, context.now)
        auth._insert_event(conn, event, user_id=context.user_id, actor_user_id=context.user_id,
                           company_id=context.company_id)
    with write_transaction(context.company_db_path, context) as conn:
        if old_key_id is not None:
            conn.execute("UPDATE ledger_chain_key SET is_active = 0, retired_at = ?, retire_reason = ? "
                         "WHERE key_id = ?", (context.now, retire_reason, old_key_id))
        return conn.execute("INSERT INTO ledger_chain_key (fingerprint, created_at, created_by) VALUES (?, ?, ?) "
                            "RETURNING key_id", (ledger_chain.fingerprint(new_key.use_for_hmac()), context.now,
                                                 context.user_id)).fetchone()[0]


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
    verification = ledger_verify.check_before_key_change(context)
    if verification["status"] == ledger_verify.UNAVAILABLE:
        raise KeyUnavailableError(ROTATION_NEEDS_KEY)
    new_key_id = _switch_keys(session, context, provider, new_key, old_key_id, event="Ledger key rotated",
                              retire_reason="Rotation")
    checkpoint = ledger_verify.record_key_checkpoint(context, verification, old_key_id=old_key_id)
    return {"old_key_id": old_key_id, "new_key_id": new_key_id, "checkpoint": checkpoint}
