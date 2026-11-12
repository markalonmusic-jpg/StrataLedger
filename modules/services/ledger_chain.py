"""The tamper-evident ledger chain: canonical form, seal and verification (docs/audit_readiness_design.md 2).

Pure functions: no database access, no stored keys. The posting service (Phase 2.5 step 3) reads the rows,
gets the key from a KeyProvider and calls `seal`; verification reads rows and calls `verify_chain`.

    chain_hash(N) = HMAC-SHA256(key, b"SLJ1" 0 company_code 0 prev_hash 0 canonical_entry(N))

* Entry 1 chains to GENESIS (64 zeros). Order is entry_number (gapless, L4).
* A chain key is 32 random bytes (`new_key`). It never appears in the company file; the file holds only its
  fingerprint, HMAC(key, FINGERPRINT_LABEL) in lowercase hex, which identifies the key and reveals nothing.
* The canonical form is defined on values, not on any driver or SQL dialect (2.4): sorted-key JSON, no spaces,
  UTF-8; integers, text and null only (floats and booleans are refused); dates as stored (YYYY-MM-DD);
  timestamps normalised to UTC whole seconds, YYYY-MM-DDTHH:MM:SSZ; lines sorted by line_id and dimensions by
  type id in Python. The golden vectors in tests/data/ledger_chain_vectors.json freeze version 1.
* Every column of journal_entry, journal_line and journal_line_dimension is listed below as hashed or excluded;
  a test fails on an unclassified column. A newly hashed field means a new chain_version.
"""
import hashlib
import hmac
import json
import re
import secrets
from datetime import datetime, timezone

CHAIN_VERSION = 1
SUPPORTED_VERSIONS = (1,)
KEY_BYTES = 32
GENESIS = "0" * 64
DOMAIN = b"SLJ1"
FINGERPRINT_LABEL = b"StrataLedger chain key fingerprint v1"

HASHED_ENTRY = (
    "entry_id", "entry_number", "entry_date", "period_id", "reference", "description", "source", "origin",
    "created_by", "created_at", "posted_by", "posted_at", "approved_by", "approved_at", "reverses_entry_id",
    "reversal_reason", "reversal_note", "auto_reverse_date", "chain_version", "chain_key_id",
)
# Excluded: state that legitimately changes after posting (is_void, set by the Void reversal; is_posted, always 1
# on a sealed entry) and the seal itself.
EXCLUDED_ENTRY = ("is_posted", "is_void", "chain_prev_hash", "chain_hash")
HASHED_LINE = (
    "line_id", "entry_id", "account_id", "debit_cents", "credit_cents", "memo", "contact_id", "project_id",
    "cost_code_id", "deferral_id", "batch_id", "is_retainage_line", "external_ref", "is_control_override",
    "is_rounding_adjustment",
)
EXCLUDED_LINE = ("recon_id",)            # set and cleared by bank reconciliation (B10)
HASHED_DIMENSION = ("dimension_type_id", "dimension_value_id")
EXCLUDED_DIMENSION = ("line_id",)        # the key that groups dimensions under their (hashed) line

TIMESTAMP_FIELDS = ("created_at", "posted_at", "approved_at")
DATE_FIELDS = ("entry_date", "auto_reverse_date")
_HEX64 = re.compile(r"[0-9a-f]{64}")


class ChainFormatError(ValueError):
    """A value cannot be sealed (wrong type, float, bad timestamp, missing field, bad key or hash)."""


# --- Keys ---------------------------------------------------------------------------------------------------

def new_key():
    """A new chain key: 32 random bytes from the operating system's secure source."""
    return secrets.token_bytes(KEY_BYTES)


def _check_key(key):
    if not isinstance(key, bytes) or len(key) != KEY_BYTES:
        raise ChainFormatError(f"A chain key is {KEY_BYTES} bytes")


def fingerprint(key):
    """The key's public identifier: HMAC-SHA256(key, FINGERPRINT_LABEL) as 64 lowercase hex characters."""
    _check_key(key)
    return hmac.new(key, FINGERPRINT_LABEL, hashlib.sha256).hexdigest()


# --- Canonical form -------------------------------------------------------------------------------------------

def _timestamp(field, value):
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ChainFormatError(f"{field} must be a timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ChainFormatError(f"{field} is not a valid timestamp") from None
    if parsed.tzinfo is None:                  # SQLite CURRENT_TIMESTAMP and datetime('now') are UTC
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _value(field, value):
    if field in DATE_FIELDS and value is not None and not isinstance(value, str):
        raise ChainFormatError(f"{field} must be a date (YYYY-MM-DD)")
    if value is None or isinstance(value, str):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    raise ChainFormatError(f"{field} has a value that cannot be sealed ({type(value).__name__})")


def _pick(row, fields, what):
    try:
        return {f: (_timestamp(f, row[f]) if f in TIMESTAMP_FIELDS else _value(f, row[f])) for f in fields}
    except (KeyError, IndexError):
        missing = [f for f in fields if f not in row.keys()]
        raise ChainFormatError(f"The {what} is missing {', '.join(missing)}") from None


def canonical_entry(header, lines, dimensions=()):
    """The exact bytes sealed for one entry. `header`, `lines` and `dimensions` are mappings (rows read by name);
    extra keys are ignored, so whole rows may be passed."""
    entry = _pick(header, HASHED_ENTRY, "entry")
    picked = sorted((_pick(line, HASHED_LINE, "line") for line in lines),
                    key=lambda line: (line["line_id"] is None, line["line_id"]))
    by_line = {line["line_id"]: [] for line in picked}
    for dim in dimensions:
        if dim["line_id"] not in by_line:
            raise ChainFormatError("A dimension belongs to a line that is not in this entry")
        values = _pick(dim, HASHED_DIMENSION, "dimension")
        by_line[dim["line_id"]].append([values["dimension_type_id"], values["dimension_value_id"]])
    for line in picked:
        line["dimensions"] = sorted(by_line[line["line_id"]], key=lambda pair: (pair[0], pair[1]))
    text = json.dumps({"entry": entry, "lines": picked}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return text.encode("utf-8")


# --- Seal and verify ---------------------------------------------------------------------------------------------

def _check_hash(value, what):
    if not isinstance(value, str) or not _HEX64.fullmatch(value):
        raise ChainFormatError(f"The {what} must be 64 lowercase hex characters")


def seal(key, company_code, prev_hash, canonical):
    """chain_hash for an entry: HMAC-SHA256 over the domain tag, company code, previous hash and canonical bytes."""
    _check_key(key)
    if not isinstance(company_code, str) or not company_code:
        raise ChainFormatError("A company code is needed to seal an entry")
    _check_hash(prev_hash, "previous hash")
    if not isinstance(canonical, bytes):
        raise ChainFormatError("The canonical entry must be bytes")
    message = b"\x00".join((DOMAIN, company_code.encode("utf-8"), prev_hash.encode("ascii"), canonical))
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def verify_chain(company_code, entries, key_for):
    """Check a run of sealed entries from entry 1. `entries` is an iterable of {'header', 'lines', 'dimensions'}
    mappings; `key_for(key_id)` returns that key's bytes or raises LookupError.

    Returns {'ok', 'through_entry_number', 'chain_hash', 'first_broken'}; first_broken is None or
    {'entry_number', 'entry_id', 'reason'} for the first entry that fails. The key never appears in the result.
    """
    expected_number, previous = 1, None
    ordered = sorted(entries, key=lambda e: e["header"]["entry_number"])

    def broken(header, reason):
        return {"ok": False, "through_entry_number": expected_number - 1, "chain_hash": previous,
                "first_broken": {"entry_number": expected_number, "entry_id": header.get("entry_id"),
                                 "reason": reason}}

    for item in ordered:
        header = dict(item["header"])
        if header.get("entry_number") != expected_number:
            return broken(header, "the entry numbers are not continuous here")
        if header.get("chain_version") not in SUPPORTED_VERSIONS:
            return broken(header, "it uses a seal format this version does not know")
        if header.get("chain_prev_hash") != (previous or GENESIS):
            return broken(header, "it does not link to the entry before it")
        try:
            key = key_for(header.get("chain_key_id"))
        except LookupError:
            return broken(header, "the key that sealed it is not available on this computer")
        try:
            expected = seal(key, company_code, header["chain_prev_hash"],
                            canonical_entry(header, item["lines"], item.get("dimensions", ())))
        except ChainFormatError:
            return broken(header, "it holds values that cannot have been sealed")
        stored = header.get("chain_hash")
        if not isinstance(stored, str) or not hmac.compare_digest(expected, stored):
            return broken(header, "it no longer matches the seal recorded when it was posted")
        previous = stored
        expected_number += 1
    return {"ok": True, "through_entry_number": expected_number - 1, "chain_hash": previous, "first_broken": None}
