"""The package lists (decision KS1): `cryptography` is a pinned runtime requirement for the key store
(docs/audit_readiness_design.md 2.7, K2); PyInstaller and pytest are developer tools, listed only in
requirements-dev.txt, never in the runtime requirements the installed app needs.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT / "requirements.txt"
DEV = ROOT / "requirements-dev.txt"
DEV_TOOLS = ("pyinstaller", "pytest")


def _requirements(path):
    lines = [line.split("#", 1)[0].strip() for line in path.read_text(encoding="utf-8").splitlines()]
    return [line for line in lines if line]


def _name(requirement):
    return re.split(r"[<>=!~\[ ;]", requirement, maxsplit=1)[0].lower()


def test_cryptography_is_a_pinned_runtime_requirement():
    pins = [r for r in _requirements(RUNTIME) if _name(r) == "cryptography"]
    assert len(pins) == 1 and re.fullmatch(r"cryptography==\d+(\.\d+)+", pins[0].replace(" ", "")), pins


def test_developer_tools_stay_out_of_the_runtime_requirements():
    assert not {_name(r) for r in _requirements(RUNTIME)} & set(DEV_TOOLS)


def test_the_developer_requirements_include_the_runtime_ones_and_the_tools():
    dev = _requirements(DEV)
    assert "-r requirements.txt" in dev
    assert {_name(r) for r in dev if not r.startswith("-r")} >= set(DEV_TOOLS)


def test_the_installed_cryptography_matches_the_pin_and_has_aes_gcm():
    import cryptography
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    [pin] = [r for r in _requirements(RUNTIME) if _name(r) == "cryptography"]
    assert cryptography.__version__ == pin.split("==", 1)[1].strip()
    assert len(AESGCM.generate_key(256)) == 32
