"""Page keys (docs/help_system_design.md section 3): every view's PAGE_KEY is unique, well formed, and equal to
the key the app's sidebar and router (`NAV_ITEMS`, `App.navigate_to`) use for that screen, where one exists.

The screen behind each key is not written down here: the tests run the app's real `navigate_to` and screen
methods on a stand-in window, with every `modules.views_*` function the app imports replaced by a recorder, and
read off which view module each key actually opens and which sidebar row it marks active.
"""
import importlib.machinery
import importlib.util
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
MODULES_DIR = ROOT / "modules"
APP = ROOT / "app_strata.pyw"
KEY_SHAPE = re.compile(r"[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*")
APP_DRAWN = "app_strata.pyw"          # a key whose screen the app draws itself (Home)


def _load_app():
    loader = importlib.machinery.SourceFileLoader("app_strata_for_page_keys", str(APP))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def app_module():
    return _load_app()


class _Workspace:
    def winfo_children(self):
        return []


def _navigate(app_module, key):
    """Run App.navigate_to(key) on a stand-in window. Returns (view modules opened, sidebar keys marked active)."""
    opened, active = [], []

    def recorder(module_name):
        return lambda *args, **kwargs: opened.append(module_name.rsplit(".", 1)[-1])

    class StandIn:
        navigate_to = app_module.App.navigate_to
        switch_customers_view = app_module.App.switch_customers_view
        show_billing_invoices_view = app_module.App.show_billing_invoices_view
        show_payroll_view = app_module.App.show_payroll_view
        workspace_content = _Workspace()

        def show_home_view(self):
            opened.append(APP_DRAWN)
            active.append("home")

        def set_active_nav(self, page_key):
            active.append(page_key)

        def set_breadcrumb(self, *parts):
            pass

    with pytest.MonkeyPatch.context() as patch:
        for name, value in list(vars(app_module).items()):
            module_name = getattr(value, "__module__", "") or ""
            if callable(value) and module_name.startswith("modules.views_"):
                patch.setattr(app_module, name, recorder(module_name))
        StandIn().navigate_to(key)
    return opened, active


@pytest.fixture(scope="module")
def routes(app_module):
    """Sidebar key -> the view module the app opens for it (APP_DRAWN when the app draws it itself)."""
    found = {}
    for item in app_module.NAV_ITEMS:
        opened, active = _navigate(app_module, item.page_key)
        assert len(opened) == 1, f"{item.page_key!r} opened {opened}"
        assert active == [item.page_key], f"{item.page_key!r} marked {active} active in the sidebar"
        found[item.page_key] = opened[0]
    return found


def _declared_keys():
    keys = {}
    for path in sorted(MODULES_DIR.glob("views_*.py")):
        found = re.findall(r"""(?m)^PAGE_KEY\s*=\s*["']([^"']+)["']""", path.read_text(encoding="utf-8"))
        assert len(found) <= 1, f"{path.name} declares PAGE_KEY more than once"
        if found:
            keys[path.stem] = found[0]
    return keys


def test_every_sidebar_key_opens_one_screen_and_marks_itself_active(routes, app_module):
    assert set(routes) == {item.page_key for item in app_module.NAV_ITEMS}


def test_the_router_knows_no_key_the_sidebar_lacks(app_module):
    with pytest.raises(KeyError):
        _navigate(app_module, "no.such.page")


def test_customer_view_names_map_to_routed_keys(app_module, routes):
    assert set(app_module._CUSTOMER_VIEW_KEYS.values()) <= set(routes)


def test_routed_screens_are_view_modules(routes):
    for key, module in routes.items():
        assert module == APP_DRAWN or (MODULES_DIR / f"{module}.py").exists(), key


def test_every_view_page_key_matches_the_key_that_opens_it(routes):
    declared = _declared_keys()
    for key, module in routes.items():
        if module in declared:
            assert declared[module] == key, f"{module}.PAGE_KEY is {declared[module]!r}, the app routes {key!r}"


def test_the_dashboard_is_what_customers_dashboard_opens(routes):
    assert routes["customers.dashboard"] == "views_dashboard"


def test_an_unrouted_view_does_not_take_a_routed_key(routes):
    routed_modules = set(routes.values())
    for module, key in _declared_keys().items():
        if module not in routed_modules:
            assert key not in routes, f"{module} uses {key!r}, which the app routes to another screen"


def test_page_keys_are_unique_and_well_formed():
    declared = _declared_keys()
    values = list(declared.values())
    assert len(values) == len(set(values)), declared
    for module, key in declared.items():
        assert KEY_SHAPE.fullmatch(key), (module, key)
