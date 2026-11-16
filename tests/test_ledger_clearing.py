"""Clearing ids on document entries (R57) and the leaf cost-code rule (RP5), Phase 2.5 step 7.

* A document entry's line may open a clearing group (`ledger.NEW_CLEARING`: the group id is the line's own id)
  or join an existing group on the same account. Manual entries and importers cannot set clearing ids.
* A line posts only to an active leaf cost code: never a level 1 division, never a code with active sub-codes.
"""
import pytest

from modules.services import ledger
from modules.services.errors import PeriodClosedError, PostingError, ValidationError
from modules.services.tx import write_transaction
from tests import ledger_helpers as lh
from tests.authz_world import world  # noqa: F401  (fixture)
from tests.test_ledger_posting import A, ctx_for, draft, env, keyed, lines, verify  # noqa: F401

NEW = ledger.NEW_CLEARING


def document_entry(env, entry_lines, *, source="Invoice", post=True, origin="System"):
    context = ctx_for(env, origin)
    with write_transaction(context.company_db_path, context) as conn:
        kwargs = {"source_rows": [2, 3]} if source in ledger.ROUNDING_SOURCES else {}
        return ledger.create_document_entry(conn, context, source=source, entry_date="2026-03-15",
                                            lines=entry_lines, post=post, **kwargs)["entry_id"]


def lines_of(env, entry_id):
    return env.rows("PARENT", "SELECT * FROM journal_line WHERE entry_id = ? ORDER BY line_id", (entry_id,))


def ar_line(env, amount, *, debit=True, clearing=NEW):
    line = {"account_id": A(env, "ar"), "contact_id": env.customer, "clearing_id": clearing}
    line["debit_cents" if debit else "credit_cents"] = amount
    return line


def sales_line(env, amount, *, debit=False):
    return {"account_id": A(env, "sales"), ("debit_cents" if debit else "credit_cents"): amount}


# --- clearing ids (R57) -------------------------------------------------------------------------------------

def test_a_new_group_takes_the_opening_lines_own_id(env):
    entry_id = document_entry(env, [ar_line(env, 1000), sales_line(env, 1000)])
    opening, other = lines_of(env, entry_id)
    assert opening["clearing_id"] == opening["line_id"]
    assert other["clearing_id"] is None
    assert verify(env)["ok"]


def test_a_line_joins_an_existing_group_on_the_same_account(env):
    first = document_entry(env, [ar_line(env, 1000), sales_line(env, 1000)])
    group = lines_of(env, first)[0]["clearing_id"]
    second = document_entry(env, [{"account_id": A(env, "cash"), "debit_cents": 1000},
                                  ar_line(env, 1000, debit=False, clearing=group)], source="Payment")
    assert lines_of(env, second)[1]["clearing_id"] == group
    total = env.rows("PARENT", "SELECT SUM(debit_cents - credit_cents) AS n FROM journal_line WHERE clearing_id = ?",
                     (group,))[0]["n"]
    assert total == 0


@pytest.mark.parametrize("clearing, match", [(9999, "not an open item posted"),
                                             ("sideways", "a new group or an existing group's number"),
                                             (1.5, "a new group or an existing group's number"),
                                             (True, "a new group or an existing group's number")])
def test_an_unknown_group_or_a_bad_value_is_refused(env, clearing, match):
    with pytest.raises(ValidationError, match=match):
        document_entry(env, [ar_line(env, 1000, clearing=clearing), sales_line(env, 1000)])


def test_a_group_on_another_account_cannot_be_joined(env):
    first = document_entry(env, [ar_line(env, 1000), sales_line(env, 1000)])
    group = lines_of(env, first)[0]["clearing_id"]
    with pytest.raises(ValidationError, match="clearing"):
        document_entry(env, [{"account_id": A(env, "cash"), "debit_cents": 1000, "clearing_id": group},
                             sales_line(env, 1000)])


def test_a_line_that_is_not_an_opening_line_does_not_name_a_group(env):
    """Only an opening line (clearing_id = line_id) defines a group; a member line's id is not a group id."""
    first = document_entry(env, [ar_line(env, 1000), sales_line(env, 1000)])
    group = lines_of(env, first)[0]["clearing_id"]
    second = document_entry(env, [{"account_id": A(env, "cash"), "debit_cents": 400},
                                  ar_line(env, 400, debit=False, clearing=group)], source="Payment")
    member = lines_of(env, second)[1]["line_id"]
    with pytest.raises(ValidationError, match="clearing"):
        document_entry(env, [{"account_id": A(env, "cash"), "debit_cents": 100},
                             ar_line(env, 100, debit=False, clearing=member)], source="Payment")


def test_a_draft_document_entry_opens_its_group_too(env):
    entry_id = document_entry(env, [ar_line(env, 1000), sales_line(env, 1000)], post=False)
    opening = lines_of(env, entry_id)[0]
    assert opening["clearing_id"] == opening["line_id"]


@pytest.mark.parametrize("source", ["Import", "Payroll", "Conversion"])
def test_importers_cannot_set_clearing_ids(env, source):
    with pytest.raises(ValidationError, match="clearing"):
        document_entry(env, [ar_line(env, 1000), sales_line(env, 1000)], source=source, post=False,
                       origin="Import")


def test_a_manual_entry_cannot_set_a_clearing_id(env):
    with pytest.raises(ValidationError, match="clearing_id"):
        draft(env, entry_lines=[ar_line(env, 1000), sales_line(env, 1000)])


# --- leaf cost codes (RP5) ----------------------------------------------------------------------------------

def cost_code(env, code, level=1, parent=None, active=1):
    with env._company("PARENT") as c:
        return c.execute("INSERT INTO cost_code (code, name, cost_type_label, level, parent_id, is_active) "
                         "VALUES (?, ?, 'Labor', ?, ?, ?) RETURNING cost_code_id",
                         (code, f"Code {code}", level, parent, active)).fetchone()[0]


def coded(env, cost_code_id):
    return lines(env, debit_extra={"cost_code_id": cost_code_id})


@pytest.fixture
def codes(env):
    division = cost_code(env, "03")
    code = cost_code(env, "03-300", 2, division)
    leaf_code = cost_code(env, "03-400", 2, division)
    sub = cost_code(env, "03-300-10", 3, code)
    return {"division": division, "code_with_subs": code, "leaf_code": leaf_code, "sub": sub}


@pytest.mark.parametrize("name", ["leaf_code", "sub"])
def test_a_leaf_code_or_sub_code_takes_postings(env, codes, name):
    entry_id = draft(env, entry_lines=coded(env, codes[name]))
    ledger.post_journal_entry(ctx_for(env), entry_id, confirm=True)


def test_a_division_is_refused(env, codes):
    with pytest.raises(ValidationError, match="not the division 03"):
        draft(env, entry_lines=coded(env, codes["division"]))


def test_a_code_with_active_sub_codes_is_refused(env, codes):
    with pytest.raises(ValidationError, match="one of its sub-codes"):
        draft(env, entry_lines=coded(env, codes["code_with_subs"]))


def test_a_code_whose_sub_codes_are_all_inactive_is_a_leaf(env, codes):
    with env._company("PARENT") as c:
        c.execute("UPDATE cost_code SET is_active = 0 WHERE cost_code_id = ?", (codes["sub"],))
    draft(env, entry_lines=coded(env, codes["code_with_subs"]))


def test_an_inactive_code_is_refused(env, codes):
    with env._company("PARENT") as c:
        c.execute("UPDATE cost_code SET is_active = 0 WHERE cost_code_id = ?", (codes["leaf_code"],))
    with pytest.raises(ValidationError, match="inactive"):
        draft(env, entry_lines=coded(env, codes["leaf_code"]))


def test_posting_checks_the_cost_code_again(env, codes):
    """A code that stops being a leaf (or goes inactive) after the draft was saved blocks the post."""
    entry_id = draft(env, entry_lines=coded(env, codes["leaf_code"]))
    cost_code(env, "03-400-10", 3, codes["leaf_code"])
    with pytest.raises(PostingError, match="sub-codes"):
        ledger.post_journal_entry(ctx_for(env), entry_id, confirm=True)
    other = draft(env, entry_lines=coded(env, codes["sub"]))
    with env._company("PARENT") as c:
        c.execute("UPDATE cost_code SET is_active = 0 WHERE cost_code_id = ?", (codes["sub"],))
    with pytest.raises(PostingError, match="inactive"):
        ledger.post_journal_entry(ctx_for(env), other, confirm=True)


# --- R60: only accounts that keep open items; a group is joined only after it posted, for the same contact ---

def test_an_account_that_keeps_no_open_items_cannot_open_a_group(env):
    with pytest.raises(ValidationError, match="does not keep open items"):
        document_entry(env, [{"account_id": A(env, "sales"), "credit_cents": 1000, "clearing_id": NEW},
                             {"account_id": A(env, "cash"), "debit_cents": 1000}])


def test_a_group_whose_opening_entry_is_still_a_draft_cannot_be_joined(env):
    draft_entry = document_entry(env, [ar_line(env, 1000), sales_line(env, 1000)], post=False)
    group = lines_of(env, draft_entry)[0]["clearing_id"]
    with pytest.raises(ValidationError, match="not an open item posted"):
        document_entry(env, [{"account_id": A(env, "cash"), "debit_cents": 1000},
                             ar_line(env, 1000, debit=False, clearing=group)], source="Payment")


def test_another_customers_group_cannot_be_joined(env):
    first = document_entry(env, [ar_line(env, 1000), sales_line(env, 1000)])
    group = lines_of(env, first)[0]["clearing_id"]
    other = dict(ar_line(env, 1000, debit=False, clearing=group), contact_id=env.plain_contact)
    with pytest.raises(ValidationError, match="another customer or vendor"):
        document_entry(env, [{"account_id": A(env, "cash"), "debit_cents": 1000}, other], source="Payment")


@pytest.mark.parametrize("control_type, tracked", [("AR", 1), ("AP", 1), ("GRNI", 0), (None, 0)])
def test_ar_and_ap_accounts_keep_open_items_from_the_start(env, control_type, tracked):
    from modules.services import accounts
    env.grant_permission("PARENT", "POSTER", "account.manage")
    type_name = "Liability" if control_type in ("AP", "GRNI") else "Asset"
    account_id = accounts.create_account(ctx_for(env), f"19{tracked}{len(control_type or '')}", "Control",
                                         type_name, control_type=control_type)
    assert env.rows("PARENT", "SELECT track_clearing_id FROM account WHERE account_id = ?",
                    (account_id,))[0]["track_clearing_id"] == tracked
    assert accounts.tracks_open_items(control_type) == tracked


# --- step 7 mutation check -----------------------------------------------------------------------------------

def test_a_group_on_another_tracked_account_cannot_be_joined(env):
    with env._company("PARENT") as c:
        env.accts["ar2"] = lh.make_account(c, "1210", control_type="AR", track_clearing_id=1)
    first = document_entry(env, [ar_line(env, 1000), sales_line(env, 1000)])
    group = lines_of(env, first)[0]["clearing_id"]
    other = dict(ar_line(env, 1000, debit=False, clearing=group), account_id=A(env, "ar2"))
    with pytest.raises(ValidationError, match="not an open item posted on this account"):
        document_entry(env, [{"account_id": A(env, "cash"), "debit_cents": 1000}, other], source="Payment")


def void_directly(env, entry_id, *, entry_date="2026-03-20", note="released"):
    context = ctx_for(env, "System")
    with write_transaction(context.company_db_path, context) as conn:
        return ledger.void_document_entry(conn, context, entry_id, entry_date=entry_date, note=note)


def posted_document(env, entry_date="2026-03-15"):
    context = ctx_for(env, "System")
    with write_transaction(context.company_db_path, context) as conn:
        return ledger.create_document_entry(conn, context, source="Payment", entry_date=entry_date,
                                            lines=lines(env), post=True)["entry_id"]


@pytest.mark.parametrize("note", ["", "   ", None])
def test_void_document_entry_needs_a_note(env, note):
    with pytest.raises(ValidationError, match="Say why in the note"):
        void_directly(env, posted_document(env), note=note)


@pytest.mark.parametrize("day", ["2026-3-20", "20/03/2026", None])
def test_void_document_entry_needs_an_iso_date(env, day):
    with pytest.raises(ValidationError, match="YYYY-MM-DD"):
        void_directly(env, posted_document(env), entry_date=day)


def test_void_document_entry_refuses_a_draft(env):
    context = ctx_for(env, "System")
    with write_transaction(context.company_db_path, context) as conn:
        entry_id = ledger.create_document_entry(conn, context, source="Payment", entry_date="2026-03-15",
                                                lines=lines(env))["entry_id"]
    before = env.rows("PARENT", "SELECT COUNT(*) AS n FROM journal_entry")[0]["n"]
    with pytest.raises(ValidationError, match="Only a posted entry"):
        void_directly(env, entry_id)
    assert env.rows("PARENT", "SELECT COUNT(*) AS n FROM journal_entry")[0]["n"] == before


def test_void_document_entry_refuses_an_entry_already_corrected(env):
    entry_id = posted_document(env)
    with env._company("PARENT") as c:
        number = c.execute("SELECT entry_number FROM journal_entry WHERE entry_id = ?", (entry_id,)).fetchone()[0]
        c.execute("INSERT INTO journal_entry (entry_date, period_id, reverses_entry_id, reversal_reason, reversal_note, "
                  "created_by) VALUES ('2026-03-16', ?, ?, 'Correction', 'wrong', 1)",
                  (lh.ensure_period(c, "2026-03-16"), entry_id))
    with pytest.raises(PostingError, match="already been voided or corrected"):
        void_directly(env, entry_id)
    assert number


def test_void_document_entry_takes_the_period_of_its_own_date(env):
    entry_id = posted_document(env, "2026-03-15")
    reversal = void_directly(env, entry_id, entry_date="2026-04-02")
    period = env.rows("PARENT", "SELECT p.start_date FROM journal_entry AS e JOIN fiscal_period AS p "
                                "ON p.period_id = e.period_id WHERE e.entry_id = ?", (reversal,))[0]["start_date"]
    assert period == "2026-04-01"
    other = posted_document(env, "2026-03-15")
    with env._company("PARENT") as c:
        may = c.execute("SELECT period_id FROM fiscal_period WHERE start_date = '2026-05-01' "
                        "AND is_adjustment_period = 0").fetchone()[0]
        lh.set_period_closed(c, may, True)
    with pytest.raises(PeriodClosedError):
        void_directly(env, other, entry_date="2026-05-04")


def test_chart_template_ar_and_ap_accounts_keep_open_items(fresh_company):
    """R60 through the chart templates (accounts.seed_chart): AR and AP control accounts are marked."""
    import modules.database as database
    from modules.services import accounts, chart_templates
    rows = chart_templates.load_template("construction")
    conn = database.get_connection(fresh_company)
    try:
        accounts.seed_chart(conn, rows)
        marked = {(r["control_type"], r["track_clearing_id"]) for r in conn.execute(
            "SELECT control_type, track_clearing_id FROM account")}
    finally:
        conn.close()
    assert ("AR", 1) in marked and ("AP", 1) in marked
    assert all(tracked == (1 if control in ("AR", "AP") else 0) for control, tracked in marked)
