"""Ledger integrity verification (Phase 2.5 step 3b; docs/audit_readiness_design.md 2.6 and 3; K3, K7, K11, K12).

`verify_ledger(context, mode=...)` checks the tamper-evident chain and records the result as a checkpoint.

* **Full** checks every posted entry from JE-000001. **Incremental** starts at the last OK checkpoint: it checks
  that the checkpointed entry still has the recorded hash, re-checks that entry's link and recomputes its seal,
  then checks the entries after it. It does NOT re-read the
  entries before the checkpoint, so an edit inside the already-verified range is found only by a full check
  (run at period and year close, on demand, and before backups).
* Per entry, in entry_number order: numbers consecutive (Gap); the sealing key's fingerprint matches the
  company's ledger_chain_key row (Key fingerprint); the previous-hash link, GENESIS first (Link); the recomputed
  seal (Hash). Then, for the whole ledger: every is_void = 1 has a posted Void reversal and every posted Void
  reversal's target is void (Void mismatch); the ledger still reaches the last OK checkpoint in the file and in
  the master's mirror and the entry counter (Truncated); every checkpoint used is checked against its MAC
  (Marker).
* **Unavailable**: the key provider cannot supply a key. That is never recorded and never reported as tampering.
* The reads use a read-only connection. The result is written afterwards in short separate writes: a
  ledger_checkpoint row in the company file and its mirror in the master (`chain_checkpoint`). A read-only
  (Auditor) context records in the master only.
* A period, Books closed through or year close signs the full verification it ran as its close check as a
  'Period close' / 'Year close' checkpoint once the close has committed (`record_close_checkpoint`).
* Messages are plain language and name the first broken entry; they never contain a hash or a key.
"""
import hmac
import logging

from modules.services import keys, ledger_chain
from modules.services.authz import authorize
from modules.services.errors import KeyUnavailableError, NotFoundError, ValidationError
from modules.services.tx import read_connection, write_transaction

_logger = logging.getLogger("strataledger")
VERIFY = "ledger.verify"
MODES = ("incremental", "full")
OK, BROKEN, UNAVAILABLE = "OK", "Broken", "Unavailable"
LINK, HASH, GAP, VOID, KEY, TRUNCATED, MARKER = (
    "Link", "Hash", "Gap", "Void mismatch", "Key fingerprint", "Truncated", "Marker")
REASON_TEXT = {
    LINK: "it does not link to the entry before it",
    HASH: "it no longer matches the seal recorded when it was posted, so it may have been changed outside "
          "StrataLedger",
    GAP: "it is missing from the ledger",
    VOID: "its void mark does not match its Void reversal",
    KEY: "the key that sealed it does not match this company's key record",
    TRUNCATED: "it and any entries after it are missing from the end of the ledger",
    MARKER: "the record of an earlier verification no longer matches its signature",
}
UNAVAILABLE_MESSAGE = ("The ledger could not be checked on this computer because its key is not available; this "
                       "is not a sign of tampering. Ask the Master to sign in and restore the ledger key with the "
                       "recovery code.")


def je_number(number):
    return f"JE-{number:06d}"


# --- The check itself (pure over a connection) -------------------------------------------------------------------

def _grouped(conn, sql, start):
    grouped = {}
    for row in conn.execute(sql, (start,)):
        grouped.setdefault(row["entry_id"], []).append(row)
    return grouped


def verify_connection(conn, company_code, key_for, *, mode="full", anchors=()):
    """Check the chain over `conn`. `key_for(key_id)` returns key bytes or raises KeyUnavailableError; `anchors`
    are extra checkpoint rows to hold the ledger to (the master's mirror). Returns {'status', 'scope',
    'through_entry_number', 'chain_hash', 'first_broken': None | {'entry_number', 'reason', 'detail'}}."""
    scope = "Incremental" if mode == "incremental" else "Full"
    try:
        return _check(conn, company_code, key_for, mode, anchors)
    except KeyUnavailableError:
        return {"status": UNAVAILABLE, "scope": scope, "through_entry_number": None, "chain_hash": None,
                "first_broken": None}


def _check(conn, company_code, key_for, mode, anchors):
    fingerprints = {r["key_id"]: r["fingerprint"] for r in conn.execute("SELECT key_id, fingerprint FROM ledger_chain_key")}
    checked = {}

    def key(key_id):
        if key_id not in checked:
            raw = key_for(key_id)                                    # may raise KeyUnavailableError
            matches = key_id in fingerprints and hmac.compare_digest(ledger_chain.fingerprint(raw),
                                                                     fingerprints[key_id])
            checked[key_id] = raw if matches else None
        return checked[key_id]

    scope = "Full"

    def hash_at(number):
        if number <= 0:
            return None
        row = conn.execute("SELECT chain_hash FROM journal_entry WHERE is_posted = 1 AND entry_number = ?",
                           (number,)).fetchone()
        return row["chain_hash"] if row else None

    def broken(number, reason, detail=None):
        return {"status": BROKEN, "scope": scope, "through_entry_number": number - 1,
                "chain_hash": hash_at(number - 1), "first_broken": {"entry_number": number, "reason": reason,
                                                                    "detail": detail}}

    # Every checkpoint we rely on must carry a valid MAC (Marker).
    marker = conn.execute("SELECT * FROM ledger_checkpoint WHERE result = 'OK' "
                          "ORDER BY checkpoint_id DESC LIMIT 1").fetchone()
    held = ([("company", dict(marker))] if marker else []) + [("master", dict(a)) for a in anchors]
    for source, anchor in held:
        through = anchor["through_entry_number"]
        raw = key(anchor["key_id"]) if anchor["key_id"] is not None else None
        place = "this computer's record" if source == "master" else "the company file's record"
        if raw is None or not hmac.compare_digest(ledger_chain.checkpoint_mac(raw, company_code, anchor),
                                                  anchor["mac"] or ""):
            return broken(max(1, through), MARKER, f"{place} of the check through {je_number(max(1, through))}")

    start, prev = 1, ledger_chain.GENESIS
    if mode == "incremental" and marker is not None:
        scope = "Incremental"
        through = marker["through_entry_number"]
        if through > 0:
            stored = hash_at(through)
            if stored is None:
                last = conn.execute("SELECT COALESCE(MAX(entry_number), 0) AS n FROM journal_entry "
                                    "WHERE is_posted = 1").fetchone()["n"]
                return broken(through if last >= through else last + 1, GAP if last >= through else TRUNCATED,
                              f"the ledger was verified through {je_number(through)} on {marker['created_at'][:10]}")
            if stored != marker["chain_hash"]:
                return broken(through, HASH, f"it no longer matches the check of {marker['created_at'][:10]}")
            # Re-check the checkpointed entry itself (its link and its recomputed seal), then everything after it.
            start, prev = through, hash_at(through - 1) or ledger_chain.GENESIS

    entries = conn.execute("SELECT * FROM journal_entry WHERE is_posted = 1 AND entry_number >= ? "
                           "ORDER BY entry_number", (start,)).fetchall()
    lines = _grouped(conn, "SELECT l.* FROM journal_line AS l JOIN journal_entry AS e ON e.entry_id = l.entry_id "
                           "WHERE e.is_posted = 1 AND e.entry_number >= ? ORDER BY l.entry_id, l.line_id", start)
    dims = {}
    for row in conn.execute("SELECT l.entry_id, d.* FROM journal_line_dimension AS d JOIN journal_line AS l "
                            "ON l.line_id = d.line_id JOIN journal_entry AS e ON e.entry_id = l.entry_id "
                            "WHERE e.is_posted = 1 AND e.entry_number >= ?", (start,)):
        dims.setdefault(row["entry_id"], []).append(row)

    expected, chain_break = start, None
    for entry in entries:
        number = entry["entry_number"]
        if number != expected:
            chain_break = (expected, GAP, None)
            break
        raw = key(entry["chain_key_id"])
        if raw is None:
            chain_break = (number, KEY, None)
            break
        if entry["chain_prev_hash"] != prev:
            chain_break = (number, LINK, None)
            break
        try:
            if entry["chain_version"] not in ledger_chain.SUPPORTED_VERSIONS:
                raise ledger_chain.ChainFormatError("unknown seal format")
            recomputed = ledger_chain.seal(raw, company_code, prev, ledger_chain.canonical_entry(
                entry, lines.get(entry["entry_id"], ()), dims.get(entry["entry_id"], ())))
        except ledger_chain.ChainFormatError:
            recomputed = None
        if recomputed is None or not hmac.compare_digest(recomputed, entry["chain_hash"] or ""):
            chain_break = (number, HASH, None)
            break
        prev, expected = entry["chain_hash"], expected + 1
    last = expected - 1

    # Void cross-check over the whole ledger (cheap: no hashing).
    void_wrong = [r["entry_number"] for r in conn.execute(
        "SELECT e.entry_number FROM journal_entry AS e WHERE e.is_posted = 1 AND e.is_void = 1 AND NOT EXISTS ("
        "  SELECT 1 FROM journal_entry AS r WHERE r.reverses_entry_id = e.entry_id AND r.reversal_reason = 'Void' "
        "  AND r.is_posted = 1) "
        "UNION SELECT e.entry_number FROM journal_entry AS e JOIN journal_entry AS r ON r.reverses_entry_id = e.entry_id "
        "  AND r.reversal_reason = 'Void' AND r.is_posted = 1 WHERE e.is_void = 0")]
    first_void = min(void_wrong) if void_wrong else None
    if chain_break is not None:
        if first_void is not None and first_void < chain_break[0]:
            return broken(first_void, VOID)
        return broken(*chain_break)
    if first_void is not None:
        return broken(first_void, VOID)

    # Truncation: the ledger must still reach every checkpoint we hold and the entry counter.
    for source, anchor in held:
        through = anchor["through_entry_number"]
        when = (anchor["created_at"] or "")[:10]
        if through > last:
            detail = (f"this looks like an older copy of the company file: this computer checked the ledger through "
                      f"{je_number(through)} on {when}" if source == "master" else
                      f"the ledger was checked through {je_number(through)} on {when}")
            return broken(last + 1, TRUNCATED, detail)
        if through > 0 and hash_at(through) != anchor["chain_hash"]:
            return broken(through, HASH, f"it differs from the check of {when}")
    counter = conn.execute("SELECT last_number FROM entry_number_sequence WHERE id = 1").fetchone()["last_number"]
    if counter > last:
        return broken(last + 1, TRUNCATED, f"the entry counter has reached {je_number(counter)}")
    if counter < last:
        return broken(counter + 1, GAP, "the entry counter is behind the ledger")
    return {"status": OK, "scope": scope, "through_entry_number": last, "chain_hash": prev if last else None,
            "first_broken": None}


# --- Context helpers -------------------------------------------------------------------------------------------

def _company_code(context):
    conn = read_connection(context.master_db_path)
    try:
        row = conn.execute("SELECT company_code FROM company_registry WHERE company_id = ?",
                           (context.company_id,)).fetchone()
    finally:
        conn.close()
    if row is None:
        raise NotFoundError("This company is not registered on this computer")
    return row["company_code"]


def _master_anchors(context):
    conn = read_connection(context.master_db_path)
    try:
        row = conn.execute("SELECT * FROM chain_checkpoint WHERE company_id = ? AND result = 'OK' "
                           "ORDER BY mirror_id DESC LIMIT 1", (context.company_id,)).fetchone()
    finally:
        conn.close()
    return [dict(row)] if row else []


def _key_for(context):
    provider = keys.get_provider()
    return lambda key_id: provider.get_key(context.company_id, key_id).use_for_hmac()


def _poster_name(context, user_id):
    if user_id is None:
        return None
    conn = read_connection(context.master_db_path)
    try:
        row = conn.execute("SELECT username, first_name, last_name FROM app_user WHERE user_id = ?",
                           (user_id,)).fetchone()
    finally:
        conn.close()
    if row is None:
        return f"user {user_id}"
    name = " ".join(part for part in (row["first_name"], row["last_name"]) if part)
    return name or row["username"]


def _describe(conn, context, core):
    """Add the entry details and the plain-language message to a core result."""
    result = dict(core)
    if core["status"] == UNAVAILABLE:
        result["message"] = UNAVAILABLE_MESSAGE
        return result
    if core["status"] == OK:
        last = core["through_entry_number"]
        result["message"] = (f"The ledger checks out: entries {je_number(1)} to {je_number(last)} match their seals."
                             if last else "There are no posted entries yet, so there is nothing to check.")
        return result
    broken = dict(core["first_broken"])
    number = broken["entry_number"]
    row = conn.execute("SELECT entry_date, posted_by, posted_at FROM journal_entry WHERE is_posted = 1 "
                       "AND entry_number = ?", (number,)).fetchone()
    broken.update(je_number=je_number(number), entry_date=row["entry_date"] if row else None,
                  posted_by=row["posted_by"] if row else None, posted_at=row["posted_at"] if row else None)
    broken["posted_by_name"] = _poster_name(context, broken["posted_by"])
    reason = REASON_TEXT[broken["reason"]] + (f" ({broken['detail']})" if broken["detail"] else "")
    if broken["reason"] == MARKER:
        message = (f"Ledger check failed: {reason}. Run a full check; if it fails too, restore a recent backup or "
                   "ask your accountant to review.")
    elif row is not None:
        posted_day = (row["posted_at"] or "")[:10]
        message = (f"Ledger check failed at entry {broken['je_number']} (dated {row['entry_date']}, posted by "
                   f"{broken['posted_by_name']} on {posted_day}): {reason}. Entries before it are intact. Restore a "
                   f"backup made before {posted_day}, or ask your accountant to review.")
    else:
        message = (f"Ledger check failed at entry {broken['je_number']}: {reason}. Entries before it are intact. "
                   "Restore a recent backup, or ask your accountant to review.")
    result["first_broken"] = broken
    result["message"] = message
    return result


# --- The service ----------------------------------------------------------------------------------------------

def verify_ledger(context, *, mode="incremental"):
    """Verify the ledger and record the result. Returns {'status' (OK | Broken | Unavailable), 'scope',
    'through_entry_number', 'chain_hash', 'first_broken', 'message', 'checkpoint_id', 'recorded_in'}."""
    authorize(context, VERIFY, record_type="journal_entry")
    if mode not in MODES:
        raise ValidationError("Choose an incremental or a full check")
    return _verify_and_record(context, mode)


def checkpoint_on_close(context):
    """Sign a checkpoint of the ledger when its company is closed (logout) or the app exits, so a cut tail is
    caught after a ledger's first close even if nobody ran a check (step 3b follow-up). System upkeep: it needs
    no permission, runs an incremental check (full when there is no checkpoint yet) and records it like
    verify_ledger. It never raises, because it runs while a window is closing; a failure is logged.
    Returns the result, or None when no company is open or the check could not run at all."""
    if context is None:
        return None
    try:
        return _verify_and_record(context, "incremental")
    except Exception:                       # noqa: BLE001  (logged; closing must go on)
        _logger.exception("The ledger checkpoint on close could not be written (company_id=%s)", context.company_id)
        return None


def _verify_and_record(context, mode):
    conn = read_connection(context.company_db_path)
    try:
        result = _describe(conn, context, verify_connection(conn, _company_code(context), _key_for(context),
                                                            mode=mode, anchors=_master_anchors(context)))
    finally:
        conn.close()
    return _record(context, {**result, "checkpoint_id": None, "recorded_in": []}, kind="Verify")


CLOSE_KINDS = {"Period close": "fiscal_period", "Year close": "fiscal_year"}
CHECKPOINT_NOT_SAVED = ("The close is done, but its ledger checkpoint could not be saved. Run a ledger check to "
                        "record one.")


CHECKPOINT_PARTLY_SAVED = ("The close is done and its ledger checkpoint is saved in the company file, but not in "
                           "this computer's copy. Run a ledger check to record one.")
_CLOSED_SQL = {"Period close": "SELECT is_closed AS closed FROM fiscal_period WHERE period_id = ?",
               "Year close": "SELECT is_year_closed AS closed FROM fiscal_year WHERE year_id = ?"}


def record_close_checkpoint(context, verification, *, kind, ref_id):
    """Sign the close's own full verification as a 'Period close' or 'Year close' checkpoint, in the company file
    and the master mirror, after the close has committed (docs/audit_readiness_design.md section 3).
    `verification` is the result full_verification returned inside the close, so the ledger is not checked twice.
    Unavailable records nothing (K16). Before signing it confirms the period or year is closed and the verified
    hash is the one stored in the ledger. The close already stands, so nothing here raises after the commit: a
    refused permission, a failed confirmation or a failed write is logged and reported in 'checkpoint_error'
    (CHECKPOINT_PARTLY_SAVED when the company row was written but the master copy was not). Only periods.py calls
    it (a static test checks)."""
    if kind not in CLOSE_KINDS:
        raise ValidationError("Unknown close checkpoint")
    result = {**verification, "checkpoint_id": None, "recorded_in": []}
    try:
        authorize(context, "period.close", record_type=CLOSE_KINDS[kind], record_id=ref_id)
        if result["status"] != UNAVAILABLE:
            _confirm_close(context, result, kind, ref_id)
        _record(context, result, kind=kind, ref_type=CLOSE_KINDS[kind], ref_id=ref_id)
    except Exception:                       # noqa: BLE001  (logged and reported; the close has committed)
        _logger.exception("The %s checkpoint could not be written (company_id=%s)", kind.lower(), context.company_id)
        result["checkpoint_error"] = CHECKPOINT_PARTLY_SAVED if result["recorded_in"] else CHECKPOINT_NOT_SAVED
    return result


def _confirm_close(context, verification, kind, ref_id):
    """Refuse to sign a close that did not happen, or a verification whose hash is not the stored ledger's."""
    conn = read_connection(context.company_db_path)
    try:
        row = conn.execute(_CLOSED_SQL[kind], (ref_id,)).fetchone()
        if row is None or not row["closed"]:
            raise ValidationError(f"{kind}: {CLOSE_KINDS[kind]} {ref_id} is not closed")
        through = verification["through_entry_number"]
        stored = None
        if through:
            entry = conn.execute("SELECT chain_hash FROM journal_entry WHERE is_posted = 1 AND entry_number = ?",
                                 (through,)).fetchone()
            stored = entry["chain_hash"] if entry else ""
        if stored != verification["chain_hash"]:
            raise ValidationError(f"{kind}: the verification through entry {through} does not match the ledger")
    finally:
        conn.close()


def _record(context, result, *, kind, ref_type=None, ref_id=None):
    """Write a verification result as a signed checkpoint row (company file unless read-only) and its master
    mirror. Fills in result['checkpoint_id'] and result['recorded_in'] as each write commits, so a caller that
    catches a failure knows what was saved. Returns the result."""
    if result["status"] == UNAVAILABLE:
        return result
    company_code = _company_code(context)
    key_for = _key_for(context)
    conn = read_connection(context.company_db_path)
    try:
        active = conn.execute("SELECT key_id FROM ledger_chain_key WHERE is_active = 1").fetchone()
    finally:
        conn.close()
    if active is None:
        return result
    checkpoint = {
        "created_at": context.now, "created_by": context.user_id, "kind": kind,
        "scope": result["scope"] if kind == "Verify" else None,
        "result": result["status"], "through_entry_number": result["through_entry_number"],
        "chain_hash": result["chain_hash"],
        "first_broken_entry_number": result["first_broken"]["entry_number"] if result["first_broken"] else None,
        "key_id": active["key_id"], "ref_type": ref_type, "ref_id": ref_id,
    }
    try:
        checkpoint["mac"] = ledger_chain.checkpoint_mac(key_for(active["key_id"]), company_code, checkpoint)
    except KeyUnavailableError:
        return result
    columns = ", ".join(checkpoint)
    marks = ", ".join("?" * len(checkpoint))
    if not context.read_only:
        with write_transaction(context.company_db_path, context) as write:
            result["checkpoint_id"] = write.execute(
                f"INSERT INTO ledger_checkpoint ({columns}) VALUES ({marks}) RETURNING checkpoint_id",
                tuple(checkpoint.values())).fetchone()[0]
        result["recorded_in"].append("company")
    mirror = {"company_id": context.company_id, "company_checkpoint_id": result["checkpoint_id"],
              "recorded_from": "Read-only" if context.read_only else "Company file", **checkpoint}
    with write_transaction(context.master_db_path, context) as master:
        master.execute(f"INSERT INTO chain_checkpoint ({', '.join(mirror)}) VALUES ({', '.join('?' * len(mirror))})",
                       tuple(mirror.values()))
    result["recorded_in"].append("master")
    return result


# --- The period-close check (L2) --------------------------------------------------------------------------------

def full_verification(conn, context):
    """A FULL verification over the caller's connection, described but not recorded (the close keeps it and
    records it with record_close_checkpoint once the close has committed)."""
    core = verify_connection(conn, _company_code(context), _key_for(context), mode="full",
                             anchors=_master_anchors(context))
    return _describe(conn, context, core)


def integrity_check(conn, context, label, mode, verification=None):
    """The ledger_integrity close check from a full verification (run here unless `verification` is given).
    Broken follows the check's mode (warn or block); Unavailable is always a warning that says the check could
    not run, never a failure."""
    described = verification if verification is not None else full_verification(conn, context)
    if described["status"] == OK:
        return {"code": "ledger_integrity", "mode": mode, "ok": True, "message": None, "period": label}
    if described["status"] == UNAVAILABLE:
        return {"code": "ledger_integrity", "mode": "warn", "ok": False, "period": label,
                "message": "Ledger verification could not run because the ledger key is not available on this "
                           "computer (this is not a sign of tampering)"}
    return {"code": "ledger_integrity", "mode": mode, "ok": False, "message": described["message"], "period": label}
