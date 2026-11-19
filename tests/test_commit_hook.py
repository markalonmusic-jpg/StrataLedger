"""The PreToolUse commit hook (owner 2026-11-18; CLAUDE.md section 8).

.claude/hooks/pre_commit_pytest.py runs `python -m pytest -q` before any `git commit` a Bash or PowerShell tool
call makes, and blocks the commit (exit code 2) when the suite fails. Any other command passes straight through.
The suite runs in parallel workers (`-n auto`, pytest-xdist, owner 2026-11-18); without xdist the commit is
blocked with what to install.
"""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parent.parent / ".claude" / "hooks" / "pre_commit_pytest.py"
SETTINGS = Path(__file__).resolve().parent.parent / ".claude" / "settings.json"


def load_hook():
    spec = importlib.util.spec_from_file_location("pre_commit_pytest", HOOK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
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


def test_settings_wire_the_hook_for_bash_and_powershell():
    settings = json.loads(SETTINGS.read_text(encoding="utf-8"))
    entries = settings["hooks"]["PreToolUse"]
    wired = [e for e in entries if any("pre_commit_pytest.py" in h["command"] for h in e["hooks"])]
    assert len(wired) == 1
    assert set(wired[0]["matcher"].split("|")) == {"Bash", "PowerShell"}
    # with -n auto the full suite took about 5 minutes on 2026-11-18 (18 minutes in one process); one run took
    # 862 s, so the owner raised the timeout to 1500 s as a stopgap (2026-11-19)
    assert 600 <= wired[0]["hooks"][0]["timeout"] <= 1500


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
