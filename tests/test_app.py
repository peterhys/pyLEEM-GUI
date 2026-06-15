import json

import numpy as np
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyqtgraph")

import tifffile

from pyleem_gui.app import ExportDialog, MainWindow
from pyleem_gui.image import ImageLayer
from pyleem_gui.process import ProcessLayer
from pyleem_gui.view import ExportOptions

from .support import FakeReader


@pytest.fixture
def win(qtbot, tmp_path):
    for i in range(3):
        (tmp_path / f"{i:03d}.dat").write_bytes(b"")
    images = ImageLayer(reader_factory=FakeReader)
    images.open_folder(tmp_path)
    window = MainWindow(images=images)
    qtbot.addWidget(window)
    window.resize(400, 400)
    window.show()
    return window


def test_mainwindow_creates_workflow_alongside_image_layer(qtbot):
    win = MainWindow()
    qtbot.addWidget(win)
    assert win.workflow is win.images.workflow
    assert isinstance(win.workflow, ProcessLayer)


def test_import_workflow_without_image_data(qtbot, tmp_path):
    win = MainWindow()
    qtbot.addWidget(win)
    assert win.images.n_frames == 0

    wf = tmp_path / "wf.json"
    wf.write_text(json.dumps([{"process_id": "builtin:autolevel", "params": {}}]))
    win.workflow.import_workflow(wf)

    assert "builtin:autolevel" in win.process_bar.labels("rendered")
    builtin = next(p for p in win.plugins if p.title == "Builtin")
    controller = builtin.controller("autolevel")
    assert controller.toggle.isChecked()


def test_tabs_reflect_workflow_present_before_construction(qtbot):
    # A process placed in the workflow BEFORE the tabs are built is reflected by
    # AutoTab's initial sync -- without it the toggle would stay off until the
    # next process_update. (Routing loads through the coordinator relies on this.)
    from pyleem_gui.process import Process

    workflow = ProcessLayer()
    images = ImageLayer(workflow=workflow, reader_factory=FakeReader)
    win = MainWindow(images=images, workflow=workflow)  # discovers + registers builtin
    qtbot.addWidget(win)
    builtin = next(p for p in win.plugins if p.title == "Builtin")
    assert not builtin.controller("autolevel").toggle.isChecked()

    workflow.add_process(Process("builtin:autolevel", {}))
    second = MainWindow(images=images, workflow=workflow)
    qtbot.addWidget(second)
    builtin2 = next(p for p in second.plugins if p.title == "Builtin")
    assert builtin2.controller("autolevel").toggle.isChecked()


def test_export_dialog_defaults(qtbot):
    dialog = ExportDialog()
    qtbot.addWidget(dialog)
    opts = dialog.options()
    assert opts.rendered and not opts.raw and not opts.edited
    assert not opts.composite  # separate-files mode by default


def test_file_menu_has_open_file_and_two_exports(win):
    items = [a.text() for a in win.file_menu.actions()]
    assert "Open File..." in items
    assert "Open Folder..." in items
    assert "Export Image..." in items
    assert "Export Stack..." in items


def test_no_plugin_visibility_menu(win):
    menus = [action.text() for action in win.menuBar().actions()]

    assert "&View" not in menus
    assert [win.tabs.tabText(i) for i in range(win.tabs.count())] == [
        "Builtin",
        "Metadata",
        "Line Profile",
        "Stack Profile",
    ]
    assert all(win.tabs.isTabVisible(i) for i in range(win.tabs.count()))


def test_export_separate_levels_writes_one_file_each(win, tmp_path):
    out = tmp_path / "e.tif"
    names = win.viewer.view.write_export(
        out,
        [0, 1, 2],
        ExportOptions(raw=True, edited=True, rendered=True, composite=False),
    )
    assert names == ["e_raw.tif", "e_edited.tif", "e_rendered.tif"]

    raw = tifffile.imread(str(tmp_path / "e_raw.tif"))
    assert raw.shape == (3, 4, 4) and raw.dtype == np.uint16  # grayscale stack
    rendered = tifffile.imread(str(tmp_path / "e_rendered.tif"))
    assert rendered.ndim == 4 and rendered.shape[-1] == 3  # RGB stack (view grab)


def test_export_composite_rendered_is_single_rgb(win, tmp_path):
    out = tmp_path / "c.tif"
    names = win.viewer.view.write_export(
        out, [0], ExportOptions(raw=False, edited=True, rendered=True, composite=True)
    )
    assert names == ["c.tif"]
    img = tifffile.imread(str(out))
    assert img.ndim == 3 and img.shape[-1] == 3  # one RGB image


def test_export_composite_without_rendered_is_grayscale(win, tmp_path):
    out = tmp_path / "g.tif"
    win.viewer.view.write_export(
        out,
        [0, 1, 2],
        ExportOptions(raw=False, edited=True, rendered=False, composite=True),
    )
    img = tifffile.imread(str(out))
    assert img.shape == (3, 4, 4)  # grayscale stack


def test_export_embeds_imagej_metadata(win, tmp_path):
    out = tmp_path / "m.tif"
    win.viewer.view.write_export(
        out,
        [0, 1, 2],
        ExportOptions(raw=False, edited=True, rendered=False, composite=True),
    )
    with tifffile.TiffFile(str(out)) as tf:
        info = tf.imagej_metadata["Info"]
    # The per-frame sections the bundled ImageJ overlay plugins parse.
    assert "[Frame 0]" in info and "[Frame 2]" in info
    assert "ImageWidth = 4" in info


def test_open_file_dialog_filter_includes_dat_and_tiff(win, monkeypatch):
    captured = {}

    def fake_get_open(*args, **kwargs):
        captured["filter"] = kwargs.get("filter", "")
        return ("", "")

    monkeypatch.setattr("pyleem_gui.app.QFileDialog.getOpenFileName", fake_get_open)
    win.open_file()
    assert "*.dat" in captured["filter"]
    assert "*.tif" in captured["filter"]
    assert "*.tiff" in captured["filter"]


def test_export_then_reimport_grayscale_tiff(win, tmp_path):
    # An exported grayscale stack reimports with its pixels and per-frame metadata.
    out = tmp_path / "roundtrip.tif"
    win.images.export_tiff(out, [0, 1, 2], level="raw")

    other = ImageLayer()
    other.open_file(out)
    assert other.n_frames == 3
    assert [int(other.raw(i)[0, 0]) for i in range(3)] == [0, 1, 2]  # FakeReader fill
    assert other.metadata(0)["ImageWidth"] == (4, None)
