"""PreToolUse hook: run the full suite before any `git commit` and block the commit if it fails (CLAUDE.md 8).

Claude Code sends the tool call as JSON on stdin. Exit 0 lets the call run; exit 2 blocks it and shows stderr to
the session. Any command that is not a git commit passes straight through without running tests.

The suite runs in parallel workers (pytest-xdist, `-n auto`; owner 2026-11-18): about 5 minutes instead of 18.
`--dist loadgroup` keeps tests marked `xdist_group` in one worker. Without xdist the commit is blocked with what to
install, because a one-process run would outlast the hook's timeout. Plain `python -m pytest -q` still works.
"""
import importlib.util
import json
import os
import re
import subprocess
import sys

# git, then any global options (-C <path>, -c <key=value>, --flag[=value]), then the commit subcommand.
_COMMIT_RE = re.compile(
    r"(?:^|[\s;&|(])git(?:\.exe)?(?:\s+(?:-C\s+\S+|-c\s+\S+|--[\w-]+(?:=\S+)?))*\s+commit(?![-\w])")
_TAIL_LINES = 40


def is_git_commit(command):
    return bool(_COMMIT_RE.search(command or ""))


def suite_command():
    return [sys.executable, "-m", "pytest", "-q", "-n", "auto", "--dist", "loadgroup"]


def xdist_available():
    return importlib.util.find_spec("xdist") is not None


def run_suite(root):
    """Returns (exit code, the output's last lines)."""
    result = subprocess.run(suite_command(), cwd=root, capture_output=True, text=True)
    output = (result.stdout + result.stderr).strip().splitlines()
    return result.returncode, "\n".join(output[-_TAIL_LINES:])


def decide(payload, root):
    command = (payload.get("tool_input") or {}).get("command", "")
    if not is_git_commit(command):
        return 0, ""
    if not xdist_available():
        return 2, ("Commit blocked: the commit hook runs the suite with pytest-xdist, which is not installed. Run "
                   "pip install -r requirements-dev.txt, then commit again.")
    code, tail = run_suite(root)
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
        print(message, file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
