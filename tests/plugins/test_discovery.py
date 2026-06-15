"""Tests for plugin auto-discovery."""

import sys

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyqtgraph")

from pyleem_gui.plugins import discover_plugins, load_plugins
from pyleem_gui.plugins.spec import PLUGINS


@pytest.fixture
def restore_plugins():
    """Restore the registry (and drop temp external modules) after a test that
    loads drop-in plugins, so they don't leak into other tests."""
    discover_plugins(external_dirs=[])  # ensure the built-ins are registered first
    saved = list(PLUGINS)
    yield
    PLUGINS[:] = saved
    for name in [m for m in list(sys.modules) if m.startswith("pyleem_plugin_")]:
        del sys.modules[name]


def _write_plugin(path, title, order=None):
    order = "" if order is None else f", order={order}"
    # An empty tab is a valid plugin; registering a component is optional.
    path.write_text(
        "from pyleem_gui.plugins import plugin\n" f"plugin({title!r}{order})\n"
    )


def test_discover_returns_builtin_specs_in_order():
    # Builtin and Metadata are pinned first; the rest follow by (order, title).
    assert [p.title for p in discover_plugins(external_dirs=[])] == [
        "Builtin",
        "Metadata",
        "Line Profile",
        "Stack Profile",
    ]


def test_discover_is_idempotent():
    first = [p.title for p in discover_plugins(external_dirs=[])]
    second = [p.title for p in discover_plugins(external_dirs=[])]
    assert first == second  # a second scan does not duplicate registrations


def test_load_plugins_mounts_a_dropped_in_module(restore_plugins, tmp_path):
    _write_plugin(tmp_path / "myplugin.py", "Dropped In")
    titles = [p.title for p in load_plugins([tmp_path])]
    assert "Dropped In" in titles


def test_builtin_and_metadata_are_always_first(restore_plugins, tmp_path):
    # Even a drop-in with a very low order cannot precede the two pinned tabs.
    _write_plugin(tmp_path / "greedy.py", "AAA Greedy", order=-999)
    titles = [p.title for p in discover_plugins(external_dirs=[tmp_path])]
    assert titles[:2] == ["Builtin", "Metadata"]
    assert titles.index("AAA Greedy") >= 2


def test_discover_orders_non_pinned_by_order_then_title(restore_plugins, tmp_path):
    _write_plugin(tmp_path / "z.py", "ZZZ Low Order", order=-1)  # late title, low order
    _write_plugin(
        tmp_path / "a.py", "AAA High Order", order=5
    )  # early title, high order
    titles = [p.title for p in discover_plugins(external_dirs=[tmp_path])]
    assert titles[:2] == ["Builtin", "Metadata"]  # pinned, unaffected
    # Among the rest, a lower order wins over an earlier title.
    assert titles.index("ZZZ Low Order") < titles.index("AAA High Order")


def test_broken_external_plugin_is_skipped(restore_plugins, tmp_path):
    (tmp_path / "broken.py").write_text("import a_module_that_does_not_exist_xyz\n")
    _write_plugin(tmp_path / "ok.py", "Survivor")
    titles = [p.title for p in discover_plugins(external_dirs=[tmp_path])]
    assert "Survivor" in titles  # broken.py is logged and skipped, ok.py still loads
