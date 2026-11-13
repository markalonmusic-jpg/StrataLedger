"""Rebuild system_master.db from the baseline (fresh start).

Dry run by default: prints the plan and writes nothing. --apply moves any
existing target into a dated backup folder (Backups/YYYYMMDD-HHMMSS) and
builds a fresh file through the normal migration runner. Nothing is ever
deleted or overwritten.

Usage (from the project root):
    python scripts/create_fresh_databases.py            # dry run
    python scripts/create_fresh_databases.py --apply

Scope: system_master.db only. Company files (comp_strata.db, Companies/*.db)
are listed but not moved or opened; the fresh master has no company_registry
rows, so companies must be registered again afterwards.

After a successful --apply in a terminal, the script offers to create the
first Master through modules/services/auth.create_first_master. The password
is read with getpass (never echoed, printed or logged). The one-time recovery
code is printed once, with a warning to store it safely; only its hash is kept.

The script refuses to run (exit code 2) while the app is running or a target
file is locked, in dry run as well as apply.

--sample-company CODE is a separate, non-interactive action for testing. It does
NOT rebuild the master: it uses the existing Master user (no password is asked,
the services are called directly) to create one company from the construction
template under that code, exactly as the New Company screen would. Without
--apply it only prints what it would do. Run the normal --apply first (it
creates the Master interactively), then --sample-company CODE --apply.
"""
import argparse
import getpass
import os
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
import modules.database as database  # noqa: E402
from modules import first_run_model, platform_support  # noqa: E402
from modules.services import auth, companies, key_store, keys  # noqa: E402
from modules.services.errors import ServiceError  # noqa: E402

APP_ENTRY = "app_strata.pyw"
LOCK_SIBLINGS = ("-journal", "-wal", "-shm")
EXIT_REFUSED = 2
EXIT_FAILED = 1
KEY_LOCKED = ("Not created: the ledger key is locked on this computer. Restore it with the Master recovery code "
              "first.")


def app_is_running():
    """Command lines of running processes that mention the app entry point."""
    if os.name != "nt":
        return []
    ps = ("Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*" + APP_ENTRY + "*' } "
          "| ForEach-Object { $_.CommandLine }")
    try:
        result = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                                capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return []
    # The scan's own PowerShell command line mentions the entry point; skip it.
    return [line.strip() for line in result.stdout.splitlines()
            if line.strip() and "Get-CimInstance" not in line]


def lock_reason(path):
    """Why path cannot be moved right now, or None."""
    path = Path(path)
    for suffix in LOCK_SIBLINGS:
        if Path(f"{path}{suffix}").exists():
            return f"{path.name}{suffix} exists (another connection is open)"
    try:
        conn = sqlite3.connect(os.fspath(path), timeout=1.0, isolation_level=None)
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("ROLLBACK")
        finally:
            conn.close()
    except sqlite3.OperationalError as error:
        return f"{path.name} is locked ({error})"
    return None


def company_files(master_path):
    """Company databases beside the master; listed only, never touched."""
    root = Path(master_path).parent
    found = sorted(p for p in root.glob("*.db") if p.resolve() != Path(master_path).resolve())
    found += sorted((root / "Companies").glob("*.db"))
    return [p for p in found if p.name != "accounting_librebase.db"]


def build_plan(master_path, backup_dir, now=None):
    master_path = Path(master_path)
    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    return {
        "backup_folder": Path(backup_dir) / stamp,
        "moves": [master_path] if master_path.exists() else [],
        "creates": [(master_path, "master", database.MASTER_MIGRATIONS[-1][0])],
        "untouched": company_files(master_path),
    }


def print_plan(plan, apply):
    print("Mode:", "APPLY" if apply else "DRY RUN (nothing will be written; pass --apply)")
    print("Backup folder:", plan["backup_folder"])
    print("Move (never deleted):")
    for path in plan["moves"] or []:
        print(f"  {path}  ->  {plan['backup_folder'] / path.name}")
    if not plan["moves"]:
        print("  (none: no existing target)")
    print("Create from migrations:")
    for path, kind, version in plan["creates"]:
        print(f"  {path}  ({kind}, schema_version {version})")
    print("Present, untouched, not registered in the fresh master:")
    for path in plan["untouched"] or []:
        print(f"  {path}")
    if not plan["untouched"]:
        print("  (none)")
    print("Users: none are created; the first Master comes from the Phase 2 auth service.")


def refusals(plan):
    reasons = [f"the app appears to be running: {line}" for line in app_is_running()]
    for path in plan["moves"]:
        reason = lock_reason(path)
        if reason:
            reasons.append(reason)
    return reasons


def unique_folder(folder):
    folder = Path(folder)
    candidate, n = folder, 1
    while candidate.exists():
        n += 1
        candidate = folder.with_name(f"{folder.name}-{n}")
    candidate.mkdir(parents=True, exist_ok=False)
    return candidate


def apply_plan(plan):
    folder = unique_folder(plan["backup_folder"]) if plan["moves"] else None
    moved = []
    for path in plan["moves"]:
        target = folder / path.name
        shutil.move(os.fspath(path), os.fspath(target))
        moved.append((path, target))
        print(f"moved  {path}  ->  {target}")
    results = []
    for path, kind, _version in plan["creates"]:
        try:
            database.ensure_master_database(path)
            conn = sqlite3.connect(os.fspath(path))
            try:
                problems = database._verify_schema(conn)
                version = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
            finally:
                conn.close()
            if problems:
                raise RuntimeError("; ".join(problems))
        except Exception as error:
            print(f"FAILED to create {path}: {error}")
            for original, backup in moved:
                print(f"  your previous file is untouched at {backup}; move it back to {original} to restore")
            return EXIT_FAILED
        print(f"created {path}  ({kind}, schema_version {version}, checks clean)")
        results.append((path, version))
    return 0


def _interactive():
    return sys.stdin is not None and sys.stdin.isatty()


def offer_first_master(master_path):
    """Ask for the first Master's details and create it. Returns an exit code."""
    if not _interactive():
        print("No terminal attached: the first Master was not created. Run --apply in a terminal to create it.")
        return 0
    if input("Create the first Master now? [y/N] ").strip().lower() not in ("y", "yes"):
        print("Skipped: no first Master was created.")
        return 0
    username = input("Master username: ").strip()
    first_name = input("First name: ").strip()
    last_name = input("Last name: ").strip()
    email = input("Email: ").strip()
    secret = getpass.getpass("Password (at least 12 characters, not shown): ")
    repeated = getpass.getpass("Repeat the password: ")
    if secret != repeated:
        print("The passwords do not match; no Master was created.")
        return EXIT_FAILED
    try:
        created = auth.create_first_master(master_path, username, secret, first_name, last_name, email,
                                           machine_wrap=platform_support.DPAPI)
    except ServiceError as error:
        print(f"No Master was created: {error}")
        return EXIT_FAILED
    print("")
    print(f"Master '{username}' created.")
    print("RECOVERY CODE: " + created.recovery_code)
    if created.ledger_key_locked:
        print(first_run_model.KEY_LOCKED_NOTICE)
    print("Store this safely, offline. It is shown only once and is the only way to reset the Master password.")
    print("")
    return 0


def find_master_user(master_path):
    """(user_id, username, first_name) of the existing active Master, or None."""
    if not os.path.isfile(master_path):
        return None
    conn = sqlite3.connect(f"{Path(master_path).resolve().as_uri()}?mode=ro", uri=True)
    try:
        row = conn.execute("SELECT user_id, username, first_name FROM app_user WHERE is_master = 1 AND is_active = 1 "
                           "ORDER BY user_id LIMIT 1").fetchone()
    except sqlite3.Error:
        return None
    finally:
        conn.close()
    return row


def sample_company(master_path, code, apply):
    """Create one construction-template company for testing with the existing Master. Returns an exit code."""
    reasons = [f"the app appears to be running: {line}" for line in app_is_running()]
    if reasons:
        print("REFUSED:")
        for reason in reasons:
            print("  -", reason)
        return EXIT_REFUSED
    try:
        code = companies.check_company_code(code)
    except ServiceError as error:
        print(f"Not created: {error}")
        return EXIT_FAILED
    master = find_master_user(master_path)
    if master is None:
        print(f"Not created: {master_path} has no Master user. Run --apply first (it creates the Master), "
              "then run --sample-company again.")
        return EXIT_FAILED
    conn = sqlite3.connect(f"{Path(master_path).resolve().as_uri()}?mode=ro", uri=True)
    try:
        taken = conn.execute("SELECT 1 FROM company_registry WHERE company_code = ?", (code,)).fetchone()
    finally:
        conn.close()
    if taken:
        print(f"Not created: the company code {code} is already used.")
        return EXIT_FAILED
    user_id, username, first_name = master
    print(f"Sample company {code}: construction template, created by Master '{username}', "
          f"in {Path(config.BASE_PROJECT_DIR) / 'Companies' / (code + '.db')}")
    if not apply:
        print("Dry run complete; nothing was written. Add --apply to create it.")
        return 0
    provider = key_store.LocalKeyProvider(str(master_path), platform_support.DPAPI)   # as the app does at start-up
    if not provider.is_unlocked:
        print(KEY_LOCKED)
        return EXIT_FAILED
    keys.set_provider(provider)
    session = auth.Session(user_id=user_id, username=username, first_name=first_name, is_master=True,
                           legacy_role="Master", must_change_password=False, master_db_path=str(master_path))
    try:
        created = companies.create_company(session, legal_name=f"Sample Company {code}", code=code,
                                           first_fiscal_year=datetime.now().year, template="construction")
    except ServiceError as error:
        print(f"Not created: {error}")
        return EXIT_FAILED
    print(f"created sample company {created['company_code']} (company_id {created['company_id']}); "
          f"sign in as '{username}' to open it")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="write changes (default is a dry run)")
    parser.add_argument("--master-path", default=config.MASTER_DB_PATH)
    parser.add_argument("--backup-dir", default=config.BACKUP_DIR)
    parser.add_argument("--sample-company", metavar="CODE",
                        help="create one construction-template company for testing with the existing Master "
                             "(does not rebuild the master; no questions asked)")
    args = parser.parse_args(argv)
    if args.sample_company is not None:
        return sample_company(args.master_path, args.sample_company, args.apply)

    plan = build_plan(args.master_path, args.backup_dir)
    print_plan(plan, args.apply)
    reasons = refusals(plan)
    if reasons:
        print("REFUSED:")
        for reason in reasons:
            print("  -", reason)
        return EXIT_REFUSED
    if not args.apply:
        print("Dry run complete; nothing was written.")
        return 0
    result = apply_plan(plan)
    if result != 0:
        return result
    return offer_first_master(args.master_path)


if __name__ == "__main__":
    sys.exit(main())
