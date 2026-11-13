"""ledger_verify: the ledger integrity check and end-to-end tamper tests (Phase 2.5 step 3b).

docs/audit_readiness_design.md sections 2.6, 3 and 12; decisions K3, K7, K11, K12. Every tamper test works on the
test's own temporary company file and may drop the posted-row lock triggers there, as an outside tool would.
Each failing case must name the correct first broken entry.
"""
import dataclasses
import shutil
import sqlite3

import pytest

from modules.services import keys, ledger, ledger_chain, ledger_verify, periods, role_templates
from modules.services.errors import PermissionDeniedError, ValidationError
from tests import ledger_helpers as lh
from tests.authz_world import world  # noqa: F401  (fixture)

NOW = "2026-03-20T10:00:00+00:00"
TODAY = "2026-03-20"
KEY_B = bytes(range(1, 33))


@pytest.fixture
def keyed(monkeypatch):
    monkeypatch.setattr(keys, "_provider", keys.FixedKeyProvider(lh.TEST_CHAIN_KEY))


@pytest.fixture
def env(world, keyed):
    world.settings("PARENT", require_separate_approver=0)
    with world._company("PARENT") as c:
        periods.seed_years(c, 1, 2026)
        lh.ensure_test_chain_key(c)
        world.accts = {"cash": lh.make_account(c, "1010"), "sales": lh.make_account(c, "4010"),
                       "fees": lh.make_account(c, "4020")}
    world.role("PARENT", "BOOKS", ["je.create", "je.post", "ledger.view", "ledger.verify", "period.view",
                                   "period.close", "company.settings"])
    world.user_id = world.user("books")
    world.grant(world.user_id, "PARENT", "BOOKS")
    return world


def ctx_for(env, origin="Human", *, user=None, **changes):
    base = env.ctx(user or env.user_id, "PARENT", origin)
    return dataclasses.replace(base, now=NOW, today=TODAY, **changes)


@pytest.fixture
def ctx(env):
    return ctx_for(env)


def post_entries(env, ctx, count, *, start_amount=1000):
    ids = []
    for index in range(count):
        amount = start_amount * (index + 1)
        entry_id = ledger.create_entry(ctx, entry_date="2026-03-15", lines=[
            {"account_id": env.accts["cash"], "debit_cents": amount, "memo": f"line {index + 1}"},
            {"account_id": env.accts["sales"], "credit_cents": amount}])
        ledger.post_journal_entry(ctx, entry_id, confirm=True)
        ids.append(entry_id)
    return ids


@pytest.fixture
def four(env, ctx):
    """A ledger with entries JE-000001 to JE-000004 (entry ids are returned in number order)."""
    return post_entries(env, ctx, 4)


def rows(env, table, where="1 = 1", params=()):
    return env.rows("PARENT", f"SELECT * FROM {table} WHERE {where} ORDER BY 1", params)


def tamper(env, *statements):
    """Edit the file as an outside tool would: drop every trigger that guards the journal, then run SQL."""
    conn = sqlite3.connect(env.path("PARENT"))
    try:
        for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type = 'trigger' AND tbl_name IN "
                                    "('journal_entry', 'journal_line', 'journal_line_dimension', "
                                    "'entry_number_sequence', 'ledger_checkpoint', 'ledger_chain_key')").fetchall():
            conn.execute(f'DROP TRIGGER "{name}"')
        for statement in statements:
            if isinstance(statement, tuple):
                conn.execute(*statement)
            else:
                conn.execute(statement)
        conn.commit()
    finally:
        conn.close()


def broken_at(result):
    assert result["status"] == "Broken", result
    return result["first_broken"]["entry_number"], result["first_broken"]["reason"]


def full(ctx):
    return ledger_verify.verify_ledger(ctx, mode="full")


def entry_id_of(env, number):
    return rows(env, "journal_entry", "entry_number = ?", (number,))[0]["entry_id"]


# --- the confirmation asked for before step 3b -------------------------------------------------------------

def test_a_clean_ledger_verifies(env, ctx, four):
    result = full(ctx)
    assert result["status"] == "OK" and result["through_entry_number"] == 4 and result["first_broken"] is None
    assert result["chain_hash"] == rows(env, "journal_entry", "entry_number = 4")[0]["chain_hash"]
    assert "JE-000001" in result["message"] and "JE-000004" in result["message"]


def test_an_empty_ledger_verifies(env, ctx):
    result = full(ctx)
    assert (result["status"], result["through_entry_number"], result["chain_hash"]) == ("OK", 0, None)


# --- tamper tests: each names the first broken entry --------------------------------------------------------

def test_edited_line_amount(env, ctx, four):
    tamper(env, ("UPDATE journal_line SET debit_cents = 2001 WHERE entry_id = ? AND debit_cents > 0",
                 (entry_id_of(env, 2),)))
    assert broken_at(full(ctx)) == (2, "Hash")


def test_edited_memo(env, ctx, four):
    tamper(env, ("UPDATE journal_line SET memo = 'changed' WHERE entry_id = ? AND memo IS NOT NULL",
                 (entry_id_of(env, 3),)))
    assert broken_at(full(ctx)) == (3, "Hash")


def test_flipped_control_override_flag(env, ctx, four):
    tamper(env, ("UPDATE journal_line SET is_control_override = 1 WHERE entry_id = ?", (entry_id_of(env, 2),)))
    assert broken_at(full(ctx)) == (2, "Hash")


def test_changed_account(env, ctx, four):
    tamper(env, ("UPDATE journal_line SET account_id = ? WHERE entry_id = ? AND credit_cents > 0",
                 (env.accts["fees"], entry_id_of(env, 4))))
    assert broken_at(full(ctx)) == (4, "Hash")


def test_deleted_middle_entry(env, ctx, four):
    target = entry_id_of(env, 2)
    tamper(env, ("DELETE FROM journal_line WHERE entry_id = ?", (target,)),
           ("DELETE FROM journal_entry WHERE entry_id = ?", (target,)))
    result = full(ctx)
    assert broken_at(result) == (2, "Gap")
    assert result["first_broken"]["je_number"] == "JE-000002"


def test_deleted_last_entries_are_truncation(env, ctx, four):
    targets = (entry_id_of(env, 3), entry_id_of(env, 4))
    tamper(env, *[(f"DELETE FROM journal_line WHERE entry_id = ?", (t,)) for t in targets],
           *[(f"DELETE FROM journal_entry WHERE entry_id = ?", (t,)) for t in targets])
    result = full(ctx)
    assert broken_at(result) == (3, "Truncated")
    assert result["through_entry_number"] == 2


def test_deleted_last_entries_with_the_counter_rolled_back_are_caught_by_the_checkpoint(env, ctx, four):
    assert full(ctx)["status"] == "OK"                    # records a checkpoint through 4
    targets = (entry_id_of(env, 3), entry_id_of(env, 4))
    tamper(env, *[("DELETE FROM journal_line WHERE entry_id = ?", (t,)) for t in targets],
           *[("DELETE FROM journal_entry WHERE entry_id = ?", (t,)) for t in targets],
           "UPDATE entry_number_sequence SET last_number = 2")
    assert broken_at(full(ctx)) == (3, "Truncated")


def test_deleted_tail_with_no_checkpoint_anywhere_is_the_documented_limit(env, ctx, four):
    """Without any checkpoint (in the file or the master) and with the counter rolled back as well, a cut tail
    leaves a consistent shorter chain: verification cannot know entries existed. Checkpoints (and auditors'
    printed copies) are what close this gap; see docs/audit_readiness_design.md 2.6."""
    targets = (entry_id_of(env, 3), entry_id_of(env, 4))
    tamper(env, *[("DELETE FROM journal_line WHERE entry_id = ?", (t,)) for t in targets],
           *[("DELETE FROM journal_entry WHERE entry_id = ?", (t,)) for t in targets],
           "UPDATE entry_number_sequence SET last_number = 2")
    result = full(ctx)
    assert result["status"] == "OK" and result["through_entry_number"] == 2


def test_swapped_entry_numbers(env, ctx, four):
    second, third = entry_id_of(env, 2), entry_id_of(env, 3)
    tamper(env, ("UPDATE journal_entry SET entry_number = 1000 WHERE entry_id = ?", (second,)),
           ("UPDATE journal_entry SET entry_number = 2 WHERE entry_id = ?", (third,)),
           ("UPDATE journal_entry SET entry_number = 3 WHERE entry_id = ?", (second,)))
    assert broken_at(full(ctx)) == (2, "Link")


def test_swapped_line_ids(env, ctx, four):
    first, second = [r["line_id"] for r in rows(env, "journal_line", "entry_id = ?", (entry_id_of(env, 3),))]
    tamper(env, ("UPDATE journal_line SET line_id = -1 WHERE line_id = ?", (first,)),
           ("UPDATE journal_line SET line_id = ? WHERE line_id = ?", (first, second)),
           ("UPDATE journal_line SET line_id = ? WHERE line_id = -1", (second,)))
    assert broken_at(full(ctx)) == (3, "Hash")


def test_a_forged_entry_without_the_key(env, ctx, four):
    last = rows(env, "journal_entry", "entry_number = 4")[0]
    forged_header = {**last, "entry_id": 999, "entry_number": 5, "description": "forged"}
    forged_lines = [{**line, "line_id": 9990 + i, "entry_id": 999} for i, line in
                    enumerate(rows(env, "journal_line", "entry_id = ?", (last["entry_id"],)))]
    fake = ledger_chain.seal(bytes(32), "PARENT", last["chain_hash"],
                             ledger_chain.canonical_entry(forged_header, forged_lines, []))
    columns = ", ".join(forged_header)
    marks = ", ".join("?" * len(forged_header))
    line_columns = ", ".join(forged_lines[0])
    tamper(env, (f"INSERT INTO journal_entry ({columns}) VALUES ({marks})",
                 tuple({**forged_header, "chain_prev_hash": last["chain_hash"], "chain_hash": fake}.values())),
           *[(f"INSERT INTO journal_line ({line_columns}) VALUES ({', '.join('?' * len(line))})", tuple(line.values()))
             for line in forged_lines],
           "UPDATE entry_number_sequence SET last_number = 5")
    assert broken_at(full(ctx)) == (5, "Hash")


def test_is_void_flipped_without_a_void_reversal(env, ctx, four):
    tamper(env, ("UPDATE journal_entry SET is_void = 1 WHERE entry_id = ?", (entry_id_of(env, 2),)))
    assert broken_at(full(ctx)) == (2, "Void mismatch")


def test_a_void_cleared_while_its_reversal_stands(env, ctx, four):
    with env._company("PARENT") as c:
        reversal = lh.make_reversal(c, entry_id_of(env, 3), "Void", entry_date="2026-03-16")
    seal_ctx = ctx
    # post the reversal through the real chain so the ledger is clean before tampering
    with env._company("PARENT") as c:
        number = c.execute("SELECT last_number FROM entry_number_sequence").fetchone()[0] + 1
    _post_reversal_like_the_service(env, reversal, number)
    assert full(seal_ctx)["status"] == "OK"
    tamper(env, ("UPDATE journal_entry SET is_void = 0 WHERE entry_id = ?", (entry_id_of(env, 3),)))
    assert broken_at(full(ctx)) == (3, "Void mismatch")


def _post_reversal_like_the_service(env, entry_id, number):
    """Step 5 posts reversals; until then seal one with the company code the service uses."""
    with env._company("PARENT") as c:
        c.execute("UPDATE entry_number_sequence SET last_number = last_number + 1")
        key_id = lh.ensure_test_chain_key(c)
        prev = c.execute("SELECT chain_hash FROM journal_entry WHERE entry_number = ?", (number - 1,)).fetchone()[0]
        header = dict(c.execute("SELECT * FROM journal_entry WHERE entry_id = ?", (entry_id,)).fetchone())
        header.update(entry_number=number, posted_by=1, posted_at=NOW, chain_version=1, chain_key_id=key_id)
        line_rows = [dict(r) for r in c.execute("SELECT * FROM journal_line WHERE entry_id = ?", (entry_id,))]
        seal = ledger_chain.seal(lh.TEST_CHAIN_KEY, "PARENT", prev, ledger_chain.canonical_entry(header, line_rows, []))
        c.execute("UPDATE journal_entry SET is_posted = 1, entry_number = ?, posted_by = 1, posted_at = ?, "
                  "chain_version = 1, chain_key_id = ?, chain_prev_hash = ?, chain_hash = ? WHERE entry_id = ?",
                  (number, NOW, key_id, prev, seal, entry_id))


def test_a_forged_checkpoint_with_a_bad_mac(env, ctx, four):
    head = rows(env, "journal_entry", "entry_number = 4")[0]["chain_hash"]
    with env._company("PARENT") as c:
        c.execute("INSERT INTO ledger_checkpoint (created_at, created_by, kind, scope, result, through_entry_number, "
                  "chain_hash, key_id, mac) VALUES ('2026-03-21T00:00:00+00:00', 1, 'Verify', 'Full', 'OK', 4, ?, 1, ?)",
                  (head, "f" * 64))
    result = ledger_verify.verify_ledger(ctx, mode="incremental")
    assert broken_at(result) == (4, "Marker")
    assert broken_at(full(ctx)) == (4, "Marker")


def test_verifying_with_the_wrong_key(env, ctx, four, monkeypatch):
    monkeypatch.setattr(keys, "_provider", keys.FixedKeyProvider(bytes(32)))
    assert broken_at(full(ctx)) == (1, "Key fingerprint")


def test_entries_sealed_under_two_keys_verify_with_the_retired_key_present(env, ctx, monkeypatch):
    post_entries(env, ctx, 2)
    with env._company("PARENT") as c:
        c.execute("UPDATE ledger_chain_key SET is_active = 0, retired_at = ?, retire_reason = 'Rotation'", (NOW,))
        new_id = c.execute("INSERT INTO ledger_chain_key (fingerprint, created_at, created_by) VALUES (?, ?, 1) "
                           "RETURNING key_id", (ledger_chain.fingerprint(KEY_B), NOW)).fetchone()[0]
    monkeypatch.setattr(keys, "_provider", keys.FixedKeyProvider({1: lh.TEST_CHAIN_KEY, new_id: KEY_B}))
    post_entries(env, ctx, 2)
    assert [r["chain_key_id"] for r in rows(env, "journal_entry")] == [1, 1, new_id, new_id]
    assert full(ctx)["status"] == "OK"


def test_a_missing_retired_key_makes_verification_unavailable_not_broken(env, ctx, monkeypatch):
    test_entries_sealed_under_two_keys_verify_with_the_retired_key_present(env, ctx, monkeypatch)
    before = {t: rows(env, t) for t in ("ledger_checkpoint", "audit_log")}
    mirrors = env.master_rows("SELECT * FROM chain_checkpoint")
    monkeypatch.setattr(keys, "_provider", keys.FixedKeyProvider({2: KEY_B}))
    result = full(ctx)
    assert result["status"] == "Unavailable" and result["first_broken"] is None and result["checkpoint_id"] is None
    assert "not a sign" in result["message"]
    assert {t: rows(env, t) for t in ("ledger_checkpoint", "audit_log")} == before
    assert env.master_rows("SELECT * FROM chain_checkpoint") == mirrors


def test_incremental_misses_an_edit_inside_the_verified_range_and_full_finds_it(env, ctx, four):
    """Expected: incremental re-checks only the checkpointed entry's hash and the entries after it, so an edit to
    JE-000002 after a checkpoint through JE-000004 passes an incremental check; the full check finds it."""
    assert full(ctx)["status"] == "OK"
    tamper(env, ("UPDATE journal_line SET memo = 'changed' WHERE entry_id = ? AND memo IS NOT NULL",
                 (entry_id_of(env, 2),)))
    incremental = ledger_verify.verify_ledger(ctx, mode="incremental")
    assert (incremental["status"], incremental["scope"]) == ("OK", "Incremental")
    assert broken_at(full(ctx)) == (2, "Hash")


def test_incremental_finds_an_edit_to_the_checkpointed_entry(env, ctx, four):
    assert full(ctx)["status"] == "OK"
    tamper(env, ("UPDATE journal_line SET memo = 'changed' WHERE entry_id = ? AND memo IS NOT NULL",
                 (entry_id_of(env, 4),)))
    assert broken_at(ledger_verify.verify_ledger(ctx, mode="incremental")) == (4, "Hash")


def test_restoring_an_older_copy_is_caught_by_the_master_checkpoint(env, ctx, tmp_path):
    post_entries(env, ctx, 2)
    assert full(ctx)["status"] == "OK"
    older = tmp_path / "older.db"
    shutil.copy2(env.path("PARENT"), older)
    post_entries(env, ctx, 2, start_amount=5000)
    assert full(ctx)["status"] == "OK"                      # master now remembers JE-000004
    shutil.copy2(older, env.path("PARENT"))                 # the older copy is consistent on its own
    result = full(ctx)
    assert broken_at(result) == (3, "Truncated")
    assert "older copy" in result["first_broken"]["detail"]


def test_a_forged_master_checkpoint_is_a_marker_break(env, ctx, four):
    assert full(ctx)["status"] == "OK"
    env.master_rows("SELECT 1")                             # master is reachable
    conn = sqlite3.connect(env.master)
    try:
        conn.execute("INSERT INTO chain_checkpoint (company_id, company_checkpoint_id, recorded_from, created_at, "
                     "created_by, kind, scope, result, through_entry_number, chain_hash, key_id, mac) VALUES (?, 1, "
                     "'Company file', ?, 1, "
                     "'Verify', 'Full', 'OK', 4, ?, 1, ?)",
                     (env.company_id("PARENT"), NOW, rows(env, "journal_entry", "entry_number = 4")[0]["chain_hash"],
                      "e" * 64))
        conn.commit()
    finally:
        conn.close()
    assert broken_at(full(ctx)) == (4, "Marker")


# --- what a result says and what it records ---------------------------------------------------------------------

def test_a_broken_result_names_the_entry_its_date_and_poster_in_plain_language(env, ctx, four):
    tamper(env, ("UPDATE journal_line SET memo = 'x' WHERE entry_id = ? AND memo IS NOT NULL", (entry_id_of(env, 2),)))
    result = full(ctx)
    broken = result["first_broken"]
    assert (broken["je_number"], broken["entry_date"], broken["posted_by"]) == ("JE-000002", "2026-03-15", env.user_id)
    assert "JE-000002" in result["message"] and "2026-03-15" in result["message"] and "F L" in result["message"]
    assert "Entries before it are intact" in result["message"]
    for secret in (lh.TEST_CHAIN_KEY.hex(), rows(env, "journal_entry", "entry_number = 2")[0]["chain_hash"]):
        assert secret not in result["message"]


def test_an_ok_full_check_records_a_maced_checkpoint_in_the_file_and_the_master(env, ctx, four):
    result = full(ctx)
    checkpoint = rows(env, "ledger_checkpoint", "checkpoint_id = ?", (result["checkpoint_id"],))[0]
    assert {k: checkpoint[k] for k in ("kind", "scope", "result", "through_entry_number", "first_broken_entry_number",
                                       "key_id", "created_at", "created_by")} == {
        "kind": "Verify", "scope": "Full", "result": "OK", "through_entry_number": 4, "first_broken_entry_number": None,
        "key_id": 1, "created_at": NOW, "created_by": env.user_id}
    assert checkpoint["chain_hash"] == result["chain_hash"]
    assert checkpoint["mac"] == ledger_chain.checkpoint_mac(lh.TEST_CHAIN_KEY, "PARENT", checkpoint)
    mirror = env.master_rows("SELECT * FROM chain_checkpoint")[-1]
    assert (mirror["company_id"], mirror["company_checkpoint_id"], mirror["recorded_from"], mirror["mac"]) == (
        env.company_id("PARENT"), checkpoint["checkpoint_id"], "Company file", checkpoint["mac"])
    assert rows(env, "audit_log", "table_name = 'ledger_checkpoint'")[-1]["record_id"] == checkpoint["checkpoint_id"]
    assert result["recorded_in"] == ["company", "master"]


def test_a_broken_check_records_the_first_broken_entry(env, ctx, four):
    tamper(env, ("UPDATE journal_line SET memo = 'x' WHERE entry_id = ? AND memo IS NOT NULL", (entry_id_of(env, 3),)))
    result = full(ctx)
    checkpoint = rows(env, "ledger_checkpoint", "checkpoint_id = ?", (result["checkpoint_id"],))[0]
    assert (checkpoint["result"], checkpoint["through_entry_number"], checkpoint["first_broken_entry_number"]) == (
        "Broken", 2, 3)
    assert checkpoint["chain_hash"] == rows(env, "journal_entry", "entry_number = 2")[0]["chain_hash"]


def test_a_break_at_the_first_entry_records_through_zero(env, ctx, four):
    tamper(env, ("UPDATE journal_line SET memo = 'x' WHERE entry_id = ? AND memo IS NOT NULL", (entry_id_of(env, 1),)))
    checkpoint = rows(env, "ledger_checkpoint", "checkpoint_id = ?", (full(ctx)["checkpoint_id"],))[0]
    assert (checkpoint["through_entry_number"], checkpoint["chain_hash"]) == (0, None)


def test_incremental_without_a_checkpoint_runs_full(env, ctx, four):
    result = ledger_verify.verify_ledger(ctx, mode="incremental")
    assert (result["status"], result["scope"]) == ("OK", "Full")


def test_incremental_seals_only_the_new_entries(env, ctx, four, monkeypatch):
    full(ctx)
    post_entries(env, ctx, 3)
    calls = []
    original = ledger_chain.seal
    monkeypatch.setattr(ledger_chain, "seal", lambda *a, **k: calls.append(1) or original(*a, **k))
    result = ledger_verify.verify_ledger(ctx, mode="incremental")
    assert (result["status"], result["scope"], result["through_entry_number"]) == ("OK", "Incremental", 7)
    assert len(calls) == 4                     # the checkpointed JE-000004 again, then the three new entries


def test_incremental_starts_from_the_last_ok_checkpoint_not_a_broken_one(env, ctx, four):
    full(ctx)                                                             # OK through 4
    tamper(env, ("UPDATE journal_line SET memo = 'x' WHERE entry_id = ? AND memo IS NOT NULL", (entry_id_of(env, 4),)))
    assert full(ctx)["status"] == "Broken"                                # recorded as Broken
    assert broken_at(ledger_verify.verify_ledger(ctx, mode="incremental")) == (4, "Hash")


def test_an_unknown_mode_is_refused(env, ctx):
    with pytest.raises(ValidationError):
        ledger_verify.verify_ledger(ctx, mode="quick")


def test_no_key_provider_is_unavailable_and_records_nothing(env, ctx, four, monkeypatch):
    monkeypatch.setattr(keys, "_provider", keys.NullKeyProvider())
    before = rows(env, "ledger_checkpoint")
    result = full(ctx)
    assert result["status"] == "Unavailable" and result["recorded_in"] == []
    assert rows(env, "ledger_checkpoint") == before


def test_a_read_only_context_records_in_the_master_only(env, four):
    reader = ctx_for(env, read_only=True)
    before = {t: rows(env, t) for t in ("ledger_checkpoint", "audit_log")}
    result = full(reader)
    assert result["status"] == "OK" and result["recorded_in"] == ["master"] and result["checkpoint_id"] is None
    assert {t: rows(env, t) for t in ("ledger_checkpoint", "audit_log")} == before
    mirror = env.master_rows("SELECT * FROM chain_checkpoint")[-1]
    assert (mirror["recorded_from"], mirror["company_checkpoint_id"], mirror["through_entry_number"]) == (
        "Read-only", None, 4)


def test_a_read_only_context_cannot_open_a_company_write(env):
    with pytest.raises(PermissionDeniedError, match="read-only"):
        ledger.create_entry(ctx_for(env, read_only=True), entry_date="2026-03-15")


def test_verify_needs_ledger_verify(env, four):
    env.role("PARENT", "ACCOUNTANT", ["je.create", "je.post", "ledger.view", "account.manage"])
    accountant = env.user("accountant")
    env.grant(accountant, "PARENT", "ACCOUNTANT")
    with pytest.raises(PermissionDeniedError):
        full(ctx_for(env, user=accountant))


def test_ledger_verify_goes_to_controller_but_not_accountant():
    assert "ledger.verify" in role_templates.ROLES["Controller"]["sensitive"]
    assert "ledger.verify" not in role_templates.ROLES["Accountant"]["sensitive"]
    assert "ledger.verify" not in role_templates.permissions_for("Accountant")


# --- the ledger_integrity close check (L2) -----------------------------------------------------------------------

def march(env):
    return rows(env, "fiscal_period", "start_date = '2026-03-01' AND is_adjustment_period = 0")[0]["period_id"]


def integrity(env, ctx):
    return {c["code"]: c for c in periods.close_checks(ctx, march(env))}["ledger_integrity"]


def test_close_checks_run_a_full_verification(env, ctx, four, monkeypatch):
    modes = []
    original = ledger_verify.verify_connection
    monkeypatch.setattr(ledger_verify, "verify_connection",
                        lambda *a, **k: modes.append(k.get("mode")) or original(*a, **k))
    check = integrity(env, ctx)
    assert check["ok"] is True and modes == ["full"]


def test_a_tampered_ledger_warns_at_close_by_default(env, ctx, four):
    tamper(env, ("UPDATE journal_line SET memo = 'x' WHERE entry_id = ? AND memo IS NOT NULL", (entry_id_of(env, 2),)))
    check = integrity(env, ctx)
    assert (check["ok"], check["mode"]) == (False, "warn") and "JE-000002" in check["message"]
    with pytest.raises(periods.CloseWarningsError) as caught:
        periods.close_period(ctx, march(env))
    assert "ledger_integrity" in [w["code"] for w in caught.value.warnings]


def test_a_tampered_ledger_blocks_the_close_when_set(env, ctx, four):
    periods.set_close_check_mode(ctx, "ledger_integrity", "block")
    tamper(env, ("UPDATE journal_line SET memo = 'x' WHERE entry_id = ? AND memo IS NOT NULL", (entry_id_of(env, 2),)))
    with pytest.raises(ValidationError, match="JE-000002"):
        periods.close_period(ctx, march(env), acknowledge_warnings=True)


def test_unavailable_is_a_warning_even_when_the_check_blocks(env, ctx, four, monkeypatch):
    periods.set_close_check_mode(ctx, "ledger_integrity", "block")
    monkeypatch.setattr(keys, "_provider", keys.NullKeyProvider())
    check = integrity(env, ctx)
    assert (check["ok"], check["mode"]) == (False, "warn") and "could not run" in check["message"]
    with env._company("PARENT") as c:          # earlier months closed so only this warning remains
        c.execute("UPDATE fiscal_period SET is_closed = 1, closed_at = ?, closed_by = 1 WHERE start_date < '2026-03-01' "
                  "AND fiscal_year_id IS NOT NULL", (NOW,))
    periods.close_period(ctx, march(env), acknowledge_warnings=True)


def test_year_close_runs_the_integrity_check(env, ctx, four):
    periods.set_close_check_mode(ctx, "ledger_integrity", "block")
    year = rows(env, "fiscal_year", "name = 'FY2026'")[0]["year_id"]
    with env._company("PARENT") as c:
        c.execute("UPDATE fiscal_period SET is_closed = 1, closed_at = ?, closed_by = 1 WHERE fiscal_year_id = ? "
                  "AND is_adjustment_period = 0", (NOW, year))
    tamper(env, ("UPDATE journal_line SET memo = 'x' WHERE entry_id = ? AND memo IS NOT NULL", (entry_id_of(env, 2),)))
    with pytest.raises(ValidationError, match="JE-000002"):
        periods.close_year(ctx, year, acknowledge_warnings=True)


# --- automatic checkpoints when a company is closed and at app exit (3b follow-up a) ----------------------------

def test_closing_a_company_writes_a_signed_checkpoint_in_the_file_and_the_master(env, four):
    env.role("PARENT", "CLERK", ["je.create", "ledger.view"])          # no ledger.verify: this is system upkeep
    clerk = env.user("clerk")
    env.grant(clerk, "PARENT", "CLERK")
    result = ledger_verify.checkpoint_on_close(ctx_for(env, user=clerk))
    assert result["status"] == "OK" and result["recorded_in"] == ["company", "master"]
    checkpoint = rows(env, "ledger_checkpoint")[-1]
    assert (checkpoint["kind"], checkpoint["result"], checkpoint["through_entry_number"]) == ("Verify", "OK", 4)
    assert checkpoint["created_by"] == clerk
    assert checkpoint["mac"] == ledger_chain.checkpoint_mac(lh.TEST_CHAIN_KEY, "PARENT", checkpoint)
    assert env.master_rows("SELECT mac FROM chain_checkpoint")[-1]["mac"] == checkpoint["mac"]


def test_after_the_first_close_a_cut_tail_with_the_counter_rolled_back_is_caught(env, ctx, four):
    """The documented limit (no checkpoint anywhere) now exists only before a ledger's first close."""
    ledger_verify.checkpoint_on_close(ctx)
    targets = (entry_id_of(env, 3), entry_id_of(env, 4))
    tamper(env, *[("DELETE FROM journal_line WHERE entry_id = ?", (t,)) for t in targets],
           *[("DELETE FROM journal_entry WHERE entry_id = ?", (t,)) for t in targets],
           "UPDATE entry_number_sequence SET last_number = 2",
           "DELETE FROM ledger_checkpoint")                       # even with the file's own checkpoints removed
    result = full(ctx)
    assert broken_at(result) == (3, "Truncated") and "older copy" in result["first_broken"]["detail"]


def test_closing_without_a_key_records_nothing_and_does_not_raise(env, ctx, four, monkeypatch):
    monkeypatch.setattr(keys, "_provider", keys.NullKeyProvider())
    result = ledger_verify.checkpoint_on_close(ctx)
    assert result["status"] == "Unavailable" and result["recorded_in"] == []
    assert rows(env, "ledger_checkpoint") == [] and env.master_rows("SELECT * FROM chain_checkpoint") == []


def test_the_first_close_runs_a_full_check_and_records_a_broken_ledger_as_broken(env, ctx, four):
    tamper(env, ("UPDATE journal_line SET memo = 'x' WHERE entry_id = ? AND memo IS NOT NULL", (entry_id_of(env, 2),)))
    result = ledger_verify.checkpoint_on_close(ctx)
    assert (result["scope"], broken_at(result)) == ("Full", (2, "Hash"))
    assert rows(env, "ledger_checkpoint")[-1]["result"] == "Broken"


def test_closing_never_raises(env, ctx, four, monkeypatch, caplog):
    def explode(*args, **kwargs):
        raise RuntimeError("disk gone")
    monkeypatch.setattr(ledger_verify, "verify_connection", explode)
    assert ledger_verify.checkpoint_on_close(ctx) is None
    assert "checkpoint" in caplog.text


def test_closing_a_read_only_company_records_in_the_master_only(env, four):
    result = ledger_verify.checkpoint_on_close(ctx_for(env, read_only=True))
    assert result["recorded_in"] == ["master"] and rows(env, "ledger_checkpoint") == []


def test_closing_with_no_company_open_does_nothing():
    assert ledger_verify.checkpoint_on_close(None) is None


def test_the_app_checkpoints_on_logout_and_on_exit():
    import ast
    from pathlib import Path
    source = (Path(__file__).resolve().parent.parent / "app_strata.pyw").read_text(encoding="utf-8")
    tree = ast.parse(source)
    functions = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    def calls(name):
        return {c.func.attr for c in ast.walk(functions[name]) if isinstance(c, ast.Call)
                and isinstance(c.func, ast.Attribute)}
    assert "close_company_ledger" in calls("handle_secure_logout")
    assert "close_company_ledger" in calls("on_app_exit")
    assert "checkpoint_on_close" in calls("close_company_ledger")
    assert 'protocol("WM_DELETE_WINDOW", self.on_app_exit)' in source


# --- signed checkpoints after a period or year close (docs/audit_readiness_design.md section 3) ------------------

def _close_rows(env, kind):
    return rows(env, "ledger_checkpoint", "kind = ?", (kind,))


def _close_earlier_months(env):
    with env._company("PARENT") as c:
        c.execute("UPDATE fiscal_period SET is_closed = 1, closed_at = ?, closed_by = 1 WHERE start_date < '2026-03-01' "
                  "AND fiscal_year_id IS NOT NULL", (NOW,))


def _fy2026(env):
    return rows(env, "fiscal_year", "name = 'FY2026'")[0]["year_id"]


def _close_months_of(env, year):
    with env._company("PARENT") as c:
        c.execute("UPDATE fiscal_period SET is_closed = 1, closed_at = ?, closed_by = 1 WHERE fiscal_year_id = ? "
                  "AND is_adjustment_period = 0", (NOW, year))


def _assert_signed_and_mirrored(env, checkpoint):
    assert checkpoint["mac"] == ledger_chain.checkpoint_mac(lh.TEST_CHAIN_KEY, "PARENT", checkpoint)
    mirror = env.master_rows("SELECT * FROM chain_checkpoint WHERE company_checkpoint_id = ?",
                             (checkpoint["checkpoint_id"],))
    assert len(mirror) == 1 and mirror[0]["recorded_from"] == "Company file"
    for field in ledger_chain.CHECKPOINT_FIELDS + ("mac",):
        assert mirror[0][field] == checkpoint[field], field


def test_a_period_close_records_a_signed_checkpoint_in_the_file_and_the_master(env, ctx, four):
    _close_earlier_months(env)
    result = periods.close_period(ctx, march(env))
    assert result["status"] == "OK" and result["recorded_in"] == ["company", "master"]
    [checkpoint] = _close_rows(env, "Period close")
    assert (checkpoint["scope"], checkpoint["result"], checkpoint["through_entry_number"]) == (None, "OK", 4)
    assert (checkpoint["ref_type"], checkpoint["ref_id"]) == ("fiscal_period", march(env))
    assert checkpoint["chain_hash"] == rows(env, "journal_entry", "entry_number = 4")[0]["chain_hash"]
    assert (checkpoint["created_by"], checkpoint["created_at"]) == (env.user_id, NOW)
    assert checkpoint["checkpoint_id"] == result["checkpoint_id"]
    _assert_signed_and_mirrored(env, checkpoint)
    assert _close_rows(env, "Verify") == []


def test_a_year_close_records_a_signed_year_close_checkpoint(env, ctx, four):
    year = _fy2026(env)
    _close_months_of(env, year)
    result = periods.close_year(ctx, year, acknowledge_warnings=True)
    assert result["status"] == "OK"
    [checkpoint] = _close_rows(env, "Year close")
    assert (checkpoint["ref_type"], checkpoint["ref_id"], checkpoint["through_entry_number"]) == ("fiscal_year", year, 4)
    _assert_signed_and_mirrored(env, checkpoint)
    assert _close_rows(env, "Period close") == []       # periods 13 and 14 close inside the year close


def test_books_closed_through_records_one_period_close_checkpoint_for_the_last_month(env, ctx, four):
    result = periods.set_books_closed_through(ctx, "2026-03-31", acknowledge_warnings=True)
    assert result["closed"][-1] == rows(env, "fiscal_period", "period_id = ?", (march(env),))[0]["name"]
    [checkpoint] = _close_rows(env, "Period close")
    assert (checkpoint["ref_type"], checkpoint["ref_id"]) == ("fiscal_period", march(env))
    assert result["checkpoint"]["checkpoint_id"] == checkpoint["checkpoint_id"]
    _assert_signed_and_mirrored(env, checkpoint)


def test_a_close_verifies_the_ledger_only_once(env, ctx, four, monkeypatch):
    _close_earlier_months(env)
    modes = []
    original = ledger_verify.verify_connection
    monkeypatch.setattr(ledger_verify, "verify_connection",
                        lambda *a, **k: modes.append(k.get("mode")) or original(*a, **k))
    periods.close_period(ctx, march(env))
    assert modes == ["full"]


def test_a_close_that_does_not_happen_records_no_checkpoint(env, ctx, four):
    with pytest.raises(periods.CloseWarningsError):            # earlier months open: a warning not acknowledged
        periods.close_period(ctx, march(env))
    periods.set_close_check_mode(ctx, "ledger_integrity", "block")
    tamper(env, ("UPDATE journal_line SET memo = 'x' WHERE entry_id = ? AND memo IS NOT NULL", (entry_id_of(env, 2),)))
    with pytest.raises(ValidationError):
        periods.close_period(ctx, march(env), acknowledge_warnings=True)
    year = _fy2026(env)
    _close_months_of(env, year)
    with pytest.raises(ValidationError):
        periods.close_year(ctx, year, acknowledge_warnings=True)
    assert rows(env, "ledger_checkpoint") == [] and env.master_rows("SELECT * FROM chain_checkpoint") == []


def test_a_close_past_an_acknowledged_broken_ledger_records_it_as_broken(env, ctx, four):
    _close_earlier_months(env)
    tamper(env, ("UPDATE journal_line SET memo = 'x' WHERE entry_id = ? AND memo IS NOT NULL", (entry_id_of(env, 2),)))
    result = periods.close_period(ctx, march(env), acknowledge_warnings=True)
    assert broken_at(result) == (2, "Hash")
    [checkpoint] = _close_rows(env, "Period close")
    assert (checkpoint["result"], checkpoint["first_broken_entry_number"], checkpoint["through_entry_number"]) == (
        "Broken", 2, 1)
    _assert_signed_and_mirrored(env, checkpoint)


def test_a_close_without_a_key_closes_and_records_nothing(env, ctx, four, monkeypatch):
    _close_earlier_months(env)
    monkeypatch.setattr(keys, "_provider", keys.NullKeyProvider())
    result = periods.close_period(ctx, march(env), acknowledge_warnings=True)
    assert result["status"] == "Unavailable" and result["recorded_in"] == []
    assert rows(env, "fiscal_period", "period_id = ?", (march(env),))[0]["is_closed"] == 1
    assert rows(env, "ledger_checkpoint") == [] and env.master_rows("SELECT * FROM chain_checkpoint") == []


def test_a_checkpoint_that_cannot_be_written_never_undoes_the_close(env, ctx, four, monkeypatch, caplog):
    _close_earlier_months(env)
    def explode(*args, **kwargs):
        raise RuntimeError("disk gone")
    monkeypatch.setattr(ledger_chain, "checkpoint_mac", explode)
    result = periods.close_period(ctx, march(env))
    assert rows(env, "fiscal_period", "period_id = ?", (march(env),))[0]["is_closed"] == 1
    assert result["checkpoint_id"] is None and result["recorded_in"] == []
    assert "could not be saved" in result["checkpoint_error"] and "disk gone" not in result["checkpoint_error"]
    assert "checkpoint" in caplog.text
    assert rows(env, "ledger_checkpoint") == []


def test_only_the_closes_sign_close_checkpoints():
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    callers = sorted(p.relative_to(root).as_posix() for p in list((root / "modules").rglob("*.py")) +
                     [root / "app_strata.pyw"] if "record_close_checkpoint(" in p.read_text(encoding="utf-8"))
    assert callers == ["modules/services/ledger_verify.py", "modules/services/periods.py"]


def _verification(env):
    conn = sqlite3.connect(env.path("PARENT"))
    conn.row_factory = sqlite3.Row
    try:
        return ledger_verify.full_verification(conn, ctx_for(env))
    finally:
        conn.close()


def _nothing_recorded(env, result):
    assert result["checkpoint_id"] is None and result["recorded_in"] == []
    assert result["checkpoint_error"] == ledger_verify.CHECKPOINT_NOT_SAVED
    assert rows(env, "ledger_checkpoint") == [] and env.master_rows("SELECT * FROM chain_checkpoint") == []


def test_signing_a_close_checkpoint_needs_period_close_and_a_denial_is_reported_not_raised(env, four, caplog):
    env.role("PARENT", "VIEWER", ["ledger.view", "period.view"])
    viewer = env.user("viewer")
    env.grant(viewer, "PARENT", "VIEWER")
    result = ledger_verify.record_close_checkpoint(ctx_for(env, user=viewer), _verification(env),
                                                   kind="Period close", ref_id=march(env))
    _nothing_recorded(env, result)
    assert "PermissionDenied" in caplog.text


def test_a_permission_check_that_fails_after_the_close_never_undoes_it(env, ctx, four, monkeypatch):
    _close_earlier_months(env)
    def deny(*args, **kwargs):
        raise PermissionDeniedError("access was removed")
    monkeypatch.setattr(ledger_verify, "authorize", deny)
    result = periods.close_period(ctx, march(env))
    assert rows(env, "fiscal_period", "period_id = ?", (march(env),))[0]["is_closed"] == 1
    _nothing_recorded(env, result)


def test_a_close_checkpoint_is_signed_only_for_a_period_that_is_closed(env, ctx, four, caplog):
    result = ledger_verify.record_close_checkpoint(ctx, _verification(env), kind="Period close", ref_id=march(env))
    _nothing_recorded(env, result)
    assert "not closed" in caplog.text


def test_a_close_checkpoint_is_signed_only_for_a_year_that_is_closed(env, ctx, four):
    result = ledger_verify.record_close_checkpoint(ctx, _verification(env), kind="Year close", ref_id=_fy2026(env))
    _nothing_recorded(env, result)


def test_a_close_checkpoint_for_a_period_that_does_not_exist_is_not_signed(env, ctx, four):
    result = ledger_verify.record_close_checkpoint(ctx, _verification(env), kind="Period close", ref_id=999999)
    _nothing_recorded(env, result)


@pytest.mark.parametrize("change", [{"chain_hash": "0" * 64}, {"through_entry_number": 3}, {"through_entry_number": 9},
                                    {"through_entry_number": 4, "chain_hash": None}])
def test_a_close_checkpoint_refuses_a_verification_that_does_not_match_the_ledger(env, ctx, four, change, caplog):
    _close_earlier_months(env)
    periods.close_period(ctx, march(env))                     # signs its own checkpoint (checkpoints are append-only)
    before = (len(rows(env, "ledger_checkpoint")), len(env.master_rows("SELECT * FROM chain_checkpoint")))
    result = ledger_verify.record_close_checkpoint(ctx, {**_verification(env), **change}, kind="Period close",
                                                   ref_id=march(env))
    assert result["checkpoint_id"] is None and result["recorded_in"] == []
    assert result["checkpoint_error"] == ledger_verify.CHECKPOINT_NOT_SAVED
    assert (len(rows(env, "ledger_checkpoint")), len(env.master_rows("SELECT * FROM chain_checkpoint"))) == before
    assert "does not match" in caplog.text


def test_a_checkpoint_saved_in_the_file_but_not_the_master_says_so(env, ctx, four, monkeypatch):
    _close_earlier_months(env)
    original = ledger_verify.write_transaction
    def master_fails(path, context):
        if path == context.master_db_path:
            raise RuntimeError("master locked")
        return original(path, context)
    monkeypatch.setattr(ledger_verify, "write_transaction", master_fails)
    result = periods.close_period(ctx, march(env))
    [checkpoint] = _close_rows(env, "Period close")
    assert result["checkpoint_id"] == checkpoint["checkpoint_id"] and result["recorded_in"] == ["company"]
    assert result["checkpoint_error"] == ledger_verify.CHECKPOINT_PARTLY_SAVED
    assert "company file" in result["checkpoint_error"] and "master locked" not in result["checkpoint_error"]
    assert env.master_rows("SELECT * FROM chain_checkpoint") == []


def test_a_close_that_records_its_checkpoint_reports_no_error(env, ctx, four):
    _close_earlier_months(env)
    assert "checkpoint_error" not in periods.close_period(ctx, march(env))


def _retire_the_key(env):
    with env._company("PARENT") as c:
        c.execute("UPDATE ledger_chain_key SET is_active = 0, retired_at = ?, retire_reason = 'Rotation'", (NOW,))


def _march_closed_by_hand(env):
    with env._company("PARENT") as c:
        c.execute("UPDATE fiscal_period SET is_closed = 1, closed_at = ?, closed_by = 1 "
                  "WHERE start_date <= '2026-03-01' AND fiscal_year_id IS NOT NULL", (NOW,))


@pytest.mark.parametrize("kind", ["Verify", "Bogus", None])
def test_an_unknown_close_kind_is_refused(env, ctx, four, kind):
    _march_closed_by_hand(env)
    with pytest.raises(ValidationError):
        ledger_verify.record_close_checkpoint(ctx, _verification(env), kind=kind, ref_id=march(env))
    assert rows(env, "ledger_checkpoint") == [] and env.master_rows("SELECT * FROM chain_checkpoint") == []


def test_a_close_on_an_empty_ledger_signs_a_checkpoint_through_zero(env, ctx):
    _close_earlier_months(env)
    result = periods.close_period(ctx, march(env))
    assert "checkpoint_error" not in result and "no_checkpoint_reason" not in result
    [checkpoint] = _close_rows(env, "Period close")
    assert (checkpoint["result"], checkpoint["through_entry_number"], checkpoint["chain_hash"]) == ("OK", 0, None)
    _assert_signed_and_mirrored(env, checkpoint)


def test_a_close_with_no_active_key_says_why_no_checkpoint_was_signed(env, ctx):
    _close_earlier_months(env)
    _retire_the_key(env)
    result = periods.close_period(ctx, march(env))
    assert rows(env, "fiscal_period", "period_id = ?", (march(env),))[0]["is_closed"] == 1
    assert "checkpoint_error" not in result and result["recorded_in"] == []
    assert result["no_checkpoint_reason"] == ledger_verify.NO_CHECKPOINT_NO_KEY
    assert rows(env, "ledger_checkpoint") == [] and env.master_rows("SELECT * FROM chain_checkpoint") == []


def test_a_close_whose_key_goes_missing_before_signing_says_why(env, ctx, four, monkeypatch):
    _close_earlier_months(env)
    real_key_for = ledger_verify._key_for
    calls = []
    def key_for_then_gone(context):
        calls.append(1)
        if len(calls) == 1:                                    # the close's own verification
            return real_key_for(context)
        return lambda key_id: keys.NullKeyProvider().get_key(context.company_id, key_id)
    monkeypatch.setattr(ledger_verify, "_key_for", key_for_then_gone)
    result = periods.close_period(ctx, march(env))
    assert result["status"] == "OK" and "checkpoint_error" not in result and result["recorded_in"] == []
    assert result["no_checkpoint_reason"] == ledger_verify.NO_CHECKPOINT_KEY_UNAVAILABLE
    assert rows(env, "ledger_checkpoint") == [] and env.master_rows("SELECT * FROM chain_checkpoint") == []


def test_a_close_without_a_key_says_why_no_checkpoint_was_signed(env, ctx, four, monkeypatch):
    _close_earlier_months(env)
    monkeypatch.setattr(keys, "_provider", keys.NullKeyProvider())
    result = periods.close_period(ctx, march(env), acknowledge_warnings=True)
    assert result["no_checkpoint_reason"] == ledger_verify.NO_CHECKPOINT_KEY_UNAVAILABLE
    assert "checkpoint_error" not in result


def test_a_close_checkpoint_that_fails_says_why_in_both_fields(env, ctx, four, monkeypatch):
    _close_earlier_months(env)
    def explode(*args, **kwargs):
        raise RuntimeError("disk gone")
    monkeypatch.setattr(ledger_chain, "checkpoint_mac", explode)
    result = periods.close_period(ctx, march(env))
    assert result["no_checkpoint_reason"] == result["checkpoint_error"] == ledger_verify.CHECKPOINT_NOT_SAVED


def test_a_recorded_close_checkpoint_has_no_reason_field(env, ctx, four):
    _close_earlier_months(env)
    result = periods.close_period(ctx, march(env))
    assert result["recorded_in"] == ["company", "master"] and "no_checkpoint_reason" not in result


def test_a_ledger_check_that_signs_nothing_says_why(env, ctx, four, monkeypatch):
    monkeypatch.setattr(keys, "_provider", keys.NullKeyProvider())
    result = ledger_verify.verify_ledger(ctx, mode="full")
    assert result["status"] == "Unavailable" and result["recorded_in"] == []
    assert result["no_checkpoint_reason"] == ledger_verify.NO_CHECKPOINT_KEY_UNAVAILABLE
    monkeypatch.setattr(keys, "_provider", keys.FixedKeyProvider(lh.TEST_CHAIN_KEY))
    assert "no_checkpoint_reason" not in ledger_verify.verify_ledger(ctx, mode="full")


def _count_full_verifications(monkeypatch):
    modes = []
    original = ledger_verify.verify_connection
    monkeypatch.setattr(ledger_verify, "verify_connection",
                        lambda *a, **k: modes.append(k.get("mode")) or original(*a, **k))
    return modes


def test_a_year_close_verifies_the_ledger_only_once(env, ctx, four, monkeypatch):
    year = _fy2026(env)
    _close_months_of(env, year)
    modes = _count_full_verifications(monkeypatch)
    periods.close_year(ctx, year, acknowledge_warnings=True)
    assert modes == ["full"]


def test_books_closed_through_several_months_verifies_the_ledger_only_once(env, ctx, four, monkeypatch):
    modes = _count_full_verifications(monkeypatch)
    result = periods.set_books_closed_through(ctx, "2026-03-31", acknowledge_warnings=True)
    assert len(result["closed"]) >= 3 and modes == ["full"]


def test_the_next_incremental_check_starts_from_the_close_checkpoint(env, ctx, four, monkeypatch):
    _close_earlier_months(env)
    periods.close_period(ctx, march(env))
    entry_id = ledger.create_entry(ctx, entry_date="2026-04-02", lines=[
        {"account_id": env.accts["cash"], "debit_cents": 500}, {"account_id": env.accts["sales"], "credit_cents": 500}])
    ledger.post_journal_entry(ctx, entry_id, confirm=True, acknowledge_date_warnings=True)
    sealed = []
    original = ledger_chain.seal
    monkeypatch.setattr(ledger_chain, "seal", lambda *a, **k: sealed.append(a[2]) or original(*a, **k))
    result = ledger_verify.verify_ledger(ctx, mode="incremental")
    assert (result["status"], result["scope"], result["through_entry_number"]) == ("OK", "Incremental", 5)
    assert len(sealed) == 2                                    # the checkpointed entry 4 and the new entry 5


# --- R26: the close checkpoint is signed with a fresh context ----------------------------------------------------

def _app_class():
    import importlib.machinery
    import importlib.util
    from pathlib import Path
    path = Path(__file__).resolve().parent.parent / "app_strata.pyw"
    loader = importlib.machinery.SourceFileLoader("app_strata_for_close_checkpoint", str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def _fake_app(module, context):
    from types import SimpleNamespace
    fake = SimpleNamespace(context=context)
    fake.action_context = lambda: module.App.action_context(fake)
    return fake


def test_the_close_checkpoint_uses_the_time_of_closing(env, ctx, monkeypatch):
    from modules.services import clock
    module = _app_class()
    seen = []
    monkeypatch.setattr(module.ledger_verify, "checkpoint_on_close", seen.append)
    monkeypatch.setattr(clock, "utc_now_iso", lambda: "2026-04-01T18:00:00+00:00")
    module.App.close_company_ledger(_fake_app(module, ctx))
    assert [c.now for c in seen] == ["2026-04-01T18:00:00+00:00"]
    assert (seen[0].user_id, seen[0].company_id, seen[0].origin) == (ctx.user_id, ctx.company_id, ctx.origin)


@pytest.mark.parametrize("failure", ["time zone", "file"])
def test_the_close_checkpoint_never_blocks_closing(env, ctx, monkeypatch, caplog, failure):
    import sqlite3
    from modules.services.errors import InstallationError
    module = _app_class()
    seen = []
    monkeypatch.setattr(module.ledger_verify, "checkpoint_on_close", seen.append)

    def broken(_context):
        if failure == "file":
            raise sqlite3.OperationalError("unable to open database file")
        raise InstallationError("Time zone data is missing")

    monkeypatch.setattr(module.companies, "action_context", broken)
    module.App.close_company_ledger(_fake_app(module, ctx))        # does not raise
    assert seen == [] and "checkpoint on close was skipped" in caplog.text
    module.App.close_company_ledger(_fake_app(module, None))        # no company open: nothing


def test_the_app_action_context_needs_an_open_company():
    from modules.services.errors import ValidationError
    module = _app_class()
    with pytest.raises(ValidationError, match="Open a company first"):
        module.App.action_context(_fake_app(module, None))
