"""The add-on registry (Phase 2.7 STOP B, decisions HA3-HA5).

An add-on is a folder `RESOURCE_DIR/addons/<key>/` (the installation, never DATA_DIR: HA3) with:
* `addon.json`: {"key": "<key>", "name": "<shown to people>", "version": "<text>"}; the key matches the folder and
  passes `database.check_addon_key` (no key may own core tables);
* `addon.py`: `register(hooks)`, which calls `hooks.on(event, handler)` (modules/services/hooks.py);
* `migrations/<key>_NNN.sql`: its tables, applied by `database.apply_addon_migrations` (HA4, HA6).

This module is the only one that imports add-on code, by file path; core never imports an add-on (static test).
`list_addons`, `enable` and `disable` need `addon.manage` (Admin and the Master, HA5). enable applies pending
migrations, loads the code and writes `company_addon` (audit-logged by the baseline triggers). disable stops the
hooks and drops nothing. `prepare_company` runs when a company opens: it applies pending migrations of the add-ons
already enabled there and loads them; one that cannot be brought up to date is logged and marked, and posting then
says so (hooks.SETUP_FAILED) while the company still opens, so an Admin can disable it.
"""
import importlib.util
import json
import logging
import os

import config
import modules.database as database
from modules.services import hooks, storage
from modules.services.authz import authorize
from modules.services.errors import AddonError, NotFoundError, PermissionDeniedError, ValidationError
from modules.services.tx import AuditStamp, read_connection, write_transaction

MANAGE = "addon.manage"
RECORD_TYPE = "company_addon"
MANIFEST, ENTRY, MIGRATIONS = "addon.json", "addon.py", "migrations"
SETUP_REFUSED = ("The {name} add-on could not set up its tables, so it was not turned on. Nothing was changed; the "
                 "details are in the log.")
ADDONS_OFF = ("Add-ons are off because the program folder can be changed by this account; reinstall StrataLedger to "
              "Program Files.")

_logger = logging.getLogger("strataledger")


ADDONS = "addons"         # the folder under RESOURCE_DIR (read through storage.py, H3)


def addons_dir():
    """The one folder add-ons are found in: RESOURCE_DIR/addons, read at call time."""
    return storage.resource_path(ADDONS)


def _real(path):
    return os.path.normcase(os.path.realpath(path))


def _inside(path, folder):
    real, base = _real(path), _real(folder)
    try:
        return os.path.commonpath([real, base]) == base
    except ValueError:           # different drives
        return False


_folder_check = None      # path -> True if a non-admin can change it; handed over by the app (HA8)


def use_folder_check(check):
    """The app hands over platform_support.folder_open_to_non_admins at start-up (services never import the
    platform module, H1). None forgets it; a frozen build without one keeps add-ons off."""
    global _folder_check
    _folder_check = check


def addons_off():
    """HA8: in the installed (frozen) build, add-ons are off when a non-admin principal can change RESOURCE_DIR or
    RESOURCE_DIR/addons (the folder's ACL, read by the folder check), since anyone who can write there could plant
    code that runs in this process. Checked on every call, before any add-on file is read or imported, and logged.
    A run from source is exempt. Returns ADDONS_OFF (the sentence to show) or None."""
    if not config.FROZEN:
        return None
    if _folder_check is None:
        _logger.error("add-ons are off: no program-folder check was set up")
        return ADDONS_OFF
    folders = [("program folder", storage.resource_root()), ("add-ons folder", addons_dir())]
    loose = [name for name, path in folders if os.path.isdir(path) and _folder_check(path)]
    if not loose:
        return None
    _logger.error("add-ons are off: a non-admin account can change the %s under %s", " and ".join(loose),
                  config.RESOURCE_DIR)
    return ADDONS_OFF


def _refuse_if_off():
    reason = addons_off()
    if reason is not None:
        raise AddonError(reason)


def discover():
    """{key: {'key', 'name', 'version', 'entry', 'migrations'}} for every valid add-on folder. A folder with a bad
    manifest is skipped and logged. Nothing is imported here. storage.py keeps every path inside RESOURCE_DIR.
    Empty when add-ons are off (HA8, addons_off)."""
    if addons_off():
        return {}
    root = addons_dir()
    apart = _real(config.DATA_DIR) == _real(config.RESOURCE_DIR) or not (
        _inside(root, config.DATA_DIR) or _inside(config.DATA_DIR, root))     # the same root: running from source
    if not apart:
        _logger.error("add-ons folder %s is inside the data folder; add-ons load only from the installation", root)
        return {}
    found = {}
    for name in storage.list_resource_dirs(ADDONS):
        if MANIFEST not in storage.list_resources(f"{ADDONS}/{name}"):
            continue
        try:
            found[name] = _manifest(name)
        except (ValueError, NotFoundError, ValidationError, database.AddonKeyError) as error:
            _logger.error("add-on folder %s skipped: %s", name, error)
    return found


def _manifest(folder_name):
    data = json.loads(storage.read_resource_text(f"{ADDONS}/{folder_name}/{MANIFEST}"))
    if not isinstance(data, dict) or "key" not in data:
        raise ValueError("the manifest has no key")
    if data["key"] != folder_name:
        raise ValueError(f"the manifest key {data['key']!r} does not match its folder")
    database.check_addon_key(folder_name)
    for field in ("name", "version"):
        if not isinstance(data.get(field), str) or not data[field].strip():
            raise ValueError(f"the manifest has no {field}")
    if ENTRY not in storage.list_resources(f"{ADDONS}/{folder_name}"):
        raise ValueError(f"the folder has no {ENTRY}")
    return {"key": folder_name, "name": data["name"].strip(), "version": data["version"].strip(),
            "entry": storage.resource_path(f"{ADDONS}/{folder_name}/{ENTRY}"),
            "migrations": storage.resource_path(f"{ADDONS}/{folder_name}/{MIGRATIONS}")}


def load(addon_key):
    """Import an installed add-on's code and register its hooks, once per process. NotFoundError if it is not
    installed; AddonError if its code fails."""
    if hooks.is_loaded(addon_key):
        return
    _refuse_if_off()
    info = discover().get(addon_key)
    if info is None:
        raise NotFoundError(f"The {addon_key} add-on is not installed on this computer.")
    try:
        spec = importlib.util.spec_from_file_location(f"strataledger_addon_{addon_key}", info["entry"])
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        register = getattr(module, "register")
    except Exception as error:
        _logger.error("add-on %s could not be imported: %s", addon_key, hooks.describe_error(error))
        raise AddonError(hooks.START_FAILED.format(name=info["name"])) from None
    hooks.install(addon_key, info["name"], register)


def _company_rows(context):
    conn = read_connection(context.company_db_path)
    try:
        rows = {r["addon_key"]: dict(r) for r in conn.execute(
            "SELECT addon_key, enabled, addon_version FROM company_addon")}
        versions = {r["addon_key"]: r["version"] for r in conn.execute(
            "SELECT addon_key, MAX(version) AS version FROM addon_schema_version GROUP BY addon_key")}
    finally:
        conn.close()
    return rows, versions


def list_addons(context):
    """Every add-on installed on this computer or known to this company: [{'addon_key', 'name', 'version',
    'installed', 'enabled', 'schema_version'}], by key."""
    authorize(context, MANAGE, record_type=RECORD_TYPE)
    installed = discover()
    rows, versions = _company_rows(context)
    result = []
    for key in sorted(set(installed) | set(rows)):
        info, row = installed.get(key), rows.get(key)
        result.append({"addon_key": key, "name": info["name"] if info else key,
                       "version": info["version"] if info else row["addon_version"], "installed": info is not None,
                       "enabled": bool(row and row["enabled"]), "schema_version": versions.get(key, 0)})
    return result


def _migrate(context, info):
    """Apply the add-on's pending migrations; a refusal is logged and raised as ValidationError."""
    try:
        return database.apply_addon_migrations(context.company_db_path, info["key"], info["migrations"],
                                               audit=AuditStamp(context))
    except (database.AddonMigrationError, database.AddonKeyError) as error:
        _logger.error("add-on %s migrations refused: %s", info["key"], error)
        raise ValidationError(SETUP_REFUSED.format(name=info["name"])) from None


def enable(context, addon_key):
    """Turn an installed add-on on for this company: migrations, then its code, then the company_addon row.
    Returns {'addon_key', 'enabled': True, 'migrations_applied'}."""
    authorize(context, MANAGE, record_type=RECORD_TYPE)
    if context.read_only:
        raise PermissionDeniedError("This company is open read-only; open it with a role that can make changes, "
                                    "or ask an Admin.")
    _refuse_if_off()
    info = discover().get(addon_key)
    if info is None:
        raise NotFoundError("That add-on is not installed on this computer; install it first.")
    applied = _migrate(context, info)
    hooks.clear_broken(context.company_db_path, addon_key)
    load(addon_key)
    with write_transaction(context.company_db_path, context) as conn:
        conn.execute(
            "INSERT INTO company_addon (addon_key, enabled, enabled_at, enabled_by, addon_version) "
            "VALUES (?, 1, ?, ?, ?) ON CONFLICT (addon_key) DO UPDATE SET enabled = 1, "
            "enabled_at = excluded.enabled_at, enabled_by = excluded.enabled_by, addon_version = excluded.addon_version",
            (addon_key, context.now, context.user_id, info["version"]))
    return {"addon_key": addon_key, "enabled": True, "migrations_applied": applied}


def disable(context, addon_key):
    """Turn an add-on off for this company: its hooks stop; its tables and data stay. Returns {'addon_key',
    'enabled': False}."""
    authorize(context, MANAGE, record_type=RECORD_TYPE)
    with write_transaction(context.company_db_path, context) as conn:
        if conn.execute("SELECT 1 FROM company_addon WHERE addon_key = ?", (addon_key,)).fetchone() is None:
            raise NotFoundError("That add-on is not turned on for this company.")
        conn.execute("UPDATE company_addon SET enabled = 0 WHERE addon_key = ?", (addon_key,))
    return {"addon_key": addon_key, "enabled": False}


def prepare_company(context):
    """When a company opens: bring each enabled, installed add-on's tables up to date and load it. A failure is
    logged and the add-on marked for this company file, so its hooks refuse with a sentence while the company still
    opens. A read-only open applies no migrations. System upkeep like periods.ensure_upcoming_years: no permission
    applies (it runs as the opening user)."""
    rows, _ = _company_rows(context)
    installed = None
    for key in sorted(k for k, row in rows.items() if row["enabled"]):
        installed = discover() if installed is None else installed
        info = installed.get(key)
        if info is None:
            _logger.error("add-on %s is enabled in company %s but not installed", key, context.company_id)
            continue
        if not context.read_only:            # a read-only open (Auditor) writes nothing, add-on tables included
            try:
                _migrate(context, info)
            except ValidationError:
                hooks.mark_broken(context.company_db_path, key, info["name"])
                continue
            hooks.clear_broken(context.company_db_path, key)
        try:
            load(key)
        except AddonError:
            continue                       # logged by load; posting tries again and says so
