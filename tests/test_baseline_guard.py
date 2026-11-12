"""Pre-release guard: a database must have been built from the current baseline text.

Until the first release the schema is one baseline file per database kind
(CLAUDE.md section 5). A SHA-256 of that file is stored in each database when it
is built. Opening a file whose stored hash differs, is missing, or whose version
is above the baseline's is blocked, and the file is left unchanged. At first
release this guard is replaced by versioned migrations.
"""
import hashlib
import shutil
import sqlite3
from pathlib import Path

import pytest

import modules.database as database

KINDS = {
    "company": (lambda: database.MIGRATIONS, database.ensure_company_database),
    "master": (lambda: database.MASTER_MIGRATIONS, database.ensure_master_database),
}


def baseline_text(kind):
    migrations, _ = KINDS[kind]
    path = Path(database.MIGRATIONS_DIR) / migrations()[0][1]
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def ensure(kind, path):
    KINDS[kind][1](path)


@pytest.fixture(params=sorted(KINDS))
def kind(request):
    return request.param


def migrations_dir_with(tmp_path, monkeypatch, kind, text, newline="\n"):
    """A copy of migrations/ whose baseline file has the given text."""
    target = tmp_path / f"migrations_{abs(hash((kind, text, newline)))}"
    target.mkdir()
    for script in Path(database.MIGRATIONS_DIR).glob("*.sql"):
        shutil.copy2(script, target / script.name)
    baseline_name = KINDS[kind][0]()[0][1]
    with open(target / baseline_name, "w", encoding="utf-8", newline=newline) as handle:
        handle.write(text)
    monkeypatch.setattr(database, "MIGRATIONS_DIR", str(target))
    return target


def stored_hash(path):
    conn = sqlite3.connect(path)
    try:
        return conn.execute("SELECT sha256 FROM schema_baseline WHERE id = 1").fetchone()[0]
    finally:
        conn.close()


def test_build_stores_the_hash_of_the_baseline_text(kind, tmp_path, backup_dir):
    path = tmp_path / f"{kind}.db"
    ensure(kind, path)
    assert stored_hash(path) == hashlib.sha256(baseline_text(kind).encode("utf-8")).hexdigest()


def test_matching_file_opens_without_changes_or_backup(kind, tmp_path, backup_dir):
    path = tmp_path / f"{kind}.db"
    ensure(kind, path)
    original = path.read_bytes()

    ensure(kind, path)

    assert path.read_bytes() == original
    assert not backup_dir.exists()


def test_line_endings_do_not_change_the_hash(kind, tmp_path, backup_dir, monkeypatch):
    path = tmp_path / f"{kind}.db"
    ensure(kind, path)
    migrations_dir_with(tmp_path, monkeypatch, kind, baseline_text(kind), newline="\r\n")

    ensure(kind, path)  # same text with CRLF endings still matches


def test_file_built_from_older_baseline_text_is_blocked_and_unchanged(kind, tmp_path, backup_dir, monkeypatch):
    path = tmp_path / f"{kind}.db"
    with monkeypatch.context() as patch:
        migrations_dir_with(tmp_path, patch, kind, baseline_text(kind) + "\n-- an older edition\n")
        ensure(kind, path)
    original = path.read_bytes()

    with pytest.raises(database.SchemaUpgradeBlockedError) as error:
        ensure(kind, path)

    assert "scripts/create_fresh_databases.py" in error.value.reason
    assert path.read_bytes() == original
    assert not backup_dir.exists()


def test_file_with_version_above_the_baseline_is_blocked_and_unchanged(kind, tmp_path, backup_dir):
    path = tmp_path / f"{kind}.db"
    ensure(kind, path)
    conn = sqlite3.connect(path)
    conn.execute("INSERT INTO schema_version (version) VALUES (99)")
    conn.commit()
    conn.close()
    original = path.read_bytes()

    with pytest.raises(database.SchemaUpgradeBlockedError) as error:
        ensure(kind, path)

    assert "scripts/create_fresh_databases.py" in error.value.reason
    assert path.read_bytes() == original
    assert not backup_dir.exists()


def test_file_without_a_stored_hash_is_blocked_and_unchanged(kind, tmp_path, backup_dir):
    path = tmp_path / f"{kind}.db"
    ensure(kind, path)
    conn = sqlite3.connect(path)
    conn.execute("DROP TABLE schema_baseline")
    conn.commit()
    conn.close()
    original = path.read_bytes()

    with pytest.raises(database.SchemaUpgradeBlockedError):
        ensure(kind, path)

    assert path.read_bytes() == original


def test_existing_tables_without_schema_version_are_blocked_and_unchanged(kind, tmp_path, backup_dir):
    path = tmp_path / f"{kind}.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE contact (contact_id INTEGER PRIMARY KEY, display_name TEXT)")
    conn.commit()
    conn.close()
    original = path.read_bytes()

    with pytest.raises(database.SchemaUpgradeBlockedError) as error:
        ensure(kind, path)

    assert "scripts/create_fresh_databases.py" in error.value.reason
    assert path.read_bytes() == original
    assert not backup_dir.exists()


def test_empty_existing_file_is_built(kind, tmp_path, backup_dir):
    path = tmp_path / f"{kind}.db"
    sqlite3.connect(path).close()  # a zero-table file, e.g. just created

    ensure(kind, path)

    assert stored_hash(path)


CHAIN_DIR = Path(__file__).resolve().parent.parent / "archive" / "migrations_chain_v5"
CHAIN = {
    "company": [(1, "001_company.sql"), (2, "002_company.sql"), (3, "003_company.sql"),
                (4, "004_company.sql"), (5, "005_company.sql")],
    "master": [(1, "001_master.sql"), (2, "002_master.sql"), (3, "003_master.sql")],
}


@pytest.mark.parametrize("kind, version", [
    ("company", 4), ("company", 5), ("master", 1), ("master", 2), ("master", 3),  # chain company 001 alone fails its own FK check
])
def test_file_built_from_the_old_chain_is_blocked_and_unchanged(kind, version, tmp_path, backup_dir, monkeypatch):
    """Chain-built files (archive/migrations_chain_v5/), including version 1, are never taken for current."""
    path = tmp_path / f"{kind}.db"
    with monkeypatch.context() as patch:
        patch.setattr(database, "MIGRATIONS_DIR", str(CHAIN_DIR))
        patch.setattr(database, "MIGRATIONS", CHAIN["company"][:version] if kind == "company" else database.MIGRATIONS)
        patch.setattr(database, "MASTER_MIGRATIONS", CHAIN["master"][:version] if kind == "master" else database.MASTER_MIGRATIONS)
        ensure(kind, path)
    conn = sqlite3.connect(path)
    assert conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] == version
    conn.close()
    original = path.read_bytes()

    with pytest.raises(database.SchemaUpgradeBlockedError) as error:
        ensure(kind, path)

    assert "scripts/create_fresh_databases.py" in error.value.reason
    assert path.read_bytes() == original
    assert not backup_dir.exists()
