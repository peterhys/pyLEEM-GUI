import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyqtgraph")

import pyqtgraph as pg

from pyleem_gui.image import ImageLayer
from pyleem_gui.plugins import AutoTab, PluginContext
from pyleem_gui.ui.processbar import ProcessBar

from ..support import FakeReader, TimeStampReader


# Metadata tab
def test_metadata_tab_shows_frame_metadata_table(qtbot, tmp_path):
    from pyleem_gui.plugins.metadata import metadata as metadata_spec

    for i in range(2):
        (tmp_path / f"{i:03d}.dat").write_bytes(b"")
    images = ImageLayer(reader_factory=FakeReader)
    images.open_folder(tmp_path)
    image_view = pg.ImageView()
    qtbot.addWidget(image_view)
    ctx = PluginContext(images=images, image_view=image_view)

    tab = AutoTab(ctx, metadata_spec)
    qtbot.addWidget(tab)
    controller = tab.controller("metadata")
    table = controller.handler.widget()

    # always_on: no toggle, active and shown from the start.
    assert controller.toggle is None
    assert controller.handler.is_active()
    assert not table.isHidden()

    # fill: the table expands to fill the whole tab -- its box takes the layout
    # stretch and there is no trailing spacer pinning it to a fixed height.
    assert controller.component.fill is True
    assert tab.layout().count() == 1 and tab.layout().stretch(0) == 1

    # FakeReader.metadata has ImageHeight + ImageWidth -> two rows.
    assert table.rowCount() == 2
    keys = {table.item(r, 0).text() for r in range(table.rowCount())}
    assert keys == {"ImageHeight", "ImageWidth"}

    # An analysis widget does not show on a strip.
    strip = ProcessBar()
    qtbot.addWidget(strip)
    strip.bind(ctx.workflow)
    assert strip.labels("analysis") == []


def test_metadata_tab_shows_timestamp_and_time_interval(qtbot, tmp_path):
    """When frames carry a TimeStamp, the Metadata tab lists it and the derived
    TimeInterval, and frame navigation updates the interval."""
    from pyleem_gui.plugins.metadata import metadata as metadata_spec

    for i in range(2):
        (tmp_path / f"{i:03d}.dat").write_bytes(b"")
    images = ImageLayer(reader_factory=TimeStampReader)
    images.open_folder(tmp_path)
    image_view = pg.ImageView()
    qtbot.addWidget(image_view)
    ctx = PluginContext(images=images, image_view=image_view)
    tab = AutoTab(ctx, metadata_spec)
    qtbot.addWidget(tab)
    table = tab.controller("metadata").handler.widget()

    def rows():
        return {
            table.item(r, 0).text(): table.item(r, 1).text()
            for r in range(table.rowCount())
        }

    assert "TimeStamp" in rows() and rows()["TimeInterval"] == "0.0"

    images.set_index(1)  # second frame is one second later
    assert rows()["TimeInterval"] == "1.0"


def test_metadata_handler_needs_no_viewer(qtbot, tmp_path):
    """Metadata analysis works without viewer access."""
    from pyleem_gui.plugins.metadata import metadata as metadata_spec

    for i in range(2):
        (tmp_path / f"{i:03d}.dat").write_bytes(b"")
    images = ImageLayer(reader_factory=FakeReader)
    images.open_folder(tmp_path)
    ctx = PluginContext(images=images, image_view=None)

    meta_tab = AutoTab(ctx, metadata_spec)
    qtbot.addWidget(meta_tab)
    assert not hasattr(meta_tab.controllers[0].handler, "image_view")

    images.set_index(1)  # analysis widgets follow image_update through the image layer
    assert meta_tab.controllers[0].handler._table.rowCount() == 2
