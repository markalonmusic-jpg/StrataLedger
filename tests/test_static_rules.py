"""Static checks for CLAUDE.md rules 11 and 12.

The allow-lists name today's offenders by file. Each file is removed from its
list when Phase 3 rewrites it; the lists can only shrink (a stale entry fails
the test) and must be empty by the end of Phase 3.

Scanned: every .py and .pyw file in the project, except .venv, caches, git,
Outdated/ (the old prototype, not imported), Backups/ and Companies/.
"""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".venv", "__pycache__", ".git", "Outdated", ".pytest_cache", "Backups", "Companies"}

# Rule 11: sqlite3.connect is allowed in these places without being listed.
CONNECT_ALLOWED_FILES = {"modules/database.py"}
CONNECT_ALLOWED_PREFIXES = ("tests/", "scripts/", "tools/")

# Rule 11 offenders today. Remove each file when Phase 3 rewrites it.
CONNECT_ALLOW_LIST = {
    "app_strata.pyw",
    "modules/views_billing.py",
    "modules/views_payroll.py",
    "modules/views_registry.py",
    "modules/views_user_profile.py",
    "modules/views_wizard.py",
}

# Rule 12 offenders today (print in modules/). Remove each file when Phase 3
# rewrites it.
PRINT_ALLOW_LIST = {
    "modules/views_registry.py",
    "modules/views_wizard.py",
}


def project_sources():
    for pattern in ("*.py", "*.pyw"):
        for path in ROOT.rglob(pattern):
            rel = path.relative_to(ROOT)
            if SKIP_DIRS.intersection(rel.parts):
                continue
            yield path, rel.as_posix()


def find_calls(path, matcher):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return [n.lineno for n in ast.walk(tree) if isinstance(n, ast.Call) and matcher(n.func)]


def is_sqlite_connect(func):
    return (
        isinstance(func, ast.Attribute)
        and func.attr == "connect"
        and isinstance(func.value, ast.Name)
        and func.value.id == "sqlite3"
    )


def is_print(func):
    return isinstance(func, ast.Name) and func.id == "print"


def connect_offenders():
    found = {}
    for path, rel in project_sources():
        if rel in CONNECT_ALLOWED_FILES or rel.startswith(CONNECT_ALLOWED_PREFIXES):
            continue
        lines = find_calls(path, is_sqlite_connect)
        if lines:
            found[rel] = lines
    return found


def print_offenders():
    found = {}
    for path, rel in project_sources():
        if not rel.startswith("modules/"):
            continue
        lines = find_calls(path, is_print)
        if lines:
            found[rel] = lines
    return found


def test_no_sqlite_connect_outside_allowed_paths():
    new = {f: lines for f, lines in connect_offenders().items() if f not in CONNECT_ALLOW_LIST}
    assert not new, f"sqlite3.connect outside database.py (rule 11): {new}"


def test_connect_allow_list_has_no_stale_entries():
    stale = CONNECT_ALLOW_LIST - set(connect_offenders())
    assert not stale, f"remove from CONNECT_ALLOW_LIST (no longer offending): {sorted(stale)}"


def test_no_print_in_modules_outside_allow_list():
    new = {f: lines for f, lines in print_offenders().items() if f not in PRINT_ALLOW_LIST}
    assert not new, f"print() in modules/ (rule 12): {new}"


def test_print_allow_list_has_no_stale_entries():
    stale = PRINT_ALLOW_LIST - set(print_offenders())
    assert not stale, f"remove from PRINT_ALLOW_LIST (no longer offending): {sorted(stale)}"


def test_services_package_is_clean():
    offenders = list(connect_offenders()) + list(print_offenders())
    assert not [f for f in offenders if f.startswith("modules/services/")]


# --- Rule 10: every write service calls authorize first ------------------------------------
#
# A "writer" is any function in modules/services/ that opens a write path: it
# calls write_transaction or database.get_connection. It must call authorize
# (or a helper that itself calls authorize) on a line before that call, so the
# denial is logged in its own transaction before the caller's transaction exists.

SERVICES_DIR = ROOT / "modules" / "services"
WRITE_CALLS = {"write_transaction", "get_connection"}
AUTHORIZING_HELPERS = {"check_approval_limit", "check_company_access", "require_master", "authorize_reset"}
# A helper counts only if its own body calls authorize or a deny function.
DENY_CALLS = {"authorize", "deny", "_deny", "_deny_master"}
# Infrastructure that is not a permission-gated action:
#  * tx.py defines write_transaction itself;
#  * authz._write_access_event is the denial / company-open log writer:
#    authorizing it would recurse, and it must write even when the action is denied.
#  * auth.py: authentication itself, where no permission can apply yet:
#    create_first_master (bootstrap: only while the master has no users,
#    checked in the same transaction), change_password (self-service, proven
#    by the old password), recover_master (proven by the recovery code), and
#    _auth_write (the throttle / auth_event writer used by login and denials).
#  * periods.ensure_upcoming_years: system upkeep run by open_company (creates the fiscal years due within
#    60 days, decision S3); it runs as the opening user so the audit log shows who triggered it.
#  * ledger_verify._record: writes a verification result as a checkpoint. Its callers are verify_ledger, which
#    authorizes ledger.verify first; checkpoint_on_close, system upkeep when a company is closed or the app
#    exits (it signs the ledger head as the closing user; audit design 2.6); and record_close_checkpoint, which
#    authorizes period.close (called only by the period and year closes, after they authorized it).
RULE_10_EXCLUDED = {
    "tx.py:write_transaction", "authz.py:_write_access_event",
    "auth.py:create_first_master", "auth.py:change_password", "auth.py:recover_master", "auth.py:_auth_write",
    "periods.py:ensure_upcoming_years", "ledger_verify.py:_record",
}


def _call_name(node):
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def rule_10_violations(source, filename="snippet.py"):
    """Return the writer functions in source that do not authorize before writing."""
    tree = ast.parse(source)
    problems = []
    for func in [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
        if f"{filename}:{func.name}" in RULE_10_EXCLUDED:
            continue
        calls = [n for n in ast.walk(func) if isinstance(n, ast.Call)]
        writes = [n.lineno for n in calls if _call_name(n) in WRITE_CALLS]
        if not writes:
            continue
        authorizes = [n.lineno for n in calls if _call_name(n) in {"authorize"} | AUTHORIZING_HELPERS]
        if not authorizes or min(authorizes) >= min(writes):
            problems.append(f"{filename}:{func.name}")
    return problems


def test_every_write_service_authorizes_before_writing():
    problems = []
    for path in sorted(SERVICES_DIR.glob("*.py")):
        problems += rule_10_violations(path.read_text(encoding="utf-8"), path.name)
    assert problems == [], f"write without a prior authorize (rule 10): {problems}"


def test_rule_10_finds_some_writers():
    # Guards against the check passing because it sees nothing.
    writers = []
    for path in sorted(SERVICES_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for func in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
            if any(_call_name(n) in WRITE_CALLS for n in ast.walk(func) if isinstance(n, ast.Call)):
                writers.append(f"{path.name}:{func.name}")
    for expected in ("approvals.py:submit_for_approval", "approvals.py:approve", "approvals.py:reject",
                     "approvals.py:cancel_on_edit", "approvals.py:create_policy", "approvals.py:deactivate_policy",
                     "approvals.py:set_approval_limit", "authz.py:_write_access_event",
                     "users.py:create_user", "users.py:deactivate_user", "users.py:grant_access",
                     "users.py:set_role", "users.py:deny_access", "users.py:reset_password"):
        assert expected in writers


def test_authorizing_helpers_themselves_call_authorize():
    functions = {}
    for path in SERVICES_DIR.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        functions.update({n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)})
    for helper in AUTHORIZING_HELPERS:
        assert helper in functions, helper
        assert any(_call_name(n) in DENY_CALLS for n in ast.walk(functions[helper]) if isinstance(n, ast.Call)), helper


def test_password_hash_is_read_only_by_the_auth_services():
    # Rule 13: no screen, script or other module touches password_hash.
    allowed = {"modules/services/auth.py", "modules/services/users.py"}
    offenders = [rel for path, rel in project_sources()
                 if not rel.startswith("tests/") and rel not in allowed
                 and "password_hash" in path.read_text(encoding="utf-8")]
    assert offenders == []


def test_rule_10_checker_flags_a_writer_without_authorize():
    source = (
        "def bad(ctx):\n"
        "    with write_transaction(ctx.company_db_path, ctx) as conn:\n"
        "        conn.execute('DELETE FROM contact')\n"
    )
    assert rule_10_violations(source) == ["snippet.py:bad"]


def test_rule_10_checker_flags_authorize_inside_the_transaction():
    source = (
        "def late(ctx):\n"
        "    with write_transaction(ctx.company_db_path, ctx) as conn:\n"
        "        authorize(ctx, 'je.create')\n"
        "        conn.execute('DELETE FROM contact')\n"
    )
    assert rule_10_violations(source) == ["snippet.py:late"]


def test_rule_10_checker_passes_a_correct_writer():
    source = (
        "def good(ctx):\n"
        "    authorize(ctx, 'je.create')\n"
        "    with write_transaction(ctx.company_db_path, ctx) as conn:\n"
        "        conn.execute('INSERT INTO contact (name) VALUES (1)')\n"
        "def also_good(ctx):\n"
        "    check_approval_limit(ctx, 'Bill', 1)\n"
        "    conn = database.get_connection(ctx.company_db_path)\n"
    )
    assert rule_10_violations(source) == []
