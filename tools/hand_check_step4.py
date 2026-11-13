"""Hand check for Phase 2.5 Step 4 (approvals in posting). In PowerShell, from the repo root:

    $env:STRATALEDGER_ALLOW_TEST_KEYS = "1"; python tools/hand_check_step4.py; Remove-Item Env:STRATALEDGER_ALLOW_TEST_KEYS

The variable lets this one run use the test suite's fixed chain key (keys.FixedKeyProvider refuses without it).

Builds a throwaway installation in a temporary folder (never the real databases), runs the real services and
prints what a person would see: each refusal's sentence and each result. Read the output against
docs/next_step.md ("Hand check"). Exits with an error if anything behaves differently from the decisions.
"""
import dataclasses
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
import modules.database as database  # noqa: E402
from modules.services import approvals, companies, keys, ledger, ledger_chain, periods  # noqa: E402
from modules.services.errors import ServiceError  # noqa: E402
from tests import ledger_helpers as lh  # noqa: E402
from tests.authz_world import World  # noqa: E402

NOW = "2026-03-20T10:00:00+00:00"
LATER = "2026-03-20T15:30:00+00:00"
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
    print(f"  {label}: OK" + (f" ({result})" if result is not None else ""))
    if expect_refusal is not None:
        problems.append(f"{label}: should have been refused ({expect_refusal})")
    return result


def main():
    if os.environ.get("STRATALEDGER_ALLOW_TEST_KEYS") != "1":
        print("Set STRATALEDGER_ALLOW_TEST_KEYS=1 for this run (see the top of this file); nothing was done.")
        return 2
    tmp = Path(tempfile.mkdtemp(prefix="strata_step4_"))
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
            cash, sales = lh.make_account(c, "1010"), lh.make_account(c, "4010")
        world.role("PARENT", "CLERK", ["je.create", "je.post", "ledger.view", "import.run"])
        world.role("PARENT", "APPROVER", ["je.approve", "import.approve", "ledger.view"])
        world.role("PARENT", "CONTROLLER", ["je.approve", "ledger.view"])
        for role in ("APPROVER", "CONTROLLER"):
            world.limit("PARENT", role, "Journal entry", 10 ** 12)
        world.limit("PARENT", "APPROVER", "Import batch", 10 ** 12)
        people = {}
        for name, role in (("clerk", "CLERK"), ("clerk2", "CLERK"), ("anna", "APPROVER"), ("ben", "APPROVER"),
                           ("carl", "CONTROLLER"), ("admin", "Admin")):
            people[name] = world.user(name)
            world.grant(people[name], "PARENT", role)

        def ctx(name, origin="Human", now=NOW):
            return dataclasses.replace(world.ctx(people[name], "PARENT", origin), now=now, today="2026-03-20")

        def entry(cents, who="clerk", origin="Human", **kw):
            return ledger.create_entry(ctx(who, origin), entry_date="2026-03-15", lines=[
                {"account_id": cash, "debit_cents": cents}, {"account_id": sales, "credit_cents": cents}], **kw)

        def post(entry_id, who="clerk", origin="Human"):
            return lambda: ledger.post_journal_entry(ctx(who, origin), entry_id,
                                                     **({"confirm": True} if origin == "Human" else {}))

        def submit(entry_id, who="clerk", origin="Human"):
            return lambda: ledger.submit_entry_for_approval(ctx(who, origin), entry_id)

        def setting(**values):
            with world._company("PARENT") as c:
                for name, value in values.items():
                    c.execute(f"UPDATE company_settings SET {name} = ? WHERE id = 1", (value,))

        def row(entry_id):
            return world.rows("PARENT", "SELECT * FROM journal_entry WHERE entry_id = ?", (entry_id,))[0]

        print("1. Every control off (the default): a manual entry posts directly")
        e = entry(50_000)
        show("send for approval", submit(e), "can be posted directly")
        show("post", post(e))

        print("2. Manual-entry approval on, threshold 1,000.00")
        setting(manual_entry_approval=1, manual_entry_approval_threshold_cents=100_000)
        show("post 1,000.00 (equal to the threshold)", post(entry(100_000)))
        e = entry(100_001)
        show("post 1,000.01 (one cent over)", post(e), "send it for approval first")
        request = show("send for approval", submit(e))
        show("send it again", submit(e), "already waiting")
        show("post while waiting", post(e), "step 1 of 1")
        show("Anna approves", lambda: approvals.approve(ctx("anna", now=LATER), request))
        show("post", post(e))
        r = row(e)
        print(f"     approved_by = {r['approved_by']} (Anna is {people['anna']}), approved_at = {r['approved_at']}")
        if (r["approved_by"], r["approved_at"]) != (people["anna"], LATER):
            problems.append("approved_by / approved_at are not Anna's")

        print("3. A two-step chain: Approver, then Controller")
        approvals.create_policy(ctx("admin"), "Two steps", "Journal entry", 0, None,
                                [(1, "APPROVER", 1), (2, "CONTROLLER", 1)])
        e = entry(200_000)
        request = show("send for approval", submit(e))
        show("Carl approves first", lambda: approvals.approve(ctx("carl"), request), "Not permitted")
        show("Anna approves step 1", lambda: approvals.approve(ctx("anna"), request))
        show("post", post(e), "step 2 of 2")
        show("Carl approves step 2", lambda: approvals.approve(ctx("carl"), request))

        print("4. An edit after approval cancels it")
        show("clerk edits the description", lambda: ledger.update_entry(ctx("clerk"), e, description="edited"))
        show("post", post(e), "cancelled because the entry was changed")
        request = show("send again", submit(e))
        show("Carl approves (back at step 1)", lambda: approvals.approve(ctx("carl"), request), "Not permitted")
        show("Ben approves step 1", lambda: approvals.approve(ctx("ben"), request))
        show("Carl approves step 2", lambda: approvals.approve(ctx("carl"), request))
        show("post", post(e))

        print("5. A rejection needs a reason and a change")
        e = entry(300_000)
        request = show("send for approval", submit(e))
        show("reject with no reason", lambda: approvals.reject(ctx("anna"), request, " "), "reason is required")
        show("reject", lambda: approvals.reject(ctx("anna"), request, "Wrong account."))
        show("post", post(e), "rejected")
        show("send again unchanged", submit(e), "Change the entry before sending it again")
        show("re-save the same lines", lambda: ledger.update_entry(ctx("clerk"), e, lines=[
            {"account_id": cash, "debit_cents": 300_000}, {"account_id": sales, "credit_cents": 300_000}]))
        show("send again after re-saving the same lines", submit(e), "Change the entry before sending it again")
        show("change the amount", lambda: ledger.update_entry(ctx("clerk"), e, lines=[
            {"account_id": cash, "debit_cents": 290_000}, {"account_id": sales, "credit_cents": 290_000}]))
        show("send again", submit(e))

        print("6. Agent and Import entries always need a person, with every control off")
        setting(manual_entry_approval=0)
        agent = entry(1_000, origin="Agent")
        show("post the agent's entry", post(agent), "send it for approval first")
        request = show("the agent sends it", submit(agent, origin="Agent"))
        show("the agent approves it", lambda: approvals.approve(ctx("anna", "Agent"), request), "Only a person")
        show("Anna approves step 1", lambda: approvals.approve(ctx("anna"), request))
        show("Carl approves step 2 (the two-step policy covers every journal entry)",
             lambda: approvals.approve(ctx("carl"), request))
        show("the agent posts it", post(agent, origin="Agent"), "Not permitted")
        show("the clerk posts it", post(agent))
        imported = entry(2_000, origin="Import", source="Import")
        request = show("the import sends it", submit(imported, origin="Import"))
        show("an Import context approves", lambda: approvals.approve(ctx("anna", "Import"), request),
             "Only a person")
        show("Anna approves", lambda: approvals.approve(ctx("anna"), request))
        show("the import posts it", post(imported, origin="Import"), "posted by a person")
        show("the clerk posts it", post(imported))

        print("7. Separation of duties on: the creator cannot post their own entry")
        setting(require_separate_approver=1)
        e = entry(4_000)
        show("the clerk posts their own entry", post(e), "different person to post")
        show("clerk2 posts it", post(e, who="clerk2"))

        print("8. The seal covers the approver")
        entries = []
        for header in world.rows("PARENT", "SELECT * FROM journal_entry WHERE is_posted = 1 ORDER BY entry_number"):
            entries.append({"header": header, "dimensions": [], "lines": world.rows(
                "PARENT", "SELECT * FROM journal_line WHERE entry_id = ?", (header["entry_id"],))})
        key_id = world.rows("PARENT", "SELECT key_id FROM ledger_chain_key WHERE is_active = 1")[0]["key_id"]
        ok = ledger_chain.verify_chain("PARENT", entries, {key_id: lh.TEST_CHAIN_KEY}.__getitem__)["ok"]
        print(f"  verification: {'OK' if ok else 'BROKEN'} ({len(entries)} posted entries)")
        if not ok:
            problems.append("verification failed")
        approved = next(x for x in entries if x["header"]["approved_by"] is not None)
        approved["header"] = dict(approved["header"], approved_by=people["ben"])
        result = ledger_chain.verify_chain("PARENT", entries, {key_id: lh.TEST_CHAIN_KEY}.__getitem__)
        print(f"  after changing one approver in memory: first broken entry {result['first_broken']['entry_number']}")

        print("9. The audit log has the approval history")
        for table in ("approval_request", "approval_action"):
            count = world.rows("PARENT", "SELECT COUNT(*) AS n FROM audit_log WHERE table_name = ?", (table,))[0]["n"]
            print(f"  {table}: {count} audit rows")
        denied = world.rows("PARENT", "SELECT COUNT(*) AS n FROM access_event WHERE event_type = 'Denied'")[0]["n"]
        print(f"  denials logged: {denied}")

        print("10. A fresh context for each action")
        opened = ctx("clerk")                     # as if the company was opened on 20 March
        fresh = companies.action_context(opened)
        if fresh.now == opened.now:
            problems.append("action_context kept the opening time")
        print(f"  opened at {opened.now}; fresh context at {fresh.now} (same user: {fresh.user_id == opened.user_id})")
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
