"""Hand check for Phase 2.5 Step 5 (reversals and automatic reversals). In PowerShell, from the repo root:

    $env:STRATALEDGER_ALLOW_TEST_KEYS = "1"; python tools/hand_check_step5.py; Remove-Item Env:STRATALEDGER_ALLOW_TEST_KEYS

The variable lets this one run use the test suite's fixed chain key (keys.FixedKeyProvider refuses without it).

Builds a throwaway installation in a temporary folder (never the real databases), runs the real services and
prints what a person would see: each refusal's sentence, each entry the actions write, and the verification.
Read the output against docs/next_step.md ("Hand check"). Exits with an error if anything behaves differently
from the decisions (L5, R4, R40-R47).
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
from modules.services import keys, ledger, ledger_chain, periods  # noqa: E402
from modules.services.errors import ServiceError  # noqa: E402
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
    tmp = Path(tempfile.mkdtemp(prefix="strata_step5_"))
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
            cash, wages, accrued = lh.make_account(c, "1010"), lh.make_account(c, "6100"), lh.make_account(c, "2100")
        world.role("PARENT", "CLERK", ["je.create", "je.post", "je.reverse", "ledger.view"])
        world.role("PARENT", "NOREVERSE", ["je.create", "je.post", "ledger.view"])
        people = {name: world.user(name) for name in ("clerk", "other")}
        world.grant(people["clerk"], "PARENT", "CLERK")
        world.grant(people["other"], "PARENT", "NOREVERSE")

        def ctx(name="clerk", origin="Human"):
            return dataclasses.replace(world.ctx(people[name], "PARENT", origin), now=NOW, today="2026-03-20")

        def entry(cents, debit, credit, day="2026-03-15", **kw):
            return ledger.create_entry(ctx(), entry_date=day, lines=[
                {"account_id": debit, "debit_cents": cents}, {"account_id": credit, "credit_cents": cents}], **kw)

        def post(entry_id):
            return ledger.post_journal_entry(ctx(), entry_id, confirm=True)

        def describe(entry_id):
            row = ledger.get_entry(ctx(), entry_id)
            print(f"     JE-{row['entry_number']:06d} {row['entry_date']} {row['reversal_reason'] or 'entry'}"
                  f" (origin {row['origin']}, void {row['is_void']}): {row['display_description']}")
            return row

        print("1. An accrual with an automatic reversal date posts both entries at once")
        accrual = entry(250_000, wages, accrued, day="2026-03-31", description="March wages accrued",
                        auto_reverse_date="2026-04-01")
        result = show("post the accrual", lambda: post(accrual))
        describe(accrual)
        auto = describe(result["reversal_entry_id"])
        if (auto["reversal_reason"], auto["origin"], auto["entry_date"]) != ("Accrual reversal", "System",
                                                                            "2026-04-01"):
            problems.append("the automatic reversal is not an Accrual reversal by System on 1 April")

        print("2. An automatic reversal date with no open period refuses the whole post")
        late = entry(1_000, wages, accrued, day="2026-03-31", auto_reverse_date="2031-01-01")
        show("post with a reversal in 2031", lambda: post(late), "has no fiscal period yet")

        print("3. Void an ordinary entry")
        rent = entry(120_000, wages, cash, description="Rent March")
        post(rent)
        show("void without a note", lambda: ledger.void_entry(ctx(), rent, note=" ", confirm=True),
             "Say why in the note")
        show("void without confirming", lambda: ledger.void_entry(ctx(), rent, note="wrong account"),
             "Confirm the void first")
        show("void dated before the entry", lambda: ledger.void_entry(ctx(), rent, note="wrong account",
                                                                     entry_date="2026-03-01", confirm=True),
             "cannot be dated before")
        show("a user without the reverse permission voids it",
             lambda: ledger.void_entry(ctx("other"), rent, note="wrong account", confirm=True), "")
        voided = show("void it", lambda: ledger.void_entry(ctx(), rent, note="wrong account", confirm=True))
        describe(rent)
        describe(voided["entry_id"])
        show("void it again", lambda: ledger.void_entry(ctx(), rent, note="again", confirm=True), "already void")
        show("void the Void", lambda: ledger.void_entry(ctx(), voided["entry_id"], note="undo", confirm=True),
             "is a reversal")

        print("4. Correct an entry (it stays standing; enter the right one as a new draft)")
        fuel = entry(4_500, wages, cash, description="Fuel")
        post(fuel)
        corrected = show("correct it", lambda: ledger.reverse_entry(ctx(), fuel, note="belongs to vehicles",
                                                                   confirm=True))
        describe(fuel)
        describe(corrected["entry_id"])
        show("void it after the correction", lambda: ledger.void_entry(ctx(), fuel, note="x", confirm=True),
             "already been voided or corrected")

        print("5. The accrual: correcting it is refused; voiding it voids both")
        show("correct the accrual", lambda: ledger.reverse_entry(ctx(), accrual, note="wrong amount", confirm=True),
             "has an automatic reversal")
        show("void the automatic reversal alone", lambda: ledger.void_entry(ctx(), auto["entry_id"], note="x",
                                                                            confirm=True),
             "is the automatic reversal of")
        pair = show("void the accrual", lambda: ledger.void_entry(ctx(), accrual, note="wrong amount", confirm=True))
        for reversal in world.rows("PARENT", "SELECT entry_id FROM journal_entry WHERE reversal_reason = 'Void' "
                                             "AND reverses_entry_id IN (?, ?) ORDER BY entry_id",
                                   (accrual, auto["entry_id"])):
            describe(reversal["entry_id"])
        if pair and pair["voided_entry_ids"] != [accrual, auto["entry_id"]]:
            problems.append("the pair void did not void both entries")

        print("6. Verification")
        entries = []
        for header in world.rows("PARENT", "SELECT * FROM journal_entry WHERE is_posted = 1 ORDER BY entry_number"):
            entries.append({"header": header, "lines": world.rows(
                "PARENT", "SELECT * FROM journal_line WHERE entry_id = ?", (header["entry_id"],)), "dimensions": []})
        key_id = world.rows("PARENT", "SELECT key_id FROM ledger_chain_key WHERE is_active = 1")[0]["key_id"]
        check = ledger_chain.verify_chain("PARENT", entries, {key_id: lh.TEST_CHAIN_KEY}.__getitem__)
        print(f"  verification: {'OK' if check['ok'] else 'BROKEN'} ({len(entries)} posted entries, "
              f"numbers 1 to {check['through_entry_number']} with no gap)")
        if not check["ok"]:
            problems.append("verification failed")
        balance = world.rows("PARENT", "SELECT COALESCE(SUM(l.debit_cents - l.credit_cents), 0) AS n FROM journal_line "
                                       "AS l JOIN journal_entry AS e ON e.entry_id = l.entry_id "
                                       "WHERE e.is_posted = 1 AND l.account_id = ?", (accrued,))[0]["n"]
        print(f"  accrued wages account after the pair void: {balance / 100:,.2f} "
              "(the refused 2031 draft never posted)")
        if balance != 0:
            problems.append("the accrued wages account does not net to zero")
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
