"""Hand check for Phase 2.5 Step 6 (rounding and document entries). In PowerShell, from the repo root:

    $env:STRATALEDGER_ALLOW_TEST_KEYS = "1"; python tools/hand_check_step6.py; Remove-Item Env:STRATALEDGER_ALLOW_TEST_KEYS

The variable lets this one run use the test suite's fixed chain key (keys.FixedKeyProvider refuses without it).

Builds a throwaway installation in a temporary folder (never the real databases), runs the real services as an
importer would (one write transaction per file) and prints what a person would see: each refusal's sentence, each
entry's lines, and the verification. Read the output against docs/next_step.md ("Hand check"). Exits with an error
if anything behaves differently from the decisions (L8, R1, R49-R54).
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
from modules.services import approvals, keys, ledger, ledger_chain, periods  # noqa: E402
from modules.services.errors import ServiceError  # noqa: E402
from modules.services.tx import write_transaction  # noqa: E402
from tests import ledger_helpers as lh  # noqa: E402
from tests.authz_world import World  # noqa: E402

NOW = "2026-03-20T10:00:00+00:00"
problems = []


def show(label, call, expect_refusal=None):
    """Run call; print the result or the refusal sentence. expect_refusal: text the refusal must contain."""
    try:
        result = call()
    except ServiceError as error:
        print(f"  {label}: REFUSED - {error}")
        if expect_refusal is None or expect_refusal not in str(error):
            problems.append(f"{label}: unexpected refusal {error!r}")
        return None
    print(f"  {label}: OK")
    if expect_refusal is not None:
        problems.append(f"{label}: should have been refused ({expect_refusal})")
    return result


def main():
    if os.environ.get("STRATALEDGER_ALLOW_TEST_KEYS") != "1":
        print("Set STRATALEDGER_ALLOW_TEST_KEYS=1 for this run (see the top of this file); nothing was done.")
        return 2
    tmp = Path(tempfile.mkdtemp(prefix="strata_step6_"))
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
            wages = lh.make_account(c, "6100", name="Wages")
            rounding = lh.make_account(c, "8020", name="Rounding Variance")
        world.role("PARENT", "CLERK", ["je.create", "je.post", "je.reverse", "ledger.view", "import.run"])
        world.role("PARENT", "REVIEWER", ["import.approve", "ledger.view"])
        world.limit("PARENT", "REVIEWER", "Import batch", 10 ** 12)
        people = {name: world.user(name) for name in ("clerk", "reviewer")}
        world.grant(people["clerk"], "PARENT", "CLERK")
        world.grant(people["reviewer"], "PARENT", "REVIEWER")

        def ctx(name="clerk", origin="Human"):
            return dataclasses.replace(world.ctx(people[name], "PARENT", origin), now=NOW, today="2026-03-20")

        def wage_lines(debit, credit):
            return [{"account_id": wages, "debit_cents": debit}, {"account_id": cash, "credit_cents": credit}]

        def import_file(rows, source="Payroll"):
            """One file, one transaction: every entry or none (R51)."""
            importer = ctx().as_import()
            with write_transaction(importer.company_db_path, importer) as conn:
                return [ledger.create_document_entry(conn, importer, source=source, entry_date="2026-03-15",
                                                     lines=entry_lines, reference=reference, source_rows=rows_)
                        for reference, rows_, entry_lines in rows]

        def describe(entry_id):
            row = ledger.get_entry(ctx(), entry_id)
            number = f"JE-{row['entry_number']:06d}" if row["entry_number"] else "draft"
            print(f"     {number} {row['reference']} ({row['source']}, origin {row['origin']})")
            for line in row["lines"]:
                side = f"Dr {line['debit_cents'] / 100:,.2f}" if line["debit_cents"] else \
                       f"Cr {line['credit_cents'] / 100:,.2f}"
                flag = "  <- rounding line" if line["is_rounding_adjustment"] else ""
                account = world.rows("PARENT", "SELECT code, name FROM account WHERE account_id = ?",
                                     (line["account_id"],))[0]
                memo = f"  {line['memo']}" if line["memo"] else ""
                print(f"       {account['code']} {account['name']}: {side}{memo}{flag}")
            return row

        print("1. A payroll file with no rounding account set: the 1-cent entry refuses the whole file")
        show("import the file", lambda: import_file([("PR-0411", [2, 3], wage_lines(500_000, 500_000)),
                                                     ("PR-0412", [4, 5], wage_lines(312_501, 312_500))]),
             "no rounding account is set")
        if world.rows("PARENT", "SELECT COUNT(*) AS n FROM journal_entry")[0]["n"] != 0:
            problems.append("a refused file left entries behind")
        with world._company("PARENT") as c:          # Company Settings > Accounts (no settings screen yet)
            c.execute("UPDATE company_settings SET rounding_variance_acct_id = ? WHERE id = 1", (rounding,))

        print("2. The same file with the rounding account set: one 1-cent line on the short side")
        saved = show("import the file", lambda: import_file([("PR-0411", [2, 3], wage_lines(500_000, 500_000)),
                                                             ("PR-0412", [4, 5], wage_lines(312_501, 312_500))]))
        if saved:
            for item in saved:
                print(f"     rounding_cents {item['rounding_cents']}")
                describe(item["entry_id"])
            if [item["rounding_cents"] for item in saved] != [0, 1]:
                problems.append("rounding_cents is not 0 then 1")

        print("3. A file with an entry 2 cents off is refused whole, naming the entry, its rows and the difference")
        show("import the file", lambda: import_file([("PR-0413", [2, 3], wage_lines(100_000, 100_000)),
                                                     ("PR-0414", [4, 5, 6, 7], wage_lines(200_002, 200_000))]),
             "Entry PR-0414 (rows 4-7) is out of balance by 0.02")
        if world.rows("PARENT", "SELECT COUNT(*) AS n FROM journal_entry")[0]["n"] != 2:
            problems.append("the 2-cent file saved something")

        print("4. A person cannot label a manual draft as an import, and cannot make a document entry")
        show("create_entry with source Payroll", lambda: ledger.create_entry(
            ctx(), entry_date="2026-03-15", lines=wage_lines(100, 100), source="Payroll"), "manual entry")
        show("create_entry with source Payroll, as the importer", lambda: ledger.create_entry(
            ctx().as_import(), entry_date="2026-03-15", lines=wage_lines(100, 100), source="Payroll"),
             "manual entry")
        show("an agent context as the importer", lambda: world.ctx(people["clerk"], "PARENT", "Agent").as_import(),
             "agent's actions stay agent actions")

        def payroll_as_system():
            system = ctx().as_system()
            with write_transaction(system.company_db_path, system) as conn:
                return ledger.create_document_entry(conn, system, source="Payroll", entry_date="2026-03-15",
                                                    lines=wage_lines(100, 100), source_rows=[2], post=True)
        show("payroll saved and posted as the system (skipping the review)", payroll_as_system,
             "saved by its importer")

        print("5. A manual entry 1 cent off is never rounded")
        manual = ledger.create_entry(ctx(), entry_date="2026-03-15", lines=wage_lines(1_001, 1_000))
        show("post it", lambda: ledger.post_journal_entry(ctx(), manual, confirm=True), "does not balance")

        print("6. The reviewer approves the rounded payroll entry; the clerk posts it with no new approval")
        if saved:
            rounded = saved[1]["entry_id"]
            request_id = ledger.submit_entry_for_approval(ctx().as_import(), rounded)
            show("approve it", lambda: approvals.approve(ctx("reviewer"), request_id))
            show("post it", lambda: ledger.post_journal_entry(ctx(), rounded, confirm=True))
            describe(rounded)
            print("7. Void it: the rounding line is mirrored")
            void = show("void it", lambda: ledger.void_entry(ctx(), rounded, note="wrong pay period",
                                                              confirm=True))
            if void:
                describe(void["entry_id"])

        print("8. Verification")
        entries = []
        for header in world.rows("PARENT", "SELECT * FROM journal_entry WHERE is_posted = 1 ORDER BY entry_number"):
            entries.append({"header": header, "lines": world.rows(
                "PARENT", "SELECT * FROM journal_line WHERE entry_id = ?", (header["entry_id"],)), "dimensions": []})
        key_id = world.rows("PARENT", "SELECT key_id FROM ledger_chain_key WHERE is_active = 1")[0]["key_id"]
        check = ledger_chain.verify_chain("PARENT", entries, {key_id: lh.TEST_CHAIN_KEY}.__getitem__)
        print(f"  verification: {'OK' if check['ok'] else 'BROKEN'} ({len(entries)} posted entries, "
              f"numbers 1 to {check['through_entry_number']} with no gap)")
        if not check["ok"] or len(entries) != 2:
            problems.append("verification failed or the wrong number of entries posted")
        balance = world.rows("PARENT", "SELECT COALESCE(SUM(l.debit_cents - l.credit_cents), 0) AS n FROM journal_line "
                                       "AS l JOIN journal_entry AS e ON e.entry_id = l.entry_id "
                                       "WHERE e.is_posted = 1 AND l.account_id = ?", (rounding,))[0]["n"]
        print(f"  rounding account after the void: {balance / 100:,.2f}")
        if balance != 0:
            problems.append("the rounding account does not net to zero after the void")
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
