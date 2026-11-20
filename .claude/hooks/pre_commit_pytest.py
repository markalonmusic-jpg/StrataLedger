"""PreToolUse hook: run the full suite before any `git commit` and block the commit if it fails (CLAUDE.md 8).

Claude Code sends the tool call as JSON on stdin. Exit 0 lets the call run; exit 2 blocks it and shows stderr to
the session. Any command that is not a git commit passes straight through without running tests.

Docs-only commits skip the suite (owner 2026-11-19): when every staged file is under docs/, the hook prints one line,
"docs only: suite skipped (N files)", and records it in LAST_RUN. Anything else runs the full suite exactly as before:
a staged file outside docs/ (code, tests, migrations, .claude, the hook itself), a rename that moves a file into or
out of docs/ (renames are read as a delete plus an add, so both paths count), nothing staged, a git error, and any
commit whose staged set the hook cannot know at call time because the same command changes it (`git add`, `-a`,
`--amend`, a pathspec, `-C`, ...). So stage in one call and commit in the next to get the skip.

The suite runs in parallel workers (pytest-xdist, `-n auto`; owner 2026-11-18): about 5 minutes instead of 18.
Tests that use the system clipboard take turns through a lock (tests/conftest.py). Without xdist the commit is
blocked with what to install, because a one-process run would outlast the hook's timeout. Plain
`python -m pytest -q` still works. Every run writes the suite's last line (its pass, skip and fail counts) to
LAST_RUN in the system temp folder, so a passing commit's counts can be reported (owner 2026-11-18).
"""
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

# git, then any global options (-C <path>, -c <key=value>, --flag[=value]), then the commit subcommand.
_COMMIT_RE = re.compile(
    r"(?:^|[\s;&|(])git(?:\.exe)?(?:\s+(?:-C\s+\S+|-c\s+\S+|--[\w-]+(?:=\S+)?))*\s+commit(?![-\w])")
_TAIL_LINES = 40
DOCS_PREFIX = "docs/"
# A command that can change what the commit contains after the hook has looked: staging commands, commit flags that
# stage or rewrite (-a/--all, -am, --amend, --include, --only, -i, -o, a pathspec after --), and git -C. The test is
# deliberately wide (a message that mentions "git add" trips it): the cost of a false alarm is one suite run.
_STAGING_RE = re.compile(
    r"(?:^|[\s;&|(])git(?:\.exe)?(?:\s+(?:-c\s+\S+|--[\w-]+(?:=\S+)?))*\s+"
    r"(?:add|mv|rm|stash|reset|checkout|restore|apply|merge|cherry-pick|rebase|revert|pull)(?![-\w])"
    r"|(?:^|\s)git(?:\.exe)?\s+-C\s"
    r"|\scommit\b[^\n]*?\s(?:-[a-zA-Z]*[aio][a-zA-Z]*(?=\s|$)|--(?:all|amend|include|only|interactive|patch)\b|--(?=\s|$))")
LAST_RUN = Path(tempfile.gettempdir()) / "strataledger-commit-hook-last-run.txt"


def is_git_commit(command):
    return bool(_COMMIT_RE.search(command or ""))


def changes_staging(command):
    """True when the command itself can change what the commit holds, so the staged set seen now is not final."""
    return bool(_STAGING_RE.search(command or ""))


def staged_files(root):
    """Paths staged for the commit (a rename counts as its old and new path), or None when git cannot say."""
    try:
        result = subprocess.run(["git", "-C", str(root), "diff", "--cached", "--name-only", "--no-renames", "-z"],
                                capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return [name for name in result.stdout.split("\0") if name]


def docs_only(files):
    """True when there is at least one staged file and every one is under docs/."""
    return bool(files) and all(name.startswith(DOCS_PREFIX) for name in files)


def suite_command():
    return [sys.executable, "-m", "pytest", "-q", "-n", "auto"]


def xdist_available():
    return importlib.util.find_spec("xdist") is not None


def run_suite(root):
    """Returns (exit code, the output's last lines)."""
    result = subprocess.run(suite_command(), cwd=root, capture_output=True, text=True)
    output = (result.stdout + result.stderr).strip().splitlines()
    return result.returncode, "\n".join(output[-_TAIL_LINES:])


def record_result(tail):
    """Write the suite's last line to LAST_RUN. A failure to write never blocks or passes a commit by itself."""
    lines = tail.strip().splitlines()
    try:
        LAST_RUN.write_text((lines[-1] if lines else "") + "\n", encoding="utf-8")
    except OSError as error:
        print(f"Commit hook could not record the result in {LAST_RUN} ({type(error).__name__}).", file=sys.stderr)


def decide(payload, root):
    command = (payload.get("tool_input") or {}).get("command", "")
    if not is_git_commit(command):
        return 0, ""
    if not changes_staging(command):
        files = staged_files(root)
        if docs_only(files):
            line = f"docs only: suite skipped ({len(files)} file{'' if len(files) == 1 else 's'})"
            record_result(line)
            return 0, line
    if not xdist_available():
        return 2, ("Commit blocked: the commit hook runs the suite with pytest-xdist, which is not installed. Run "
                   "pip install -r requirements-dev.txt, then commit again.")
    code, tail = run_suite(root)
    record_result(tail)
    if code == 0:
        return 0, ""
    return 2, f"Commit blocked: python -m pytest -q -n auto failed (exit {code}). Fix the failures, then commit again.\n{tail}"


def main():
    try:
        payload = json.loads(sys.stdin.read())
    except ValueError as error:
        print(f"Commit hook could not read the tool call ({error}); the call was blocked.", file=sys.stderr)
        return 2
    root = os.environ.get("CLAUDE_PROJECT_DIR") or os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))
    code, message = decide(payload, root)
    if message:
        print(message, file=sys.stderr if code else sys.stdout)
    return code


if __name__ == "__main__":
    sys.exit(main())
