"""ledger.post_journal_entry, Phase 2.5 step 3 (decisions L4, L6, A5, R2, R5, R8, R9, K3; audit design 2.5, 2.7).

Approvals (step 4), reversals and auto-reversal (step 5), rounding (step 6) and the verify service (step 3b) are
later steps: until step 4, posting FAILS CLOSED for anything that would need an approval.

Replaces the post half of pending test `cannot_post_to_header_or_inactive_account` and pending test
`manual_entry_to_controlled_account_is_blocked` (the pending file is untouched until step 7).
"""
import dataclasses
import re
import sqlite3
import threading
from pathlib import Path

import pytest

from modules.services import keys, ledger, ledger_chain, periods
from modules.services.errors import (
    KeyUnavailableError, PeriodClosedError, PermissionDeniedError, PostingError, ValidationError,
)
from tests import ledger_helpers as lh
from tests.authz_world import world  # noqa: F401  (fixture)

NOW = "2026-03-20T10:00:00+00:00"
TODAY = "2026-03-20"
APPROVAL_MESSAGE = "This entry needs the approval step, which is not available yet."


@pytest.fixture
def keyed(monkeypatch):
    monkeypatch.setattr(keys, "_provider", keys.FixedKeyProvider(lh.TEST_CHAIN_KEY))


@pytest.fixture
def env(world, keyed):
    world.settings("PARENT", require_separate_approver=0)
    with world._company("PARENT") as c:
        periods.seed_years(c, 1, 2026)
        lh.ensure_test_chain_key(c)
        world.accts = {
            "cash": lh.make_account(c, "1010"),
            "sales": lh.make_account(c, "4010"),
            "ar": lh.make_account(c, "1200", control_type="AR"),
            "ap": lh.make_account(c, "2000", control_type="AP"),
            "inventory": lh.make_account(c, "1300", control_type="Inventory"),
        }
        world.customer = c.execute("INSERT INTO contact (name, is_customer, customer_code) VALUES "
                                   "('Client', 1, 'CL0001') RETURNING contact_id").fetchone()[0]
        world.vendor = c.execute("INSERT INTO contact (name, is_vendor, vendor_code) VALUES "
                                 "('Supplier', 1, 'VSU0001') RETURNING contact_id").fetchone()[0]
        world.plain_contact = lh.make_contact(c, "Neighbour")
    world.role("PARENT", "POSTER", ["je.create", "je.post", "ledger.view"])     # no period.view on purpose
    world.user_id = world.user("poster")
    world.grant(world.user_id, "PARENT", "POSTER")
    return world


def ctx_for(env, origin="Human", *, now=NOW, today=TODAY, user=None):
    return dataclasses.replace(env.ctx(user or env.user_id, "PARENT", origin), now=now, today=today)


@pytest.fixture
def ctx(env):
    return ctx_for(env)


def A(env, name):
    return env.accts[name]


def lines(env, amount=1000, debit="cash", credit="sales", **extra):
    return [{"account_id": A(env, debit), "debit_cents": amount, **extra.get("debit_extra", {})},
            {"account_id": A(env, credit), "credit_cents": amount, **extra.get("credit_extra", {})}]


def draft(env, ctx=None, *, entry_date="2026-03-15", entry_lines=None, **kwargs):
    return ledger.create_entry(ctx or ctx_for(env), entry_date=entry_date,
                               lines=entry_lines if entry_lines is not None else lines(env), **kwargs)


def entry_row(env, entry_id):
    return env.rows("PARENT", "SELECT * FROM journal_entry WHERE entry_id = ?", (entry_id,))[0]


def snapshot(env):
    return {t: env.rows("PARENT", f"SELECT * FROM {t} ORDER BY 1") for t in
            ("journal_entry", "journal_line", "audit_log", "entry_number_sequence", "ledger_checkpoint")}


def settings(env, **values):
    with env._company("PARENT") as c:
        for name, value in values.items():
            c.execute(f"UPDATE company_settings SET {name} = ? WHERE id = 1", (value,))


def verify(env):
    entries = []
    for header in env.rows("PARENT", "SELECT * FROM journal_entry WHERE is_posted = 1 ORDER BY entry_number"):
        entries.append({
            "header": header,
            "lines": env.rows("PARENT", "SELECT * FROM journal_line WHERE entry_id = ?", (header["entry_id"],)),
            "dimensions": env.rows("PARENT", "SELECT d.* FROM journal_line_dimension AS d JOIN journal_line AS l "
                                             "ON l.line_id = d.line_id WHERE l.entry_id = ?", (header["entry_id"],)),
        })
    key_id = env.rows("PARENT", "SELECT key_id FROM ledger_chain_key WHERE is_active = 1")[0]["key_id"]
    return ledger_chain.verify_chain("PARENT", entries, {key_id: lh.TEST_CHAIN_KEY}.__getitem__)


def refused(env, call, error=PostingError, match=None):
    before = snapshot(env)
    with pytest.raises(error, match=match):
        call()
    assert snapshot(env) == before


# --- happy path and the chain -----------------------------------------------------------------------------

def test_post_numbers_stamps_and_seals_the_entry(env, ctx):
    entry_id = draft(env)
    result = ledger.post_journal_entry(ctx, entry_id, confirm=True)
    row = entry_row(env, entry_id)
    assert result == {"entry_id": entry_id, "entry_number": 1, "warnings": []}
    assert (row["is_posted"], row["entry_number"], row["posted_by"], row["posted_at"]) == (1, 1, env.user_id, NOW)
    assert (row["chain_version"], row["chain_prev_hash"]) == (1, ledger_chain.GENESIS)
    assert re.fullmatch(r"[0-9a-f]{64}", row["chain_hash"])
    assert env.rows("PARENT", "SELECT last_number FROM entry_number_sequence") == [{"last_number": 1}]


def test_the_first_entry_chains_to_genesis_and_the_second_to_the_first(env, ctx):
    first, second = draft(env), draft(env)
    ledger.post_journal_entry(ctx, first, confirm=True)
    ledger.post_journal_entry(ctx, second, confirm=True)
    assert entry_row(env, first)["chain_prev_hash"] == ledger_chain.GENESIS
    assert entry_row(env, second)["chain_prev_hash"] == entry_row(env, first)["chain_hash"]
    result = verify(env)
    assert result["ok"] and result["through_entry_number"] == 2


def test_the_seal_is_bound_to_the_company_code(env, ctx):
    ledger.post_journal_entry(ctx, draft(env), confirm=True)
    entries = [{"header": entry_row(env, 1), "lines": env.rows("PARENT", "SELECT * FROM journal_line WHERE entry_id = 1"),
                "dimensions": []}]
    assert not ledger_chain.verify_chain("OTHER", entries, lambda key_id: lh.TEST_CHAIN_KEY)["ok"]


def test_posting_is_audited_as_a_post_with_who_when_and_origin(env, ctx):
    entry_id = draft(env)
    ledger.post_journal_entry(ctx, entry_id, confirm=True)
    log = env.rows("PARENT", "SELECT user_id, action, new_value FROM audit_log WHERE table_name = 'journal_entry' "
                             "AND record_id = ? AND action = 'Post'", (entry_id,))
    assert len(log) == 1 and log[0]["user_id"] == env.user_id
    import json
    snap = json.loads(log[0]["new_value"])
    assert (snap["posted_by"], snap["posted_at"], snap["origin"]) == (env.user_id, NOW, "Human")
    assert snap["chain_hash"] == entry_row(env, entry_id)["chain_hash"] and len(snap["lines"]) == 2


def test_a_system_post_needs_no_confirm(env):
    system = ctx_for(env, "System")
    entry_id = draft(env, system, source="Deferral")
    ledger.post_journal_entry(system, entry_id)
    assert entry_row(env, entry_id)["is_posted"] == 1


def test_posting_does_not_need_period_view(env, ctx):
    ledger.post_journal_entry(ctx, draft(env), confirm=True)     # the POSTER role has no period.view


# --- refusals that write nothing ------------------------------------------------------------------------

def test_post_needs_je_post(env):
    env.role("PARENT", "DRAFTER", ["je.create", "ledger.view"])
    drafter = env.user("drafter")
    env.grant(drafter, "PARENT", "DRAFTER")
    entry_id = draft(env)
    before = snapshot(env)
    with pytest.raises(PermissionDeniedError):
        ledger.post_journal_entry(ctx_for(env, user=drafter), entry_id, confirm=True)
    after = snapshot(env)
    assert {k: v for k, v in after.items() if k != "audit_log"} == {k: v for k, v in before.items() if k != "audit_log"}


@pytest.mark.parametrize("confirm", [False, None, "yes", 1])
def test_a_human_post_needs_confirm_true(env, ctx, confirm):
    entry_id = draft(env)
    refused(env, lambda: ledger.post_journal_entry(ctx, entry_id, confirm=confirm), ValidationError, "Confirm")


def test_an_agent_context_cannot_post(env):
    entry_id = draft(env)
    refused(env, lambda: ledger.post_journal_entry(ctx_for(env, "Agent"), entry_id, confirm=True),
            PermissionDeniedError)


def test_unknown_entry(env, ctx):
    with pytest.raises(Exception) as caught:
        ledger.post_journal_entry(ctx, 9999, confirm=True)
    assert type(caught.value).__name__ == "NotFoundError"


def test_an_entry_posts_only_once(env, ctx):
    entry_id = draft(env)
    ledger.post_journal_entry(ctx, entry_id, confirm=True)
    refused(env, lambda: ledger.post_journal_entry(ctx, entry_id, confirm=True), PostingError, "already posted")


def test_a_voided_entry_cannot_be_posted_again(env, ctx):
    entry_id = draft(env)
    ledger.post_journal_entry(ctx, entry_id, confirm=True)
    with env._company("PARENT") as c:
        lh.post(c, lh.make_reversal(c, entry_id, "Void", entry_date="2026-03-16"))
    assert entry_row(env, entry_id)["is_void"] == 1
    refused(env, lambda: ledger.post_journal_entry(ctx, entry_id, confirm=True), PostingError, "already posted")


def test_an_unbalanced_entry_is_refused_with_the_amounts(env, ctx):
    entry_id = draft(env, entry_lines=[{"account_id": A(env, "cash"), "debit_cents": 1000},
                                       {"account_id": A(env, "sales"), "credit_cents": 999}])
    refused(env, lambda: ledger.post_journal_entry(ctx, entry_id, confirm=True), PostingError,
            r"does not balance.*10\.00.*9\.99")


@pytest.mark.parametrize("count", [0, 1])
def test_an_entry_needs_two_lines(env, ctx, count):
    entry_id = draft(env, entry_lines=[{"account_id": A(env, "cash"), "debit_cents": 1000}][:count])
    refused(env, lambda: ledger.post_journal_entry(ctx, entry_id, confirm=True), PostingError, "two lines")


def close_month(env, day):
    with env._company("PARENT") as c:
        c.execute("UPDATE fiscal_period SET is_closed = 1, closed_at = '2026-04-01 00:00:00', closed_by = 1 "
                  "WHERE ? BETWEEN start_date AND end_date AND is_adjustment_period = 0", (day,))


def test_a_draft_made_before_its_period_closed_cannot_post(env, ctx):
    entry_id = draft(env, entry_date="2026-03-15")
    close_month(env, "2026-03-15")
    refused(env, lambda: ledger.post_journal_entry(ctx, entry_id, confirm=True), PeriodClosedError, "closed")


@pytest.mark.parametrize("change, wording", [
    ("is_active = 0", "inactive"),
    ("is_postable = 0", "header"),
    ("child", "header"),
])
def test_an_account_deactivated_or_made_a_header_since_the_draft_is_refused(env, ctx, change, wording):
    entry_id = draft(env)
    with env._company("PARENT") as c:
        if change == "child":
            lh.make_account(c, "1011", parent_id=A(env, "cash"))
        else:
            c.execute(f"UPDATE account SET {change} WHERE account_id = ?", (A(env, "cash"),))
    refused(env, lambda: ledger.post_journal_entry(ctx, entry_id, confirm=True), PostingError, wording)


def test_an_adjustment_period_entry_cannot_post_after_the_control_is_turned_off(env, ctx):
    settings(env, adjustment_periods_enabled=1)
    period_13 = env.rows("PARENT", "SELECT period_id FROM fiscal_period WHERE period_number = 13 "
                                   "AND start_date LIKE '2026-%'")[0]["period_id"]
    entry_id = draft(env, entry_date="2026-12-31", period_id=period_13)
    settings(env, adjustment_periods_enabled=0)
    refused(env, lambda: ledger.post_journal_entry(ctx, entry_id, confirm=True, acknowledge_date_warnings=True),
            ValidationError, "turned off")


def test_a_reversal_draft_is_not_posted_here(env, ctx):
    original = draft(env)
    ledger.post_journal_entry(ctx, original, confirm=True)
    with env._company("PARENT") as c:
        reversal = lh.make_reversal(c, original, "Correction", entry_date="2026-03-16")
    refused(env, lambda: ledger.post_journal_entry(ctx, reversal, confirm=True), PostingError, "reverse or void")


def test_an_entry_with_an_automatic_reversal_date_waits_for_step_5(env, ctx):
    entry_id = draft(env, entry_date="2026-03-31", auto_reverse_date="2026-04-01")
    refused(env, lambda: ledger.post_journal_entry(ctx, entry_id, confirm=True), PostingError, "automatic reversal")


# --- the key (K3: never post without it) ------------------------------------------------------------------

def test_no_key_provider_means_no_posting(env, ctx, monkeypatch):
    monkeypatch.setattr(keys, "_provider", keys.NullKeyProvider())
    entry_id = draft(env)
    refused(env, lambda: ledger.post_journal_entry(ctx, entry_id, confirm=True), KeyUnavailableError,
            "cannot seal ledger entries")


def test_a_key_that_does_not_match_the_company_fingerprint_is_refused(env, ctx, monkeypatch):
    monkeypatch.setattr(keys, "_provider", keys.FixedKeyProvider(bytes(32)))
    entry_id = draft(env)
    refused(env, lambda: ledger.post_journal_entry(ctx, entry_id, confirm=True), KeyUnavailableError, "does not match")


def test_a_company_without_an_active_key_cannot_post(env, ctx):
    with env._company("PARENT") as c:
        c.execute("UPDATE ledger_chain_key SET is_active = 0, retired_at = '2026-03-01T00:00:00+00:00', "
                  "retire_reason = 'Rotation'")
    entry_id = draft(env)
    refused(env, lambda: ledger.post_journal_entry(ctx, entry_id, confirm=True), KeyUnavailableError)


def test_drafts_still_save_without_a_key(env, ctx, monkeypatch):
    monkeypatch.setattr(keys, "_provider", keys.NullKeyProvider())
    assert draft(env)


def test_the_key_never_appears_in_errors_or_rows(env, ctx, monkeypatch):
    monkeypatch.setattr(keys, "_provider", keys.FixedKeyProvider(bytes(32)))
    with pytest.raises(KeyUnavailableError) as caught:
        ledger.post_journal_entry(ctx, draft(env), confirm=True)
    for secret in (bytes(32).hex(), lh.TEST_CHAIN_KEY.hex()):
        assert secret not in str(caught.value) and secret not in repr(caught.value)
    monkeypatch.setattr(keys, "_provider", keys.FixedKeyProvider(lh.TEST_CHAIN_KEY))
    ledger.post_journal_entry(ctx, draft(env), confirm=True)
    dump = repr(snapshot(env))
    assert lh.TEST_CHAIN_KEY.hex() not in dump


# --- the key provider interface ---------------------------------------------------------------------------

def test_secret_key_is_redacted_and_cannot_be_pickled():
    import pickle
    secret = keys.SecretKey(bytes(range(32)))
    assert "redacted" in repr(secret) and bytes(range(32)).hex() not in repr(secret) + str(secret)
    assert secret.use_for_hmac() == bytes(range(32))
    with pytest.raises(TypeError):
        pickle.dumps(secret)


def test_null_provider_always_refuses():
    with pytest.raises(KeyUnavailableError):
        keys.NullKeyProvider().get_key(1, 1)


def test_fixed_provider_is_for_tests_only(monkeypatch):
    monkeypatch.delenv("STRATALEDGER_ALLOW_TEST_KEYS", raising=False)
    with pytest.raises(RuntimeError):
        keys.FixedKeyProvider(bytes(32))


def test_the_default_provider_refuses(monkeypatch):
    import importlib
    fresh = importlib.reload(keys)
    try:
        assert isinstance(fresh.get_provider(), fresh.NullKeyProvider)
    finally:
        importlib.reload(keys)


# --- fail closed until step 4: anything that would need an approval --------------------------------------

def test_an_agent_drafted_entry_waits_for_the_approval_step(env, ctx):
    entry_id = draft(env, ctx_for(env, "Agent"))
    refused(env, lambda: ledger.post_journal_entry(ctx, entry_id, confirm=True), PostingError, APPROVAL_MESSAGE)


def test_an_import_entry_waits_for_the_approval_step(env, ctx):
    entry_id = draft(env, ctx_for(env, "Import"), source="Import")
    refused(env, lambda: ledger.post_journal_entry(ctx, entry_id, confirm=True), PostingError, APPROVAL_MESSAGE)
    refused(env, lambda: ledger.post_journal_entry(ctx_for(env, "Import"), entry_id), PostingError, APPROVAL_MESSAGE)


@pytest.mark.parametrize("threshold, amount, posts", [
    (None, 1, False),          # on with no threshold: every manual entry
    (1000, 1000, True),        # equal to the threshold posts (R5)
    (1000, 1001, False),       # strictly over needs approval
    (5000, 1000, True),
])
def test_manual_entry_approval_fails_closed_when_the_entry_qualifies(env, ctx, threshold, amount, posts):
    settings(env, manual_entry_approval=1, manual_entry_approval_threshold_cents=threshold)
    entry_id = draft(env, entry_lines=lines(env, amount))
    if posts:
        ledger.post_journal_entry(ctx, entry_id, confirm=True)
        assert entry_row(env, entry_id)["is_posted"] == 1
    else:
        refused(env, lambda: ledger.post_journal_entry(ctx, entry_id, confirm=True), PostingError, APPROVAL_MESSAGE)


def test_manual_entry_approval_is_off_by_default(env, ctx):
    ledger.post_journal_entry(ctx, draft(env, entry_lines=lines(env, 10 ** 9)), confirm=True)


def test_approval_refusals_apply_only_when_the_company_turns_the_control_on(env):
    """Confirmation before step 3b: with manual_entry_approval off (the default) a plain manual entry posts with
    no approval at any amount, even when a threshold is stored; a document type whose switch is off posts too."""
    settings(env, manual_entry_approval=0, manual_entry_approval_threshold_cents=1)
    human = ctx_for(env)
    for amount in (1, 2, 10 ** 6, 10 ** 12):
        entry_id = draft(env, entry_lines=lines(env, amount))
        ledger.post_journal_entry(human, entry_id, confirm=True)
        assert entry_row(env, entry_id)["is_posted"] == 1
    system = ctx_for(env, "System")
    for source in ("Bill", "Payment"):                 # their document_approval_setting rows default to off
        entry_id = draft(env, system, source=source)
        ledger.post_journal_entry(system, entry_id)
        assert entry_row(env, entry_id)["is_posted"] == 1


def test_a_document_entry_whose_document_type_needs_approval_fails_closed(env):
    with env._company("PARENT") as c:
        c.execute("UPDATE document_approval_setting SET requires_approval = 1 WHERE document_type = 'Bill'")
    system = ctx_for(env, "System")
    bill = draft(env, system, source="Bill")
    refused(env, lambda: ledger.post_journal_entry(system, bill), PostingError, APPROVAL_MESSAGE)
    other = draft(env, system, source="Deferral")
    ledger.post_journal_entry(system, other)                    # Deferral has no approval switch


# --- date warnings (L6), Human origin only ----------------------------------------------------------------

@pytest.mark.parametrize("entry_date, today, code", [
    ("2026-04-19", "2026-03-20", None),          # exactly 30 days ahead: no warning
    ("2026-04-20", "2026-03-20", "future"),      # 31 days ahead
    ("2026-04-01", "2026-06-30", None),          # exactly 90 days ago
    ("2026-03-31", "2026-06-30", "past"),        # 91 days ago
])
def test_date_warnings_boundaries(env, entry_date, today, code):
    human = ctx_for(env, today=today)
    entry_id = draft(env, human, entry_date=entry_date)
    if code is None:
        assert ledger.post_journal_entry(human, entry_id, confirm=True)["warnings"] == []
        return
    before = snapshot(env)
    with pytest.raises(ledger.DateWarningsError) as caught:
        ledger.post_journal_entry(human, entry_id, confirm=True)
    assert [w["code"] for w in caught.value.warnings] == [code]
    assert snapshot(env) == before
    result = ledger.post_journal_entry(human, entry_id, confirm=True, acknowledge_date_warnings=True)
    assert [w["code"] for w in result["warnings"]] == [code] and entry_row(env, entry_id)["is_posted"] == 1


def test_date_warning_days_follow_the_settings(env):
    settings(env, warn_future_days=5)
    human = ctx_for(env)
    entry_id = draft(env, human, entry_date="2026-03-26")
    with pytest.raises(ledger.DateWarningsError):
        ledger.post_journal_entry(human, entry_id, confirm=True)


def test_system_posts_get_no_date_warnings(env):
    system = ctx_for(env, "System", today="2026-12-01")
    entry_id = draft(env, system, entry_date="2026-03-15", source="Deferral")
    assert ledger.post_journal_entry(system, entry_id)["warnings"] == []


def test_a_warning_never_blocks_an_open_period(env):
    human = ctx_for(env, today="2027-12-01")
    entry_id = draft(env, human, entry_date="2026-01-05")
    ledger.post_journal_entry(human, entry_id, confirm=True, acknowledge_date_warnings=True)
    assert entry_row(env, entry_id)["is_posted"] == 1


# --- controlled accounts (A5, R9) ---------------------------------------------------------------------------

def test_a_manual_line_to_a_controlled_account_is_allowed_and_flagged_by_default(env, ctx):
    entry_id = draft(env, entry_lines=lines(env, debit="inventory"))
    ledger.post_journal_entry(ctx, entry_id, confirm=True)
    flags = {l["account_id"]: l["is_control_override"] for l in
             env.rows("PARENT", "SELECT * FROM journal_line WHERE entry_id = ?", (entry_id,))}
    assert flags == {A(env, "inventory"): 1, A(env, "sales"): 0}
    assert verify(env)["ok"]                       # the flag was set before sealing, so it is in the seal


def test_the_override_flag_is_part_of_the_seal(env, ctx):
    entry_id = draft(env, entry_lines=lines(env, debit="inventory"))
    ledger.post_journal_entry(ctx, entry_id, confirm=True)
    conn = sqlite3.connect(env.path("PARENT"))
    try:
        conn.execute("DROP TRIGGER journal_line_lock_update_posted")
        conn.execute("UPDATE journal_line SET is_control_override = 0 WHERE entry_id = ?", (entry_id,))
        conn.commit()
    finally:
        conn.close()
    assert verify(env)["first_broken"]["entry_number"] == 1


@pytest.mark.parametrize("source", [None, "Manual", "Adjustment"])
def test_manual_lines_to_controlled_accounts_are_refused_when_the_control_is_off(env, ctx, source):
    settings(env, allow_manual_control_je=0)
    entry_id = draft(env, entry_lines=lines(env, debit="inventory"), source=source)
    refused(env, lambda: ledger.post_journal_entry(ctx, entry_id, confirm=True), PostingError, "1300")


def test_document_entries_to_controlled_accounts_are_not_overrides(env):
    settings(env, allow_manual_control_je=0)
    system = ctx_for(env, "System")
    entry_id = draft(env, system, source="Invoice",
                     entry_lines=lines(env, debit="ar", debit_extra={"contact_id": env.customer}))
    ledger.post_journal_entry(system, entry_id)
    assert {l["is_control_override"] for l in env.rows("PARENT", "SELECT * FROM journal_line WHERE entry_id = ?",
                                                        (entry_id,))} == {0}


@pytest.mark.parametrize("account, contact, ok", [
    ("ar", None, False), ("ar", "plain_contact", False), ("ar", "vendor", False), ("ar", "customer", True),
    ("ap", None, False), ("ap", "customer", False), ("ap", "vendor", True),
])
def test_a_manual_ar_or_ap_line_must_name_the_customer_or_vendor(env, ctx, account, contact, ok):
    extra = {"contact_id": getattr(env, contact)} if contact else {}
    side = {"debit": account, "debit_extra": extra} if account == "ar" else {"credit": account, "debit": "cash",
                                                                            "credit_extra": extra}
    entry_id = draft(env, entry_lines=lines(env, **side))
    if ok:
        ledger.post_journal_entry(ctx, entry_id, confirm=True)
        assert entry_row(env, entry_id)["is_posted"] == 1
    else:
        wording = "customer" if account == "ar" else "vendor"
        refused(env, lambda: ledger.post_journal_entry(ctx, entry_id, confirm=True), PostingError, wording)


# --- numbering, rollback and concurrency --------------------------------------------------------------------

def test_a_failed_post_returns_the_number_and_leaves_the_chain_unchanged(env, ctx, monkeypatch):
    first = draft(env)
    ledger.post_journal_entry(ctx, first, confirm=True)
    second = draft(env)
    first_hash = entry_row(env, first)["chain_hash"]
    with monkeypatch.context() as patch:
        patch.setattr(ledger_chain, "seal", lambda *args, **kwargs: first_hash)   # collides at the final UPDATE
        refused(env, lambda: ledger.post_journal_entry(ctx, second, confirm=True), PostingError)
    ledger.post_journal_entry(ctx, second, confirm=True)
    assert entry_row(env, second)["entry_number"] == 2
    assert verify(env)["ok"]


def test_concurrent_posts_get_consecutive_numbers_and_an_unbroken_chain(env):
    writers = 6
    drafts = [draft(env) for _ in range(writers)]
    barrier = threading.Barrier(writers)
    errors = []

    def post(entry_id):
        try:
            barrier.wait(timeout=10)
            ledger.post_journal_entry(ctx_for(env), entry_id, confirm=True)
        except Exception as exc:          # noqa: BLE001  (collected and asserted below)
            errors.append(exc)

    threads = [threading.Thread(target=post, args=(entry_id,)) for entry_id in drafts]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert errors == []
    numbers = sorted(entry_row(env, entry_id)["entry_number"] for entry_id in drafts)
    assert numbers == list(range(1, writers + 1))
    result = verify(env)
    assert result["ok"] and result["through_entry_number"] == writers


# --- the period-close check for control overrides (R9) -------------------------------------------------------

def march_id(env):
    return env.rows("PARENT", "SELECT period_id FROM fiscal_period WHERE start_date = '2026-03-01' "
                              "AND is_adjustment_period = 0")[0]["period_id"]


def run_checks(env):
    with env._company("PARENT") as c:
        return {r["code"]: r for r in periods._run_checks(c, periods._period(c, march_id(env)))}


def test_control_overrides_close_check_lists_flagged_entries(env, ctx):
    assert run_checks(env)["control_overrides"]["ok"] is True
    flagged = draft(env, entry_lines=lines(env, debit="inventory"))
    ledger.post_journal_entry(ctx, flagged, confirm=True)
    ledger.post_journal_entry(ctx, draft(env), confirm=True)
    check = run_checks(env)["control_overrides"]
    assert (check["ok"], check["mode"]) == (False, "warn")
    assert "JE-000001" in check["message"] and "JE-000002" not in check["message"]


def test_control_overrides_check_can_block_a_close(env, ctx):
    ledger.post_journal_entry(ctx, draft(env, entry_lines=lines(env, debit="inventory")), confirm=True)
    with env._company("PARENT") as c:
        c.execute("UPDATE period_close_check SET mode = 'block' WHERE check_code = 'control_overrides'")
    assert run_checks(env)["control_overrides"]["mode"] == "block"


@pytest.mark.parametrize("code", ["control_overrides", "ledger_integrity"])
def test_set_close_check_mode_knows_the_new_codes(env, code):
    env.role("PARENT", "SETTINGS", ["company.settings"])
    admin = env.user("settings")
    env.grant(admin, "PARENT", "SETTINGS")
    periods.set_close_check_mode(ctx_for(env, user=admin), code, "block")
    assert env.rows("PARENT", "SELECT mode FROM period_close_check WHERE check_code = ?", (code,)) == [{"mode": "block"}]
    assert code in periods.CHECK_CODES


def test_ledger_integrity_is_registered_but_not_run_yet(env):
    assert "ledger_integrity" not in run_checks(env)


# --- static: one place posts ------------------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
POST_SQL = re.compile(r"\bis_posted\s*=\s*1\s*,", re.IGNORECASE)


def test_only_ledger_py_posts_and_it_has_one_posting_statement():
    offenders = []
    for path in list((ROOT / "modules").rglob("*.py")) + [ROOT / "app_strata.pyw"]:
        rel = path.relative_to(ROOT).as_posix()
        if "__pycache__" in rel:
            continue
        hits = POST_SQL.findall(path.read_text(encoding="utf-8"))
        if rel == "modules/services/ledger.py":
            assert len(hits) == 1, "ledger.py posts through exactly one UPDATE"
        elif hits:
            offenders.append(rel)
    assert offenders == []
