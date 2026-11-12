import shutil

import pytest

import modules.database as database

# The tests never open real database files; every database is built in tmp_path.


@pytest.fixture
def backup_dir(tmp_path, monkeypatch):
    path = tmp_path / "Backups"
    monkeypatch.setattr(database, "BACKUP_DIR", str(path))
    return path


@pytest.fixture(scope="session")
def _company_template(tmp_path_factory):
    # A new file is never backed up, so BACKUP_DIR is not touched here.
    path = tmp_path_factory.mktemp("template") / "company.db"
    database.ensure_company_database(path)
    return path


@pytest.fixture
def fresh_company(tmp_path, backup_dir, _company_template):
    db_path = tmp_path / "company.db"
    shutil.copy2(_company_template, db_path)
    return db_path
