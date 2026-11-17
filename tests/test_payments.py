"""Payment and credit allocation, Phase 2.5 step 7 (decisions R7, B2, B4, B6, RP11, R56-R58).

* `payments.allocate` links a payment or credit memo to an invoice or bill: never more than either has open,
  same contact, the right side, an open applied date, the existing receive/pay permissions (R56). Allocating a
  posted source posts a zero-net application entry between the two clearing groups (R58).
* `payments.release_allocations` (inside a void) undoes them once the source's entry is voided (RP11).
* `payments.open_item` and `payments.clearing_lines` are the clearing helpers the Phase 4 posting services use
  (R57).

Moved here from tests/test_service_rules_pending.py: "a payment cannot be over-allocated" and "an allocation
targets exactly one document" (the strict xfails, now real tests).
"""
import pytest

from modules.services import ledger, payments, periods
from modules.services.errors import PeriodClosedError, PermissionDeniedError, PostingError, ValidationError
from modules.services.tx import write_transaction
from tests import ledger_helpers as lh
from tests.authz_world import world  # noqa: F401  (fixture)
from tests.test_ledger_posting import A, ctx_for, env, keyed, verify  # noqa: F401  (fixtures and helpers)

NEW = ledger.NEW_CLEARING


@pytest.fixture
def pay(env):
    env.grant_permission("PARENT", "POSTER", "payment.receive")
    env.grant_permission("PARENT", "POSTER", "payment.make")
    with env._company("PARENT") as c:
        env.accts["expense"] = lh.make_account(c, "5010")
    return env


def ctx(env, origin="Human"):
    return ctx_for(env, origin)


def post_entry(env, source, entry_lines, entry_date="2026-03-02"):
    system = ctx_for(env, "System")
    with write_transaction(system.company_db_path, system) as conn:
        return ledger.create_document_entry(conn, system, source=source, entry_date=entry_date, lines=entry_lines,
                                            post=True)["entry_id"]


def side_line(env, account, amount, debit, contact, clearing=NEW):
    line = {"account_id": A(env, account), "contact_id": contact, "clearing_id": clearing}
    line["debit_cents" if debit else "credit_cents"] = amount
    return line


def plain_line(env, account, amount, debit):
    return {"account_id": A(env, account), ("debit_cents" if debit else "credit_cents"): amount}


def document(env, kind, amount=1000, *, contact=None, posted=True, entry_date="2026-03-02", retainage=0,
             status="Sent"):
    """An invoice, bill, credit memo or vendor credit; posted ones open their AR/AP group (R57)."""
    itype, side = {"invoice": ("Invoice", "Sales"), "bill": ("Bill", "Purchase"),
                   "credit_memo": ("Credit Memo", "Sales"), "vendor_credit": ("Credit Memo", "Purchase")}[kind]
    contact = contact or (env.customer if side == "Sales" else env.vendor)
    entry_id = None
    if posted:
        control, other = ("ar", "sales") if side == "Sales" else ("ap", "expense")
        control_debit = kind in ("invoice", "vendor_credit")
        entry_id = post_entry(env, "Invoice" if side == "Sales" else "Bill",
                              [side_line(env, control, amount, control_debit, contact),
                               plain_line(env, other, amount, not control_debit)], entry_date)
    with env._company("PARENT") as c:
        invoice_id = lh.make_invoice(c, itype=itype, ledger_side=side, contact_id=contact, lines=((1, amount),))
        if retainage:
            c.execute("UPDATE invoice SET retainage_cents = ? WHERE invoice_id = ?", (retainage, invoice_id))
        if posted:
            lh.send_invoice(c, invoice_id, status=status, entry_id=entry_id)
        return invoice_id


def payment(env, direction="Received", amount=1000, *, contact=None, posted=True, date="2026-03-05"):
    """A payment; a posted one carries its whole amount as one unapplied remainder line (a new group)."""
    contact = contact or (env.customer if direction == "Received" else env.vendor)
    entry_id = None
    if posted:
        if direction == "Received":
            entry_lines = [plain_line(env, "cash", amount, True), side_line(env, "ar", amount, False, contact)]
        else:
            entry_lines = [side_line(env, "ap", amount, True, contact), plain_line(env, "cash", amount, False)]
        entry_id = post_entry(env, "Payment", entry_lines, date)
    with env._company("PARENT") as c:
        return c.execute("INSERT INTO payment (direction, contact_id, payment_date, amount_cents, entry_id) "
                         "VALUES (?, ?, ?, ?, ?) RETURNING payment_id",
                         (direction, contact, date, amount, entry_id)).fetchone()[0]


def allocate(env, source, target, amount, applied_date="2026-03-06", context=None):
    return payments.allocate(context or ctx(env), source=source, target=target, amount_cents=amount,
                             applied_date=applied_date)


def refused(call, match, error=ValidationError):
    with pytest.raises(error, match=match):
        call()


def group(env, account, clearing_id):
    return env.rows("PARENT", "SELECT COALESCE(SUM(debit_cents - credit_cents), 0) AS n FROM journal_line "
                              "WHERE account_id = ? AND clearing_id = ?", (A(env, account), clearing_id))[0]["n"]


def entry_of(env, table, key, record_id):
    return env.rows("PARENT", f"SELECT entry_id FROM {table} WHERE {key} = ?", (record_id,))[0]["entry_id"]


def open_group(env, entry_id, side="Sales"):
    with env._company("PARENT") as c:
        return payments.open_item(c, entry_id, side)["clearing_id"]


def invoice_status(env, invoice_id):
    return env.rows("PARENT", "SELECT status FROM invoice WHERE invoice_id = ?", (invoice_id,))[0]["status"]


def allocations(env):
    return env.rows("PARENT", "SELECT * FROM payment_allocation ORDER BY allocation_id")


def void_document_entry(env, entry_id, day="2026-03-20"):
    """Void a document's entry the way its void service will (Phase 4): the ledger's own Void reversal, which mirrors
    every line, clearing ids included (MIRRORED_LINE_FIELDS), sealed under the company's key and code."""
    context = ctx(env)
    with write_transaction(context.company_db_path, context) as conn:
        target = conn.execute("SELECT * FROM journal_entry WHERE entry_id = ?", (entry_id,)).fetchone()
        reversal = ledger._insert_reversal(conn, context, target, target["entry_number"], "Void", entry_date=day,
                                           period_id=periods.resolve_entry_period(conn, day), note="test void",
                                           origin="Human")
        key_id, key = ledger._active_key(conn, context)
        ledger._seal_and_post(conn, context, reversal, ledger._company_code(context), key_id, key)


def release(env, source, reason="Payment voided", day="2026-03-20"):
    system = ctx_for(env, "System")
    with write_transaction(system.company_db_path, system) as conn:
        return payments.release_allocations(conn, system, source=source, reason=reason, entry_date=day)


# --- the moved xfails --------------------------------------------------------------------------------------

def test_a_payment_cannot_be_over_allocated(pay):
    invoice = document(pay, "invoice", 1000)
    first = payment(pay, amount=600, posted=False)
    refused(lambda: allocate(pay, ("payment", first), ("invoice", invoice), 700), r"6\.00")
    allocate(pay, ("payment", first), ("invoice", invoice), 600)
    second = payment(pay, amount=600, posted=False)
    refused(lambda: allocate(pay, ("payment", second), ("invoice", invoice), 500), r"4\.00")   # only 4.00 open
    allocate(pay, ("payment", second), ("invoice", invoice), 400)
    assert invoice_status(pay, invoice) == "Paid"


@pytest.mark.parametrize("target", [None, ("deferral", 1), ("bill", 1), ("invoice", None), "invoice"])
def test_an_allocation_targets_exactly_one_document(pay, target):
    source = payment(pay, posted=False)
    refused(lambda: allocate(pay, ("payment", source), target, 100), "Choose the invoice or bill")


@pytest.mark.parametrize("source", [None, ("cheque", 1), ("payment", None), "payment"])
def test_an_allocation_names_exactly_one_source(pay, source):
    invoice = document(pay, "invoice")
    refused(lambda: allocate(pay, source, ("invoice", invoice), 100), "Choose the payment or credit memo")


# --- amounts, dates and documents ----------------------------------------------------------------------------

@pytest.mark.parametrize("amount", [0, -5, 10.5, "100", True, None])
def test_the_amount_is_positive_whole_cents(pay, amount):
    invoice, source = document(pay, "invoice"), payment(pay, posted=False)
    refused(lambda: allocate(pay, ("payment", source), ("invoice", invoice), amount), "amount")


def test_retainage_and_live_allocations_reduce_the_open_amount(pay):
    invoice = document(pay, "invoice", 1000, retainage=100)
    source = payment(pay, amount=2000, posted=False)
    refused(lambda: allocate(pay, ("payment", source), ("invoice", invoice), 901), r"9\.00")
    allocate(pay, ("payment", source), ("invoice", invoice), 900)
    assert invoice_status(pay, invoice) == "Paid"


def test_a_credit_memo_applies_up_to_its_total(pay):
    invoice = document(pay, "invoice", 1000)
    memo = document(pay, "credit_memo", 300, posted=False)
    refused(lambda: allocate(pay, ("credit_memo", memo), ("invoice", invoice), 301), r"3\.00")
    allocate(pay, ("credit_memo", memo), ("invoice", invoice), 300)


def test_the_contact_must_match(pay):
    other = pay.rows("PARENT", "SELECT contact_id FROM contact WHERE name = 'Neighbour'")[0]["contact_id"]
    invoice = document(pay, "invoice")
    source = payment(pay, contact=other, posted=False)
    refused(lambda: allocate(pay, ("payment", source), ("invoice", invoice), 100), "same customer or vendor")


@pytest.mark.parametrize("source_kind, target_kind", [
    ("Made", "invoice"), ("Received", "bill"), ("vendor_credit", "invoice"), ("credit_memo", "bill"),
])
def test_each_side_pairs_with_its_own_documents(pay, source_kind, target_kind):
    target = document(pay, target_kind)
    if source_kind in ("Made", "Received"):
        contact = pay.customer if target_kind == "invoice" else pay.vendor
        source = ("payment", payment(pay, source_kind, contact=contact, posted=False))
    else:
        contact = pay.customer if target_kind == "invoice" else pay.vendor
        source = ("credit_memo", document(pay, source_kind, contact=contact, posted=False))
    target_ref = ("invoice", target)
    refused(lambda: allocate(pay, source, target_ref, 100), "applies to")
    number = pay.rows("PARENT", "SELECT invoice_number FROM invoice WHERE invoice_id = ?", (target,))[0]["invoice_number"]
    with pytest.raises(ValidationError) as wrong_side:
        allocate(pay, source, target_ref, 100)
    assert number not in str(wrong_side.value)      # the other side's document is not named (secrets audit)


def test_a_draft_void_or_paid_target_is_refused(pay):
    draft = document(pay, "invoice", posted=False)
    source = payment(pay, amount=5000, posted=False)
    refused(lambda: allocate(pay, ("payment", source), ("invoice", draft), 100), "not been sent")
    paid = document(pay, "invoice", 500)
    allocate(pay, ("payment", source), ("invoice", paid), 500)
    refused(lambda: allocate(pay, ("payment", source), ("invoice", paid), 1), "already paid")


def test_a_target_without_an_open_item_is_refused(pay):
    """An invoice posted before clearing (no AR line opening a group) cannot be matched (R57)."""
    entry_id = post_entry(pay, "Invoice", [plain_line(pay, "ar", 1000, True), plain_line(pay, "sales", 1000, False)])
    with pay._company("PARENT") as c:
        invoice = lh.make_invoice(c, contact_id=pay.customer, status="Sent", entry_id=entry_id)
    source = payment(pay, posted=False)
    refused(lambda: allocate(pay, ("payment", source), ("invoice", invoice), 100), "no open receivable")


def test_a_voided_source_is_refused(pay):
    invoice = document(pay, "invoice")
    source = payment(pay)
    void_document_entry(pay, entry_of(pay, "payment", "payment_id", source))
    refused(lambda: allocate(pay, ("payment", source), ("invoice", invoice), 100), "voided")


@pytest.mark.parametrize("applied, match", [("21/03/2026", "date"), ("2026-03-01", "before"),
                                            ("2026-03-04", "before")])
def test_the_applied_date_is_a_date_after_both_documents(pay, applied, match):
    invoice = document(pay, "invoice", entry_date="2026-03-02")
    source = payment(pay, posted=False, date="2026-03-05")
    refused(lambda: allocate(pay, ("payment", source), ("invoice", invoice), 100, applied_date=applied), match)


def test_the_applied_date_must_be_in_an_open_period(pay):
    invoice = document(pay, "invoice")
    source = payment(pay, posted=False)
    with pay._company("PARENT") as c:
        period = lh.ensure_period(c, "2026-04-10")
        lh.set_period_closed(c, period, True)
    refused(lambda: allocate(pay, ("payment", source), ("invoice", invoice), 100, applied_date="2026-04-10"),
            "closed", PeriodClosedError)


@pytest.mark.parametrize("area, kind", [("Sales", "invoice"), ("Purchases", "bill")])
def test_a_locked_area_refuses_the_applied_date(pay, area, kind):
    target = document(pay, kind)
    source = payment(pay, "Received" if kind == "invoice" else "Made", posted=False)
    with pay._company("PARENT") as c:
        period = lh.ensure_period(c, "2026-03-06")
        c.execute("INSERT INTO fiscal_period_lock (period_id, area, locked_by, reason) VALUES (?, ?, 1, 'done')",
                  (period, area))
    refused(lambda: allocate(pay, ("payment", source), ("invoice", target), 100), "locked")


# --- permissions (R56) -------------------------------------------------------------------------------------

@pytest.mark.parametrize("kind, permission", [("invoice", "payment.receive"), ("bill", "payment.make")])
def test_each_side_needs_its_own_permission(pay, kind, permission):
    target = document(pay, kind)
    source = payment(pay, "Received" if kind == "invoice" else "Made", posted=False)
    pay.remove_permission("PARENT", "POSTER", permission)
    with pytest.raises(PermissionDeniedError):
        allocate(pay, ("payment", source), ("invoice", target), 100)
    assert allocations(pay) == []


def test_an_agent_cannot_allocate(pay):
    invoice, source = document(pay, "invoice"), payment(pay, posted=False)
    with pytest.raises(PermissionDeniedError):
        allocate(pay, ("payment", source), ("invoice", invoice), 100, context=ctx(pay, "Agent"))


# --- draft source: the row only; posted source: the application entry (R57, R58) ---------------------------

def test_a_draft_source_writes_the_allocation_only(pay):
    invoice = document(pay, "invoice", 1000)
    source = payment(pay, posted=False)
    result = allocate(pay, ("payment", source), ("invoice", invoice), 400)
    assert result["application_entry_id"] is None and result["target_status"] == "Sent"
    row = allocations(pay)[0]
    assert (row["payment_id"], row["invoice_id"], row["amount_applied_cents"], row["applied_date"]) == \
        (source, invoice, 400, "2026-03-06")
    assert row["created_by"] == pay.user_id and row["created_at"] and row["application_entry_id"] is None


def test_a_posted_payment_posts_an_application_entry_that_settles_both_groups(pay):
    invoice = document(pay, "invoice", 1000)
    source = payment(pay, amount=1000)
    invoice_group = open_group(pay, entry_of(pay, "invoice", "invoice_id", invoice))
    payment_group = open_group(pay, entry_of(pay, "payment", "payment_id", source))
    assert (group(pay, "ar", invoice_group), group(pay, "ar", payment_group)) == (1000, -1000)
    result = allocate(pay, ("payment", source), ("invoice", invoice), 1000)
    assert result["target_status"] == "Paid"
    entry = pay.rows("PARENT", "SELECT * FROM journal_entry WHERE entry_id = ?", (result["application_entry_id"],))[0]
    assert (entry["is_posted"], entry["source"], entry["origin"], entry["entry_date"]) == \
        (1, "Payment", "System", "2026-03-06")
    application = pay.rows("PARENT", "SELECT * FROM journal_line WHERE entry_id = ? ORDER BY line_id",
                           (result["application_entry_id"],))
    assert {(l["account_id"], l["debit_cents"], l["credit_cents"], l["clearing_id"], l["contact_id"])
            for l in application} == {(A(pay, "ar"), 1000, 0, payment_group, pay.customer),
                                      (A(pay, "ar"), 0, 1000, invoice_group, pay.customer)}
    assert (group(pay, "ar", invoice_group), group(pay, "ar", payment_group)) == (0, 0)
    assert allocations(pay)[0]["application_entry_id"] == result["application_entry_id"]
    assert verify(pay)["ok"]


def test_a_vendor_credit_applied_to_a_bill_moves_the_ap_groups(pay):
    bill = document(pay, "bill", 800)
    credit = document(pay, "vendor_credit", 300)
    bill_group = open_group(pay, entry_of(pay, "invoice", "invoice_id", bill), "Purchase")
    credit_group = open_group(pay, entry_of(pay, "invoice", "invoice_id", credit), "Purchase")
    allocate(pay, ("credit_memo", credit), ("invoice", bill), 300)
    assert (group(pay, "ap", bill_group), group(pay, "ap", credit_group)) == (-500, 0)
    assert invoice_status(pay, bill) == "Sent"


def test_a_posted_source_cannot_apply_more_than_its_open_remainder(pay):
    first, second = document(pay, "invoice", 700), document(pay, "invoice", 700)
    source = payment(pay, amount=1000)
    allocate(pay, ("payment", source), ("invoice", first), 700)
    refused(lambda: allocate(pay, ("payment", source), ("invoice", second), 301), r"3\.00")
    allocate(pay, ("payment", source), ("invoice", second), 300)


def test_payment_approval_never_blocks_an_application_or_its_release(pay):
    """R59: the application entry and its release are system consequences of the allocation, like the R47
    automatic reversal, so the Payment approval control (OFF by default) gates neither; a void is never blocked."""
    invoice, source = document(pay, "invoice", 1000), payment(pay, amount=1000)
    with pay._company("PARENT") as c:
        c.execute("UPDATE document_approval_setting SET requires_approval = 1 WHERE document_type = 'Payment'")
    result = allocate(pay, ("payment", source), ("invoice", invoice), 1000)
    assert result["application_entry_id"] and result["target_status"] == "Paid"
    void_document_entry(pay, entry_of(pay, "payment", "payment_id", source))
    released = release(pay, ("payment", source))
    assert len(released["entries"]) == 1 and invoice_status(pay, invoice) == "Sent"


# --- release (RP11, R58) -----------------------------------------------------------------------------------

def test_release_before_the_void_is_refused(pay):
    invoice, source = document(pay, "invoice"), payment(pay)
    allocate(pay, ("payment", source), ("invoice", invoice), 1000)
    refused(lambda: release(pay, ("payment", source)), "Void the payment")
    assert allocations(pay)[0]["released_at"] is None


def test_voiding_and_releasing_a_payment_reopens_the_invoice(pay):
    """The worked example: application, then the payment's void, then the release (R58)."""
    invoice, source = document(pay, "invoice", 1000), payment(pay, amount=1000)
    invoice_group = open_group(pay, entry_of(pay, "invoice", "invoice_id", invoice))
    payment_group = open_group(pay, entry_of(pay, "payment", "payment_id", source))
    allocate(pay, ("payment", source), ("invoice", invoice), 1000)
    void_document_entry(pay, entry_of(pay, "payment", "payment_id", source))
    assert (group(pay, "ar", invoice_group), group(pay, "ar", payment_group)) == (0, 1000)
    result = release(pay, ("payment", source))
    assert (group(pay, "ar", invoice_group), group(pay, "ar", payment_group)) == (1000, 0)
    assert invoice_status(pay, invoice) == "Sent"
    row = allocations(pay)[0]
    assert (row["released_by"], row["release_reason"]) == (pay.user_id, "Payment voided") and row["released_at"]
    assert result["released"] == [row["allocation_id"]] and len(result["entries"]) == 1
    assert verify(pay)["ok"]


def test_releasing_a_draft_source_allocation_posts_no_entry(pay):
    invoice = document(pay, "invoice", 1000)
    source = payment(pay, posted=False)
    allocate(pay, ("payment", source), ("invoice", invoice), 1000)
    assert invoice_status(pay, invoice) == "Paid"
    result = release(pay, ("payment", source))
    assert result["entries"] == [] and invoice_status(pay, invoice) == "Sent"


def test_release_skips_allocations_already_released(pay):
    invoice, source = document(pay, "invoice"), payment(pay, posted=False)
    allocate(pay, ("payment", source), ("invoice", invoice), 100)
    release(pay, ("payment", source))
    assert release(pay, ("payment", source))["released"] == []


def test_a_released_allocation_no_longer_counts_against_the_invoice(pay):
    invoice = document(pay, "invoice", 1000)
    first = payment(pay, posted=False)
    allocate(pay, ("payment", first), ("invoice", invoice), 1000)
    release(pay, ("payment", first))
    second = payment(pay, posted=False)
    allocate(pay, ("payment", second), ("invoice", invoice), 1000)


def test_release_needs_a_reason(pay):
    invoice, source = document(pay, "invoice"), payment(pay, posted=False)
    allocate(pay, ("payment", source), ("invoice", invoice), 100)
    refused(lambda: release(pay, ("payment", source), reason="  "), "reason")


# --- clearing helpers (R57) -----------------------------------------------------------------------------------

def test_open_item_finds_the_line_that_opened_the_group(pay):
    invoice = document(pay, "invoice", 1000)
    entry_id = entry_of(pay, "invoice", "invoice_id", invoice)
    with pay._company("PARENT") as c:
        item = payments.open_item(c, entry_id, "Sales")
        assert item["clearing_id"] == item["line_id"] and item["account_id"] == A(pay, "ar")
        assert payments.open_item(c, entry_id, "Purchase") is None


def test_clearing_lines_split_a_payment_per_document_plus_the_remainder(pay):
    first, second = document(pay, "invoice", 300), document(pay, "invoice", 500)
    groups = [open_group(pay, entry_of(pay, "invoice", "invoice_id", d)) for d in (first, second)]
    with pay._company("PARENT") as c:
        split = payments.clearing_lines(c, side="Sales", account_id=A(pay, "ar"), contact_id=pay.customer,
                                        amount_cents=1000, allocations=[(first, 300), (second, 500)])
    assert split == [
        {"account_id": A(pay, "ar"), "credit_cents": 300, "contact_id": pay.customer, "clearing_id": groups[0]},
        {"account_id": A(pay, "ar"), "credit_cents": 500, "contact_id": pay.customer, "clearing_id": groups[1]},
        {"account_id": A(pay, "ar"), "credit_cents": 200, "contact_id": pay.customer, "clearing_id": NEW},
    ]
    entry_id = post_entry(pay, "Payment", [plain_line(pay, "cash", 1000, True), *split])
    assert [group(pay, "ar", g) for g in groups] == [0, 0]
    remainder = open_group(pay, entry_id)
    assert group(pay, "ar", remainder) == -200


def test_clearing_lines_for_a_bill_payment_are_debits_and_a_full_payment_has_no_remainder(pay):
    bill = document(pay, "bill", 400)
    with pay._company("PARENT") as c:
        split = payments.clearing_lines(c, side="Purchase", account_id=A(pay, "ap"), contact_id=pay.vendor,
                                        amount_cents=400, allocations=[(bill, 400)])
    assert [(l["debit_cents"], l["clearing_id"] != NEW) for l in split] == [(400, True)]


def test_clearing_lines_refuse_more_than_the_payment(pay):
    invoice = document(pay, "invoice", 1000)
    with pay._company("PARENT") as c:
        with pytest.raises(ValidationError, match="more than the payment"):
            payments.clearing_lines(c, side="Sales", account_id=A(pay, "ar"), contact_id=pay.customer,
                                    amount_cents=500, allocations=[(invoice, 600)])


# --- step 7 review: authorize before disclosing anything (rule 10), and the rules each test pins ------------

def state(env):
    """Everything an allocation or a release can write, to prove a refused call wrote nothing."""
    return {t: env.rows("PARENT", f"SELECT * FROM {t} ORDER BY 1") for t in
            ("journal_entry", "journal_line", "payment_allocation", "invoice", "invoice_series",
             "entry_number_sequence")}


@pytest.mark.parametrize("origin", ["Human", "Agent"])
def test_a_refused_person_or_agent_learns_nothing_about_the_documents(pay, origin):
    """The permission is checked before the amounts: an over-allocation by someone without the right is a denial,
    not "Only 10.00 is open on invoice ...", and nothing is written."""
    invoice, source = document(pay, "invoice", 1000), payment(pay, amount=1000)
    if origin == "Human":
        pay.remove_permission("PARENT", "POSTER", "payment.receive")
    before = state(pay)
    with pytest.raises(PermissionDeniedError) as denied:
        allocate(pay, ("payment", source), ("invoice", invoice), 999999, context=ctx(pay, origin))
    assert "open" not in str(denied.value) and "SI-" not in str(denied.value)
    assert state(pay) == before


def test_the_applied_date_cannot_be_before_the_invoice(pay):
    invoice = document(pay, "invoice")                         # issued 2026-03-01 (tests/ledger_helpers.py)
    source = payment(pay, posted=False, date="2026-02-20")
    refused(lambda: allocate(pay, ("payment", source), ("invoice", invoice), 100, applied_date="2026-02-25"),
            "before the date of invoice")
    allocate(pay, ("payment", source), ("invoice", invoice), 100, applied_date="2026-03-01")


def test_a_void_target_is_refused_by_its_voided_entry_or_by_status(pay):
    target = document(pay, "invoice")
    void_document_entry(pay, entry_of(pay, "invoice", "invoice_id", target))
    source = payment(pay, amount=5000, posted=False)
    refused(lambda: allocate(pay, ("payment", source), ("invoice", target), 100), "is void")
    with pay._company("PARENT") as c:
        c.execute("UPDATE invoice SET status = 'Void' WHERE invoice_id = ?", (target,))
    refused(lambda: allocate(pay, ("payment", source), ("invoice", target), 100), "is void")


def test_a_voided_credit_memo_cannot_be_applied(pay):
    invoice = document(pay, "invoice")
    memo = document(pay, "credit_memo", 300)
    void_document_entry(pay, entry_of(pay, "invoice", "invoice_id", memo))
    refused(lambda: allocate(pay, ("credit_memo", memo), ("invoice", invoice), 100), "voided")
    with pay._company("PARENT") as c:
        c.execute("UPDATE invoice SET status = 'Void' WHERE invoice_id = ?", (memo,))
    refused(lambda: allocate(pay, ("credit_memo", memo), ("invoice", invoice), 100), "voided")


def test_a_posted_source_without_an_unapplied_line_is_refused(pay):
    invoice = document(pay, "invoice")
    entry_id = post_entry(pay, "Payment", [plain_line(pay, "cash", 1000, True), plain_line(pay, "ar", 1000, False)],
                          "2026-03-05")
    with pay._company("PARENT") as c:
        source = c.execute("INSERT INTO payment (direction, contact_id, payment_date, amount_cents, entry_id) VALUES "
                           "('Received', ?, '2026-03-05', 1000, ?) RETURNING payment_id",
                           (pay.customer, entry_id)).fetchone()[0]
    refused(lambda: allocate(pay, ("payment", source), ("invoice", invoice), 100), "no unapplied receivable")


def test_a_bill_in_a_pay_run_is_paid_when_settled(pay):
    bill = document(pay, "bill", 400)
    with pay._company("PARENT") as c:
        c.execute("UPDATE invoice SET status = 'In pay run' WHERE invoice_id = ?", (bill,))
    source = payment(pay, "Made", 400, posted=False)
    assert allocate(pay, ("payment", source), ("invoice", bill), 400)["target_status"] == "Paid"


def test_an_invoice_covered_by_an_advance_takes_no_allocation(pay):
    """It never gets an entry of its own (the invoice lock allows entry_id only from Draft to Sent), so it has no
    open item; the advance already covers it."""
    with pay._company("PARENT") as c:
        invoice = lh.make_invoice(c, contact_id=pay.customer, lines=((1, 500),), status="Covered by advance")
    source = payment(pay, amount=500, posted=False)
    refused(lambda: allocate(pay, ("payment", source), ("invoice", invoice), 500), "not been sent")


def test_a_vendor_credit_on_two_bills_is_released_whole(pay):
    bills = [document(pay, "bill", 300), document(pay, "bill", 200)]
    credit = document(pay, "vendor_credit", 500)
    groups = [open_group(pay, entry_of(pay, "invoice", "invoice_id", d), "Purchase") for d in (*bills, credit)]
    allocate(pay, ("credit_memo", credit), ("invoice", bills[0]), 300)
    allocate(pay, ("credit_memo", credit), ("invoice", bills[1]), 200)
    assert [group(pay, "ap", g) for g in groups] == [0, 0, 0]
    assert [invoice_status(pay, b) for b in bills] == ["Paid", "Paid"]
    void_document_entry(pay, entry_of(pay, "invoice", "invoice_id", credit))
    result = release(pay, ("credit_memo", credit), reason="Credit issued in error")
    assert len(result["released"]) == 2 and len(result["entries"]) == 2
    assert [group(pay, "ap", g) for g in groups] == [-300, -200, 0]
    assert [invoice_status(pay, b) for b in bills] == ["Sent", "Sent"]
    assert verify(pay)["ok"]


def test_the_release_voids_each_application_entry(pay):
    invoice, source = document(pay, "invoice", 1000), payment(pay, amount=1000)
    application = allocate(pay, ("payment", source), ("invoice", invoice), 1000)["application_entry_id"]
    void_document_entry(pay, entry_of(pay, "payment", "payment_id", source))
    reversal = release(pay, ("payment", source))["entries"][0]
    row = pay.rows("PARENT", "SELECT * FROM journal_entry WHERE entry_id = ?", (reversal,))[0]
    assert (row["reverses_entry_id"], row["reversal_reason"], row["is_posted"]) == (application, "Void", 1)
    assert pay.rows("PARENT", "SELECT is_void FROM journal_entry WHERE entry_id = ?", (application,))[0]["is_void"] == 1
    assert "Payment voided" in row["reversal_note"]


def test_the_release_cannot_be_dated_before_the_application(pay):
    invoice, source = document(pay, "invoice"), payment(pay)
    allocate(pay, ("payment", source), ("invoice", invoice), 1000, applied_date="2026-03-10")
    void_document_entry(pay, entry_of(pay, "payment", "payment_id", source), day="2026-03-12")
    before = state(pay)
    refused(lambda: release(pay, ("payment", source), day="2026-03-09"), "before")
    assert state(pay) == before


def test_the_release_date_respects_the_area_lock(pay):
    invoice, source = document(pay, "invoice"), payment(pay)
    allocate(pay, ("payment", source), ("invoice", invoice), 1000)
    void_document_entry(pay, entry_of(pay, "payment", "payment_id", source))
    with pay._company("PARENT") as c:
        period = lh.ensure_period(c, "2026-03-20")
        c.execute("INSERT INTO fiscal_period_lock (period_id, area, locked_by, reason) VALUES (?, 'Sales', 1, 'x')",
                  (period,))
    refused(lambda: release(pay, ("payment", source)), "locked")


@pytest.mark.parametrize("day", ["20/03/2026", None])
def test_the_release_date_is_an_iso_date(pay, day):
    invoice, source = document(pay, "invoice"), payment(pay, posted=False)
    allocate(pay, ("payment", source), ("invoice", invoice), 100)
    refused(lambda: release(pay, ("payment", source), day=day), "date")


def test_a_refused_release_writes_nothing(pay):
    invoice, source = document(pay, "invoice"), payment(pay)
    allocate(pay, ("payment", source), ("invoice", invoice), 1000)
    before = state(pay)
    refused(lambda: release(pay, ("payment", source)), "Void the payment")
    assert state(pay) == before


# --- step 7 mutation check: one test per surviving mutant -----------------------------------------------------

def test_a_void_credit_memo_without_an_entry_is_still_refused(pay):
    """Status Void alone (a memo sent with no entry, then voided) refuses it; it is not taken for a draft."""
    invoice = document(pay, "invoice")
    with pay._company("PARENT") as c:
        memo = lh.make_invoice(c, itype="Credit Memo", contact_id=pay.customer, lines=((1, 300),))
        lh.send_invoice(c, memo)
        c.execute("UPDATE invoice SET status = 'Void' WHERE invoice_id = ?", (memo,))
    refused(lambda: allocate(pay, ("credit_memo", memo), ("invoice", invoice), 100), "voided")
    assert allocations(pay) == []


@pytest.mark.parametrize("applied", ["20260306", "2026-02-30"])
def test_the_applied_date_must_be_a_real_dashed_date(pay, applied):
    invoice, source = document(pay, "invoice"), payment(pay, posted=False)
    refused(lambda: allocate(pay, ("payment", source), ("invoice", invoice), 100, applied_date=applied), "a date like")


def test_the_release_date_must_be_a_real_date(pay):
    invoice, source = document(pay, "invoice"), payment(pay, posted=False)
    allocate(pay, ("payment", source), ("invoice", invoice), 100)
    refused(lambda: release(pay, ("payment", source), day="2026-02-30"), "a date like")


def test_a_payment_with_no_direction_is_not_a_source(pay):
    invoice = document(pay, "invoice")
    with pay._company("PARENT") as c:
        source = c.execute("INSERT INTO payment (contact_id, payment_date, amount_cents) VALUES (?, '2026-03-05', 500) "
                           "RETURNING payment_id", (pay.customer,)).fetchone()[0]
    refused(lambda: allocate(pay, ("payment", source), ("invoice", invoice), 100), "Choose the payment or credit memo")


def test_an_agent_is_refused_before_anything_is_looked_up(pay):
    with pytest.raises(PermissionDeniedError):
        allocate(pay, ("payment", 999999), ("invoice", 999999), 100, context=ctx(pay, "Agent"))


def test_a_source_whose_side_changes_between_the_reads_is_refused(pay, monkeypatch):
    invoice, source = document(pay, "invoice"), payment(pay, posted=False)
    monkeypatch.setattr(payments, "_source_side", lambda conn, ref: "Purchase")
    before = state(pay)
    refused(lambda: allocate(pay, ("payment", source), ("invoice", invoice), 100), "changed while you were applying")
    assert state(pay) == before


def test_the_release_stamps_who_when_and_the_trimmed_reason(pay):
    invoice, source = document(pay, "invoice"), payment(pay, posted=False)
    allocate(pay, ("payment", source), ("invoice", invoice), 100)
    release(pay, ("payment", source), reason="  Payment voided  ")
    row = allocations(pay)[0]
    assert (row["release_reason"], row["released_at"], row["released_by"]) == \
        ("Payment voided", ctx_for(pay, "System").now, pay.user_id)


def test_the_release_may_be_dated_the_same_day_as_the_application(pay):
    invoice, source = document(pay, "invoice"), payment(pay)
    allocate(pay, ("payment", source), ("invoice", invoice), 1000, applied_date="2026-03-10")
    void_document_entry(pay, entry_of(pay, "payment", "payment_id", source), day="2026-03-10")
    result = release(pay, ("payment", source), day="2026-03-10")
    assert len(result["entries"]) == 1
    assert pay.rows("PARENT", "SELECT is_posted FROM journal_entry WHERE entry_id = ?",
                    (result["entries"][0],))[0]["is_posted"] == 1


def test_clearing_lines_join_each_group_on_its_own_account(pay):
    with pay._company("PARENT") as c:
        pay.accts["ar2"] = lh.make_account(c, "1210", control_type="AR", track_clearing_id=1)
    invoice = document(pay, "invoice", 300)                  # opened on the first AR account
    with pay._company("PARENT") as c:
        split = payments.clearing_lines(c, side="Sales", account_id=A(pay, "ar2"), contact_id=pay.customer,
                                        amount_cents=500, allocations=[(invoice, 300)])
    assert [line["account_id"] for line in split] == [A(pay, "ar"), A(pay, "ar2")]


@pytest.mark.parametrize("kwargs, match", [
    ({"side": "Other", "allocations": []}, "Sales or Purchase"),
    ({"side": "Sales", "allocations": [("INVOICE", 0)]}, "positive"),
    ({"side": "Sales", "allocations": [("INVOICE", -5)]}, "positive"),
    ({"side": "Sales", "allocations": [(999999, 100)]}, "no open receivable line"),
])
def test_clearing_lines_check_their_inputs(pay, kwargs, match):
    invoice = document(pay, "invoice", 300)
    allocs = [(invoice if doc == "INVOICE" else doc, part) for doc, part in kwargs["allocations"]]
    with pay._company("PARENT") as c:
        with pytest.raises(ValidationError, match=match):
            payments.clearing_lines(c, side=kwargs["side"], account_id=A(pay, "ar"), contact_id=pay.customer,
                                    amount_cents=500, allocations=allocs)


# --- LOW 2 (MR6): the side is read first; a missing source is a denial for someone with neither right ---------

@pytest.mark.parametrize("missing", [("payment", 999999), ("credit_memo", 999999)])
def test_someone_with_neither_permission_cannot_tell_a_missing_source(pay, missing):
    """One sentence for a missing source and for an existing payment or credit memo on either side; each refusal
    writes one access_event naming the side's code, and nothing else changes."""
    invoice, received, made = document(pay, "invoice"), payment(pay, posted=False), payment(pay, "Made", posted=False)
    memo, vendor_credit = document(pay, "credit_memo"), document(pay, "vendor_credit")
    pay.remove_permission("PARENT", "POSTER", "payment.receive")
    pay.remove_permission("PARENT", "POSTER", "payment.make")
    refs = (missing, ("payment", received), ("payment", made), ("credit_memo", memo), ("credit_memo", vendor_credit))
    before, events = state(pay), len(pay.events("PARENT"))
    sentences = set()
    for ref in refs:
        with pytest.raises(PermissionDeniedError) as denied:
            allocate(pay, ref, ("invoice", invoice), 100)
        sentences.add(str(denied.value))
    assert sentences == {payments.CANNOT_APPLY}
    written = pay.events("PARENT")[events:]
    assert [(e["event_type"], e["permission_code"], e["record_type"]) for e in written] == [
        ("Denied", code, "payment_allocation") for code in
        ("payment.receive", "payment.receive", "payment.make", "payment.receive", "payment.make")]
    assert state(pay) == before


@pytest.mark.parametrize("case, sentence", [("inactive", "account is inactive"), ("no access", "do not have access")])
def test_an_inactive_user_or_one_without_access_is_told_that(pay, case, sentence):
    invoice, source = document(pay, "invoice"), payment(pay, posted=False)
    if case == "inactive":
        pay.set_user_active(pay.user_id, False)
    else:
        pay.revoke(pay.user_id, "PARENT")
    before = state(pay)
    for ref in (("payment", source), ("payment", 999999)):
        with pytest.raises(PermissionDeniedError, match=sentence):
            allocate(pay, ref, ("invoice", invoice), 100)
    assert state(pay) == before


@pytest.mark.parametrize("held", ["payment.receive", "payment.make"])
def test_someone_with_one_permission_cannot_tell_a_missing_source_from_the_other_side(pay, held):
    """LOW-A (owner, 2026-11-17): one sentence, one error type and one access_event for a missing id and for an
    existing id on the side the person has no right to; nothing else changes."""
    lacked = "payment.make" if held == "payment.receive" else "payment.receive"
    invoice = document(pay, "invoice")
    received, made = payment(pay, posted=False), payment(pay, "Made", posted=False)
    memo, vendor_credit = document(pay, "credit_memo"), document(pay, "vendor_credit")
    pay.remove_permission("PARENT", "POSTER", lacked)
    other_side = [("payment", made), ("credit_memo", vendor_credit)] if held == "payment.receive" else [
        ("payment", received), ("credit_memo", memo)]
    refs = [("payment", 999999), ("credit_memo", 999999)] + other_side
    before, events = state(pay), len(pay.events("PARENT"))
    sentences = set()
    for ref in refs:
        with pytest.raises(PermissionDeniedError) as denied:
            allocate(pay, ref, ("invoice", invoice), 100)
        assert type(denied.value) is PermissionDeniedError
        sentences.add(str(denied.value))
    assert sentences == {payments.ONE_SIDE_ONLY[held]}
    written = pay.events("PARENT")[events:]
    assert [(e["event_type"], e["permission_code"], e["record_type"], e["record_id"]) for e in written] == [
        ("Denied", lacked, "payment_allocation", None)] * len(refs)
    assert state(pay) == before


def test_the_one_side_sentences_name_no_document():
    for sentence in payments.ONE_SIDE_ONLY.values():
        assert sentence.endswith(".") and "ask an Admin" in sentence
    assert payments.ONE_SIDE_ONLY["payment.receive"] != payments.ONE_SIDE_ONLY["payment.make"]


def test_someone_with_both_permissions_is_told_the_source_is_missing(pay):
    invoice = document(pay, "invoice")
    refused(lambda: allocate(pay, ("payment", 999999), ("invoice", invoice), 100), "Choose the payment or credit memo")


@pytest.mark.parametrize("held", ["payment.receive", "payment.make"])
def test_someone_with_one_permission_still_applies_their_own_side(pay, held):
    if held == "payment.receive":
        target, source = document(pay, "invoice"), payment(pay, posted=False)
    else:
        target, source = document(pay, "bill"), payment(pay, "Made", posted=False)
    pay.remove_permission("PARENT", "POSTER", "payment.make" if held == "payment.receive" else "payment.receive")
    assert allocate(pay, ("payment", source), ("invoice", target), 100)["allocation_id"]


@pytest.mark.parametrize("direction, permission", [("Received", "payment.receive"), ("Made", "payment.make")])
def test_the_denial_log_names_the_sources_side(pay, direction, permission):
    target = document(pay, "invoice" if direction == "Received" else "bill")
    source = payment(pay, direction, posted=False)
    pay.remove_permission("PARENT", "POSTER", permission)
    with pytest.raises(PermissionDeniedError):
        allocate(pay, ("payment", source), ("invoice", target), 100)
    assert pay.events("PARENT")[-1]["permission_code"] == permission


def test_the_master_in_an_archived_company_gets_the_archived_sentence(pay):
    invoice, source = document(pay, "invoice"), payment(pay, posted=False)
    master = pay.user("owner", master=True)
    pay.set_company_active("PARENT", False)
    for ref in (("payment", source), ("payment", 999999)):
        with pytest.raises(PermissionDeniedError, match="This company is archived"):
            allocate(pay, ref, ("invoice", invoice), 100, context=ctx_for(pay, user=master))
