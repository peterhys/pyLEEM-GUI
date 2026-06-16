"""Shared Qt fixtures for the UI tests."""

import pytest

import pyqtgraph as pg

from pyleem_gui.image import ImageLayer
from pyleem_gui.plugins import PluginContext

from ..support import FakeReader


@pytest.fixture
def context(qtbot):
    images = ImageLayer(reader_factory=FakeReader)
    image_view = pg.ImageView()
    qtbot.addWidget(image_view)
    return PluginContext(images=images, image_view=image_view)
