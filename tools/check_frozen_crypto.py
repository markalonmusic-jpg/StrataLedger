"""Check that `cryptography` still works inside a PyInstaller one-file build (decisions K2, KS1).

Builds a tiny program that wraps and unwraps a 32-byte key with AES-256-GCM (and rejects the wrong associated
data) and derives a key with hashlib.scrypt, then runs the frozen exe. Everything is built in a temporary folder
outside the repository and removed afterwards. Run it after upgrading `cryptography` or PyInstaller:

    python tools/check_frozen_crypto.py

Needs requirements-dev.txt installed. Exit code 0 means the frozen build works.
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PROGRAM = '''
import hashlib, os, sys
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
key = AESGCM.generate_key(256)
nonce = os.urandom(12)
blob = AESGCM(key).encrypt(nonce, b"k" * 32, b"StrataLedger build check")
assert AESGCM(key).decrypt(nonce, blob, b"StrataLedger build check") == b"k" * 32
try:
    AESGCM(key).decrypt(nonce, blob, b"wrong")
    sys.exit("wrong associated data was accepted")
except InvalidTag:
    pass
assert len(hashlib.scrypt(b"c", salt=os.urandom(16), n=2 ** 15, r=8, p=1, dklen=32, maxmem=64 * 1024 * 1024)) == 32
assert getattr(sys, "frozen", False), "not running frozen"
print("frozen build: AES-GCM and scrypt OK")
'''


def main():
    work = Path(tempfile.mkdtemp(prefix="strataledger_pyi_"))
    try:
        source = work / "crypto_build_check.py"
        source.write_text(PROGRAM, encoding="utf-8")
        subprocess.run([sys.executable, "-m", "PyInstaller", "--onefile", "--noconfirm", "--log-level", "WARN",
                        "--distpath", str(work / "dist"), "--workpath", str(work / "build"),
                        "--specpath", str(work), str(source)], check=True)
        exe = next((work / "dist").glob("crypto_build_check*"))
        print(f"built {exe.name}: {exe.stat().st_size / 1e6:.1f} MB")
        return subprocess.run([str(exe)], check=False).returncode
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
