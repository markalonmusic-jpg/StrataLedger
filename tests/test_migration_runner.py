"""F1: the migration runner is atomic: a failed apply leaves the file exactly as it was."""
import re
import shutil
import sqlite3
from pathlib import Path

import pytest

import modules.database as database


def readonly(path):
    conn = sqlite3.connect(f"{Path(path).resolve().as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def table_names(conn):
    return {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    }


def assert_integrity_clean(path):
    conn = readonly(path)
    try:
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        assert [row[0] for row in conn.execute("PRAGMA integrity_check")] == ["ok"]
    finally:
        conn.close()


def _normalize(sql):
    return re.sub(r"\s+", " ", sql or "").strip().lower()


def schema_signature(path):
    """Structural view of a schema: columns, FKs and whitespace-normalized SQL."""
    conn = readonly(path)
    try:
        signature = {}
        for row in conn.execute(
            "SELECT type, name, tbl_name, sql FROM sqlite_master "
            "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
        ):
            entry = {"sql": _normalize(row["sql"])}
            if row["type"] == "table":
                entry["columns"] = [
                    tuple(col) for col in conn.execute(f'PRAGMA table_xinfo("{row["name"]}")')
                ]
                entry["fks"] = sorted(
                    tuple(fk)[2:] for fk in conn.execute(f'PRAGMA foreign_key_list("{row["name"]}")')
                )
            signature[(row["type"], row["name"])] = entry
        return signature
    finally:
        conn.close()


def schema_version(path):
    conn = readonly(path)
    try:
        if "schema_version" not in table_names(conn):
            return None
        return conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
    finally:
        conn.close()


@pytest.fixture
def migrations_with_failure(tmp_path, monkeypatch):
    """Copy the real migration scripts and append one failing company migration."""

    def _install(failing_sql):
        migration_dir = tmp_path / "migrations_with_failure"
        migration_dir.mkdir()
        for script in Path(database.MIGRATIONS_DIR).glob("*.sql"):
            shutil.copy2(script, migration_dir / script.name)
        (migration_dir / "099_fail.sql").write_text(failing_sql, encoding="utf-8")
        monkeypatch.setattr(database, "MIGRATIONS_DIR", str(migration_dir))
        monkeypatch.setattr(database, "MIGRATIONS", [*database.MIGRATIONS, (99, "099_fail.sql")])

    return _install


FAILING_MIGRATIONS = {
    "sql_error": "SELECT * FROM table_that_does_not_exist;\n",
    # Valid SQL that leaves a dangling reference only foreign_key_check can see.
    "fk_violation": (
        "INSERT INTO journal_line (entry_id, debit_cents, credit_cents) VALUES (999999, 0, 0);\n"
    ),
    # Scripts must not manage their own transactions.
    "own_transaction": "COMMIT;\n",
}


@pytest.mark.parametrize("failure", sorted(FAILING_MIGRATIONS))
def test_failing_migration_leaves_existing_file_unchanged(
    failure, tmp_path, backup_dir, migrations_with_failure
):
    db_path = tmp_path / "company.db"
    database.ensure_company_database(db_path)  # built with the real migrations
    original_bytes = db_path.read_bytes()
    version_before = schema_version(db_path)
    migrations_with_failure(FAILING_MIGRATIONS[failure])

    with pytest.raises(database.SchemaUpgradeBlockedError) as error:
        database.ensure_company_database(db_path)

    assert error.value.db_path == str(db_path)
    assert db_path.read_bytes() == original_bytes
    assert not Path(f"{db_path}-journal").exists()
    assert schema_version(db_path) == version_before
    assert len(list(backup_dir.glob("company_*.db"))) == 1


def test_failed_upgrade_of_new_file_leaves_no_file(tmp_path, backup_dir, migrations_with_failure):
    migrations_with_failure(FAILING_MIGRATIONS["sql_error"])
    db_path = tmp_path / "brand-new.db"

    with pytest.raises(database.SchemaUpgradeBlockedError):
        database.ensure_company_database(db_path)

    assert not db_path.exists()


@pytest.mark.parametrize("kind", ["company", "master"])
def test_apply_with_nothing_pending_changes_nothing(tmp_path, backup_dir, kind):
    """A second upgrade call that loses the race must not touch the file (seen on system_master.db)."""
    path = tmp_path / f"{kind}.db"
    if kind == "company":
        migrations = database.MIGRATIONS
        database.ensure_company_database(path)
    else:
        migrations = database.MASTER_MIGRATIONS
        database.ensure_master_database(path)
    before_bytes = path.read_bytes()
    before = schema_signature(path)

    # Simulates the losing caller: it passed the read-only version check
    # before the winner committed, so it goes straight to _apply_migrations.
    database._apply_migrations(path, migrations, kind)

    assert schema_signature(path) == before
    assert path.read_bytes() == before_bytes
