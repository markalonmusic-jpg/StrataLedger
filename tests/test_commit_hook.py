"""The PreToolUse commit hook (owner 2026-11-18; CLAUDE.md section 8).

.claude/hooks/pre_commit_pytest.py runs `python -m pytest -q` before any `git commit` a Bash or PowerShell tool
call makes, and blocks the commit (exit code 2) when the suite fails. Any other command passes straight through.
The suite runs in parallel workers (`-n auto`, pytest-xdist, owner 2026-11-18); without xdist the commit is
blocked with what to install.
"""
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parent.parent / ".claude" / "hooks" / "pre_commit_pytest.py"
GIT_HOOK = Path(__file__).resolve().parent.parent / ".githooks" / "pre-commit"
ROOT = Path(__file__).resolve().parent.parent


def load_hook(staged=None, real_git=False):
    """The hook module. staged_files is pinned (default None: "git cannot say", so the suite runs) so no test depends
    on what happens to be staged in this repo; real_git=True keeps the real function for the temp-repo tests."""
    spec = importlib.util.spec_from_file_location("pre_commit_pytest", HOOK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not real_git:
        module.staged_files = lambda root: staged
    return module


@pytest.mark.parametrize("command", [
    "git commit -m 'B2'",
    "git -C C:/x commit -m x",
    "git -c user.name=x commit --amend",
    "git --no-pager commit -F msg.txt",
    "cd repo && git commit -m x",
    "git add a.py; git commit -m x",
    "git status\ngit commit -m @'\nmessage\n'@",
    "git.exe commit -m x",
    "(git commit -m x)",
])
def test_a_commit_is_recognised(command):
    assert load_hook().is_git_commit(command)


@pytest.mark.parametrize("command", [
    "git status", "git log --oneline", "git log --grep commit", "git commit-tree abc", "git diff --cached",
    "python -m pytest -q", "git push origin main", "",
])
def test_other_commands_pass_through(command):
    assert not load_hook().is_git_commit(command)


def run_hook(payload):
    return subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload), capture_output=True, text=True,
                          timeout=60)


def test_a_non_commit_call_exits_zero_without_running_tests():
    result = run_hook({"tool_name": "Bash", "tool_input": {"command": "git status"}})
    assert result.returncode == 0
    assert result.stderr == ""


def test_a_failing_suite_blocks_the_commit_with_exit_code_2(monkeypatch):
    hook = load_hook()
    monkeypatch.setattr(hook, "run_suite", lambda root: (1, "1 failed, 10 passed"))
    code, message = hook.decide({"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}}, root=".")
    assert code == 2
    assert "1 failed, 10 passed" in message
    assert "commit blocked" in message.lower()


def test_a_passing_suite_lets_the_commit_through(monkeypatch):
    hook = load_hook()
    monkeypatch.setattr(hook, "run_suite", lambda root: (0, "10 passed"))
    assert hook.decide({"tool_name": "PowerShell", "tool_input": {"command": "git commit -m x"}}, root=".")[0] == 0


def test_every_suite_run_records_its_summary_line(monkeypatch, tmp_path):
    """Owner 2026-11-18: the hook's pass and skip counts are reported, so each run leaves its last line in LAST_RUN
    (the system temp folder, outside the repo), whether it passed or failed."""
    hook = load_hook()
    monkeypatch.setattr(hook, "LAST_RUN", tmp_path / "last.txt")
    commit = {"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}}
    monkeypatch.setattr(hook, "run_suite", lambda root: (0, "....\n3894 passed, 2 skipped in 288.00s"))
    assert hook.decide(commit, root=".")[0] == 0
    assert (tmp_path / "last.txt").read_text(encoding="utf-8") == "3894 passed, 2 skipped in 288.00s\n"
    monkeypatch.setattr(hook, "run_suite", lambda root: (1, "F\n1 failed, 10 passed in 2.00s"))
    assert hook.decide(commit, root=".")[0] == 2
    assert (tmp_path / "last.txt").read_text(encoding="utf-8") == "1 failed, 10 passed in 2.00s\n"


def test_a_non_commit_call_records_nothing(monkeypatch, tmp_path):
    hook = load_hook()
    monkeypatch.setattr(hook, "LAST_RUN", tmp_path / "last.txt")
    assert hook.decide({"tool_name": "Bash", "tool_input": {"command": "git status"}}, root=".") == (0, "")
    assert not (tmp_path / "last.txt").exists()


def test_the_record_lives_outside_the_repo():
    hook = load_hook()
    assert HOOK.parent.parent.parent not in Path(hook.LAST_RUN).resolve().parents


def test_unreadable_input_never_blocks_silently():
    result = subprocess.run([sys.executable, str(HOOK)], input="not json", capture_output=True, text=True, timeout=60)
    assert result.returncode == 2
    assert "could not read" in result.stderr.lower()


def test_tracked_git_pre_commit_hook_wires_the_existing_check_and_fails_closed():
    source = GIT_HOOK.read_text(encoding="utf-8")
    assert source.startswith("#!/bin/sh\n")
    assert "STRATALEDGER_PYTHON" in source
    assert "default_python='/c/Users/marka/AppData/Local/Programs/Python/Python311/python.exe'" in source
    assert "Commit blocked: no Python found" in source
    assert 'hook = root / ".claude" / "hooks" / "pre_commit_pytest.py"' in source
    assert 'payload = json.dumps({"tool_input": {"command": "git commit"}})' in source
    assert "timeout=1500" in source
    assert "if result.returncode != 0:" in source
    assert "sys.exit(result.returncode)" in source
    assert "test hook did not update the record file" in source
    tracked = subprocess.run(["git", "ls-files", "--error-unmatch", "--", ".githooks/pre-commit"],
                             cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert tracked.returncode == 0, tracked.stderr


def test_the_suite_runs_in_parallel_workers():
    hook = load_hook()
    assert hook.suite_command() == [sys.executable, "-m", "pytest", "-q", "-n", "auto"]


def test_the_suite_command_is_what_run_suite_runs(monkeypatch):
    hook = load_hook()
    seen = {}

    def fake_run(command, **kwargs):
        seen["command"] = command
        return subprocess.CompletedProcess(command, 0, stdout="1 passed", stderr="")
    monkeypatch.setattr(hook.subprocess, "run", fake_run)
    assert hook.run_suite(".") == (0, "1 passed")
    assert seen["command"] == hook.suite_command()


def test_without_xdist_the_commit_is_blocked_with_what_to_install(monkeypatch):
    """A serial run would outlast the hook's timeout, so the hook never falls back to one."""
    hook = load_hook()
    monkeypatch.setattr(hook, "xdist_available", lambda: False)
    monkeypatch.setattr(hook, "run_suite", lambda root: pytest.fail("the suite must not run without xdist"))
    code, message = hook.decide({"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}}, root=".")
    assert code == 2
    assert "pip install -r requirements-dev.txt" in message


def test_xdist_is_found_when_installed():
    pytest.importorskip("xdist")          # plain `python -m pytest -q` must pass without xdist (step-reviewer L4)
    assert load_hook().xdist_available()


def test_xdist_is_reported_missing_when_it_cannot_be_found(monkeypatch):
    hook = load_hook()
    monkeypatch.setattr(hook.importlib.util, "find_spec", lambda name: None)
    assert hook.xdist_available() is False


def test_plain_pytest_still_works_without_xdist():
    """No addopts turn on xdist, so `python -m pytest -q` runs in one process when xdist is absent or disabled."""
    result = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:xdist", "-p", "no:cacheprovider",
                             "tests/test_requirements.py"], cwd=HOOK.parent.parent.parent, capture_output=True,
                            text=True, timeout=300)
    assert result.returncode == 0, result.stdout[-2000:]


# --- docs-only commits skip the suite (owner 2026-11-19) ------------------------------------------------------

COMMIT = {"tool_name": "Bash", "tool_input": {"command": "git commit -q -F msg.txt"}}


def suite_must_not_run(root):
    pytest.fail("the suite must not run for a docs-only commit")


def test_a_commit_of_only_docs_files_skips_the_suite(monkeypatch, tmp_path):
    hook = load_hook(staged=["docs/next_step.md", "docs/replan_2.9/area_13_close_and_locks.md"])
    monkeypatch.setattr(hook, "LAST_RUN", tmp_path / "last.txt")
    monkeypatch.setattr(hook, "run_suite", suite_must_not_run)
    assert hook.decide(COMMIT, root=".") == (0, "docs only: suite skipped (2 files)")
    assert (tmp_path / "last.txt").read_text(encoding="utf-8") == "docs only: suite skipped (2 files)\n"


def test_one_staged_docs_file_is_worded_in_the_singular(monkeypatch, tmp_path):
    hook = load_hook(staged=["docs/status_log.md"])
    monkeypatch.setattr(hook, "LAST_RUN", tmp_path / "last.txt")
    monkeypatch.setattr(hook, "run_suite", suite_must_not_run)
    assert hook.decide(COMMIT, root=".") == (0, "docs only: suite skipped (1 file)")


def test_docs_plus_one_other_file_runs_the_full_suite(monkeypatch, tmp_path):
    hook = load_hook(staged=["docs/next_step.md", "modules/services/periods.py"])
    monkeypatch.setattr(hook, "LAST_RUN", tmp_path / "last.txt")
    ran = []
    monkeypatch.setattr(hook, "run_suite", lambda root: ran.append(root) or (0, "5 passed in 1.00s"))
    assert hook.decide(COMMIT, root=".") == (0, "")
    assert ran == ["."]
    assert (tmp_path / "last.txt").read_text(encoding="utf-8") == "5 passed in 1.00s\n"


@pytest.mark.parametrize("other", [
    "tests/test_commit_hook.py", "migrations/001_company.sql", ".claude/hooks/pre_commit_pytest.py",
    ".claude/settings.json", "CLAUDE.md", "documents/x.md", "docs", "scripts/docs/x.md",
])
def test_any_file_outside_docs_runs_the_suite(monkeypatch, tmp_path, other):
    """Only the path prefix docs/ counts: a look-alike (documents/, docs without the slash, a nested docs/) does not."""
    hook = load_hook(staged=["docs/a.md", other])
    monkeypatch.setattr(hook, "LAST_RUN", tmp_path / "last.txt")
    monkeypatch.setattr(hook, "run_suite", lambda root: (1, "1 failed in 1.00s"))
    assert hook.decide(COMMIT, root=".")[0] == 2


@pytest.mark.parametrize("staged", [None, []])
def test_nothing_staged_or_git_unreadable_runs_the_suite(monkeypatch, tmp_path, staged):
    hook = load_hook(staged=staged)
    monkeypatch.setattr(hook, "LAST_RUN", tmp_path / "last.txt")
    monkeypatch.setattr(hook, "run_suite", lambda root: (1, "1 failed in 1.00s"))
    assert hook.decide(COMMIT, root=".")[0] == 2


@pytest.mark.parametrize("command", [
    "git add docs/a.md && git commit -m x",
    "git add docs/a.md; git commit -m x",
    "git commit -a -m x",
    "git commit -am x",
    "git commit --all -m x",
    "git commit --amend --no-edit",
    "git commit -m x -- modules/a.py",
    "git commit --include modules/a.py -m x",
    "git commit --only modules/a.py -m x",
    "git -C ../elsewhere commit -m x",
    "git mv docs/a.md modules/a.md && git commit -m x",
])
def test_a_command_that_changes_the_staged_set_runs_the_suite(monkeypatch, tmp_path, command):
    """The hook looks before the command runs, so a staged set of docs only is not final when the same command stages
    or rewrites: those commits run the suite (stage in one call and commit in the next to get the skip)."""
    hook = load_hook(staged=["docs/a.md"])
    monkeypatch.setattr(hook, "LAST_RUN", tmp_path / "last.txt")
    monkeypatch.setattr(hook, "run_suite", lambda root: (1, "1 failed in 1.00s"))
    assert hook.decide({"tool_name": "Bash", "tool_input": {"command": command}}, root=".")[0] == 2


@pytest.mark.parametrize("command", [
    "git commit -q -F msg.txt", "git commit -m 'Area 12 fix'", "git commit --allow-empty -m x",
    "git commit -q -F - <<'EOF'\nArea 13 answers recorded\nEOF",
])
def test_a_plain_commit_command_is_eligible_for_the_skip(command):
    assert not load_hook().changes_staging(command)


def test_a_non_commit_call_never_asks_git_for_the_staged_files(monkeypatch):
    hook = load_hook()
    monkeypatch.setattr(hook, "staged_files", lambda root: pytest.fail("git must not be asked"))
    assert hook.decide({"tool_name": "Bash", "tool_input": {"command": "git status"}}, root=".") == (0, "")


# --- the staged list is read from git, renames included ---------------------------------------------------------

def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false",
                    *args], check=True, capture_output=True, text=True, timeout=60)


def make_repo(tmp_path):
    repo = tmp_path / "repo"
    (repo / "docs").mkdir(parents=True)
    (repo / "modules").mkdir()
    (repo / "docs" / "a.md").write_text("a\n", encoding="utf-8")
    (repo / "modules" / "x.py").write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(repo)], check=True, capture_output=True, timeout=60)
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "start")
    return repo


def decide_in(repo, monkeypatch, tmp_path):
    """The hook's verdict for a plain commit in repo, with the real staged_files; (decision, suite_ran)."""
    hook = load_hook(real_git=True)
    monkeypatch.setattr(hook, "LAST_RUN", tmp_path / "last.txt")
    ran = []
    monkeypatch.setattr(hook, "run_suite", lambda root: ran.append(root) or (0, "1 passed in 1.00s"))
    return hook.decide(COMMIT, root=str(repo)), bool(ran)


def test_the_docs_only_line_is_printed_to_stdout_with_exit_zero(tmp_path):
    """Run as the real hook, in a temp repo with only docs staged: exit 0 and the one line on stdout."""
    repo = make_repo(tmp_path)
    git(repo, "mv", "docs/a.md", "docs/b.md")
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(repo)}
    result = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(COMMIT), capture_output=True, text=True,
                            timeout=60, env=env)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "docs only: suite skipped (2 files)"      # a rename counts as old and new path
    assert result.stderr == ""


def test_staged_files_lists_what_git_has_staged(tmp_path):
    repo = make_repo(tmp_path)
    (repo / "docs" / "new.md").write_text("n\n", encoding="utf-8")
    git(repo, "add", "docs/new.md")
    assert load_hook(real_git=True).staged_files(str(repo)) == ["docs/new.md"]


def test_a_real_docs_only_commit_skips_and_a_real_code_commit_runs(tmp_path, monkeypatch):
    repo = make_repo(tmp_path)
    (repo / "docs" / "a.md").write_text("changed\n", encoding="utf-8")
    git(repo, "add", "docs/a.md")
    assert decide_in(repo, monkeypatch, tmp_path) == ((0, "docs only: suite skipped (1 file)"), False)
    (repo / "modules" / "x.py").write_text("x = 2\n", encoding="utf-8")
    git(repo, "add", "modules/x.py")
    assert decide_in(repo, monkeypatch, tmp_path) == ((0, ""), True)


def test_a_rename_out_of_docs_runs_the_suite(tmp_path, monkeypatch):
    """git sees docs/a.md -> modules/a.md as one rename whose new path is outside docs/; both paths are read."""
    repo = make_repo(tmp_path)
    git(repo, "mv", "docs/a.md", "modules/a.md")
    assert decide_in(repo, monkeypatch, tmp_path) == ((0, ""), True)


def test_a_rename_into_docs_runs_the_suite(tmp_path, monkeypatch):
    repo = make_repo(tmp_path)
    git(repo, "mv", "modules/x.py", "docs/x.py")
    assert decide_in(repo, monkeypatch, tmp_path) == ((0, ""), True)


def test_a_rename_inside_docs_is_still_docs_only(tmp_path, monkeypatch):
    repo = make_repo(tmp_path)
    git(repo, "mv", "docs/a.md", "docs/renamed.md")
    assert decide_in(repo, monkeypatch, tmp_path) == ((0, "docs only: suite skipped (2 files)"), False)


def test_a_deletion_outside_docs_runs_the_suite(tmp_path, monkeypatch):
    repo = make_repo(tmp_path)
    git(repo, "rm", "-q", "modules/x.py")
    assert decide_in(repo, monkeypatch, tmp_path) == ((0, ""), True)


def test_git_failing_in_a_folder_that_is_not_a_repo_runs_the_suite(tmp_path):
    assert load_hook(real_git=True).staged_files(str(tmp_path)) is None
