"""Tests for the Qt-free declarative plugin spec and registry."""

import numpy as np
import pytest

from pyleem_gui.process import REGISTRY, get_spec
from pyleem_gui.plugins.spec import (
    Bool,
    Choice,
    Float,
    Int,
    ComponentHandlerMark,
    is_handler,
    plugin,
)


class FakeHandler(ComponentHandlerMark):
    """A Qt-free stand-in for a ComponentHandler subclass."""


@pytest.fixture(autouse=True)
def restore_spec_test_plugins():
    """Keep fake spec-only plugins out of later AutoTab/MainWindow tests."""
    yield
    from pyleem_gui.plugins.spec import PLUGINS

    test_titles = {
        "My Plugin",
        "Inline",
        "Src",
        "Ref",
        "Handlers",
        "Analysis",
        "Always",
        "Bad",
    }
    PLUGINS[:] = [plug for plug in PLUGINS if plug.title not in test_titles]
    for process_id in (
        "inline:blur",
        "src:thing",
        "handlers:crosshair",
        "handlers:levels",
    ):
        REGISTRY.pop(process_id, None)


def test_param_helpers_emit_schema():
    assert Float(1.5, min=0.0, max=20.0) == {
        "type": "float",
        "default": 1.5,
        "min": 0.0,
        "max": 20.0,
        "label": None,
    }
    assert Int(256, min=2, max=65536, label="Bins") == {
        "type": "int",
        "default": 256,
        "min": 2,
        "max": 65536,
        "label": "Bins",
    }
    assert Bool(True) == {"type": "bool", "default": True, "label": None}
    assert Choice("a", ["a", "b"]) == {
        "type": "choice",
        "default": "a",
        "choices": ["a", "b"],
        "label": None,
    }


def test_is_handler_detects_marker_subclasses_only():
    assert is_handler(FakeHandler)
    assert is_handler(ComponentHandlerMark)
    assert not is_handler(FakeHandler())  # an instance is not a handler class
    assert not is_handler(lambda image, params: image)


def test_plugin_auto_registers():
    from pyleem_gui.plugins.spec import PLUGINS

    before = len(PLUGINS)
    plug = plugin("My Plugin")
    assert PLUGINS[-1] is plug
    assert len(PLUGINS) == before + 1
    assert plug.components == []


def test_inline_edit_namespaces_id_under_plugin():
    plug = plugin("Inline")

    @plug.edit(
        process_id="blur",
        help="blur it",
        params={"sigma": Float(1.5, min=0, max=20)},
    )
    def blur(image, params):
        return image + params["sigma"]

    # The function is returned unchanged and remains importable/callable.
    assert blur(np.zeros((2, 2)), {"sigma": 2.0}).tolist() == [[2.0, 2.0], [2.0, 2.0]]

    # The short id is registered as <plugin>:<id>; label defaults to the id.
    assert "inline:blur" in REGISTRY
    spec = get_spec("inline:blur")
    assert spec.kind == "edit" and spec.label == "blur"
    component = plug.components[0]
    assert component.kind == "edit"
    assert component.id == "inline:blur"
    assert component.handler is None
    assert component.params_schema["sigma"]["default"] == 1.5


def test_component_by_spec_id_reference():
    src = plugin("Src")

    @src.edit(process_id="thing")
    def thing(image, params):
        return image

    # A second plugin composes the already-registered process by its full id.
    ref = plugin("Ref")
    ref.edit(spec_id="src:thing")

    component = ref.components[0]
    assert component.kind == "edit"
    assert component.id == "src:thing"
    assert component.handler is None


def test_spec_id_kind_mismatch_is_rejected():
    src = plugin("Src")

    @src.edit(process_id="thing")
    def thing(image, params):
        return image

    bad = plugin("Bad")
    with pytest.raises(ValueError, match="edit process, not render"):
        bad.render(spec_id="src:thing")


def test_inline_component_requires_process_id():
    plug = plugin("Bad")
    with pytest.raises(ValueError, match="process_id"):
        plug.edit(lambda image, params: image)


def test_render_handler_registers_noop_process():
    plug = plugin("Handlers")
    plug.render(
        FakeHandler,
        process_id="crosshair",
        help="crosshair help",
    )

    component = plug.components[0]
    assert component.kind == "render"
    assert component.handler is FakeHandler
    assert component.id == "handlers:crosshair"
    # The paired no-op render process keeps the process list canonical.
    spec = get_spec("handlers:crosshair")
    assert spec.kind == "render"
    assert spec.apply(np.zeros((2, 2)), {}) == {}


def test_render_handler_process_apply_is_registered():
    class ApplyHandler(ComponentHandlerMark):
        @staticmethod
        def process_apply(image, params):
            return {"levels": tuple(params["levels"])}

    plug = plugin("Handlers")
    plug.render(ApplyHandler, process_id="levels", help="apply levels")

    # The handler's process_apply replaces the no-op, so a workflow replay
    # reproduces the view from the recorded params.
    spec = get_spec("handlers:levels")
    assert spec.kind == "render"
    assert spec.apply(None, {"levels": [1, 2]}) == {"levels": (1, 2)}


def test_replaces_qualifies_sibling_ids():
    plug = plugin("Handlers")
    plug.render(FakeHandler, process_id="a", replaces=["b", "other:c"])
    # A sibling short id is qualified to this plugin; a full id is kept as given.
    assert plug.components[0].replaces == ("handlers:b", "other:c")


def test_edit_rejects_handler_class():
    plug = plugin("Bad")
    with pytest.raises(TypeError, match="plain fn"):
        plug.edit(FakeHandler, process_id="x")


def test_analysis_requires_handler_class():
    plug = plugin("Bad")
    with pytest.raises(TypeError, match="ComponentHandler subclass"):
        plug.analysis(lambda image, params: image, process_id="x")


def test_analysis_component_registers_no_process():
    plug = plugin("Analysis")
    plug.analysis(FakeHandler, process_id="histogram", help="show histogram")

    component = plug.components[0]
    assert component.kind == "analysis"
    assert component.handler is FakeHandler
    assert component.id == "analysis:histogram"
    assert component.always_on is False  # opt-in
    # Analysis renders in the plugin widget; it never enters the registry.
    assert "analysis:histogram" not in REGISTRY


def test_always_on_tag_is_recorded():
    plug = plugin("Always")
    plug.analysis(FakeHandler, process_id="info", always_on=True)
    assert plug.components[0].always_on is True


def test_builtin_plugin_components():
    from pyleem_gui.plugins.builtin import builtin

    assert [c.label for c in builtin.components] == ["autolevel", "manuallevel", "ROI"]
    assert [c.kind for c in builtin.components] == ["render", "render", "render"]
    assert [c.id for c in builtin.components] == [
        "builtin:autolevel",
        "builtin:manuallevel",
        "builtin:ROI",
    ]
    # Auto and manual level replace each other (mutual exclusion); ROI does not.
    by_id = {c.id: c for c in builtin.components}
    assert by_id["builtin:autolevel"].replaces == ("builtin:manuallevel",)
    assert by_id["builtin:manuallevel"].replaces == ("builtin:autolevel",)
    assert by_id["builtin:ROI"].replaces == ()
    assert "builtin:autolevel" in REGISTRY
    assert "builtin:manuallevel" in REGISTRY
    assert "builtin:ROI" in REGISTRY


def test_spec_source_imports_no_qt():
    # `spec` stays a Qt-free module (it imports no toolkit) so the declaration
    # layer stays simple, even though importing it through the plugins package now
    # pulls in PySide6 via the Qt host (see pyleem_gui/plugins/__init__.py).
    import pyleem_gui.plugins.spec as spec_module

    source = open(spec_module.__file__, encoding="utf-8").read()
    assert "PySide6" not in source
    assert "pyqtgraph" not in source
