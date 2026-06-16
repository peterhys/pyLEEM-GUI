"""Shared Qt fixtures for the plugin tests."""

import pytest

import pyqtgraph as pg

from pyleem_gui.image import ImageLayer
from pyleem_gui.plugins import AutoTab, PluginContext
from pyleem_gui.plugins.builtin import builtin as builtin_spec
from pyleem_gui.ui.processbar import ProcessBar

from ..support import FakeReader


@pytest.fixture
def context(qtbot):
    images = ImageLayer(reader_factory=FakeReader)
    image_view = pg.ImageView()
    qtbot.addWidget(image_view)
    # workflow defaults to the image layer's own layer.
    return PluginContext(images=images, image_view=image_view)


@pytest.fixture
def bar(context, qtbot):
    """A process bar bound to the context's process layer (canonical render)."""
    bar = ProcessBar()
    qtbot.addWidget(bar)
    bar.bind(context.workflow)
    return bar


@pytest.fixture
def builtin(context, qtbot):
    tab = AutoTab(context, builtin_spec)
    qtbot.addWidget(tab)
    return tab


@pytest.fixture
def tunable(context, qtbot):
    """A throwaway plugin with a parameterized edit, for form-wiring tests."""
    from pyleem_gui.process import REGISTRY
    from pyleem_gui.plugins.spec import PLUGINS, Int, plugin

    plug = plugin("Tunable")

    @plug.edit(
        process_id="gain",
        help="add k to every pixel",
        params={"k": Int(3, min=0, max=100)},
    )
    def gain(image, params):
        return image + params["k"]

    tab = AutoTab(context, plug)
    qtbot.addWidget(tab)
    yield tab
    PLUGINS.remove(plug)  # keep it out of the discovery and MainWindow tests
    REGISTRY.pop("tunable:gain", None)
