"""Page keys (docs/help_system_design.md section 3): every view's PAGE_KEY is unique, well formed, and equal to
the key the app's sidebar and router (`NAV_ITEMS`, `App.navigate_to`) use for that screen, where one exists.

SCREEN_ROUTES names the view module behind each routed key. It must list every sidebar key, so a new sidebar
item cannot be added without saying which screen it opens; a view that declares a PAGE_KEY must then use
exactly that key.
"""
import importlib.machinery
import importlib.util
import inspect
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
MODULES_DIR = ROOT / "modules"
APP = ROOT / "app_strata.pyw"
KEY_SHAPE = re.compile(r"[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*")

# Sidebar / router key -> the view module that renders it (None: drawn by app_strata.pyw itself).
SCREEN_ROUTES = {
    "home": None,
    "customers.dashboard": "views_dashboard",
    "customers.list": "views_registry",
    "customers.create": "views_wizard",
    "billing": "views_billing",
    "payroll": "views_payroll",
}


def _load_app():
    loader = importlib.machinery.SourceFileLoader("app_strata_for_page_keys", str(APP))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def app_module():
    return _load_app()


def _declared_keys():
    keys = {}
    for path in sorted(MODULES_DIR.glob("views_*.py")):
        found = re.findall(r"""(?m)^PAGE_KEY\s*=\s*["']([^"']+)["']""", path.read_text(encoding="utf-8"))
        assert len(found) <= 1, f"{path.name} declares PAGE_KEY more than once"
        if found:
            keys[path.stem] = found[0]
    return keys


def _router_keys(app_module):
    source = inspect.getsource(app_module.App.navigate_to)
    return set(re.findall(r"""^\s*["']([^"']+)["']\s*:""", source, re.MULTILINE))


def test_routes_table_covers_every_sidebar_and_router_key(app_module):
    sidebar = {item.page_key for item in app_module.NAV_ITEMS}
    assert set(SCREEN_ROUTES) == sidebar
    assert _router_keys(app_module) == sidebar


def test_customer_view_names_map_to_routed_keys(app_module):
    assert set(app_module._CUSTOMER_VIEW_KEYS.values()) <= set(SCREEN_ROUTES)


def test_routed_view_modules_exist_and_are_imported_by_the_app():
    source = APP.read_text(encoding="utf-8")
    for key, module in SCREEN_ROUTES.items():
        if module is None:
            continue
        assert (MODULES_DIR / f"{module}.py").exists(), key
        assert re.search(rf"^from modules\.{module} import ", source, re.MULTILINE), key


def test_every_view_page_key_matches_its_route():
    declared = _declared_keys()
    for key, module in SCREEN_ROUTES.items():
        if module in declared:
            assert declared[module] == key, f"{module}.PAGE_KEY is {declared[module]!r}, the app routes {key!r}"


def test_an_unrouted_view_does_not_take_a_routed_key():
    routed_modules = {module: key for key, module in SCREEN_ROUTES.items() if module}
    for module, key in _declared_keys().items():
        if module not in routed_modules:
            assert key not in SCREEN_ROUTES, f"{module} uses {key!r}, which the app routes to another screen"


def test_page_keys_are_unique_and_well_formed():
    declared = _declared_keys()
    values = list(declared.values())
    assert len(values) == len(set(values)), declared
    for module, key in declared.items():
        assert KEY_SHAPE.fullmatch(key), (module, key)
