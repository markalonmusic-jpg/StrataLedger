"""Hook events for add-ons (Phase 2.7 STOP B, decisions HA1 and HA2).

* `EVENTS`: `entry.posted` and `entry.voided` are fired by `ledger` (every posted entry, from `_seal_and_post`; a
  Void reversal also fires `entry.voided` for the entry it voids). `stage.entered` and `stage.left` are declared
  for the CRM step and fired by nothing yet.
* An add-on's `register(hooks)` gets a handle bound to its own key (`HookApi.on(event, handler)`); add-ons are
  found and imported by `modules/services/addons.py` only (HA3).
* `fire(conn, context, event, payload)` runs inside the caller's write transaction, after the caller's own writes.
  It runs the handlers of the add-ons enabled in this company (`company_addon.enabled = 1`), in key order, and is
  refused for an Agent context. An enabled add-on that is not loaded yet is loaded here.
* A handler is called as `handler(db, payload)`: `db.execute(sql, params)` returns the rows as dicts, and works
  only while the handler runs; `payload` is read-only and also holds the event, company, user and time. While it
  runs, `database.addon_write_guard` lets it write only its own `<key>_` tables (HA2).
* Any handler error (its own, or a refused write, even one the handler caught) is logged with its details and
  raised as AddonError with one sentence naming the add-on and the next step; the caller's transaction then rolls
  back.
* Trust (HA3, HA7): an add-on is code shipped in the installation and runs in this process. The authorizer and the
  narrow handle guard against an add-on's mistakes in SQL; they cannot stop Python code that sets out to get
  around them. Only RESOURCE_DIR/addons is trusted. The hosted version replaces the authorizer with a database
  role per add-on (docs/audit_readiness_design.md section 16).
"""
import logging
import traceback
from types import MappingProxyType

import modules.database as database
from modules.services import authz
from modules.services.errors import AddonError, DeferredDenialError, NotFoundError

EVENTS = frozenset({"entry.posted", "entry.voided", "stage.entered", "stage.left"})

FAILED = ("The {name} add-on could not finish, so nothing was saved; disable it in Company Settings > Add-ons and "
          "try again.")
NOT_INSTALLED = ("The {key} add-on is turned on for this company but is not installed on this computer; install it, "
                 "or disable it in Company Settings > Add-ons and try again.")
SETUP_FAILED = ("The {name} add-on could not set up its tables, so nothing was saved; disable it in Company "
                "Settings > Add-ons and try again.")
START_FAILED = ("The {name} add-on could not start, so nothing was saved; disable it in Company Settings > Add-ons "
                "and try again.")
AGENT_REFUSED = "Add-ons do not run for an agent's actions; a person does this."

_logger = logging.getLogger("strataledger")
_handlers = {}     # addon_key -> {event: [handler, ...]}
_names = {}        # addon_key -> name, for every loaded add-on
_broken = {}       # (company file, addon_key) -> name: its tables could not be brought up to date at company open


def describe_error(error):
    """For the log: an add-on error's type and where it was raised (file, line, function), never its message or
    source lines, which could quote data the add-on read (secrets audit LOW-2)."""
    frames = "; ".join(f"{frame.filename}:{frame.lineno} in {frame.name}"
                       for frame in traceback.extract_tb(error.__traceback__))
    return f"{type(error).__name__} at {frames or 'an unknown place'}"


def _check_event(event):
    if event not in EVENTS:
        raise ValueError(f"Unknown hook event {event!r}; the events are {', '.join(sorted(EVENTS))}")


class HookApi:
    """What an add-on's register() gets: `on(event, handler)` for its own key only."""

    __slots__ = ("_collected",)

    def __init__(self, addon_key, name):
        self._collected = {}

    def on(self, event, handler):
        _check_event(event)
        if not callable(handler):
            raise ValueError(f"A handler for {event} must be a function")
        self._collected.setdefault(event, []).append(handler)


def install(addon_key, name, register):
    """Call an add-on's register() and keep its handlers under its key, all or nothing. Raises AddonError."""
    api = HookApi(addon_key, name)
    try:
        register(api)
    except Exception as error:
        _logger.error("add-on %s could not register its hooks: %s", addon_key, describe_error(error))
        raise AddonError(START_FAILED.format(name=name)) from None
    _handlers[addon_key] = api._collected
    _names[addon_key] = name


def is_loaded(addon_key):
    return addon_key in _names


def mark_broken(company_db_path, addon_key, name):
    _broken[(str(company_db_path), addon_key)] = name


def clear_broken(company_db_path, addon_key):
    _broken.pop((str(company_db_path), addon_key), None)


def _clear():
    """Forget every loaded add-on (tests; a new process starts empty)."""
    _handlers.clear()
    _names.clear()
    _broken.clear()


class _HandlerDb:
    """A handler's view of the caller's connection: `execute` only, rows as dicts, and it stops working when the
    handler returns. This narrows what a well-meaning add-on can do by mistake; it is not a sandbox (Python code can
    still reach the connection), which is why only installation add-ons are trusted (HA3, HA7)."""

    __slots__ = ("execute",)


def _handle(conn):
    held = [conn]

    def execute(sql, params=()):
        if held[0] is None:
            raise RuntimeError("This database handle is closed; it works only while the handler runs.")
        return [dict(row) for row in held[0].execute(sql, params).fetchall()]

    def close():
        held[0] = None

    handle = _HandlerDb()
    handle.execute = execute
    return handle, close


def fire(conn, context, event, payload):
    """Run the enabled add-ons' handlers for an event inside the caller's transaction (see the module docstring)."""
    _check_event(event)
    if context.origin == "Agent":
        raise DeferredDenialError(AGENT_REFUSED, lambda: authz.record_denial(context, record_type="addon_hook"))
    enabled = [row["addon_key"] for row in conn.execute(
        "SELECT addon_key FROM company_addon WHERE enabled = 1 ORDER BY addon_key").fetchall()]
    for addon_key in enabled:
        broken = _broken.get((str(context.company_db_path), addon_key))
        if broken is not None:
            raise AddonError(SETUP_FAILED.format(name=broken))
        if addon_key not in _names:
            from modules.services import addons     # the registry imports this module, so it is imported here
            try:
                addons.load(addon_key)
            except NotFoundError:
                raise AddonError(NOT_INSTALLED.format(key=addon_key)) from None
        handlers = _handlers.get(addon_key, {}).get(event, ())
        if handlers:
            data = MappingProxyType(dict(payload, event=event, company_id=context.company_id,
                                         user_id=context.user_id, now=context.now))
        for handler in handlers:
            _run(conn, addon_key, event, handler, data)


def _run(conn, addon_key, event, handler, data):
    handle, close = _handle(conn)
    failure, refused = None, []
    try:
        with database.addon_write_guard(conn, addon_key) as guard:
            try:
                handler(handle, data)
            except (Exception, SystemExit) as error:     # anything but KeyboardInterrupt, a refused write too
                failure = error
            refused = guard.refused
    finally:
        close()
    if failure is None and refused:          # a refused write the handler caught is still a failure
        failure = RuntimeError("the handler's refused actions were caught by the handler")
    if failure is None and not conn.in_transaction:
        failure = RuntimeError("the handler ended the caller's transaction")
    if failure is not None:
        _logger.error("add-on %s failed in %s; refused actions: %s; %s", addon_key, event, refused,
                      describe_error(failure))
        raise AddonError(FAILED.format(name=_names.get(addon_key, addon_key))) from None
