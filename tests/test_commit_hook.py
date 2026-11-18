"""The PreToolUse commit hook (owner 2026-11-18; CLAUDE.md section 8).

.claude/hooks/pre_commit_pytest.py runs `python -m pytest -q` before any `git commit` a Bash or PowerShell tool
call makes, and blocks the commit (exit code 2) when the suite fails. Any other command passes straight through.
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
    assert wired[0]["hooks"][0]["timeout"] >= 1800      # the full suite took 18 minutes on 2026-11-18
