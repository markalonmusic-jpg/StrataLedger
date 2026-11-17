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
* Any handler error (its own, or a refused write) is logged with its details and raised as AddonError with one
  sentence naming the add-on and the next step; the caller's transaction then rolls back.
"""
import logging
from types import MappingProxyType

import modules.database as database
from modules.services.errors import AddonError, NotFoundError, PermissionDeniedError

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
_broken = {}       # addon_key -> name: its tables could not be brought up to date when the company opened


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
        _logger.error("add-on %s could not register its hooks", addon_key, exc_info=error)
        raise AddonError(START_FAILED.format(name=name)) from None
    _handlers[addon_key] = api._collected
    _names[addon_key] = name


def is_loaded(addon_key):
    return addon_key in _names


def mark_broken(addon_key, name):
    _broken[addon_key] = name


def clear_broken(addon_key):
    _broken.pop(addon_key, None)


def _clear():
    """Forget every loaded add-on (tests; a new process starts empty)."""
    _handlers.clear()
    _names.clear()
    _broken.clear()


class _HandlerDb:
    """A handler's view of the caller's connection: execute only, rows as dicts, closed when the handler returns."""

    __slots__ = ("_conn",)

    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, params=()):
        if self._conn is None:
            raise RuntimeError("This database handle is closed; it works only while the handler runs.")
        return [dict(row) for row in self._conn.execute(sql, params).fetchall()]


def fire(conn, context, event, payload):
    """Run the enabled add-ons' handlers for an event inside the caller's transaction (see the module docstring)."""
    _check_event(event)
    if context.origin == "Agent":
        raise PermissionDeniedError(AGENT_REFUSED)
    enabled = [row["addon_key"] for row in conn.execute(
        "SELECT addon_key FROM company_addon WHERE enabled = 1 ORDER BY addon_key").fetchall()]
    for addon_key in enabled:
        if addon_key in _broken:
            raise AddonError(SETUP_FAILED.format(name=_broken[addon_key]))
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
    handle = _HandlerDb(conn)
    failure, refused = None, []
    try:
        with database.addon_write_guard(conn, addon_key) as guard:
            try:
                handler(handle, data)
            except Exception as error:      # anything the handler raised, a refused write included
                failure = error
            refused = guard.refused
    finally:
        handle._conn = None
    if failure is None and not conn.in_transaction:
        failure = RuntimeError("the handler ended the caller's transaction")
    if failure is not None:
        _logger.error("add-on %s failed in %s; refused actions: %s", addon_key, event, refused, exc_info=failure)
        raise AddonError(FAILED.format(name=_names.get(addon_key, addon_key))) from None
