"""Rounding and document entries, Phase 2.5 step 6 (decisions L8, R1, R49-R54; audit design section 13).

`ledger.create_document_entry` is the one way document, import, payroll and conversion entries are made: inside
the caller's write transaction, origin System or Import. An Import, Payroll or Conversion entry that is out of
balance by exactly 1 cent gets one flagged 1-cent line to the rounding account when it is saved, worked out again
on every save (R49); 2 cents or more is refused when it is saved, so nothing is saved (R51). `create_entry` takes
manual sources only (R50). Posting checks every rounding line again (R53).
"""
import dataclasses

import pytest

from modules.services import approvals, ledger
from modules.services.errors import PeriodClosedError, PostingError, ValidationError
from modules.services.tx import write_transaction
from tests import ledger_helpers as lh
from tests.authz_world import world  # noqa: F401  (fixture)
from tests.test_ledger_approvals import as_, team  # noqa: F401  (fixture and helper)
from tests.test_ledger_posting import (  # noqa: F401  (fixtures and helpers)
    A, NOW, TODAY, ctx_for, entry_row, env, keyed, lines, refused, settings, snapshot, verify,
)

ROUNDING_SOURCES = ("Import", "Payroll", "Conversion")
ORIGIN_FOR = {"Import": "Import", "Payroll": "Import", "Conversion": "Import"}           # R55


@pytest.fixture
def rnd(env):
    """env with a rounding account (8020) set in Company Settings, and the poster allowed to void."""
    with env._company("PARENT") as c:
        env.accts["rounding"] = lh.make_account(c, "8020", name="Rounding Variance")
    settings(env, rounding_variance_acct_id=env.accts["rounding"])
    env.grant_permission("PARENT", "POSTER", "je.reverse")
    return env


def off_by(env, cents, amount=1000):
    """Two lines whose debits exceed the credits by `cents` (negative: the credits are higher)."""
    return [{"account_id": A(env, "cash"), "debit_cents": amount + max(cents, 0)},
            {"account_id": A(env, "sales"), "credit_cents": amount + max(-cents, 0)}]


def doc(env, source, entry_lines, *, context=None, source_rows=(2, 3), **kwargs):
    """create_document_entry in its own write transaction, as an importer or document service does."""
    context = context or ctx_for(env, ORIGIN_FOR.get(source, "System"))
    if source not in ROUNDING_SOURCES and source_rows == (2, 3):
        source_rows = None
    with write_transaction(context.company_db_path, context) as conn:
        return ledger.create_document_entry(conn, context, source=source, entry_date="2026-03-15",
                                            lines=entry_lines, source_rows=source_rows, **kwargs)


def post_after_review(env, entry_id):
    """R18, R55: the importer sends the entry for review, the same person approves it (separation off, the default)
    and posts it. Returns the entry number."""
    reviewer_rights(env)
    request_id = ledger.submit_entry_for_approval(ctx_for(env, "Import"), entry_id)
    approvals.approve(ctx_for(env), request_id)
    return ledger.post_journal_entry(ctx_for(env), entry_id, confirm=True)["entry_number"]


def reviewer_rights(env):
    """The poster may run imports, send them for review and approve an Import batch of any amount."""
    held = {r["permission_code"] for r in env.rows("PARENT", "SELECT permission_code FROM role_permission WHERE "
                                                             "role_code = 'POSTER'")}
    for permission in {"import.run", "import.approve"} - held:
        env.grant_permission("PARENT", "POSTER", permission)
    if not env.rows("PARENT", "SELECT 1 FROM approval_limit WHERE role_code = 'POSTER' AND "
                              "document_type = 'Import batch'"):
        env.limit("PARENT", "POSTER", "Import batch", 10 ** 12)


def lines_of(env, entry_id):
    return env.rows("PARENT", "SELECT * FROM journal_line WHERE entry_id = ? ORDER BY line_id", (entry_id,))


def rounding_lines(env, entry_id):
    return [l for l in lines_of(env, entry_id) if l["is_rounding_adjustment"]]


# --- R49: one cent is balanced when the entry is saved ----------------------------------------------------------

@pytest.mark.parametrize("source", ROUNDING_SOURCES)
@pytest.mark.parametrize("cents, side", [(1, "credit_cents"), (-1, "debit_cents")])
def test_one_cent_gets_one_flagged_line_on_the_rounding_account(rnd, source, cents, side):
    result = doc(rnd, source, off_by(rnd, cents))
    assert result["rounding_cents"] == cents and result["entry_number"] is None
    saved = lines_of(rnd, result["entry_id"])
    assert len(saved) == 3
    line = saved[-1]                                                        # the entry's last line
    assert (line["account_id"], line["is_rounding_adjustment"], line["memo"]) == (
        A(rnd, "rounding"), 1, "Rounding (1 cent)")
    assert (line[side], line["debit_cents"] + line["credit_cents"]) == (1, 1)
    assert (line["contact_id"], line["project_id"], line["cost_code_id"], line["external_ref"]) == (None,) * 4
    assert sum(l["debit_cents"] for l in saved) == sum(l["credit_cents"] for l in saved)
    assert [l["is_rounding_adjustment"] for l in saved[:2]] == [0, 0]


@pytest.mark.parametrize("source", ROUNDING_SOURCES)
def test_a_balanced_entry_gets_no_rounding_line(rnd, source):
    result = doc(rnd, source, off_by(rnd, 0))
    assert result["rounding_cents"] == 0 and rounding_lines(rnd, result["entry_id"]) == []
    assert len(lines_of(rnd, result["entry_id"])) == 2


@pytest.mark.parametrize("source", ROUNDING_SOURCES)
def test_a_balanced_entry_needs_no_rounding_account(env, source):
    result = doc(env, source, off_by(env, 0))                  # env has no rounding account set
    assert rounding_lines(env, result["entry_id"]) == []


@pytest.mark.parametrize("source", ["Invoice", "Bill", "Payment", "Deferral", "Completion"])
def test_other_document_sources_are_never_rounded(rnd, source):
    entry_id = doc(rnd, source, off_by(rnd, 1))["entry_id"]
    assert rounding_lines(rnd, entry_id) == []
    system = ctx_for(rnd, "System")
    refused(rnd, lambda: ledger.post_journal_entry(system, entry_id), PostingError, "does not balance")


def test_a_manual_entry_has_zero_tolerance(rnd):
    entry_id = ledger.create_entry(ctx_for(rnd), entry_date="2026-03-15", lines=off_by(rnd, 1))
    assert rounding_lines(rnd, entry_id) == []
    refused(rnd, lambda: ledger.post_journal_entry(ctx_for(rnd), entry_id, confirm=True), PostingError,
            r"^This entry does not balance: debits 10\.01, credits 10\.00")


def test_a_rounded_conversion_entry_posts_after_its_review_and_verifies(rnd):
    entry_id = doc(rnd, "Conversion", off_by(rnd, -1))["entry_id"]
    assert post_after_review(rnd, entry_id) == 1
    assert (entry_row(rnd, entry_id)["is_posted"], len(rounding_lines(rnd, entry_id))) == (1, 1)
    assert verify(rnd)["ok"]


# --- R51: two cents or more is refused when the entry is saved, and nothing is saved ---------------------------

@pytest.mark.parametrize("source", ROUNDING_SOURCES)
@pytest.mark.parametrize("cents, shown", [(2, "0.02"), (-2, "0.02"), (125, "1.25")])
def test_two_cents_or_more_is_refused_when_saved(rnd, source, cents, shown):
    refused(rnd, lambda: doc(rnd, source, off_by(rnd, cents), reference="PR-0412", source_rows=[12, 13, 14, 15]),
            ValidationError,
            rf"^Entry PR-0412 \(rows 12-15\) is out of balance by {shown}; only a 1-cent rounding difference is "
            r"balanced automatically, so nothing was saved\. Correct the amounts and import it again\.$")


def test_the_refusal_names_an_entry_without_a_reference_by_its_date_and_its_rows(rnd):
    refused(rnd, lambda: doc(rnd, "Import", off_by(rnd, 3), source_rows=[9, 4, 5, 7]), ValidationError,
            r"^The entry dated 2026-03-15 \(rows 4-5, 7, 9\) is out of balance by 0\.03; ")
    refused(rnd, lambda: doc(rnd, "Import", off_by(rnd, 3), source_rows=[8]), ValidationError,
            r"^The entry dated 2026-03-15 \(row 8\) is out of balance")


def test_an_import_is_all_or_nothing(rnd):
    # The first entry of the file is fine, the second is 2 cents off: the importer's one transaction saves nothing.
    before = snapshot(rnd)
    context = ctx_for(rnd, "Import")
    with pytest.raises(ValidationError, match=r"\(row 3\) is out of balance by 0\.02"):
        with write_transaction(context.company_db_path, context) as conn:
            ledger.create_document_entry(conn, context, source="Import", entry_date="2026-03-15",
                                         lines=off_by(rnd, 1), source_rows=[2])
            ledger.create_document_entry(conn, context, source="Import", entry_date="2026-03-15",
                                         lines=off_by(rnd, 2), source_rows=[3])
    assert snapshot(rnd) == before


@pytest.mark.parametrize("source", ROUNDING_SOURCES)
@pytest.mark.parametrize("bad", [None, [], (), [0], [-1], [True], ["2"], "2-3", [2.0]])
def test_the_three_sources_must_give_their_source_rows(rnd, source, bad):
    refused(rnd, lambda: doc(rnd, source, off_by(rnd, 0), source_rows=bad), ValidationError,
            r"^Give the file rows this entry came from")


# --- R52: the rounding account ----------------------------------------------------------------------------------

def test_no_rounding_account_refuses_a_one_cent_entry(env):
    refused(env, lambda: doc(env, "Import", off_by(env, 1), reference="PR-1"), ValidationError,
            r"^Entry PR-1 \(rows 2-3\) is out of balance by 0\.01 and no rounding account is set; choose one in "
            r"Company Settings > Accounts, or correct the amounts\.$")


@pytest.mark.parametrize("change, words", [
    ({"is_active": 0}, "is inactive"),
    ({"is_postable": 0}, "is a header account"),
])
def test_an_unusable_rounding_account_refuses_a_one_cent_entry(rnd, change, words):
    with rnd._company("PARENT") as c:
        for column, value in change.items():
            c.execute(f"UPDATE account SET {column} = ? WHERE account_id = ?", (value, A(rnd, "rounding")))
    refused(rnd, lambda: doc(rnd, "Payroll", off_by(rnd, -1), reference="PR-1"), ValidationError,
            rf"^Entry PR-1 \(rows 2-3\) is out of balance by 0\.01 and the rounding account 8020 Rounding Variance "
            rf"{words}; choose another in Company Settings > Accounts, or correct the amounts\.$")


def test_a_rounding_account_with_sub_accounts_is_refused(rnd):
    with rnd._company("PARENT") as c:
        lh.make_account(c, "8021", parent_id=A(rnd, "rounding"))
    refused(rnd, lambda: doc(rnd, "Import", off_by(rnd, 1)), ValidationError, "is a header account")


# --- R50: create_entry takes manual sources only; create_document_entry takes the others ----------------------

@pytest.mark.parametrize("origin", ["Human", "Agent", "Import", "System"])
@pytest.mark.parametrize("source", ["Import", "Payroll", "Conversion", "Invoice", "Bill", "Payment", "Deferral",
                                    "Completion"])
def test_create_entry_refuses_document_sources_for_every_origin(env, origin, source):
    refused(env, lambda: ledger.create_entry(env.ctx(env.user_id, "PARENT", origin), entry_date="2026-03-15",
                                             source=source), ValidationError, "manual")


@pytest.mark.parametrize("origin", ["Import", "System"])
def test_import_and_system_origin_still_make_manual_drafts(env, origin):
    entry_id = ledger.create_entry(env.ctx(env.user_id, "PARENT", origin), entry_date="2026-03-15", lines=lines(env))
    assert (entry_row(env, entry_id)["source"], entry_row(env, entry_id)["origin"]) == (None, origin)


@pytest.mark.parametrize("origin", ["Human", "Agent"])
def test_a_person_or_agent_cannot_make_a_document_entry(env, origin):
    refused(env, lambda: doc(env, "Invoice", lines(env), context=ctx_for(env, origin)), ValidationError,
            r"^A document entry is made by its document's service")


@pytest.mark.parametrize("source", [None, "Manual", "Adjustment", "Opening"])
def test_create_document_entry_takes_document_sources_only(env, source):
    refused(env, lambda: doc(env, source, lines(env)), ValidationError, "is not a document or import source")


@pytest.mark.parametrize("origin, source", [("Import", "Import"), ("Import", "Payroll"), ("Import", "Conversion"),
                                            ("System", "Invoice"), ("System", "Deferral")])
def test_document_entries_keep_their_source_origin_and_person(rnd, origin, source):
    entry_id = doc(rnd, source, lines(rnd), context=ctx_for(rnd, origin), description="March payroll",
                   reference="R-9")["entry_id"]
    row = entry_row(rnd, entry_id)
    assert (row["source"], row["origin"], row["created_by"], row["is_posted"]) == (source, origin, rnd.user_id, 0)
    assert (row["description"], row["reference"], row["period_id"] is not None) == ("March payroll", "R-9", True)


def test_create_document_entry_runs_the_line_checks(rnd):
    bad = [{"account_id": A(rnd, "cash"), "debit_cents": 1.5}, {"account_id": A(rnd, "sales"), "credit_cents": 1}]
    refused(rnd, lambda: doc(rnd, "Import", bad), ValidationError, "whole number of cents")
    flagged = [dict(l, is_rounding_adjustment=1) for l in lines(rnd)]
    refused(rnd, lambda: doc(rnd, "Import", flagged), ValidationError, "cannot be set on a line")


def test_create_document_entry_refuses_a_closed_period(rnd):
    from tests.test_ledger_reversals import close
    close(rnd, "2026-03-15")
    refused(rnd, lambda: doc(rnd, "Import", lines(rnd)), PeriodClosedError, "is closed")


def test_an_imported_entry_cannot_be_posted_on_save(rnd):
    refused(rnd, lambda: doc(rnd, "Import", lines(rnd), post=True), ValidationError,
            r"^An imported entry is posted by a person after its review")


def test_a_document_entry_that_needs_approval_cannot_be_posted_on_save(rnd):
    with rnd._company("PARENT") as c:
        c.execute("UPDATE document_approval_setting SET requires_approval = 1 WHERE document_type = 'Bill'")
    refused(rnd, lambda: doc(rnd, "Bill", lines(rnd), post=True), PostingError, "needs approval")


# --- R49: worked out again on every save ----------------------------------------------------------------------------

def test_update_works_the_rounding_out_again(rnd):
    importer = ctx_for(rnd, "Import")
    entry_id = doc(rnd, "Import", off_by(rnd, 1), context=importer)["entry_id"]
    ledger.update_entry(importer, entry_id, lines=off_by(rnd, 0))                 # 1 cent -> balanced
    assert rounding_lines(rnd, entry_id) == [] and len(lines_of(rnd, entry_id)) == 2
    ledger.update_entry(importer, entry_id, lines=off_by(rnd, -1))                # balanced -> 1 cent
    assert [l["debit_cents"] for l in rounding_lines(rnd, entry_id)] == [1]
    ledger.update_entry(importer, entry_id, lines=off_by(rnd, 1))                 # the other side
    assert [(l["debit_cents"], l["credit_cents"]) for l in rounding_lines(rnd, entry_id)] == [(0, 1)]
    assert len(lines_of(rnd, entry_id)) == 3


def test_update_with_two_cents_is_refused_and_changes_nothing(rnd):
    importer = ctx_for(rnd, "Import")
    entry_id = doc(rnd, "Import", off_by(rnd, 1), context=importer, reference="PR-7")["entry_id"]
    refused(rnd, lambda: ledger.update_entry(importer, entry_id, lines=off_by(rnd, 2)), ValidationError,
            r"^Entry PR-7 is out of balance by 0\.02; only a 1-cent rounding difference is balanced automatically, "
            r"so nothing was saved\.")


def test_a_manual_draft_is_not_rounded_on_update(rnd):
    entry_id = ledger.create_entry(ctx_for(rnd), entry_date="2026-03-15", lines=lines(rnd))
    ledger.update_entry(ctx_for(rnd), entry_id, lines=off_by(rnd, 1))
    assert rounding_lines(rnd, entry_id) == []


def test_saving_again_after_the_rounding_account_changed_moves_the_line(rnd):
    importer = ctx_for(rnd, "Import")
    entry_id = doc(rnd, "Import", off_by(rnd, 1), context=importer)["entry_id"]
    with rnd._company("PARENT") as c:
        new = lh.make_account(c, "8030")
    settings(rnd, rounding_variance_acct_id=new)
    ledger.update_entry(importer, entry_id, lines=off_by(rnd, 1))                 # the same lines, saved again
    assert [l["account_id"] for l in rounding_lines(rnd, entry_id)] == [new]


@pytest.mark.parametrize("source", [None, "Manual", "Adjustment"])
def test_a_document_entry_keeps_its_source(rnd, source):
    importer = ctx_for(rnd, "Import")
    entry_id = doc(rnd, "Import", off_by(rnd, 1), context=importer)["entry_id"]
    refused(rnd, lambda: ledger.update_entry(importer, entry_id, source=source), ValidationError,
            r"^An import or document entry keeps its source \(Import\)")


# --- The approval covers the rounding line (R15, R49) ---------------------------------------------------------------

def test_an_approved_rounded_import_posts_without_a_new_approval(team):
    with team._company("PARENT") as c:
        team.accts["rounding"] = lh.make_account(c, "8020", name="Rounding Variance")
    settings(team, rounding_variance_acct_id=team.accts["rounding"])
    importer = as_(team, "poster", "Import")
    entry_id = doc(team, "Import", off_by(team, 1), context=importer)["entry_id"]
    request_id = ledger.submit_entry_for_approval(importer, entry_id)
    approvals.approve(as_(team, "appr1"), request_id)
    result = ledger.post_journal_entry(as_(team, "poster"), entry_id, confirm=True)
    assert result["entry_number"] == 1 and len(rounding_lines(team, entry_id)) == 1
    assert entry_row(team, entry_id)["approved_by"] == team.people["appr1"]
    assert verify(team)["ok"]


# --- R53: posting checks every rounding line again ------------------------------------------------------------------

def force(env, sql, params):
    with env._company("PARENT") as c:
        c.execute(sql, params)


def test_posting_refuses_two_rounding_lines(rnd):
    entry_id = doc(rnd, "Conversion", off_by(rnd, 1))["entry_id"]
    force(rnd, "INSERT INTO journal_line (entry_id, account_id, debit_cents, credit_cents, is_rounding_adjustment) "
               "VALUES (?, ?, 1, 0, 1)", (entry_id, A(rnd, "rounding")))
    force(rnd, "UPDATE journal_line SET credit_cents = 1002 WHERE entry_id = ? AND account_id = ?",
          (entry_id, A(rnd, "sales")))                                     # still balanced: 1001 + 1 = 1002
    refused(rnd, lambda: ledger.post_journal_entry(ctx_for(rnd, "System"), entry_id), PostingError,
            r"^This entry has more than one rounding line; nothing was posted\.$")


def test_posting_refuses_a_rounding_line_over_one_cent(rnd):
    entry_id = doc(rnd, "Conversion", off_by(rnd, 1))["entry_id"]
    force(rnd, "UPDATE journal_line SET credit_cents = 2 WHERE entry_id = ? AND is_rounding_adjustment = 1",
          (entry_id,))
    force(rnd, "UPDATE journal_line SET debit_cents = 1002 WHERE entry_id = ? AND account_id = ?",
          (entry_id, A(rnd, "cash")))
    refused(rnd, lambda: ledger.post_journal_entry(ctx_for(rnd, "System"), entry_id), PostingError,
            r"^Line 3: a rounding line is exactly 1 cent; nothing was posted\.$")


def test_posting_refuses_a_rounding_line_on_another_account(rnd):
    entry_id = doc(rnd, "Conversion", off_by(rnd, 1))["entry_id"]
    force(rnd, "UPDATE journal_line SET account_id = ? WHERE entry_id = ? AND is_rounding_adjustment = 1",
          (A(rnd, "sales"), entry_id))
    refused(rnd, lambda: ledger.post_journal_entry(ctx_for(rnd, "System"), entry_id), PostingError,
            r"^Line 3: the rounding line is not on the rounding account in Company Settings > Accounts; save the "
            r"entry again to work it out again\.$")


@pytest.mark.parametrize("source", [None, "Manual", "Invoice", "Deferral"])
def test_posting_refuses_a_rounding_line_on_any_other_source(rnd, source):
    entry_id = doc(rnd, "Conversion", off_by(rnd, 1))["entry_id"]
    force(rnd, "UPDATE journal_entry SET source = ? WHERE entry_id = ?", (source, entry_id))
    system = ctx_for(rnd, "System")
    refused(rnd, lambda: ledger.post_journal_entry(system, entry_id), PostingError,
            r"^Line 3 is marked as a rounding line, which only import, payroll and conversion entries may have; "
            r"nothing was posted\.$")


def test_a_manual_entry_with_the_flag_forced_is_refused(rnd):
    entry_id = ledger.create_entry(ctx_for(rnd), entry_date="2026-03-15", lines=lines(rnd))
    force(rnd, "UPDATE journal_line SET is_rounding_adjustment = 1 WHERE entry_id = ? AND account_id = ?",
          (entry_id, A(rnd, "sales")))
    refused(rnd, lambda: ledger.post_journal_entry(ctx_for(rnd), entry_id, confirm=True), PostingError,
            "is marked as a rounding line")


# --- Reversals of a rounded entry (R45) -----------------------------------------------------------------------------

def test_a_void_of_a_rounded_entry_mirrors_its_rounding_line(rnd):
    entry_id = doc(rnd, "Conversion", off_by(rnd, 1))["entry_id"]
    post_after_review(rnd, entry_id)
    result = ledger.void_entry(ctx_for(rnd), entry_id, note="wrong file", confirm=True)
    mirror = rounding_lines(rnd, result["entry_id"])
    assert [(l["account_id"], l["debit_cents"], l["credit_cents"]) for l in mirror] == [(A(rnd, "rounding"), 1, 0)]
    assert verify(rnd)["ok"]


def test_a_void_still_works_after_the_rounding_account_changed(rnd):
    entry_id = doc(rnd, "Conversion", off_by(rnd, 1))["entry_id"]
    post_after_review(rnd, entry_id)
    with rnd._company("PARENT") as c:
        new = lh.make_account(c, "8030")
    settings(rnd, rounding_variance_acct_id=new)
    ledger.void_entry(ctx_for(rnd), entry_id, note="wrong file", confirm=True)
    assert entry_row(rnd, entry_id)["is_void"] == 1


# --- R54: as_system and as_import --------------------------------------------------------------------------------

@pytest.mark.parametrize("method, origin", [("as_system", "System"), ("as_import", "Import")])
def test_as_system_and_as_import_keep_the_person(env, method, origin):
    human = ctx_for(env)
    other = getattr(human, method)()
    assert other.origin == origin
    assert dataclasses.replace(other, origin="Human") == human                  # nothing else changes


@pytest.mark.parametrize("method", ["as_system", "as_import"])
def test_an_agent_context_cannot_become_system_or_import(env, method):
    with pytest.raises(ValidationError, match=r"^An agent's actions stay agent actions"):
        getattr(ctx_for(env, "Agent"), method)()


# --- Step 6 review: closing the narrow path -------------------------------------------------------------------

@pytest.mark.parametrize("source, article", [("Import", "An"), ("Payroll", "A")])
@pytest.mark.parametrize("post", [False, True])
def test_an_import_or_payroll_entry_comes_only_from_an_importer(rnd, source, article, post):
    # Section 0: import-origin batches always need one human review. As System they would post unreviewed.
    refused(rnd, lambda: doc(rnd, source, lines(rnd), context=ctx_for(rnd).as_system(), post=post),
            ValidationError, rf"^{article} {source.lower()} entry is saved by its importer \(origin Import\), so a "
                             r"person reviews it before it posts; save it as an import and send it for review\.$")


# --- R55 final (owner, 2026-11-14): Conversion entries also come only from an importer -------------------------
#
# Conversion entries, typed opening balances among them (a future wizard: create_document_entry, source Conversion,
# origin Import), always need one human review. With separation of duties off (the default) the person who entered
# them may review and post them; with it on, someone else must.

def test_a_system_context_cannot_save_a_conversion_entry(rnd):
    for post in (False, True):
        refused(rnd, lambda: doc(rnd, "Conversion", lines(rnd), context=ctx_for(rnd).as_system(), post=post),
                ValidationError,
                r"^A conversion entry is saved by its importer \(origin Import\), so a person reviews it before it "
                r"posts; save it as an import and send it for review\.$")


def test_an_import_origin_conversion_entry_posts_only_after_one_review(rnd):
    reviewer_rights(rnd)
    importer = ctx_for(rnd, "Import")
    refused(rnd, lambda: doc(rnd, "Conversion", off_by(rnd, 1), context=importer, post=True), ValidationError,
            r"^An imported entry is posted by a person after its review")
    result = doc(rnd, "Conversion", off_by(rnd, 1), context=importer)
    entry_id = result["entry_id"]
    assert (result["entry_number"], entry_row(rnd, entry_id)["origin"]) == (None, "Import")
    assert len(rounding_lines(rnd, entry_id)) == 1
    refused(rnd, lambda: ledger.post_journal_entry(ctx_for(rnd), entry_id, confirm=True), PostingError,
            "needs approval")
    request_id = ledger.submit_entry_for_approval(importer, entry_id)
    approvals.approve(ctx_for(rnd), request_id)              # separation off: the same person reviews
    posted = ledger.post_journal_entry(ctx_for(rnd), entry_id, confirm=True)
    row = entry_row(rnd, entry_id)
    assert (posted["entry_number"], row["approved_by"], row["posted_by"]) == (1, rnd.user_id, rnd.user_id)
    assert verify(rnd)["ok"]


def test_with_separation_on_the_person_who_entered_a_conversion_cannot_review_or_post_it(team):
    from modules.services.errors import PermissionDeniedError
    settings(team, require_separate_approver=1)
    reviewer_rights(team)
    importer = as_(team, "poster", "Import")
    entry_id = doc(team, "Conversion", lines(team), context=importer)["entry_id"]
    request_id = ledger.submit_entry_for_approval(importer, entry_id)
    refused(team, lambda: approvals.approve(as_(team, "poster"), request_id), PermissionDeniedError,
            r"^This company needs a different person to approve the .* you (created|sent for approval);")
    approvals.approve(as_(team, "appr1"), request_id)
    refused(team, lambda: ledger.post_journal_entry(as_(team, "poster"), entry_id, confirm=True),
            PermissionDeniedError, rf"^{ledger.CREATOR_CANNOT_POST}$")                  # R17: not the creator
    ledger.post_journal_entry(as_(team, "poster2"), entry_id, confirm=True)
    row = entry_row(team, entry_id)
    assert (row["is_posted"], row["approved_by"], row["posted_by"]) == (
        1, team.people["appr1"], team.people["poster2"])


@pytest.mark.parametrize("switch", [0, 1])
def test_a_conversion_entry_always_needs_its_review(rnd, switch):
    with rnd._company("PARENT") as c:
        c.execute("UPDATE document_approval_setting SET requires_approval = ? WHERE document_type = 'Import batch'",
                  (switch,))
    entry_id = doc(rnd, "Conversion", lines(rnd))["entry_id"]
    refused(rnd, lambda: ledger.post_journal_entry(ctx_for(rnd), entry_id, confirm=True), PostingError,
            "needs approval")


@pytest.mark.parametrize("switch", [0, 1])
def test_a_payroll_entry_always_needs_its_review(rnd, switch):
    with rnd._company("PARENT") as c:
        c.execute("UPDATE document_approval_setting SET requires_approval = ? WHERE document_type = 'Import batch'",
                  (switch,))
    entry_id = doc(rnd, "Payroll", lines(rnd))["entry_id"]
    refused(rnd, lambda: ledger.post_journal_entry(ctx_for(rnd), entry_id, confirm=True), PostingError,
            "needs approval")


@pytest.mark.parametrize("source, words", [("Invoice", "an invoice; change the invoice"),
                                           ("Bill", "a bill; change the bill"),
                                           ("Deferral", "a deferral; change the deferral")])
def test_a_document_draft_is_changed_only_through_its_document(rnd, source, words):
    entry_id = doc(rnd, source, lines(rnd))["entry_id"]
    for context in (ctx_for(rnd), ctx_for(rnd, "System")):
        refused(rnd, lambda: ledger.update_entry(context, entry_id, lines=lines(rnd, 5)), PostingError,
                rf"^This entry was made by {words} instead\.$")
        refused(rnd, lambda: ledger.delete_entry(context, entry_id), PostingError,
                rf"^This entry was made by {words} instead\.$")


@pytest.mark.parametrize("source", ROUNDING_SOURCES)
def test_saving_the_lines_back_as_read_keeps_the_rounding_line(rnd, source):
    reviewer = ctx_for(rnd, ORIGIN_FOR[source])
    entry_id = doc(rnd, source, off_by(rnd, 1), context=reviewer)["entry_id"]
    shown = ledger.get_entry(reviewer, entry_id)["lines"]
    back = [{k: line[k] for k in ledger.LINE_FIELDS if line[k] is not None} for line in shown]
    assert len(back) == 3                                            # the screen sends all three lines back
    ledger.update_entry(reviewer, entry_id, lines=back)
    saved = lines_of(rnd, entry_id)
    assert len(saved) == 3 and [l["is_rounding_adjustment"] for l in saved] == [0, 0, 1]


def test_the_rounding_line_takes_nothing_from_the_other_lines(rnd):
    # R49: no contact, project, cost code or reference, even when the entry's other lines carry them.
    project = rnd.project("PARENT")
    with rnd._company("PARENT") as c:
        division = c.execute("INSERT INTO cost_code (code, name, cost_type_label) VALUES ('03', 'Concrete', "
                             "'Cement') RETURNING cost_code_id").fetchone()[0]
        # RP5: lines post to a leaf code (level 2 or 3), never to the division itself.
        cost_code = c.execute("INSERT INTO cost_code (code, name, cost_type_label, level, parent_id) VALUES "
                              "('03-300', 'Concrete', 'Cement', 2, ?) RETURNING cost_code_id", (division,)).fetchone()[0]
    entry_lines = off_by(rnd, 1)
    for line in entry_lines:
        line.update(contact_id=rnd.plain_contact, project_id=project, cost_code_id=cost_code, external_ref="R-1",
                    memo="Week 12")
    entry_id = doc(rnd, "Import", entry_lines)["entry_id"]
    line = rounding_lines(rnd, entry_id)[0]
    assert (line["memo"], line["contact_id"], line["project_id"], line["cost_code_id"], line["external_ref"]) == (
        "Rounding (1 cent)", None, None, None, None)


@pytest.mark.parametrize("change", ["memo", "contact", "project", "account"])
def test_a_line_that_only_looks_like_the_rounding_line_is_kept(rnd, change):
    # R55: only a line sent back exactly as read is taken as the rounding line. A real 1-cent line that differs in
    # one field stays a person's line; here it balances the entry, so no rounding line is written.
    importer = ctx_for(rnd, "Import")
    entry_id = doc(rnd, "Import", off_by(rnd, 1), context=importer)["entry_id"]
    look_alike = {"account_id": A(rnd, "rounding"), "credit_cents": 1, "memo": "Rounding (1 cent)"}
    if change == "memo":
        look_alike["memo"] = "Bank fee"
    elif change == "contact":
        look_alike["contact_id"] = rnd.plain_contact
    elif change == "project":
        look_alike["project_id"] = rnd.project("PARENT")
    else:                    # a person's line on the new rounding account, not on the stored rounding line's account
        with rnd._company("PARENT") as c:
            new = lh.make_account(c, "8030")
        settings(rnd, rounding_variance_acct_id=new)
        look_alike["account_id"] = new
    ledger.update_entry(importer, entry_id, lines=off_by(rnd, 1) + [look_alike])
    saved = lines_of(rnd, entry_id)
    assert [l["is_rounding_adjustment"] for l in saved] == [0, 0, 0]
    assert saved[-1]["account_id"] == look_alike["account_id"]


def test_an_edited_import_draft_two_cents_off_says_save_again(rnd):
    importer = ctx_for(rnd, "Import")
    entry_id = doc(rnd, "Import", off_by(rnd, 0), context=importer)["entry_id"]
    refused(rnd, lambda: ledger.update_entry(ctx_for(rnd), entry_id, lines=off_by(rnd, 4)), ValidationError,
            r"^The entry dated 2026-03-15 is out of balance by 0\.04; only a 1-cent rounding difference is balanced "
            r"automatically, so nothing was saved\. Correct the amounts and save again\.$")


@pytest.mark.parametrize("source", ["Invoice", "Deferral"])       # not Conversion: it is reviewed first (R55)
def test_a_document_entry_posted_on_save_with_separation_on(rnd, source):
    # R54: create and post are one action of the document's service; R17 (the creator may not post) is for a draft
    # posted later by a person, and a document's separation is its own approval.
    rnd.settings("PARENT", require_separate_approver=1)
    result = doc(rnd, source, off_by(rnd, 0), post=True)
    row = entry_row(rnd, result["entry_id"])
    assert (result["entry_number"], row["entry_number"], row["is_posted"], row["posted_by"]) == (1, 1, 1, rnd.user_id)
    assert verify(rnd)["ok"]
