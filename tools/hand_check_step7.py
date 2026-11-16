"""Hand check for Phase 2.5 Step 7 (allocation, clearing and numbering). In PowerShell, from the repo root:

    $env:STRATALEDGER_ALLOW_TEST_KEYS = "1"; python tools/hand_check_step7.py; Remove-Item Env:STRATALEDGER_ALLOW_TEST_KEYS

The variable lets this one run use the test suite's fixed chain key (keys.FixedKeyProvider refuses without it).

Builds a throwaway installation in a temporary folder (never the real databases) and walks the clearing story a
bookkeeper would see (R57, R58, RP11):
1. an invoice for 1,000.00 opens its receivable group;
2. a payment of 1,500.00 posts with its whole amount unapplied (a group of its own);
3. 1,000.00 of it is applied to the invoice: an application entry settles both groups and the invoice is Paid;
4. over-applying the rest to a second invoice is refused with its sentence;
5. the payment is voided (the ledger's mirrored reversal) and its allocation released: the invoice is open again.
It prints every group's balance after each step and the chain verification, and exits with an error if anything
differs from the decisions. It also takes the next two invoice numbers: the two invoices above came from the
test helpers' SI- series, so numbering continues it with no gap (the R6 default series is in tests/test_sequences.py).
"""
import dataclasses
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
import modules.database as database  # noqa: E402
from modules.services import keys, ledger, ledger_chain, payments, periods, sequences  # noqa: E402
from modules.services.errors import ServiceError  # noqa: E402
from modules.services.tx import write_transaction  # noqa: E402
from tests import ledger_helpers as lh  # noqa: E402
from tests.authz_world import World  # noqa: E402

NOW = "2026-03-20T10:00:00+00:00"
problems = []


def main():
    if os.environ.get("STRATALEDGER_ALLOW_TEST_KEYS") != "1":
        print("Set STRATALEDGER_ALLOW_TEST_KEYS=1 for this run (see the top of this file); nothing was done.")
        return 2
    tmp = Path(tempfile.mkdtemp(prefix="strata_step7_"))
    try:
        config.BASE_PROJECT_DIR = str(tmp)
        database.BACKUP_DIR = str(tmp / "Backups")
        keys._provider = keys.FixedKeyProvider(lh.TEST_CHAIN_KEY)
        template = tmp / "template.db"
        database.ensure_company_database(template)
        world = World(tmp, template)
        world.settings("PARENT", require_separate_approver=0)
        with world._company("PARENT") as c:
            periods.seed_years(c, 1, 2026)
            lh.ensure_test_chain_key(c)
            cash = lh.make_account(c, "1010", name="Operating Cash")
            ar = lh.make_account(c, "1100", name="Accounts Receivable", control_type="AR", track_clearing_id=1)
            sales = lh.make_account(c, "4010", name="Sales")
            customer = c.execute("INSERT INTO contact (name, is_customer, customer_code) VALUES ('Acme Builders', 1, "
                                 "'AC0001') RETURNING contact_id").fetchone()[0]
        world.role("PARENT", "CLERK", ["je.create", "je.post", "ledger.view", "payment.receive"])
        clerk = world.user("clerk")
        world.grant(clerk, "PARENT", "CLERK")

        def ctx(origin="Human"):
            return dataclasses.replace(world.ctx(clerk, "PARENT", origin), now=NOW, today="2026-03-20")

        def post(source, entry_lines, day):
            system = ctx("System")
            with write_transaction(system.company_db_path, system) as conn:
                return ledger.create_document_entry(conn, system, source=source, entry_date=day, lines=entry_lines,
                                                    post=True)["entry_id"]

        def invoice(amount, day="2026-03-02"):
            entry_id = post("Invoice", [{"account_id": ar, "debit_cents": amount, "contact_id": customer,
                                         "clearing_id": ledger.NEW_CLEARING},
                                        {"account_id": sales, "credit_cents": amount}], day)
            with world._company("PARENT") as c:
                return lh.make_invoice(c, contact_id=customer, lines=((1, amount),), status="Sent", entry_id=entry_id)

        def group_of(entry_id):
            with world._company("PARENT") as c:
                return payments.open_item(c, entry_id, "Sales")["clearing_id"]

        def balances(label, groups):
            shown = []
            for name, group in groups.items():
                n = world.rows("PARENT", "SELECT COALESCE(SUM(debit_cents - credit_cents), 0) AS n FROM journal_line "
                                         "WHERE clearing_id = ?", (group,))[0]["n"]
                shown.append(f"{name} {n / 100:,.2f}")
            print(f"  {label}: " + ", ".join(shown))
            return [world.rows("PARENT", "SELECT COALESCE(SUM(debit_cents - credit_cents), 0) AS n FROM journal_line "
                                         "WHERE clearing_id = ?", (g,))[0]["n"] for g in groups.values()]

        first = invoice(100000)
        second = invoice(80000)
        first_entry = world.rows("PARENT", "SELECT entry_id FROM invoice WHERE invoice_id = ?", (first,))[0]["entry_id"]
        pay_entry = post("Payment", [{"account_id": cash, "debit_cents": 150000},
                                     {"account_id": ar, "credit_cents": 150000, "contact_id": customer,
                                      "clearing_id": ledger.NEW_CLEARING}], "2026-03-05")
        with world._company("PARENT") as c:
            payment_id = c.execute("INSERT INTO payment (direction, contact_id, payment_date, amount_cents, entry_id) "
                                   "VALUES ('Received', ?, '2026-03-05', 150000, ?) RETURNING payment_id",
                                   (customer, pay_entry)).fetchone()[0]
        groups = {"invoice 1": group_of(first_entry), "payment": group_of(pay_entry)}
        print("Clearing groups (debit - credit):")
        if balances("posted", groups) != [100000, -150000]:
            problems.append("the posted groups are not +1,000.00 and -1,500.00")

        result = payments.allocate(ctx(), source=("payment", payment_id), target=("invoice", first),
                                   amount_cents=100000, applied_date="2026-03-06")
        print(f"  applied 1,000.00: invoice 1 is {result['target_status']}, application entry "
              f"{result['application_entry_id']}")
        if balances("after the application", groups) != [0, -50000] or result["target_status"] != "Paid":
            problems.append("the application did not settle invoice 1 and leave 500.00 unapplied")

        try:
            payments.allocate(ctx(), source=("payment", payment_id), target=("invoice", second), amount_cents=60000,
                              applied_date="2026-03-06")
            problems.append("applying 600.00 of the 500.00 left was not refused")
        except ServiceError as error:
            print(f"  apply 600.00 to invoice 2: REFUSED - {error}")

        voider = ctx()
        with write_transaction(voider.company_db_path, voider) as conn:
            target = conn.execute("SELECT * FROM journal_entry WHERE entry_id = ?", (pay_entry,)).fetchone()
            reversal = ledger._insert_reversal(conn, voider, target, target["entry_number"], "Void",
                                               entry_date="2026-03-20",
                                               period_id=periods.resolve_entry_period(conn, "2026-03-20"),
                                               note="bounced", origin="Human")
            key_id, key = ledger._active_key(conn, voider)
            ledger._seal_and_post(conn, voider, reversal, ledger._company_code(voider), key_id, key)
            released = payments.release_allocations(conn, voider.as_system(), source=("payment", payment_id),
                                                    reason="Payment bounced", entry_date="2026-03-20")
        status = world.rows("PARENT", "SELECT status FROM invoice WHERE invoice_id = ?", (first,))[0]["status"]
        print(f"  voided and released {len(released['released'])} allocation(s): invoice 1 is {status}")
        if balances("after the void and release", groups) != [100000, 0] or status != "Sent":
            problems.append("the void and release did not reopen invoice 1")

        entries = []
        for header in world.rows("PARENT", "SELECT * FROM journal_entry WHERE is_posted = 1 ORDER BY entry_number"):
            entries.append({"header": header,
                            "lines": world.rows("PARENT", "SELECT * FROM journal_line WHERE entry_id = ?",
                                                (header["entry_id"],)),
                            "dimensions": []})
        key_id = world.rows("PARENT", "SELECT key_id FROM ledger_chain_key WHERE is_active = 1")[0]["key_id"]
        check = ledger_chain.verify_chain("PARENT", entries, {key_id: lh.TEST_CHAIN_KEY}.__getitem__)
        print(f"  verification: {'OK' if check['ok'] else 'BROKEN'} ({len(entries)} posted entries)")
        if not check["ok"]:
            problems.append("the chain does not verify")

        system = ctx("System")
        with write_transaction(system.company_db_path, system) as conn:
            numbers = [sequences.next_invoice_number(conn, system, "Invoice", issue_date="2026-03-20")["invoice_number"]
                       for _ in range(2)]
        print(f"Next invoice numbers (the active series continues, gapless): {', '.join(numbers)}")
        if numbers != ["SI-000003", "SI-000004"]:
            problems.append("numbering did not continue the active series as SI-000003, SI-000004")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print()
    if problems:
        print("DIFFERENT FROM THE DECISIONS:")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("Every step behaved as decided.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
