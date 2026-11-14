"""Reversals and automatic reversals, Phase 2.5 step 5 (decisions L5, R2, R4, R8, R9, R40-R47).

* Posting an entry with an automatic reversal date also posts its Accrual reversal in the same transaction (L5,
  R47).
* `ledger.void_entry` posts a Void reversal and marks the original void; `ledger.reverse_entry` posts a Correction
  (R40-R46). A Void of an accrual that has an automatic reversal voids both (R4).
* Every reversal mirrors its original line by line, dimensions included (R45), and keeps the chain whole.
"""
import sqlite3

import pytest

from modules.services import approvals, ledger
from modules.services.errors import PeriodClosedError, PermissionDeniedError, PostingError, ValidationError
from tests import ledger_helpers as lh
from tests.authz_world import world  # noqa: F401  (fixture)
from tests.test_ledger_approvals import as_, team  # noqa: F401  (fixture and helper)
from tests.test_ledger_posting import (  # noqa: F401  (fixtures and helpers)
    A, NOW, TODAY, ctx_for, draft, entry_row, env, keyed, lines, refused, settings, snapshot, verify,
)

NOTE = "wrong account"


@pytest.fixture
def rev(env):
    """The poster may also void and correct (je.reverse)."""
    env.grant_permission("PARENT", "POSTER", "je.reverse")
    return env


def ctx(env, origin="Human", **kwargs):
    return ctx_for(env, origin, **kwargs)


def posted(env, *, entry_date="2026-03-15", entry_lines=None, **kwargs):
    entry_id = draft(env, entry_date=entry_date, entry_lines=entry_lines, description="Rent", reference="R-1",
                     **kwargs)
    return entry_id, ledger.post_journal_entry(ctx(env), entry_id, confirm=True, acknowledge_date_warnings=True)


def accrual(env, *, entry_date="2026-03-31", auto_reverse_date="2026-04-01", entry_lines=None):
    entry_id = draft(env, entry_date=entry_date, entry_lines=entry_lines, description="Accrued wages",
                     reference="ACC-3", auto_reverse_date=auto_reverse_date)
    return entry_id, ledger.post_journal_entry(ctx(env), entry_id, confirm=True)


def void(env, entry_id, *, note=NOTE, confirm=True, context=None, **kwargs):
    return ledger.void_entry(context or ctx(env), entry_id, note=note, confirm=confirm, **kwargs)


def correct(env, entry_id, *, note=NOTE, confirm=True, context=None, **kwargs):
    return ledger.reverse_entry(context or ctx(env), entry_id, note=note, confirm=confirm, **kwargs)


def lines_of(env, entry_id):
    return env.rows("PARENT", "SELECT * FROM journal_line WHERE entry_id = ? ORDER BY line_id", (entry_id,))


def dims_of(env, entry_id):
    return env.rows("PARENT", "SELECT l.line_id, d.dimension_type_id, d.dimension_value_id FROM journal_line_dimension "
                              "AS d JOIN journal_line AS l ON l.line_id = d.line_id WHERE l.entry_id = ? "
                              "ORDER BY l.line_id, d.dimension_type_id", (entry_id,))


def reversal_of(env, entry_id, reason):
    rows = env.rows("PARENT", "SELECT * FROM journal_entry WHERE reverses_entry_id = ? AND reversal_reason = ?",
                    (entry_id, reason))
    assert len(rows) == 1
    return rows[0]


def period_of(env, day):
    return env.rows("PARENT", "SELECT period_id FROM fiscal_period WHERE is_adjustment_period = 0 "
                              "AND ? BETWEEN start_date AND end_date", (day,))[0]["period_id"]


def close(env, day, closed=True):
    with env._company("PARENT") as c:
        lh.set_period_closed(c, period_of(env, day), closed)


def add_dimensions(env, entry_id):
    """Two dimension types on the draft's lines (set directly: drafts take no dimensions through the service)."""
    with env._company("PARENT") as c:
        types = [c.execute("INSERT INTO dimension_type (name) VALUES (?) RETURNING dimension_type_id",
                           (name,)).fetchone()[0] for name in ("Class", "Location")]
        values = [c.execute("INSERT INTO dimension_value (dimension_type_id, code, name) VALUES (?, ?, ?) "
                            "RETURNING dimension_value_id", (t, f"V{t}", f"Value {t}")).fetchone()[0] for t in types]
        line_ids = [r[0] for r in c.execute("SELECT line_id FROM journal_line WHERE entry_id = ? ORDER BY line_id",
                                            (entry_id,))]
        c.execute("INSERT INTO journal_line_dimension VALUES (?, ?, ?)", (line_ids[0], types[0], values[0]))
        c.execute("INSERT INTO journal_line_dimension VALUES (?, ?, ?)", (line_ids[0], types[1], values[1]))
        c.execute("INSERT INTO journal_line_dimension VALUES (?, ?, ?)", (line_ids[1], types[0], values[0]))


def assert_mirror(env, original_id, reversal_id):
    """Line by line: the same keys and flags, debit and credit swapped, the same dimensions (R45)."""
    original, reversal = lines_of(env, original_id), lines_of(env, reversal_id)
    assert len(original) == len(reversal)
    copied = ("account_id", "memo", "contact_id", "project_id", "cost_code_id", "deferral_id", "batch_id",
              "is_retainage_line", "external_ref", "is_control_override", "is_rounding_adjustment")
    for old, new in zip(original, reversal):
        assert {k: new[k] for k in copied} == {k: old[k] for k in copied}
        assert (new["debit_cents"], new["credit_cents"]) == (old["credit_cents"], old["debit_cents"])
    old_dims = [(d["dimension_type_id"], d["dimension_value_id"]) for d in dims_of(env, original_id)]
    new_dims = [(d["dimension_type_id"], d["dimension_value_id"]) for d in dims_of(env, reversal_id)]
    assert old_dims == new_dims


def as_source(env, entry_id, source):
    with env._company("PARENT") as c:
        c.execute("UPDATE journal_entry SET source = ? WHERE entry_id = ?", (source, entry_id))


# --- Automatic reversals (L5, R47) -------------------------------------------------------------------------

def test_posting_an_accrual_posts_its_reversal_in_the_same_post(rev):
    entry_id, result = accrual(rev)
    original = entry_row(rev, entry_id)
    reversal = reversal_of(rev, entry_id, "Accrual reversal")
    assert (original["entry_number"], reversal["entry_number"]) == (1, 2)
    assert result["entry_number"] == 1
    assert (result["reversal_entry_id"], result["reversal_entry_number"]) == (reversal["entry_id"], 2)
    assert reversal["is_posted"] == 1 and reversal["is_void"] == 0
    assert reversal["entry_date"] == "2026-04-01" and reversal["period_id"] == period_of(rev, "2026-04-01")
    assert reversal["origin"] == "System"
    assert (reversal["created_by"], reversal["posted_by"]) == (rev.user_id, rev.user_id)
    assert reversal["posted_at"] == NOW
    assert reversal["source"] == original["source"]
    assert (reversal["approved_by"], reversal["approved_at"]) == (None, None)
    assert reversal["reversal_note"] is None and reversal["auto_reverse_date"] is None
    assert reversal["description"] == "Automatic reversal of JE-000001: Accrued wages"
    assert reversal["reference"] == "ACC-3"
    assert reversal["chain_prev_hash"] == original["chain_hash"]
    check = verify(rev)
    assert check["ok"] and check["through_entry_number"] == 2


def test_the_automatic_reversal_mirrors_every_line_and_dimension(rev):
    entry_lines = [{"account_id": A(rev, "cash"), "debit_cents": 700, "memo": "a", "contact_id": rev.plain_contact},
                   {"account_id": A(rev, "cash"), "debit_cents": 300, "memo": "b"},
                   {"account_id": A(rev, "sales"), "credit_cents": 1000, "memo": "c"}]
    entry_id = draft(rev, entry_date="2026-03-31", entry_lines=entry_lines, auto_reverse_date="2026-04-01")
    add_dimensions(rev, entry_id)
    ledger.post_journal_entry(ctx(rev), entry_id, confirm=True)
    assert_mirror(rev, entry_id, reversal_of(rev, entry_id, "Accrual reversal")["entry_id"])
    assert verify(rev)["ok"]


def test_an_accrual_without_a_description_gets_the_short_text(rev):
    entry_id = draft(rev, entry_date="2026-03-31", auto_reverse_date="2026-04-01")
    ledger.post_journal_entry(ctx(rev), entry_id, confirm=True)
    assert reversal_of(rev, entry_id, "Accrual reversal")["description"] == "Automatic reversal of JE-000001"


def test_an_automatic_reversal_date_with_no_period_refuses_the_whole_post(rev):
    entry_id = draft(rev, entry_date="2026-03-31", auto_reverse_date="2031-01-01")
    refused(rev, lambda: ledger.post_journal_entry(ctx(rev), entry_id, confirm=True), PostingError,
            r"^The automatic reversal date \(2031-01-01\) has no fiscal period yet; add the fiscal year or change "
            r"the date\.$")


def test_an_automatic_reversal_date_in_a_closed_period_refuses_the_whole_post(rev):
    entry_id = draft(rev, entry_date="2026-03-31", auto_reverse_date="2026-04-01")
    close(rev, "2026-04-01")
    period_name = rev.rows("PARENT", "SELECT name FROM fiscal_period WHERE period_id = ?",
                           (period_of(rev, "2026-04-01"),))[0]["name"]
    refused(rev, lambda: ledger.post_journal_entry(ctx(rev), entry_id, confirm=True), PeriodClosedError,
            rf"^The automatic reversal date \(2026-04-01\) is in {period_name}, which is closed; reopen it or "
            r"change the date\.$")


def test_submitting_an_accrual_checks_the_reversal_date_too(team):
    entry_id = ledger.create_entry(as_(team, "poster", "Agent"), entry_date="2026-03-31",
                                   lines=lines(team), auto_reverse_date="2031-01-01")
    with pytest.raises(PostingError, match="no fiscal period yet"):
        ledger.submit_entry_for_approval(as_(team, "poster", "Agent"), entry_id)


def test_an_agent_accrual_needs_approval_and_then_posts_both(team):
    entry_id = ledger.create_entry(as_(team, "poster", "Agent"), entry_date="2026-03-31", lines=lines(team),
                                   auto_reverse_date="2026-04-01")
    with pytest.raises(PostingError, match="needs approval"):
        ledger.post_journal_entry(as_(team, "poster"), entry_id, confirm=True)
    request_id = ledger.submit_entry_for_approval(as_(team, "poster", "Agent"), entry_id)
    approvals.approve(as_(team, "appr1"), request_id)
    result = ledger.post_journal_entry(as_(team, "poster"), entry_id, confirm=True)
    reversal = reversal_of(team, entry_id, "Accrual reversal")
    assert result["reversal_entry_id"] == reversal["entry_id"]
    assert entry_row(team, entry_id)["approved_by"] == team.people["appr1"]
    assert (reversal["approved_by"], reversal["origin"]) == (None, "System")
    assert verify(team)["ok"]


def test_changing_the_reversal_date_after_approval_cancels_it(team):
    entry_id = ledger.create_entry(as_(team, "poster", "Agent"), entry_date="2026-03-31", lines=lines(team),
                                   auto_reverse_date="2026-04-01")
    request_id = ledger.submit_entry_for_approval(as_(team, "poster", "Agent"), entry_id)
    approvals.approve(as_(team, "appr1"), request_id)
    ledger.update_entry(as_(team, "poster", "Agent"), entry_id, auto_reverse_date="2026-04-02")
    with pytest.raises(PostingError, match="cancelled because the entry was changed"):
        ledger.post_journal_entry(as_(team, "poster"), entry_id, confirm=True)


def test_an_entry_without_an_automatic_reversal_date_posts_alone(rev):
    entry_id, result = posted(rev)
    assert result["reversal_entry_id"] is None and result["reversal_entry_number"] is None
    assert rev.rows("PARENT", "SELECT COUNT(*) AS n FROM journal_entry WHERE is_posted = 1")[0]["n"] == 1


def test_cash_basis_can_find_an_accrual_and_its_reversal(rev):
    # CB1 removes auto-reversing accruals together with their reversals; the link must be queryable.
    entry_id, _ = accrual(rev)
    posted(rev)
    pairs = rev.rows("PARENT", "SELECT o.entry_id AS original, r.entry_id AS reversal FROM journal_entry AS o "
                               "JOIN journal_entry AS r ON r.reverses_entry_id = o.entry_id "
                               "AND r.reversal_reason = 'Accrual reversal' WHERE o.auto_reverse_date IS NOT NULL")
    assert pairs == [{"original": entry_id, "reversal": reversal_of(rev, entry_id, "Accrual reversal")["entry_id"]}]


# --- Void (R40-R46) ----------------------------------------------------------------------------------------

def test_void_posts_a_mirror_and_marks_the_original_void(rev):
    entry_id, _ = posted(rev)
    result = void(rev, entry_id)
    original, reversal = entry_row(rev, entry_id), reversal_of(rev, entry_id, "Void")
    assert original["is_void"] == 1
    assert result == {"entry_id": reversal["entry_id"], "entry_number": 2, "voided_entry_ids": [entry_id],
                      "warnings": []}
    assert reversal["entry_date"] == "2026-03-15"                         # R41: the original's date by default
    assert (reversal["origin"], reversal["created_by"], reversal["posted_by"]) == ("Human", rev.user_id, rev.user_id)
    assert reversal["source"] == original["source"]
    assert reversal["reversal_note"] == NOTE
    assert reversal["description"] == "Void of JE-000001: Rent"
    assert reversal["reference"] == "R-1"
    assert_mirror(rev, entry_id, reversal["entry_id"])
    assert verify(rev)["ok"]


def test_the_note_is_shown_with_the_generated_description(rev):
    entry_id, _ = posted(rev)
    reversal_id = void(rev, entry_id)["entry_id"]
    shown = ledger.get_entry(ctx(rev), reversal_id)["display_description"]
    assert shown == "Void of JE-000001: Rent (note: wrong account)"
    shown = {e["entry_id"]: e["display_description"] for e in ledger.list_entries(ctx(rev))}
    assert shown == {entry_id: "Rent", reversal_id: "Void of JE-000001: Rent (note: wrong account)"}


def test_the_note_is_trimmed(rev):
    entry_id, _ = posted(rev)
    reversal_id = void(rev, entry_id, note="  typo  ")["entry_id"]
    assert entry_row(rev, reversal_id)["reversal_note"] == "typo"


def test_void_copies_dimensions_memos_contacts_and_flags(rev):
    entry_lines = [{"account_id": A(rev, "ar"), "debit_cents": 1000, "contact_id": rev.customer, "memo": "x"},
                   {"account_id": A(rev, "sales"), "credit_cents": 1000, "memo": "y"}]
    entry_id = draft(rev, entry_lines=entry_lines)
    add_dimensions(rev, entry_id)
    ledger.post_journal_entry(ctx(rev), entry_id, confirm=True)
    assert lines_of(rev, entry_id)[0]["is_control_override"] == 1
    reversal_id = void(rev, entry_id)["entry_id"]
    assert_mirror(rev, entry_id, reversal_id)
    assert lines_of(rev, reversal_id)[0]["is_control_override"] == 1
    assert verify(rev)["ok"]


def test_void_is_allowed_when_manual_entries_to_controlled_accounts_are_off(rev):
    entry_lines = [{"account_id": A(rev, "ar"), "debit_cents": 1000, "contact_id": rev.customer},
                   {"account_id": A(rev, "sales"), "credit_cents": 1000}]
    entry_id = draft(rev, entry_lines=entry_lines)
    ledger.post_journal_entry(ctx(rev), entry_id, confirm=True)
    settings(rev, allow_manual_control_je=0)
    void(rev, entry_id)
    assert entry_row(rev, entry_id)["is_void"] == 1


def test_void_needs_no_approval_even_with_manual_entry_approval_on(rev):        # R8
    entry_id, _ = posted(rev)
    settings(rev, manual_entry_approval=1, manual_entry_approval_threshold_cents=0)
    void(rev, entry_id)
    assert entry_row(rev, entry_id)["is_void"] == 1


def test_with_separation_on_the_creator_may_still_void(rev):                    # R42
    entry_id, _ = posted(rev)
    rev.settings("PARENT", require_separate_approver=1)
    void(rev, entry_id)
    assert entry_row(rev, entry_id)["is_void"] == 1


def test_void_may_be_dated_later(rev):
    entry_id, _ = posted(rev)
    reversal_id = void(rev, entry_id, entry_date="2026-03-18")["entry_id"]
    assert entry_row(rev, reversal_id)["entry_date"] == "2026-03-18"


def test_void_cannot_be_dated_before_the_original(rev):
    # The pending rule "reversal cannot predate original" (controls audit), rewritten against the service (R25).
    entry_id, _ = posted(rev, entry_date="2026-03-15")
    refused(rev, lambda: void(rev, entry_id, entry_date="2026-03-10"), ValidationError,
            r"^A void cannot be dated before the entry it reverses \(2026-03-15\)\.$")


def test_void_cannot_be_dated_in_a_closed_period(rev):
    entry_id, _ = posted(rev)
    close(rev, "2026-03-15")
    refused(rev, lambda: void(rev, entry_id), PeriodClosedError, "is closed")


def test_void_of_an_entry_in_a_closed_period_can_be_dated_in_an_open_one(rev):
    entry_id, _ = posted(rev, entry_date="2026-02-10")
    close(rev, "2026-02-10")
    reversal_id = void(rev, entry_id, entry_date="2026-03-02")["entry_id"]
    assert entry_row(rev, reversal_id)["period_id"] == period_of(rev, "2026-03-02")
    assert entry_row(rev, entry_id)["is_void"] == 1


def test_void_with_a_bad_date_is_refused(rev):
    entry_id, _ = posted(rev)
    refused(rev, lambda: void(rev, entry_id, entry_date="15/03/2026"), ValidationError)


def test_void_far_in_the_past_asks_to_check_the_date(rev):
    entry_id, _ = posted(rev, entry_date="2026-01-05")
    refused(rev, lambda: void(rev, entry_id, context=ctx(rev, today="2026-06-30", now="2026-06-30T10:00:00+00:00")),
            ledger.DateWarningsError, "days ago")
    result = void(rev, entry_id, context=ctx(rev, today="2026-06-30", now="2026-06-30T10:00:00+00:00"),
                  acknowledge_date_warnings=True)
    assert [w["code"] for w in result["warnings"]] == ["past"]


@pytest.mark.parametrize("note", [None, "", "   "])
def test_void_needs_a_note(rev, note):
    entry_id, _ = posted(rev)
    refused(rev, lambda: void(rev, entry_id, note=note), ValidationError,
            r"^Say why in the note, so the reason stays with the entry\.$")


def test_void_needs_confirm(rev):
    entry_id, _ = posted(rev)
    refused(rev, lambda: void(rev, entry_id, confirm=False), ValidationError, r"^Confirm the void first")


def test_void_needs_the_reverse_permission(env):
    entry_id, _ = posted(env)
    refused(env, lambda: void(env, entry_id), PermissionDeniedError)


def test_an_agent_cannot_void(rev):
    entry_id, _ = posted(rev)
    refused(rev, lambda: void(rev, entry_id, context=ctx(rev, "Agent")), PermissionDeniedError)


@pytest.mark.parametrize("origin", ["Import", "System"])
def test_only_a_person_voids(rev, origin):
    entry_id, _ = posted(rev)
    with pytest.raises(PermissionDeniedError) as error:
        void(rev, entry_id, context=ctx(rev, origin))
    assert str(error.value) == "Only a person can void or correct an entry; sign in and do it from the entry."
    assert entry_row(rev, entry_id)["is_void"] == 0


def test_a_draft_cannot_be_voided(rev):
    entry_id = draft(rev)
    refused(rev, lambda: void(rev, entry_id), PostingError,
            r"^Only a posted entry can be voided or corrected; change or delete the draft instead\.$")


def test_a_missing_entry_cannot_be_voided(rev):
    from modules.services.errors import NotFoundError
    refused(rev, lambda: void(rev, 999), NotFoundError)


def test_a_voided_entry_cannot_be_voided_again(rev):
    entry_id, _ = posted(rev)
    void(rev, entry_id)
    refused(rev, lambda: void(rev, entry_id), PostingError, r"^JE-000001 is already void\.$")


def test_a_corrected_entry_cannot_be_voided(rev):
    entry_id, _ = posted(rev)
    correct(rev, entry_id)
    refused(rev, lambda: void(rev, entry_id), PostingError, r"^JE-000001 has already been voided or corrected\.$")


def test_a_voided_entry_cannot_be_corrected(rev):
    entry_id, _ = posted(rev)
    void(rev, entry_id)
    refused(rev, lambda: correct(rev, entry_id), PostingError, r"^JE-000001 is already void\.$")


@pytest.mark.parametrize("first", ["void", "correct"])
@pytest.mark.parametrize("second", ["void", "correct"])
def test_a_reversal_cannot_be_reversed(rev, first, second):                        # R43
    entry_id, _ = posted(rev)
    reversal_id = (void if first == "void" else correct)(rev, entry_id)["entry_id"]
    refused(rev, lambda: (void if second == "void" else correct)(rev, reversal_id), PostingError,
            r"^JE-000002 is a reversal; enter a new entry to change its effect\.$")


@pytest.mark.parametrize("source, made_by, word", [
    ("Invoice", "an invoice", "invoice"), ("Bill", "a bill", "bill"), ("Payment", "a payment", "payment"),
    ("Deferral", "a deferral", "deferral"),
    ("Completion", "a percentage-of-completion entry", "percentage-of-completion entry")])
def test_an_entry_from_a_document_is_voided_through_the_document(rev, source, made_by, word):   # R40
    entry_id = draft(rev)
    as_source(rev, entry_id, source)
    ledger.post_journal_entry(ctx(rev), entry_id, confirm=True)
    for action in (void, correct):
        refused(rev, lambda: action(rev, entry_id), PostingError,
                rf"^This entry was made by {made_by}; void the {word} instead\.$")


@pytest.mark.parametrize("source", [None, "Manual", "Adjustment", "Import", "Payroll", "Conversion"])
def test_manual_import_payroll_and_conversion_entries_can_be_voided(rev, source):
    entry_id = draft(rev)
    as_source(rev, entry_id, source)
    ledger.post_journal_entry(ctx(rev), entry_id, confirm=True)
    reversal_id = void(rev, entry_id)["entry_id"]
    assert entry_row(rev, reversal_id)["source"] == source


def test_a_second_void_that_loses_the_race_gets_a_sentence(rev, monkeypatch):
    entry_id, _ = posted(rev)
    correct(rev, entry_id)
    # Make the pre-check miss the taken slot, as two people acting at once would: the unique index decides.
    monkeypatch.setattr(ledger, "_slot_taken", lambda conn, entry_id: False)
    refused(rev, lambda: correct(rev, entry_id), PostingError, r"^JE-000001 has already been voided or corrected\.$")


def test_the_audit_log_records_the_reversal_and_the_void_flag(rev):
    entry_id, _ = posted(rev)
    reversal_id = void(rev, entry_id)["entry_id"]
    def actions(record_id):
        return [r["action"] for r in rev.rows("PARENT", "SELECT action FROM audit_log WHERE table_name = "
                                                        "'journal_entry' AND record_id = ? ORDER BY 1", (record_id,))]
    assert sorted(actions(reversal_id)) == ["Insert", "Post"]
    assert "Void" in actions(entry_id)


def test_tampering_with_a_reversal_breaks_the_chain_there(rev):
    entry_id, _ = posted(rev)
    reversal_id = void(rev, entry_id)["entry_id"]
    conn = sqlite3.connect(rev.path("PARENT"))
    try:
        conn.execute("DROP TRIGGER journal_line_lock_update_posted")
        conn.execute("UPDATE journal_line SET memo = 'changed' WHERE entry_id = ?", (reversal_id,))
        conn.commit()
    finally:
        conn.close()
    check = verify(rev)
    assert not check["ok"] and check["first_broken"]["entry_number"] == 2


# --- Correction (R40, R41, R44) ------------------------------------------------------------------------------

def test_correction_posts_a_mirror_and_leaves_the_original_standing(rev):
    entry_id, _ = posted(rev)
    result = correct(rev, entry_id)
    reversal = reversal_of(rev, entry_id, "Correction")
    assert entry_row(rev, entry_id)["is_void"] == 0
    assert result["voided_entry_ids"] == []
    assert reversal["entry_date"] == TODAY                                   # R41: today by default
    assert reversal["description"] == "Correction of JE-000001: Rent"
    assert reversal["reversal_note"] == NOTE
    assert_mirror(rev, entry_id, reversal["entry_id"])
    assert verify(rev)["ok"]


def test_correction_can_be_dated_on_the_original_date_but_not_before(rev):
    entry_id, _ = posted(rev, entry_date="2026-03-15")
    refused(rev, lambda: correct(rev, entry_id, entry_date="2026-03-14"), ValidationError,
            r"^A correction cannot be dated before the entry it reverses \(2026-03-15\)\.$")
    reversal_id = correct(rev, entry_id, entry_date="2026-03-15")["entry_id"]
    assert entry_row(rev, reversal_id)["entry_date"] == "2026-03-15"


def test_correction_needs_confirm(rev):
    entry_id, _ = posted(rev)
    refused(rev, lambda: correct(rev, entry_id, confirm=False), ValidationError, r"^Confirm the correction first")


def test_an_accrual_with_an_automatic_reversal_cannot_be_corrected(rev):           # R44
    entry_id, _ = accrual(rev)
    refused(rev, lambda: correct(rev, entry_id), PostingError,
            r"^JE-000001 has an automatic reversal \(JE-000002\); void JE-000001 and both are voided together, "
            r"then enter a new accrual\.$")


# --- Pair void (R4, R41) ---------------------------------------------------------------------------------------

def test_voiding_an_accrual_voids_its_automatic_reversal_too(rev):
    entry_id, _ = accrual(rev)
    auto_id = reversal_of(rev, entry_id, "Accrual reversal")["entry_id"]
    result = void(rev, entry_id)
    void_original, void_auto = reversal_of(rev, entry_id, "Void"), reversal_of(rev, auto_id, "Void")
    assert result["voided_entry_ids"] == [entry_id, auto_id]
    assert result["entry_id"] == void_original["entry_id"]
    assert (void_original["entry_number"], void_auto["entry_number"]) == (3, 4)
    assert (entry_row(rev, entry_id)["is_void"], entry_row(rev, auto_id)["is_void"]) == (1, 1)
    assert (void_original["entry_date"], void_auto["entry_date"]) == ("2026-03-31", "2026-04-01")
    assert void_auto["description"] == "Void of JE-000002: Automatic reversal of JE-000001: Accrued wages"
    assert void_auto["reversal_note"] == NOTE
    assert_mirror(rev, entry_id, void_original["entry_id"])
    assert_mirror(rev, auto_id, void_auto["entry_id"])
    check = verify(rev)
    assert check["ok"] and check["through_entry_number"] == 4


@pytest.mark.parametrize("closed_day, name_day", [("2026-03-31", "2026-03-31"), ("2026-04-01", "2026-04-01")])
def test_a_pair_void_with_either_period_closed_writes_nothing(rev, closed_day, name_day):
    entry_id, _ = accrual(rev)
    close(rev, closed_day)
    period_name = rev.rows("PARENT", "SELECT name FROM fiscal_period WHERE period_id = ?",
                           (period_of(rev, name_day),))[0]["name"]
    refused(rev, lambda: void(rev, entry_id), PeriodClosedError,
            rf"^JE-000001 and its automatic reversal JE-000002 are voided together, and {period_name} is closed; "
            r"reopen it first\.$")


def test_a_pair_void_takes_no_date(rev):
    entry_id, _ = accrual(rev)
    refused(rev, lambda: void(rev, entry_id, entry_date="2026-04-05"), ValidationError,
            r"^An accrual and its automatic reversal are each voided on their own date; leave the date empty\.$")


def test_the_automatic_reversal_cannot_be_voided_on_its_own(rev):
    entry_id, _ = accrual(rev)
    auto_id = reversal_of(rev, entry_id, "Accrual reversal")["entry_id"]
    for action in (void, correct):
        refused(rev, lambda: action(rev, auto_id), PostingError,
                r"^JE-000002 is the automatic reversal of JE-000001; void JE-000001 and both are voided together\.$")


# --- The mirror check itself (R45) -------------------------------------------------------------------------------

def test_the_mirror_check_refuses_a_missing_dimension(rev):
    entry_id = draft(rev)
    add_dimensions(rev, entry_id)
    ledger.post_journal_entry(ctx(rev), entry_id, confirm=True)
    real_copy = ledger._copy_dimensions

    def drop_one(conn, pairs):
        real_copy(conn, pairs)
        conn.execute("DELETE FROM journal_line_dimension WHERE line_id = ?", (pairs[-1][1],))

    import unittest.mock
    with unittest.mock.patch.object(ledger, "_copy_dimensions", drop_one):
        refused(rev, lambda: void(rev, entry_id), PostingError, "does not mirror")


def test_posting_a_reversal_draft_directly_is_still_refused(rev):
    entry_id, _ = posted(rev)
    with rev._company("PARENT") as c:
        reversal = lh.make_reversal(c, entry_id, "Correction", entry_date="2026-03-16")
    refused(rev, lambda: ledger.post_journal_entry(ctx(rev), reversal, confirm=True), PostingError, "reverse or void")


def test_get_entry_of_an_ordinary_entry_shows_its_description(rev):
    entry_id, _ = posted(rev)
    assert ledger.get_entry(ctx(rev), entry_id)["display_description"] == "Rent"



# --- Review of step 5: adjustment periods (R48), errors and gaps ---------------------------------------------

def period_13(env):
    settings(env, adjustment_periods_enabled=1)
    return env.rows("PARENT", "SELECT period_id FROM fiscal_period WHERE period_number = 13 "
                              "AND start_date = '2026-12-31'")[0]["period_id"]


def test_a_void_of_a_period_13_entry_stays_in_period_13(rev):
    p13 = period_13(rev)
    entry_id = draft(rev, entry_date="2026-12-31", period_id=p13)
    ledger.post_journal_entry(ctx(rev), entry_id, confirm=True)
    close(rev, "2026-12-31")                                # period 12 is closed, period 13 open: the usual case
    result = void(rev, entry_id)
    reversal = entry_row(rev, result["entry_id"])
    assert (reversal["period_id"], reversal["entry_date"]) == (p13, "2026-12-31")
    assert result["warnings"] == []                         # R12: no date warnings in period 13
    assert verify(rev)["ok"]


def test_a_void_of_a_period_13_entry_on_a_later_date_takes_that_month(rev):
    p13 = period_13(rev)
    entry_id = draft(rev, entry_date="2026-12-31", period_id=p13)
    ledger.post_journal_entry(ctx(rev), entry_id, confirm=True)
    reversal_id = void(rev, entry_id, entry_date="2027-01-05", acknowledge_date_warnings=True)["entry_id"]
    assert entry_row(rev, reversal_id)["period_id"] == period_of(rev, "2027-01-05")


def test_a_period_13_accrual_is_voided_as_a_pair_with_period_12_closed(rev):
    p13 = period_13(rev)
    entry_id = draft(rev, entry_date="2026-12-31", period_id=p13, auto_reverse_date="2027-01-01")
    ledger.post_journal_entry(ctx(rev), entry_id, confirm=True)
    close(rev, "2026-12-31")
    auto_id = reversal_of(rev, entry_id, "Accrual reversal")["entry_id"]
    void(rev, entry_id, acknowledge_date_warnings=True)
    assert reversal_of(rev, entry_id, "Void")["period_id"] == p13
    assert reversal_of(rev, auto_id, "Void")["period_id"] == period_of(rev, "2027-01-01")
    assert verify(rev)["ok"]


def close_period(env, period_id):
    with env._company("PARENT") as c:
        lh.set_period_closed(c, period_id, True)


@pytest.mark.parametrize("action, word", [("void", "void"), ("correct", "correction")])
def test_a_reversal_into_a_closed_period_13_is_refused_and_never_moves(rev, action, word):
    # R48 (final): a reversal dated its period-13 target's date stays in period 13; with period 13 closed it is
    # refused with the next step, never posted in period 12 (open here) or anywhere else.
    p13 = period_13(rev)
    entry_id = draft(rev, entry_date="2026-12-31", period_id=p13)
    ledger.post_journal_entry(ctx(rev), entry_id, confirm=True)
    close_period(rev, p13)
    call = void if action == "void" else correct
    refused(rev, lambda: call(rev, entry_id, entry_date="2026-12-31"), PeriodClosedError,
            rf"^FY2026-13 is closed; reopen it with a reason, or date the {word} in the next fiscal year\.$")


def test_a_void_of_a_closed_period_13_entry_can_be_dated_in_the_next_year(rev):
    p13 = period_13(rev)
    entry_id = draft(rev, entry_date="2026-12-31", period_id=p13)
    ledger.post_journal_entry(ctx(rev), entry_id, confirm=True)
    close_period(rev, p13)
    reversal_id = void(rev, entry_id, entry_date="2027-01-05", acknowledge_date_warnings=True)["entry_id"]
    assert entry_row(rev, reversal_id)["period_id"] == period_of(rev, "2027-01-05")


def test_a_period_13_accrual_pair_void_with_period_13_closed_writes_nothing(rev):
    p13 = period_13(rev)
    entry_id = draft(rev, entry_date="2026-12-31", period_id=p13, auto_reverse_date="2027-01-01")
    ledger.post_journal_entry(ctx(rev), entry_id, confirm=True)
    close_period(rev, p13)
    refused(rev, lambda: void(rev, entry_id, acknowledge_date_warnings=True), PeriodClosedError,
            r"^JE-000001 and its automatic reversal JE-000002 are voided together, and FY2026-13 is closed; ")


def test_an_automatic_reversal_into_the_next_fiscal_year(rev):
    entry_id = draft(rev, entry_date="2026-12-31", auto_reverse_date="2027-01-01")
    ledger.post_journal_entry(ctx(rev), entry_id, confirm=True, acknowledge_date_warnings=True)
    reversal = reversal_of(rev, entry_id, "Accrual reversal")
    assert reversal["period_id"] == period_of(rev, "2027-01-01")
    assert verify(rev)["ok"]


def test_a_correction_with_no_period_for_today_says_what_to_do(rev):
    entry_id, _ = posted(rev)
    refused(rev, lambda: correct(rev, entry_id, context=ctx(rev, today="2031-01-01", now="2031-01-01T09:00:00+00:00")),
            PostingError, r"^There is no fiscal period for 2031-01-01 yet; add the fiscal year or choose another "
                          r"date\.$")


def test_a_correction_into_a_closed_period_is_refused(rev):
    entry_id, _ = posted(rev)
    close(rev, TODAY)
    refused(rev, lambda: correct(rev, entry_id), PeriodClosedError, "is closed")


def test_a_person_voids_an_imported_entry(team):
    team.grant_permission("PARENT", "POSTER", "je.reverse")
    entry_id = ledger.create_entry(as_(team, "poster", "Import"), entry_date="2026-03-15", lines=lines(team),
                                   source="Import")
    request_id = ledger.submit_entry_for_approval(as_(team, "poster", "Import"), entry_id)
    approvals.approve(as_(team, "appr1"), request_id)
    ledger.post_journal_entry(as_(team, "poster"), entry_id, confirm=True)
    result = ledger.void_entry(as_(team, "poster"), entry_id, note=NOTE, confirm=True)
    reversal = entry_row(team, result["entry_id"])
    assert (reversal["origin"], reversal["source"]) == ("Human", "Import")
    assert entry_row(team, entry_id)["is_void"] == 1


def test_reversals_carry_no_approval_with_separation_on(rev):
    first, _ = posted(rev)
    second, _ = posted(rev)
    rev.settings("PARENT", require_separate_approver=1)        # after posting: the creator may not post (R17)
    for result in (void(rev, first), correct(rev, second)):
        row = entry_row(rev, result["entry_id"])
        assert (row["approved_by"], row["approved_at"]) == (None, None)


def test_another_database_error_on_the_reversal_is_not_called_a_race(rev, monkeypatch):
    from modules.services.errors import SaveFailedError
    entry_id, _ = posted(rev)
    real = ledger._reversal_period

    def wrong_period(conn, day, target):
        period_id, period = real(conn, day, target)
        return 99999, dict(period, period_id=99999)            # a period that does not exist: a foreign key error

    monkeypatch.setattr(ledger, "_reversal_period", wrong_period)
    refused(rev, lambda: void(rev, entry_id), SaveFailedError)


def test_every_journal_line_column_is_mirrored_or_named():
    # R45: a new journal_line column must be added to MIRRORED_LINE_FIELDS (or here, with a reason).
    import modules.database as database
    import tempfile, os
    from pathlib import Path
    path = Path(tempfile.mkdtemp()) / "c.db"
    database.ensure_company_database(path)
    conn = sqlite3.connect(path)
    try:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(journal_line)")}
    finally:
        conn.close()
        os.remove(path)
    not_copied = {"line_id", "entry_id", "debit_cents", "credit_cents", "recon_id"}   # keys, swapped sides, B10
    assert columns == set(ledger.MIRRORED_LINE_FIELDS) | not_copied


# --- Mutation check of step 5: the gaps it found -------------------------------------------------------------

def test_the_person_who_voids_is_the_creator_and_poster_of_the_void(rev):
    entry_id, _ = posted(rev)                                     # created and posted by the poster
    other = rev.user("reverser")
    rev.grant(other, "PARENT", "POSTER")
    result = void(rev, entry_id, context=ctx_for(rev, user=other))
    row = entry_row(rev, result["entry_id"])
    assert (row["created_by"], row["posted_by"]) == (other, other)
    assert entry_row(rev, entry_id)["created_by"] == rev.user_id


@pytest.mark.parametrize("action", ["void", "correct"])
@pytest.mark.parametrize("confirm", [False, None, 1, "yes"])
def test_only_confirm_true_confirms(rev, action, confirm):
    entry_id, _ = posted(rev)
    refused(rev, lambda: (void if action == "void" else correct)(rev, entry_id, confirm=confirm), ValidationError,
            r"^Confirm the (void|correction) first")


@pytest.mark.parametrize("bad", ["next week", "2026-3-16", "2026-13-01", 20260316])
def test_a_reversal_date_must_be_an_iso_date(rev, bad):
    entry_id, _ = posted(rev)
    refused(rev, lambda: void(rev, entry_id, entry_date=bad), ValidationError)


def test_a_pair_void_shows_each_date_warning_once(rev):
    entry_id, _ = accrual(rev)                               # 31 March and 1 April, both far behind in September
    late = ctx(rev, today="2026-09-30", now="2026-09-30T10:00:00+00:00")
    with pytest.raises(ledger.DateWarningsError) as error:
        void(rev, entry_id, context=late)
    assert [w["code"] for w in error.value.warnings] == ["past"]
    result = void(rev, entry_id, context=late, acknowledge_date_warnings=True)
    assert [w["code"] for w in result["warnings"]] == ["past"]


def test_display_description_without_a_description():
    assert ledger.display_description({"description": None, "reversal_note": "typo"}) == "(note: typo)"
    assert ledger.display_description({"description": "Rent", "reversal_note": None}) == "Rent"
    assert ledger.display_description({"description": None, "reversal_note": None}) is None
