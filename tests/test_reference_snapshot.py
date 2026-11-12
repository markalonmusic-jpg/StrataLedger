import importlib.util
from pathlib import Path

import pytest

import modules.database as database
from tests.test_migration_runner import assert_integrity_clean, schema_signature, schema_version

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "build_reference_snapshot.py"


@pytest.fixture
def snapshot_module():
    spec = importlib.util.spec_from_file_location("build_reference_snapshot", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_snapshots_match_fresh_builds(tmp_path, backup_dir, snapshot_module):
    company_out = tmp_path / "out" / "accounting_librebase.db"
    master_out = tmp_path / "out" / "master_reference.db"
    fresh_company = tmp_path / "fresh_company.db"
    fresh_master = tmp_path / "fresh_master.db"
    database.ensure_company_database(fresh_company)
    database.ensure_master_database(fresh_master)

    snapshot_module.build_snapshots(company_out, master_out)

    assert schema_signature(company_out) == schema_signature(fresh_company)
    assert schema_signature(master_out) == schema_signature(fresh_master)
    assert schema_version(company_out) == database.MIGRATIONS[-1][0]
    assert_integrity_clean(company_out)
    assert_integrity_clean(master_out)


def test_existing_snapshot_needs_force(tmp_path, snapshot_module):
    out = tmp_path / "accounting_librebase.db"
    out.write_bytes(b"keep me")

    with pytest.raises(FileExistsError):
        snapshot_module.build_snapshots(out)
    assert out.read_bytes() == b"keep me"

    snapshot_module.build_snapshots(out, force=True)
    assert schema_version(out) == database.MIGRATIONS[-1][0]
