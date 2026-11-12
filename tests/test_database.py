import sqlite3
import shutil
from pathlib import Path

import pytest

import modules.database as database

LATEST_COMPANY = database.MIGRATIONS[-1][0]
LATEST_MASTER = database.MASTER_MIGRATIONS[-1][0]


@pytest.fixture

def backup_dir(tmp_path, monkeypatch):
    path = tmp_path / "Backups"
    monkeypatch.setattr(database, "BACKUP_DIR", str(path))
    return path


def test_fresh_company_reaches_latest_version(tmp_path, backup_dir):
    db_path = tmp_path / "fresh.db"

    database.ensure_company_database(db_path)

    with database.get_connection(db_path) as conn:
        assert conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] == LATEST_COMPANY
        names = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert {"account", "invoice", "invoice_line", "journal_line", "time_entry"} <= names
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_company_migrates_from_scripts_without_source_database(tmp_path, monkeypatch, backup_dir):
    migration_dir = tmp_path / "migrations"
    migration_dir.mkdir()
    for script in Path(database.MIGRATIONS_DIR).glob("*.sql"):
        shutil.copy2(script, migration_dir / script.name)
    monkeypatch.setattr(database, "MIGRATIONS_DIR", str(migration_dir))

    assert not (tmp_path / "accounting_librebase.db").exists()
    assert not hasattr(database, "SCHEMA_SOURCE_PATH")
    db_path = tmp_path / "offline-company.db"
    database.ensure_company_database(db_path)

    with database.get_connection(db_path) as conn:
        assert conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] == LATEST_COMPANY
        table_names = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert "account" in table_names
        assert "chart_of_accounts" not in table_names


def test_dimension_depth_four_is_rejected(tmp_path, backup_dir):
    db_path = tmp_path / "dimensions.db"
    database.ensure_company_database(db_path)

    with database.get_connection(db_path) as conn:
        dimension_type_id = conn.execute(
            "INSERT INTO dimension_type (name) VALUES (?) RETURNING dimension_type_id",
            ("Department",),
        ).fetchone()[0]
        parent_id = None
        for index in range(1, database.MAX_DIMENSION_DEPTH + 1):
            parent_id = conn.execute(
                "INSERT INTO dimension_value (dimension_type_id, code, name, parent_value_id) "
                "VALUES (?, ?, ?, ?) RETURNING dimension_value_id",
                (dimension_type_id, f"D{index}", f"Depth {index}", parent_id),
            ).fetchone()[0]

        with pytest.raises(sqlite3.IntegrityError, match="depth limit"):
            conn.execute(
                "INSERT INTO dimension_value (dimension_type_id, code, name, parent_value_id) "
                "VALUES (?, ?, ?, ?)",
                (dimension_type_id, "D4", "Depth 4", parent_id),
            )


def test_invoice_line_rejects_two_values_of_one_dimension_type(tmp_path, backup_dir):
    db_path = tmp_path / "line-dimensions.db"
    database.ensure_company_database(db_path)

    with database.get_connection(db_path) as conn:
        dimension_type_id = conn.execute(
            "INSERT INTO dimension_type (name) VALUES (?) RETURNING dimension_type_id",
            ("Department",),
        ).fetchone()[0]
        values = [
            conn.execute(
                "INSERT INTO dimension_value (dimension_type_id, code, name) VALUES (?, ?, ?) "
                "RETURNING dimension_value_id",
                (dimension_type_id, code, name),
            ).fetchone()[0]
            for code, name in (("OPS", "Operations"), ("SALES", "Sales"))
        ]
        line_id = conn.execute("INSERT INTO invoice_line DEFAULT VALUES RETURNING line_id").fetchone()[0]
        conn.execute(
            "INSERT INTO invoice_line_dimension (line_id, dimension_type_id, dimension_value_id) "
            "VALUES (?, ?, ?)",
            (line_id, dimension_type_id, values[0]),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO invoice_line_dimension (line_id, dimension_type_id, dimension_value_id) "
                "VALUES (?, ?, ?)",
                (line_id, dimension_type_id, values[1]),
            )


def test_running_migrations_twice_is_a_noop(tmp_path, backup_dir):
    db_path = tmp_path / "idempotent.db"
    database.ensure_company_database(db_path)
    with database.get_connection(db_path) as conn:
        before_tables = conn.execute(
            "SELECT name, sql FROM sqlite_master WHERE type IN ('table', 'trigger') ORDER BY type, name"
        ).fetchall()
        before_versions = conn.execute("SELECT version FROM schema_version ORDER BY version").fetchall()

    database.ensure_company_database(db_path)

    with database.get_connection(db_path) as conn:
        after_tables = conn.execute(
            "SELECT name, sql FROM sqlite_master WHERE type IN ('table', 'trigger') ORDER BY type, name"
        ).fetchall()
        after_versions = conn.execute("SELECT version FROM schema_version ORDER BY version").fetchall()
    assert after_tables == before_tables
    assert after_versions == before_versions
    assert not backup_dir.exists()
