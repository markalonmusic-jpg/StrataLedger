"""platform_support.machine_protect / machine_unprotect: the DPAPI wrap of the installation key (Step 1c, KS;
docs/audit_readiness_design.md 2.7).

The installation key is wrapped with DPAPI in MACHINE scope (CRYPTPROTECT_LOCAL_MACHINE), so every Windows account
on the computer can open the app (P1), never with a prompt (CRYPTPROTECT_UI_FORBIDDEN), and with a fixed StrataLedger
label as extra entropy so a blob from another program does not open as ours. A failure is one typed error with fixed
text: never the data, never the Windows detail, no chained cause. Services never call this module (H1); the app
hands these two functions to the key store at start-up.
"""
import logging
import re
import subprocess
import sys
from pathlib import Path

import pytest

from modules import platform_support
from modules.platform_support import MACHINE_KEY_UNAVAILABLE, MachineKeyError, machine_protect, machine_unprotect

windows_only = pytest.mark.skipif(sys.platform != "win32", reason="DPAPI exists only on Windows")
KEY = bytes(range(32))
ROOT = Path(__file__).resolve().parent.parent


# --- The real DPAPI (Windows) ---------------------------------------------------------------------------------------

@windows_only
def test_a_wrapped_key_unwraps_to_the_same_bytes():
    assert machine_unprotect(machine_protect(KEY)) == KEY


@windows_only
def test_the_wrapped_blob_does_not_hold_the_key_in_clear():
    blob = machine_protect(KEY)
    assert isinstance(blob, bytes) and len(blob) > len(KEY)
    assert KEY not in blob and KEY.hex().encode() not in blob


@windows_only
def test_wrapping_the_same_key_twice_gives_different_blobs():
    assert machine_protect(KEY) != machine_protect(KEY)


@windows_only
def test_a_changed_blob_is_refused_with_the_fixed_message():
    blob = bytearray(machine_protect(KEY))
    blob[-1] ^= 0x01
    with pytest.raises(MachineKeyError) as caught:
        machine_unprotect(bytes(blob))
    assert str(caught.value) == MACHINE_KEY_UNAVAILABLE
    assert caught.value.__cause__ is None and caught.value.__suppress_context__


@windows_only
def test_a_blob_wrapped_without_the_strataledger_label_is_refused():
    other = platform_support._call_dpapi("protect", KEY, b"another program", platform_support.PROTECT_FLAGS)
    with pytest.raises(MachineKeyError):
        machine_unprotect(other)


@windows_only
def test_a_blob_unwraps_in_another_process():
    """Machine scope is not tied to this process: a later start of the app opens what an earlier one wrapped."""
    blob = machine_protect(KEY)
    code = ("import sys; from modules.platform_support import machine_unprotect; "
            "sys.stdout.write(machine_unprotect(bytes.fromhex(sys.argv[1])).hex())")
    out = subprocess.run([sys.executable, "-c", code, blob.hex()], cwd=ROOT, capture_output=True, text=True,
                         check=True, timeout=60)
    assert out.stdout == KEY.hex()


@windows_only
def test_garbage_and_an_empty_blob_are_refused():
    for blob in (b"not a dpapi blob", b"\x00" * 64):
        with pytest.raises(MachineKeyError):
            machine_unprotect(blob)
    with pytest.raises(ValueError):
        machine_unprotect(b"")


# --- What is asked of Windows, and how failures look (no real DPAPI needed) -----------------------------------------

@pytest.fixture
def fake_dpapi(monkeypatch):
    calls = []

    def fake(direction, data, entropy, flags):
        calls.append((direction, data, entropy, flags))
        return b"wrapped:" + data if direction == "protect" else data[len(b"wrapped:"):]

    monkeypatch.setattr(platform_support, "IS_WINDOWS", True)
    monkeypatch.setattr(platform_support, "_call_dpapi", fake)
    return calls


def test_protect_asks_for_machine_scope_no_prompt_and_the_strataledger_label(fake_dpapi):
    machine_protect(KEY)
    [(direction, data, entropy, flags)] = fake_dpapi
    assert direction == "protect" and data == KEY
    assert flags == platform_support.PROTECT_FLAGS == 0x1 | 0x4      # UI_FORBIDDEN | LOCAL_MACHINE
    assert entropy == platform_support.DPAPI_ENTROPY == b"StrataLedger installation key v1"


def test_unprotect_never_prompts_and_uses_the_same_label(fake_dpapi):
    assert machine_unprotect(b"wrapped:" + KEY) == KEY
    [(direction, _data, entropy, flags)] = fake_dpapi
    assert direction == "unprotect" and flags == platform_support.UNPROTECT_FLAGS == 0x1
    assert entropy == platform_support.DPAPI_ENTROPY


def test_only_non_empty_bytes_are_accepted(fake_dpapi):
    for bad in ("text", bytearray(KEY), None, 32):
        with pytest.raises(TypeError):
            machine_protect(bad)
        with pytest.raises(TypeError):
            machine_unprotect(bad)
    with pytest.raises(ValueError):
        machine_protect(b"")
    assert fake_dpapi == []


def test_off_windows_both_refuse_without_calling_windows(monkeypatch):
    def never(*_args):
        raise AssertionError("DPAPI was called off Windows")
    monkeypatch.setattr(platform_support, "IS_WINDOWS", False)
    monkeypatch.setattr(platform_support, "_call_dpapi", never)
    for call, value in ((machine_protect, KEY), (machine_unprotect, b"blob")):
        with pytest.raises(MachineKeyError) as caught:
            call(value)
        assert str(caught.value) == MACHINE_KEY_UNAVAILABLE


def test_a_failing_windows_call_gives_the_fixed_error_and_never_the_detail(monkeypatch, caplog):
    def broken(direction, data, entropy, flags):
        raise OSError(f"detail that must not escape {data.hex()}")
    monkeypatch.setattr(platform_support, "IS_WINDOWS", True)
    monkeypatch.setattr(platform_support, "_call_dpapi", broken)
    caplog.set_level(logging.DEBUG)
    for call, value in ((machine_protect, KEY), (machine_unprotect, KEY)):
        with pytest.raises(MachineKeyError) as caught:
            call(value)
        assert str(caught.value) == MACHINE_KEY_UNAVAILABLE
        assert caught.value.__cause__ is None and caught.value.__suppress_context__
    assert KEY.hex() not in caplog.text and "must not escape" not in caplog.text
    assert "OSError" in caplog.text


def test_the_error_and_its_repr_never_hold_the_data(fake_dpapi):
    error = MachineKeyError(MACHINE_KEY_UNAVAILABLE)
    assert KEY.hex() not in repr(error) and str(error) == MACHINE_KEY_UNAVAILABLE


# --- Where DPAPI lives -----------------------------------------------------------------------------------------------

def test_dpapi_is_called_only_from_the_platform_module():
    pattern = re.compile(r"CryptProtectData|CryptUnprotectData|crypt32", re.IGNORECASE)
    offenders = [str(p.relative_to(ROOT)) for p in list((ROOT / "modules").rglob("*.py")) + [ROOT / "app_strata.pyw"]
                 if p.name != "platform_support.py" and pattern.search(p.read_text(encoding="utf-8"))]
    assert offenders == []
