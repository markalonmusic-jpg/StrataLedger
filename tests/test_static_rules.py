"""Static checks for CLAUDE.md rules 11 and 12.

The allow-lists name today's offenders by file. Each file is removed from its
list when Phase 3 rewrites it; the lists can only shrink (a stale entry fails
the test) and must be empty by the end of Phase 3.

Scanned: every .py and .pyw file in the project, except .venv, caches, git,
Outdated/ (the old prototype, not imported), Backups/ and Companies/.
"""
import ast
from pathlib import Path

import pytest

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


# --- R19: screens pass a fresh context to every post, approval and close ----------------------

FRESH_CONTEXT_CALLS = {
    "ledger": {"post_journal_entry", "submit_entry_for_approval"},
    "approvals": {"approve", "reject"},
    "periods": {"close_period", "close_year", "set_books_closed_through"},
    "ledger_verify": {"checkpoint_on_close"},           # R26
}
_FRESH_BARE_NAMES = {"post_journal_entry", "submit_entry_for_approval", "close_period", "close_year",
                     "set_books_closed_through", "checkpoint_on_close"}


def _is_action_context_call(node):
    return isinstance(node, ast.Call) and _call_name(node) == "action_context"


def fresh_context_violations(source, filename="snippet.py"):
    """Calls to a post, approval or close service whose first argument is not an action_context() call."""
    problems = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            guarded = func.attr in FRESH_CONTEXT_CALLS.get(func.value.id, ())
        else:
            guarded = isinstance(func, ast.Name) and func.id in _FRESH_BARE_NAMES
        if guarded and not (node.args and _is_action_context_call(node.args[0])):
            problems.append(f"{filename}:{node.lineno}")
    return problems


def screen_sources():
    yield ROOT / "app_strata.pyw"
    yield from sorted((ROOT / "modules").glob("views_*.py"))
    yield from sorted((ROOT / "modules").glob("*_model.py"))      # a screen's model may call services too


def test_screens_pass_a_fresh_context_to_post_approve_and_close():
    paths = list(screen_sources())
    assert len(paths) > 5  # the scan sees the screens
    problems = []
    for path in paths:
        problems += fresh_context_violations(path.read_text(encoding="utf-8"), path.name)
    assert problems == [], f"pass self.app.action_context() (R19): {problems}"


def test_screens_do_not_import_the_guarded_functions_under_other_names():
    for path in screen_sources():
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.module in {f"modules.services.{m}" for m in FRESH_CONTEXT_CALLS}:
                guarded = FRESH_CONTEXT_CALLS[node.module.rsplit(".", 1)[1]]
                for alias in node.names:
                    assert alias.name not in guarded or alias.asname in (None, alias.name), (path.name, alias.name)
                    assert alias.name not in {"approve", "reject"}, (path.name, alias.name)


@pytest.mark.parametrize("call", [
    "ledger.post_journal_entry(self.app.context, 5)", "approvals.approve(ctx, 1)",
    "approvals.reject(self.context, 1, 'no')", "periods.close_period(self.app.context, 3)",
    "periods.close_year(c, 1)", "periods.set_books_closed_through(c, '2026-01-31')",
    "ledger.submit_entry_for_approval(c, 5)", "post_journal_entry(c, 5)", "ledger.post_journal_entry()",
    "ledger_verify.checkpoint_on_close(self.context)",
    "ledger.post_journal_entry(self.app.get_context(), 5)", "approvals.approve(fresh(), 1)",
    "ledger.post_journal_entry(context=self.app.action_context(), entry_id=5)",
])
def test_fresh_context_checker_flags_a_stored_context(call):
    assert fresh_context_violations(f"def f(self):\n    {call}\n") == ["snippet.py:2"]


@pytest.mark.parametrize("call", [
    "ledger.post_journal_entry(self.app.action_context(), 5)", "approvals.approve(self.app.action_context(), 1)",
    "periods.close_period(app.action_context(), 3, acknowledge_warnings=True)",
    "post_journal_entry(action_context(), 5)", "ledger.get_entry(self.app.context, 5)",
    "self.approve(self.app.context)",
])
def test_fresh_context_checker_passes_a_fresh_context(call):
    assert fresh_context_violations(f"def f(self):\n    {call}\n") == []


# --- Section 13 (R54): who may make document entries -------------------------------------------------------
#
# create_document_entry, as_system and as_import are the narrow path for document, import, payroll and
# conversion entries (docs/audit_readiness_design.md section 13). Only the modules below (paths relative to
# modules/) may name them, and a call to create_document_entry passes a literal source from that module's row.
# ledger.py defines the function (its auto-reversal and rounding paths need no call) and context.py defines the
# two context methods. Outside context.py, no module builds a context with any origin but a literal "Human"
# (ServiceContext(...) or a replace(..., origin=...)), so an Agent context cannot be rebuilt as System or Import.

DOCUMENT_ENTRY_CALLERS = {
    "services/billing.py": {"Invoice"},            # Step 7: payments are made only by services/payments.py
    "services/bills.py": {"Bill"},
    "services/payments.py": {"Payment"},
    "services/payroll_import.py": {"Payroll"},
    "services/imports.py": {"Import"},
    "services/conversion.py": {"Conversion"},
    "services/deferrals.py": {"Deferral"},
    "services/poc.py": {"Completion"},
    "services/ledger.py": set(),
}
DOCUMENT_ENTRY_NAMES = {"create_document_entry", "as_system", "as_import"}


def document_entry_violations(source, filename="snippet.py"):
    """Every use of the narrow path in source that its module may not make: a module outside the table naming it
    (called, passed on, imported under any name or looked up by string), or a create_document_entry call whose
    source is not a literal from the module's row."""
    allowed = DOCUMENT_ENTRY_CALLERS.get(filename)
    problems = []
    for node in ast.walk(ast.parse(source)):
        named = ((isinstance(node, ast.Name) and node.id in DOCUMENT_ENTRY_NAMES)
                 or (isinstance(node, ast.Attribute) and node.attr in DOCUMENT_ENTRY_NAMES)
                 or (isinstance(node, ast.Constant) and node.value in DOCUMENT_ENTRY_NAMES)
                 or (isinstance(node, ast.ImportFrom) and any(a.name in DOCUMENT_ENTRY_NAMES for a in node.names)))
        if named and allowed is None:
            problems.append(f"{filename}:{node.lineno}")
        if isinstance(node, ast.Call) and _call_name(node) in ("ServiceContext", "replace"):
            origins = [k.value for k in node.keywords if k.arg == "origin"]
            if _call_name(node) == "ServiceContext" and not origins:
                origins = node.args[2:3]
            if any(not (isinstance(o, ast.Constant) and o.value == "Human") for o in origins):
                problems.append(f"{filename}:{node.lineno}")
        if isinstance(node, ast.Call) and _call_name(node) == "create_document_entry" and allowed is not None:
            given = [k.value for k in node.keywords if k.arg == "source"]
            if not (len(given) == 1 and isinstance(given[0], ast.Constant) and given[0].value in allowed):
                problems.append(f"{filename}:{node.lineno}")
    return problems


def test_only_the_listed_modules_make_document_entries():
    paths = sorted((ROOT / "modules").rglob("*.py"))
    assert len(paths) > 20                                     # the scan sees the modules
    problems = []
    for path in paths:
        name = path.relative_to(ROOT / "modules").as_posix()
        if name == "services/context.py":
            continue                                           # defines as_system and as_import
        problems += document_entry_violations(path.read_text(encoding="utf-8"), name)
    assert problems == [], f"create_document_entry, as_system and as_import (section 13): {problems}"


def test_ledger_defines_the_narrow_path():
    source = (SERVICES_DIR / "ledger.py").read_text(encoding="utf-8")
    assert "def create_document_entry(conn, context, *," in source
    assert "def as_system(self)" in (SERVICES_DIR / "context.py").read_text(encoding="utf-8")


@pytest.mark.parametrize("filename, snippet", [
    ("views_billing.py", "ledger.create_document_entry(conn, ctx, source='Invoice', entry_date=d, lines=l)"),
    ("billing.py", "ledger.create_document_entry(conn, ctx, source='Invoice', entry_date=d, lines=l)"),
    ("other/billing.py", "ledger.create_document_entry(conn, ctx, source='Invoice', entry_date=d, lines=l)"),
    ("services/reports.py", "ctx2 = ctx.as_system()"),
    ("services/reports.py", "ctx2 = ctx.as_import()"),
    ("services/reports.py", "from modules.services.ledger import create_document_entry as make"),
    ("services/reports.py", "make = getattr(ledger, 'create_document_entry')"),
    ("services/reports.py", "run(ledger.create_document_entry)"),
    ("services/billing.py", "ledger.create_document_entry(conn, ctx, source=kind, entry_date=d, lines=l)"),
    ("services/billing.py", "ledger.create_document_entry(conn, ctx, source='Bill', entry_date=d, lines=l)"),
    # Step 7: payment entries come only from services/payments.py.
    ("services/billing.py", "ledger.create_document_entry(conn, ctx, source='Payment', entry_date=d, lines=l)"),
    ("services/billing.py", "ledger.create_document_entry(conn, ctx, entry_date=d, lines=l)"),
    ("services/billing.py", "ledger.create_document_entry(conn, ctx, **values)"),
    ("services/ledger.py", "create_document_entry(conn, ctx, source='Import', entry_date=d, lines=l)"),
    ("services/billing.py", "c = ServiceContext(user_id=1, company_id=1, origin='System', company_db_path=p, "
                            "master_db_path=m)"),
    ("services/reports.py", "c = ServiceContext(1, 1, 'Import', p, m)"),
    ("services/reports.py", "c = ServiceContext(user_id=1, company_id=1, origin=kind, company_db_path=p, "
                            "master_db_path=m)"),
    ("services/reports.py", "c = dataclasses.replace(ctx, origin='System')"),
    ("services/billing.py", "c = replace(ctx, origin=agent.origin)"),
])
def test_document_entry_checker_flags(filename, snippet):
    assert document_entry_violations(f"def f(conn, ctx):\n    {snippet}\n", filename) != []


@pytest.mark.parametrize("filename, snippet", [
    ("services/billing.py", "ledger.create_document_entry(conn, ctx.as_system(), source='Invoice', entry_date=d, "
                            "lines=l)"),
    ("services/payments.py", "ledger.create_document_entry(conn, ctx.as_system(), source='Payment', entry_date=d, "
                             "lines=l)"),
    ("services/imports.py", "ledger.create_document_entry(conn, ctx.as_import(), source='Import', entry_date=d, "
                            "lines=l)"),
    ("services/reports.py", "ledger.create_entry(ctx, entry_date=d)"),
    ("services/users.py", "c = ServiceContext(user_id=1, company_id=1, origin='Human', company_db_path=p, "
                          "master_db_path=m)"),
    ("services/reports.py", "c = dataclasses.replace(ctx, now=n, today=t)"),
])
def test_document_entry_checker_passes(filename, snippet):
    assert document_entry_violations(f"def f(conn, ctx):\n    {snippet}\n", filename) == []


# R59: only an allocation's application entry posts without document approval. Allow-lists only shrink.
APPROVAL_EXEMPT_CALLERS = {"payments.py"}


def approval_exemption_users(source):
    """Lines that pass exempt_from_approval to a call (the keyword, whatever its value)."""
    return [node.lineno for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Call) and any(k.arg == "exempt_from_approval" for k in node.keywords)]


def test_only_the_payments_service_posts_without_document_approval():
    users = {path.name for path in SERVICES_DIR.glob("*.py")
             if approval_exemption_users(path.read_text(encoding="utf-8"))}
    assert users <= APPROVAL_EXEMPT_CALLERS
    assert users == APPROVAL_EXEMPT_CALLERS, "the check sees no caller; did the keyword change?"


# R59: the void of a document's own entry and the release of allocations run only inside a document service's
# transaction (they do not authorize; their caller has). Today only the payments service calls them.
UNAUTHORIZED_HELPER_CALLERS = {"void_document_entry": {"payments.py"}, "release_allocations": set()}


def helper_callers(name):
    found = set()
    for path in SERVICES_DIR.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if any(isinstance(n, ast.Call) and _call_name(n) == name for n in ast.walk(tree)):
            found.add(path.name)
    return found


@pytest.mark.parametrize("name", sorted(UNAUTHORIZED_HELPER_CALLERS))
def test_document_void_helpers_have_only_their_listed_callers(name):
    assert helper_callers(name) <= UNAUTHORIZED_HELPER_CALLERS[name]


def test_the_approval_exemption_checker_finds_a_call():
    assert approval_exemption_users("ledger.create_document_entry(conn, ctx, exempt_from_approval=True)") == [1]
    assert approval_exemption_users("ledger.create_document_entry(conn, ctx, post=True)") == []


# Owner answers 2026-11-18: people see the product name "Melara" (config.APP_NAME), never StrataLedger. No string in
# modules/services/ or modules/database.py (whose refusals the services pass on) may hold "strataledger" in any
# case. Docstrings, comments and bytes (the key-derivation labels, which are identifiers) are not checked. The
# identifiers below (logger names, an environment variable, the add-on module prefix) keep the old name until the
# packaging step (U1) renames them; each is matched as the whole string, so no sentence can hide behind one. The
# list only shrinks: an entry no longer found fails. A run-time join ("Strata" + "Ledger") is not caught.
OLD_NAME = "strataledger"
OLD_NAME_IDENTIFIERS = {"strataledger", "strataledger.clock", "strataledger.keys", "strataledger_addon_",
                        "STRATALEDGER_ALLOW_TEST_KEYS"}


def old_name_strings(source, allowed=frozenset()):
    """Line numbers of str constants (f-string parts included, docstrings not) that name StrataLedger in any case,
    other than a constant that is exactly one of `allowed`."""
    tree = ast.parse(source)
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                docstrings.add(id(body[0].value))
    return [n.lineno for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and OLD_NAME in n.value.lower()
            and n.value not in allowed and id(n) not in docstrings]


def _old_name_scope():
    return [*sorted(SERVICES_DIR.glob("*.py")), ROOT / "modules" / "database.py"]


def test_no_service_string_names_strataledger():
    found = {path.name: lines for path in _old_name_scope()
             if (lines := old_name_strings(path.read_text(encoding="utf-8"), OLD_NAME_IDENTIFIERS))}
    assert found == {}, "user-facing text says config.APP_NAME, not StrataLedger"


def test_every_old_name_identifier_is_still_used():
    used = set()
    for path in _old_name_scope():
        used |= {n.value for n in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
                 if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    assert OLD_NAME_IDENTIFIERS <= used, "remove the renamed identifier from OLD_NAME_IDENTIFIERS"


def test_the_old_name_checker_finds_strings_and_skips_docstrings_comments_and_bytes():
    source = ('"""StrataLedger module."""\n'
              '# StrataLedger comment\n'
              'LABEL = b"StrataLedger key v1"\n'
              'LOGGER = "strataledger"\n'
              'A = "Reinstall StrataLedger."\n'
              'def f(zone):\n'
              '    """StrataLedger function."""\n'
              '    return f"{zone}: reinstall StrataLedger"\n'
              'B = "Open STRATALEDGER now"\n'
              'C = "the strataledger log"\n')
    assert sorted(old_name_strings(source)) == [4, 5, 8, 9, 10]
    assert sorted(old_name_strings(source, {"strataledger"})) == [5, 8, 9, 10]   # only the whole string is allowed


def test_the_product_name_is_melara():
    import config
    assert config.APP_NAME == "Melara"
