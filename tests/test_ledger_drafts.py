"""ledger.py, step 2 of Phase 2.5: draft entries (create, update, delete, read), line validation, entry periods.

Posting, numbering, approvals, reversals and rounding are later steps. These tests replace pending tests
`cannot_post_to_header_or_inactive_account` (the draft half; the post half is in step 3) and
`period_is_set_from_entry_date`.
"""
import re
import sqlite3
from pathlib import Path

import pytest

from modules.services import ledger, periods
from modules.services.errors import NotFoundError, PeriodClosedError, PermissionDeniedError, PostingError, ValidationError
from tests import ledger_helpers as lh
from tests.authz_world import world  # noqa: F401  (fixture)

CREATE = ["je.create", "ledger.view"]


@pytest.fixture
def env(world):
    """PARENT with two fiscal years (2026, 2027), a few accounts, and an Accountant-like user."""
    world.settings("PARENT", require_separate_approver=0)
    with world._company("PARENT") as c:
        periods.seed_years(c, 1, 2026)
        accts = {
            "cash": lh.make_account(c, "1010"),
            "sales": lh.make_account(c, "4010"),
            "header": lh.make_account(c, "1000", is_postable=0),
            "inactive": lh.make_account(c, "1099", is_active=0),
        }
        parent = lh.make_account(c, "1200")
        lh.make_account(c, "1210", parent_id=parent)
        accts["parent"] = parent
        accts["contact"] = lh.make_contact(c)
    world.role("PARENT", "ACCT", CREATE)
    user = world.user("acct")
    world.grant(user, "PARENT", "ACCT")
    world.accts = accts
    world.user_id = user
    world.ctx_ = world.ctx(user, "PARENT")
    return world


@pytest.fixture
def ctx(env):
    return env.ctx_


def A(env, name):
    return env.accts[name]


def two_lines(env, amount=1000):
    return [{"account_id": A(env, "cash"), "debit_cents": amount},
            {"account_id": A(env, "sales"), "credit_cents": amount}]


def entry_row(world, entry_id):
    return world.rows("PARENT", "SELECT * FROM journal_entry WHERE entry_id = ?", (entry_id,))[0]


def line_rows(world, entry_id):
    return world.rows("PARENT", "SELECT * FROM journal_line WHERE entry_id = ? ORDER BY line_id", (entry_id,))


def snapshot(world):
    """Everything a refused call must leave alone."""
    return {t: world.rows("PARENT", f"SELECT * FROM {t} ORDER BY 1") for t in
            ("journal_entry", "journal_line", "audit_log", "entry_number_sequence")}


# --- create ---------------------------------------------------------------------------------------

def test_create_makes_an_unposted_draft(env, ctx):
    entry_id = ledger.create_entry(ctx, entry_date="2026-03-15", lines=two_lines(env), description="Rent",
                                   reference="R-1")
    row = entry_row(env, entry_id)
    assert (row["is_posted"], row["is_void"], row["entry_number"]) == (0, 0, None)
    assert (row["entry_date"], row["description"], row["reference"]) == ("2026-03-15", "Rent", "R-1")
    assert (row["created_by"], row["origin"], row["posted_by"], row["approved_by"]) == (env.user_id, "Human", None, None)
    assert [(l["account_id"], l["debit_cents"], l["credit_cents"]) for l in line_rows(env, entry_id)] == [
        (A(env, "cash"), 1000, 0), (A(env, "sales"), 0, 1000)]


def test_create_never_takes_an_entry_number(env, ctx):
    ledger.create_entry(ctx, entry_date="2026-03-15", lines=two_lines(env))
    assert env.rows("PARENT", "SELECT last_number FROM entry_number_sequence") == [{"last_number": 0}]


def test_unbalanced_and_empty_drafts_may_be_saved(env, ctx):
    unbalanced = ledger.create_entry(ctx, entry_date="2026-03-15",
                                     lines=[{"account_id": A(env, "cash"), "debit_cents": 500}])
    empty = ledger.create_entry(ctx, entry_date="2026-03-15")
    assert len(line_rows(env, unbalanced)) == 1 and line_rows(env, empty) == []


def test_line_optional_fields_are_stored(env, ctx):
    lines = [{"account_id": A(env, "cash"), "debit_cents": 700, "memo": " deposit ", "contact_id": A(env, "contact"),
              "external_ref": "X-9"},
             {"account_id": A(env, "sales"), "credit_cents": 700}]
    entry_id = ledger.create_entry(ctx, entry_date="2026-03-15", lines=lines)
    first = line_rows(env, entry_id)[0]
    assert (first["memo"], first["contact_id"], first["external_ref"]) == ("deposit", A(env, "contact"), "X-9")


def test_blank_text_is_stored_as_null_and_text_is_trimmed(env, ctx):
    entry_id = ledger.create_entry(ctx, entry_date="2026-03-15", description="  ", reference=" ref ")
    row = entry_row(env, entry_id)
    assert row["description"] is None and row["reference"] == "ref"


@pytest.mark.parametrize("source", [None, "Manual", "Adjustment"])
def test_create_accepts_manual_sources(env, ctx, source):
    entry_id = ledger.create_entry(ctx, entry_date="2026-03-15", source=source)
    assert entry_row(env, entry_id)["source"] == source


def test_create_refuses_an_unknown_source(env, ctx):
    with pytest.raises(ValidationError):
        ledger.create_entry(ctx, entry_date="2026-03-15", source="Opening")


@pytest.mark.parametrize("origin", ["Human", "Agent"])
@pytest.mark.parametrize("source", ["Payroll", "Import", "Conversion", "Invoice"])
def test_a_person_or_agent_cannot_label_a_draft_with_a_document_source(env, origin, source):
    """Otherwise a manual entry could escape the manual-entry rules by claiming to be a payroll or import entry."""
    before = snapshot(env)
    with pytest.raises(ValidationError, match="manual"):
        ledger.create_entry(env.ctx(env.user_id, "PARENT", origin), entry_date="2026-03-15", source=source)
    assert snapshot(env) == before


@pytest.mark.parametrize("origin, source", [("Import", "Import"), ("Import", "Payroll"), ("Import", "Conversion"),
                                              ("System", "Invoice"), ("System", "Deferral")])
def test_import_and_system_origin_may_use_document_sources(env, origin, source):
    entry_id = ledger.create_entry(env.ctx(env.user_id, "PARENT", origin), entry_date="2026-03-15", source=source)
    assert (entry_row(env, entry_id)["source"], entry_row(env, entry_id)["origin"]) == (source, origin)


def test_update_cannot_relabel_a_draft_as_a_document_entry(env, ctx):
    entry_id = ledger.create_entry(ctx, entry_date="2026-03-15")
    with pytest.raises(ValidationError, match="manual"):
        ledger.update_entry(ctx, entry_id, source="Payroll")


def test_create_is_audited_with_the_user(env, ctx):
    entry_id = ledger.create_entry(ctx, entry_date="2026-03-15")
    log = env.rows("PARENT", "SELECT user_id, action FROM audit_log WHERE table_name = 'journal_entry' "
                             "AND record_id = ?", (entry_id,))
    assert log == [{"user_id": env.user_id, "action": "Insert"}]


def test_an_agent_context_makes_an_agent_draft(env):
    entry_id = ledger.create_entry(env.ctx(env.user_id, "PARENT", "Agent"), entry_date="2026-03-15", lines=two_lines(env))
    assert entry_row(env, entry_id)["origin"] == "Agent"


def test_create_needs_je_create(env):
    other = env.user("viewer")
    env.role("PARENT", "VIEWER", ["ledger.view"])
    env.grant(other, "PARENT", "VIEWER")
    before = snapshot(env)
    with pytest.raises(PermissionDeniedError):
        ledger.create_entry(env.ctx(other, "PARENT"), entry_date="2026-03-15")
    assert snapshot(env)["journal_entry"] == before["journal_entry"]


def test_auto_reverse_date_is_stored_and_must_follow_the_entry(env, ctx):
    entry_id = ledger.create_entry(ctx, entry_date="2026-03-31", auto_reverse_date="2026-04-01")
    assert entry_row(env, entry_id)["auto_reverse_date"] == "2026-04-01"
    for bad in ("2026-03-31", "2026-03-30", "04/01/2026", "2026-02-30"):
        with pytest.raises(ValidationError):
            ledger.create_entry(ctx, entry_date="2026-03-31", auto_reverse_date=bad)


# --- the shared line check -------------------------------------------------------------------------

BAD_AMOUNTS = [
    pytest.param({"debit_cents": 10.0}, id="float"),
    pytest.param({"debit_cents": "10"}, id="string"),
    pytest.param({"debit_cents": True}, id="bool"),
    pytest.param({"debit_cents": -5}, id="negative debit"),
    pytest.param({"credit_cents": -5}, id="negative credit"),
    pytest.param({"debit_cents": 10, "credit_cents": 10}, id="both sides"),
    pytest.param({}, id="no amount"),
    pytest.param({"debit_cents": 0, "credit_cents": 0}, id="zero"),
    pytest.param({"debit_cents": None}, id="none"),
]


@pytest.mark.parametrize("amounts", BAD_AMOUNTS)
def test_bad_line_amounts_are_refused_and_nothing_is_written(env, ctx, amounts):
    before = snapshot(env)
    with pytest.raises(ValidationError):
        ledger.create_entry(ctx, entry_date="2026-03-15",
                            lines=[{"account_id": A(env, "cash"), "debit_cents": 5}, {"account_id": A(env, "sales"), **amounts}])
    assert snapshot(env) == before


@pytest.mark.parametrize("line", [
    pytest.param({"debit_cents": 5}, id="missing account"),
    pytest.param({"account_id": 99999, "debit_cents": 5}, id="unknown account"),
    pytest.param({"account_id": "1010", "debit_cents": 5}, id="account as text"),
    pytest.param({"account_id": 1, "debit_cents": 5, "contact_id": 99999}, id="unknown contact"),
    pytest.param({"account_id": 1, "debit_cents": 5, "is_control_override": 1}, id="system flag"),
    pytest.param({"account_id": 1, "debit_cents": 5, "is_rounding_adjustment": 1}, id="rounding flag"),
    pytest.param({"account_id": 1, "debit_cents": 5, "batch_id": 1}, id="unknown field"),
    pytest.param("not a dict", id="not a mapping"),
])
def test_bad_lines_are_refused(env, ctx, line):
    if isinstance(line, dict) and line.get("account_id") == 1:
        line = {**line, "account_id": A(env, "cash")}
    before = snapshot(env)
    with pytest.raises(ValidationError):
        ledger.create_entry(ctx, entry_date="2026-03-15", lines=[line])
    assert snapshot(env) == before


def test_lines_must_be_a_list(env, ctx):
    with pytest.raises(ValidationError):
        ledger.create_entry(ctx, entry_date="2026-03-15", lines="nope")


# --- header and inactive accounts (replaces the draft half of the pending test) ----------------------

@pytest.mark.parametrize("name, wording", [
    ("header", "header"),        # is_postable = 0
    ("inactive", "inactive"),
    ("parent", "header"),       # has a child account
])
def test_cannot_use_a_header_or_inactive_account(env, ctx, name, wording):
    before = snapshot(env)
    with pytest.raises(PostingError, match=wording):
        ledger.create_entry(ctx, entry_date="2026-03-15",
                            lines=[{"account_id": A(env, name), "debit_cents": 100},
                                   {"account_id": A(env, "sales"), "credit_cents": 100}])
    assert snapshot(env) == before


def test_the_message_names_the_account(env, ctx):
    with pytest.raises(PostingError, match="1000"):
        ledger.create_entry(ctx, entry_date="2026-03-15", lines=[{"account_id": A(env, "header"), "debit_cents": 1}])


@pytest.mark.parametrize("name", ["header", "inactive", "parent"])
def test_update_applies_the_same_account_check(env, ctx, name):
    entry_id = ledger.create_entry(ctx, entry_date="2026-03-15", lines=two_lines(env))
    before = snapshot(env)
    with pytest.raises(PostingError):
        ledger.update_entry(ctx, entry_id, lines=[{"account_id": A(env, name), "debit_cents": 1000},
                                                   {"account_id": A(env, "sales"), "credit_cents": 1000}])
    assert snapshot(env) == before


def test_an_account_deactivated_after_the_draft_is_caught_by_the_stored_lines_check(env, ctx):
    entry_id = ledger.create_entry(ctx, entry_date="2026-03-15", lines=two_lines(env))
    conn = sqlite3.connect(env.path("PARENT"))
    conn.row_factory = sqlite3.Row
    try:
        ledger.check_entry_lines(conn, entry_id)                      # fine today
        conn.execute("UPDATE account SET is_active = 0 WHERE account_id = ?", (A(env, "cash"),))
        with pytest.raises(PostingError, match="inactive"):
            ledger.check_entry_lines(conn, entry_id)
        conn.execute("UPDATE account SET is_active = 1, is_postable = 0 WHERE account_id = ?", (A(env, "cash"),))
        with pytest.raises(PostingError, match="header"):
            ledger.check_entry_lines(conn, entry_id)
    finally:
        conn.close()


def test_check_lines_is_the_single_choke_point(env, ctx, monkeypatch):
    calls = []
    original = ledger.check_lines
    monkeypatch.setattr(ledger, "check_lines", lambda *a, **k: calls.append(1) or original(*a, **k))
    entry_id = ledger.create_entry(ctx, entry_date="2026-03-15", lines=two_lines(env))
    ledger.update_entry(ctx, entry_id, lines=two_lines(env, 2000))
    assert len(calls) == 2


# --- entry dates and periods (replaces pending test period_is_set_from_entry_date) --------------------------

def test_period_comes_from_the_entry_date(env, ctx):
    march = ledger.create_entry(ctx, entry_date="2026-03-15")
    december_31 = ledger.create_entry(ctx, entry_date="2026-12-31")
    march_period = env.rows("PARENT", "SELECT * FROM fiscal_period WHERE period_id = ?", (entry_row(env, march)["period_id"],))[0]
    assert (march_period["period_number"], march_period["start_date"]) == (3, "2026-03-01")
    period = env.rows("PARENT", "SELECT * FROM fiscal_period WHERE period_id = ?", (entry_row(env, december_31)["period_id"],))[0]
    assert (period["period_number"], period["is_adjustment_period"]) == (12, 0)    # not 13, even on year end


def test_create_delegates_the_period_to_periods_resolve_entry_period(env, ctx, monkeypatch):
    seen = []
    original = periods.resolve_entry_period

    def spy(conn, entry_date, period_id=None):
        seen.append((entry_date, period_id))
        return original(conn, entry_date, period_id)

    monkeypatch.setattr(periods, "resolve_entry_period", spy)
    ledger.create_entry(ctx, entry_date="2026-03-15")
    assert seen == [("2026-03-15", None)]


def test_update_delegates_a_changed_date_too(env, ctx, monkeypatch):
    entry_id = ledger.create_entry(ctx, entry_date="2026-03-15")
    seen = []
    original = periods.resolve_entry_period
    monkeypatch.setattr(periods, "resolve_entry_period",
                        lambda conn, d, p=None: seen.append((d, p)) or original(conn, d, p))
    ledger.update_entry(ctx, entry_id, entry_date="2026-04-02")
    assert seen == [("2026-04-02", None)]
    assert entry_row(env, entry_id)["period_id"] == env.rows(
        "PARENT", "SELECT period_id FROM fiscal_period WHERE '2026-04-02' BETWEEN start_date AND end_date "
                  "AND is_adjustment_period = 0")[0]["period_id"]


def adjustment_period_id(env):
    return env.rows("PARENT", "SELECT period_id FROM fiscal_period WHERE period_number = 13 "
                              "AND start_date LIKE '2026-%'")[0]["period_id"]


def test_explicit_period_13_needs_the_control_and_the_year_end_date(env, ctx):
    period_13 = adjustment_period_id(env)
    with pytest.raises(ValidationError, match="turned off"):
        ledger.create_entry(ctx, entry_date="2026-12-31", period_id=period_13)
    with env._company("PARENT") as c:
        c.execute("UPDATE company_settings SET adjustment_periods_enabled = 1 WHERE id = 1")
    with pytest.raises(ValidationError, match="last day"):
        ledger.create_entry(ctx, entry_date="2026-12-30", period_id=period_13)
    entry_id = ledger.create_entry(ctx, entry_date="2026-12-31", period_id=period_13)
    assert entry_row(env, entry_id)["period_id"] == period_13


def test_explicit_period_must_hold_the_date(env, ctx):
    april = env.rows("PARENT", "SELECT period_id FROM fiscal_period WHERE '2026-04-10' BETWEEN start_date AND end_date "
                               "AND is_adjustment_period = 0")[0]["period_id"]
    with pytest.raises(ValidationError):
        ledger.create_entry(ctx, entry_date="2026-03-15", period_id=april)


@pytest.mark.parametrize("value", ["03/15/2026", "2026-3-5", "2026-02-30", "", None, 20260315])
def test_bad_dates_are_refused(env, ctx, value):
    before = snapshot(env)
    with pytest.raises(ValidationError):
        ledger.create_entry(ctx, entry_date=value)
    assert snapshot(env) == before


def test_a_date_with_no_period_is_refused(env, ctx):
    with pytest.raises(NotFoundError):
        ledger.create_entry(ctx, entry_date="2031-01-01")


def test_a_draft_in_a_closed_period_is_refused(env, ctx):
    with env._company("PARENT") as c:
        c.execute("UPDATE fiscal_period SET is_closed = 1, closed_at = '2026-05-01 00:00:00', closed_by = 1 "
                  "WHERE '2026-03-15' BETWEEN start_date AND end_date AND is_adjustment_period = 0")
    before = snapshot(env)
    with pytest.raises(PeriodClosedError, match="closed"):
        ledger.create_entry(ctx, entry_date="2026-03-15", lines=two_lines(env))
    assert snapshot(env) == before


# --- update ---------------------------------------------------------------------------------------------

def test_update_changes_fields_and_replaces_lines(env, ctx):
    entry_id = ledger.create_entry(ctx, entry_date="2026-03-15", lines=two_lines(env), description="old")
    ledger.update_entry(ctx, entry_id, description="new", entry_date="2026-04-02", lines=two_lines(env, 2500))
    row = entry_row(env, entry_id)
    assert (row["description"], row["entry_date"]) == ("new", "2026-04-02")
    assert [(l["debit_cents"], l["credit_cents"]) for l in line_rows(env, entry_id)] == [(2500, 0), (0, 2500)]


def test_update_without_lines_keeps_them(env, ctx):
    entry_id = ledger.create_entry(ctx, entry_date="2026-03-15", lines=two_lines(env))
    ids = [l["line_id"] for l in line_rows(env, entry_id)]
    ledger.update_entry(ctx, entry_id, description="only text")
    assert [l["line_id"] for l in line_rows(env, entry_id)] == ids


def test_update_with_an_empty_list_clears_the_lines(env, ctx):
    entry_id = ledger.create_entry(ctx, entry_date="2026-03-15", lines=two_lines(env))
    ledger.update_entry(ctx, entry_id, lines=[])
    assert line_rows(env, entry_id) == []


def test_update_can_clear_text_and_the_auto_reverse_date(env, ctx):
    entry_id = ledger.create_entry(ctx, entry_date="2026-03-31", description="x", auto_reverse_date="2026-04-01")
    ledger.update_entry(ctx, entry_id, description=None, auto_reverse_date=None)
    row = entry_row(env, entry_id)
    assert row["description"] is None and row["auto_reverse_date"] is None


def test_update_moving_to_a_closed_period_changes_nothing(env, ctx):
    entry_id = ledger.create_entry(ctx, entry_date="2026-03-15", lines=two_lines(env))
    with env._company("PARENT") as c:
        c.execute("UPDATE fiscal_period SET is_closed = 1, closed_at = '2026-05-01 00:00:00', closed_by = 1 "
                  "WHERE '2026-01-10' BETWEEN start_date AND end_date AND is_adjustment_period = 0")
    before = snapshot(env)
    with pytest.raises(PeriodClosedError):
        ledger.update_entry(ctx, entry_id, entry_date="2026-01-10", lines=two_lines(env, 9))
    assert snapshot(env) == before


def test_update_unknown_entry(env, ctx):
    with pytest.raises(NotFoundError):
        ledger.update_entry(ctx, 9999, description="x")


def posted(env):
    with env._company("PARENT") as c:
        return lh.posted_entry(c, 1000, entry_date="2026-03-10")


def test_a_posted_entry_cannot_be_updated_or_deleted(env, ctx):
    entry_id = posted(env)
    before = snapshot(env)
    with pytest.raises(PostingError, match="reverse"):
        ledger.update_entry(ctx, entry_id, description="edit")
    with pytest.raises(PostingError, match="reverse"):
        ledger.delete_entry(ctx, entry_id)
    assert snapshot(env) == before


def test_a_reversal_draft_is_not_edited_here(env, ctx):
    original = posted(env)
    with env._company("PARENT") as c:
        reversal = lh.make_reversal(c, original, "Void")
    with pytest.raises(PostingError, match="reversal"):
        ledger.update_entry(ctx, reversal, description="edit")


def test_update_needs_je_create(env):
    entry_id = ledger.create_entry(env.ctx_, entry_date="2026-03-15")
    other = env.user("viewer")
    env.role("PARENT", "VIEWER", ["ledger.view"])
    env.grant(other, "PARENT", "VIEWER")
    with pytest.raises(PermissionDeniedError):
        ledger.update_entry(env.ctx(other, "PARENT"), entry_id, description="x")
    with pytest.raises(PermissionDeniedError):
        ledger.delete_entry(env.ctx(other, "PARENT"), entry_id)


# --- delete -------------------------------------------------------------------------------------------------

def test_delete_removes_the_draft_and_its_lines_and_is_audited(env, ctx):
    entry_id = ledger.create_entry(ctx, entry_date="2026-03-15", lines=two_lines(env))
    ledger.delete_entry(ctx, entry_id)
    assert env.rows("PARENT", "SELECT 1 FROM journal_entry WHERE entry_id = ?", (entry_id,)) == []
    assert line_rows(env, entry_id) == []
    actions = [r["action"] for r in env.rows("PARENT", "SELECT action FROM audit_log WHERE table_name = 'journal_entry' "
                                                       "AND record_id = ? ORDER BY log_id", (entry_id,))]
    assert actions == ["Insert", "Delete"]


def test_delete_unknown_entry(env, ctx):
    with pytest.raises(NotFoundError):
        ledger.delete_entry(ctx, 9999)


def test_deleting_leaves_the_entry_counter_alone(env, ctx):
    entry_id = ledger.create_entry(ctx, entry_date="2026-03-15", lines=two_lines(env))
    ledger.delete_entry(ctx, entry_id)
    assert env.rows("PARENT", "SELECT last_number FROM entry_number_sequence") == [{"last_number": 0}]


# --- read ------------------------------------------------------------------------------------------------------

def test_get_entry_returns_the_entry_with_its_lines(env, ctx):
    entry_id = ledger.create_entry(ctx, entry_date="2026-03-15", lines=two_lines(env), description="Rent")
    entry = ledger.get_entry(ctx, entry_id)
    assert entry["entry_id"] == entry_id and entry["description"] == "Rent" and entry["is_posted"] == 0
    assert [(l["account_id"], l["debit_cents"], l["credit_cents"]) for l in entry["lines"]] == [
        (A(env, "cash"), 1000, 0), (A(env, "sales"), 0, 1000)]
    assert entry["total_debit_cents"] == 1000 and entry["total_credit_cents"] == 1000


def test_get_entry_unknown_and_permission(env, ctx):
    with pytest.raises(NotFoundError):
        ledger.get_entry(ctx, 9999)
    entry_id = ledger.create_entry(ctx, entry_date="2026-03-15")
    nobody = env.user("nobody")
    env.role("PARENT", "NONE", ["period.view"])
    env.grant(nobody, "PARENT", "NONE")
    with pytest.raises(PermissionDeniedError):
        ledger.get_entry(env.ctx(nobody, "PARENT"), entry_id)


def test_list_entries_filters_by_state(env, ctx):
    draft = ledger.create_entry(ctx, entry_date="2026-03-15")
    done = posted(env)
    assert [e["entry_id"] for e in ledger.list_entries(ctx, state="draft")] == [draft]
    assert [e["entry_id"] for e in ledger.list_entries(ctx, state="posted")] == [done]
    assert {e["entry_id"] for e in ledger.list_entries(ctx)} == {draft, done}
    with pytest.raises(ValidationError):
        ledger.list_entries(ctx, state="maybe")


# --- static: one place writes the journal ------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
WRITE_SQL = re.compile(
    r"\b(insert\s+(or\s+\w+\s+)?into|update|delete\s+from|replace\s+into)\s+\"?(journal_entry|journal_line|"
    r"journal_line_dimension|entry_number_sequence)\b", re.IGNORECASE)
SKIP = {".git", "__pycache__", "tests", "archive", "tools", "scripts", ".venv", "migrations", "Outdated"}


def project_python():
    for pattern in ("*.py", "*.pyw"):
        for path in ROOT.rglob(pattern):
            rel = path.relative_to(ROOT)
            if not SKIP.intersection(rel.parts):
                yield path, rel.as_posix()


def test_only_ledger_py_writes_journal_tables():
    """No screen or other service writes journal entries, lines or the entry counter (CLAUDE.md rule 7)."""
    offenders = {}
    for path, rel in project_python():
        if rel == "modules/services/ledger.py":
            continue
        hits = [m.group(0) for m in WRITE_SQL.finditer(path.read_text(encoding="utf-8"))]
        if hits:
            offenders[rel] = hits
    assert not offenders, f"journal tables are written only by modules/services/ledger.py: {offenders}"


def test_the_static_scan_would_catch_a_writer(tmp_path):
    for sql in ("INSERT INTO journal_line (x) VALUES (1)", 'UPDATE "journal_entry" SET x = 1',
                "delete from journal_line", "INSERT OR REPLACE INTO journal_entry (x)", "UPDATE entry_number_sequence SET"):
        assert WRITE_SQL.search(sql), sql
    for sql in ("SELECT * FROM journal_entry", "UPDATE journal_entry_hash SET x = 1"):
        assert not WRITE_SQL.search(sql), sql
