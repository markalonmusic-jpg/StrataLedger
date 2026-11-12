"""Static checks for CLAUDE.md rule 15 (portability, decisions H1, H2, H4, H5).

Services must port to FastAPI and PostgreSQL without a rewrite. Each check has an
allow-list of today's offenders. The lists can only shrink: an entry that no longer
offends fails the stale-entry test, and a new offender fails the main test.

Strings are checked, not docstrings or comments.
"""
import ast
import re

from tests.test_static_rules import ROOT, SERVICES_DIR, project_sources

# --- Shared scanning ------------------------------------------------------------------------


def _docstring_nodes(tree):
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                found.add(id(body[0].value))
    return found


def _walk_with_function(tree):
    """Yield (node, enclosing function name or '<module>') for every node."""
    def visit(node, function):
        yield node, function
        for child in ast.iter_child_nodes(node):
            name = child.name if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) else function
            yield from visit(child, name)
    yield from visit(tree, "<module>")


def service_sources():
    for path in sorted(SERVICES_DIR.glob("*.py")):
        yield path, path.name


def _parse(source_or_path):
    if hasattr(source_or_path, "read_text"):
        return ast.parse(source_or_path.read_text(encoding="utf-8"), filename=str(source_or_path))
    return ast.parse(source_or_path)


# --- H1: no UI or OS-specific imports in services -----------------------------------------

H1_BANNED_MODULES = ("tkinter", "_tkinter", "customtkinter", "winreg", "msvcrt", "win32", "pywin", "pythoncom")
H1_BANNED_NAMES = {"messagebox", "filedialog", "simpledialog"}
H1_BANNED_PREFIXES = ("modules.views_", "modules.ui_components")
# Entries are file names in modules/services/. Must stay empty.
H1_ALLOW_LIST = set()


def h1_violations(source):
    found = []
    for node in ast.walk(_parse(source)):
        modules = []
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            modules = [base] + [f"{base}.{alias.name}" for alias in node.names]
            if any(alias.name in H1_BANNED_NAMES for alias in node.names):
                found.append(node.lineno)
        for name in modules:
            top = name.split(".")[0]
            if top in H1_BANNED_MODULES or any(top.startswith(m) for m in ("win32", "pywin")) \
                    or name.startswith(H1_BANNED_PREFIXES):
                found.append(node.lineno)
    return sorted(set(found))


def h1_offenders():
    return {name: lines for path, name in service_sources() if (lines := h1_violations(path))}


def test_services_import_no_ui_or_os_specific_modules():
    new = {f: v for f, v in h1_offenders().items() if f not in H1_ALLOW_LIST}
    assert not new, f"UI or OS-specific import in modules/services/ (H1): {new}"


def test_h1_allow_list_has_no_stale_entries():
    assert not H1_ALLOW_LIST - set(h1_offenders())


def test_h1_checker_flags_ui_imports():
    for line in ("import tkinter", "from tkinter import messagebox", "import customtkinter as ctk",
                 "from tkinter.filedialog import askopenfilename", "import winreg",
                 "import modules.views_billing", "from modules.views_billing import Screen",
                 "from modules.ui_components import Button"):
        assert h1_violations(line), line
    assert not h1_violations("import os\nfrom pathlib import Path\nimport sqlite3")


# --- H2: services never read the system clock ---------------------------------------------

CLOCK_ATTRS = {("datetime", "now"), ("datetime", "utcnow"), ("date", "today"), ("datetime", "today")}
CLOCK_FUNCTIONS = {"utc_now_iso"}
# clock.py is the one place that reads the system clock. The context builders are where
# a context's `now` and `today` will be set (decision H2).
H2_EXEMPT_FILES = {"clock.py"}
H2_EXEMPT_FUNCTIONS = {"auth.py:login", "companies.py:open_company", "context.py:__post_init__"}
# Today's offenders ("file:function"); each is removed when Step 2.4 adds `now` and
# `today` to ServiceContext and these callers read them from the context.
H2_ALLOW_LIST = {
    # Throttle and recovery timestamps are written before any context exists (login,
    # recovery and first-Master creation run before a company is open), so this clock
    # stays until the auth functions take `now` as an argument.
    "auth.py:_now",
}


def h2_violations(source):
    """Return [(function, line)] for system-clock reads."""
    found = []
    for node, function in _walk_with_function(_parse(source)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) \
                and (func.value.id, func.attr) in CLOCK_ATTRS:
            found.append((function, node.lineno))
        elif isinstance(func, ast.Attribute) and isinstance(func.value, ast.Attribute) \
                and (func.value.attr, func.attr) in CLOCK_ATTRS:
            found.append((function, node.lineno))
        elif (isinstance(func, ast.Name) and func.id in CLOCK_FUNCTIONS) \
                or (isinstance(func, ast.Attribute) and func.attr in CLOCK_FUNCTIONS):
            found.append((function, node.lineno))
    return found


def h2_offenders():
    found = {}
    for path, name in service_sources():
        if name in H2_EXEMPT_FILES:
            continue
        for function, line in h2_violations(path):
            key = f"{name}:{function}"
            if key not in H2_EXEMPT_FUNCTIONS:
                found.setdefault(key, []).append(line)
    return found


def test_services_do_not_read_the_system_clock_outside_the_allow_list():
    new = {k: v for k, v in h2_offenders().items() if k not in H2_ALLOW_LIST}
    assert not new, f"system clock read in modules/services/ (H2): {new}"


def test_h2_allow_list_has_no_stale_entries():
    stale = H2_ALLOW_LIST - set(h2_offenders())
    assert not stale, f"remove from H2_ALLOW_LIST (no longer offending): {sorted(stale)}"


def test_h2_checker_flags_clock_reads():
    snippets = [
        "from datetime import datetime\ndef f():\n    return datetime.now()",
        "import datetime\ndef f():\n    return datetime.datetime.utcnow()",
        "from datetime import date\ndef f():\n    return date.today()",
        "def f():\n    return utc_now_iso()",
        "def f():\n    return clock.utc_now_iso()",
    ]
    for snippet in snippets:
        assert h2_violations(snippet), snippet
    assert not h2_violations("def f(context):\n    return context.now")


# --- H5: portable SQL in services -----------------------------------------------------------

H5_PATTERNS = [re.compile(p, re.IGNORECASE) for p in (
    r"date\s*\(\s*'now'", r"datetime\s*\(\s*'now'", r"strftime\s*\(", r"julianday\s*\(",
    r"insert\s+or\s+replace", r"group_concat", r"\bpragma\b",
)]
# Entries are file names in modules/services/. Must stay empty.
H5_ALLOW_LIST = set()


def h5_violations(source):
    tree = _parse(source)
    skip = _docstring_nodes(tree)
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in skip:
            if any(p.search(node.value) for p in H5_PATTERNS):
                found.append(node.lineno)
    return sorted(set(found))


def h5_offenders():
    return {name: lines for path, name in service_sources() if (lines := h5_violations(path))}


def test_service_sql_is_portable():
    new = {f: v for f, v in h5_offenders().items() if f not in H5_ALLOW_LIST}
    assert not new, f"SQLite-only SQL in modules/services/ (H5): {new}"


def test_h5_allow_list_has_no_stale_entries():
    assert not H5_ALLOW_LIST - set(h5_offenders())


def test_h5_checker_flags_sqlite_only_sql():
    for sql in ("SELECT date('now')", "select datetime( 'now' )", "SELECT strftime('%Y', d) FROM t",
                "SELECT julianday(a) - julianday(b)", "INSERT OR REPLACE INTO t VALUES (1)",
                "SELECT GROUP_CONCAT(name) FROM t"):
        assert h5_violations(f"conn.execute({sql!r})"), sql
    ok = "INSERT INTO t (id) VALUES (1) ON CONFLICT (id) DO UPDATE SET id = excluded.id"
    assert not h5_violations(f"conn.execute({ok!r})")
    assert not h5_violations('def f():\n    """Replaces date(\'now\') and strftime( calls."""\n    return 1')


# --- H4: audit_context is touched only in tx.py ---------------------------------------------

H4_ALLOWED_FILES = {"modules/services/tx.py"}
H4_ALLOWED_PREFIXES = ("tests/", "tools/", "scripts/")
# Entries are project-relative paths. Must stay empty.
H4_ALLOW_LIST = set()


def h4_violations(source):
    tree = _parse(source)
    skip = _docstring_nodes(tree)
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in skip \
                and "audit_context" in node.value:
            found.append(node.lineno)
        elif isinstance(node, ast.Name) and node.id == "audit_context":
            found.append(node.lineno)
        elif isinstance(node, ast.Attribute) and node.attr == "audit_context":
            found.append(node.lineno)
    return sorted(set(found))


def h4_offenders():
    found = {}
    for path, rel in project_sources():
        if rel in H4_ALLOWED_FILES or rel.startswith(H4_ALLOWED_PREFIXES):
            continue
        lines = h4_violations(path)
        if lines:
            found[rel] = lines
    return found


def test_audit_context_is_touched_only_in_tx_py():
    new = {f: v for f, v in h4_offenders().items() if f not in H4_ALLOW_LIST}
    assert not new, f"audit_context outside modules/services/tx.py (H4): {new}"


def test_h4_allow_list_has_no_stale_entries():
    assert not H4_ALLOW_LIST - set(h4_offenders())


def test_h4_checker_flags_audit_context_access():
    assert h4_violations("conn.execute('UPDATE audit_context SET user_id = 1')")
    assert h4_violations("x = audit_context")
    assert h4_violations("x = db.audit_context")
    assert not h4_violations('def f():\n    """Sets audit_context."""\n    return 1')
    assert not h4_violations("conn.execute('UPDATE app_user SET x = 1')")


def test_tx_py_is_the_one_place_that_sets_it():
    assert h4_violations(ROOT / "modules" / "services" / "tx.py")
