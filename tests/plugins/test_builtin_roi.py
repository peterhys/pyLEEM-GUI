import json

import numpy as np
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyqtgraph")

import pyqtgraph as pg

from pyleem_gui.image import ImageLayer
from pyleem_gui.plugins import AutoTab
from pyleem_gui.plugins.builtin import builtin as builtin_spec

from ..support import FakeReader


# ROI render component
def test_roi_toggle_is_builtin_roi_button(builtin, context, bar):
    iv = context.image_view
    controller = builtin.controller("ROI")
    assert controller.toggle is iv.ui.roiBtn
    assert "builtin:ROI" not in bar.labels("rendered")

    iv.ui.roiBtn.click()
    # Default view mode is rendered, so the ROI overlay shows.
    assert iv.roi.isVisible()
    assert "builtin:ROI" in bar.labels("rendered")
    context.view.set_mode("edited")  # rendered processes are not shown in edited mode
    assert not iv.roi.isVisible()
    context.view.set_mode("rendered")
    assert iv.roi.isVisible()
    iv.ui.roiBtn.click()
    assert not iv.roi.isVisible()
    assert "builtin:ROI" not in bar.labels("rendered")


def test_roi_shape_options(builtin, context):
    iv = context.image_view
    iv.setImage(np.zeros((50, 50)))
    shape = builtin.controller("ROI").handler.shape

    shape.setCurrentText("Ellipse")
    assert isinstance(iv.roi, pg.EllipseROI)
    shape.setCurrentText("Circle")
    assert isinstance(iv.roi, pg.CircleROI)
    shape.setCurrentText("Polygon")
    assert isinstance(iv.roi, pg.PolyLineROI)
    shape.setCurrentText("Line")
    assert isinstance(iv.roi, pg.LineROI)  # width-aware line, not LineSegmentROI


def test_roi_params_pushed_to_status(context, qtbot):
    messages = []
    context.status = messages.append
    tab = AutoTab(context, builtin_spec)
    qtbot.addWidget(tab)
    iv = context.image_view
    iv.setImage(np.zeros((120, 120)))

    controller = tab.controller("ROI")
    controller.handler.shape.setCurrentText("Circle")
    controller.toggle.setChecked(True)  # showing the ROI pushes its params
    assert any("builtin:ROI Circle" in m for m in messages)
    assert any("center=" in m for m in messages)


def test_roi_toggle_shows_overlay_not_profile_pane(qtbot, tmp_path):
    """The ROI button shows only the overlay; the built-in profile pane stays
    hidden (Stack Profile is the supported ROI profiling UI)."""
    from pyleem_gui.ui.viewer import Viewer

    for i in range(2):
        (tmp_path / f"{i:03d}.dat").write_bytes(b"")
    images = ImageLayer(reader_factory=FakeReader)
    images.open_folder(tmp_path)
    viewer = Viewer(images)
    qtbot.addWidget(viewer)
    iv = viewer.image_view

    assert iv.ui.roiPlot.isHidden()  # the built-in profile pane starts hidden
    iv.ui.roiBtn.click()  # show the ROI overlay only
    assert iv.roi.isVisible()
    assert iv.ui.roiPlot.isHidden()  # ... and the profile pane stays hidden
    assert not iv.roiCurves  # no profile curve is ever built
    iv.ui.roiBtn.click()  # toggling off hides the overlay
    assert not iv.roi.isVisible()


def test_roi_imagej_conversion_per_shape(builtin, context):
    from roifile import ImagejRoi

    context.image_view.setImage(np.zeros((120, 120)))
    handler = builtin.controller("ROI").handler
    builtin.controller("ROI").toggle.setChecked(True)
    for shape in ("Line", "Circle", "Ellipse", "Rectangle"):
        handler.shape.setCurrentText(shape)
        assert isinstance(handler.imagej_roi(), ImagejRoi), shape
    handler.shape.setCurrentText("Polygon")  # no ImageJ mapping
    assert handler.imagej_roi() is None


def test_save_roi_writes_a_round_trippable_file(
    builtin, context, tmp_path, monkeypatch
):
    from roifile import ImagejRoi

    context.image_view.setImage(np.zeros((120, 120)))
    roi = builtin.controller("ROI")
    roi.handler.shape.setCurrentText("Line")
    roi.toggle.setChecked(True)

    out = tmp_path / "line.roi"
    monkeypatch.setattr(
        "pyleem_gui.plugins.builtin_roi.QFileDialog.getSaveFileName",
        staticmethod(lambda *a, **k: (str(out), "ImageJ ROI (*.roi)")),
    )
    roi.handler._save_roi()
    assert out.exists() and out.stat().st_size > 0
    ImagejRoi.fromfile(str(out))  # reads back as a valid ImageJ ROI


def test_save_roi_inactive_is_a_noop(builtin, context, monkeypatch):
    messages = []
    context.status = messages.append
    called = []
    monkeypatch.setattr(
        "pyleem_gui.plugins.builtin_roi.QFileDialog.getSaveFileName",
        staticmethod(lambda *a, **k: called.append(True) or ("", "")),
    )
    builtin.controller("ROI").handler._save_roi()  # ROI off
    assert not called  # no dialog opened
    assert any("No active ROI" in m for m in messages)


def test_import_workflow_restores_roi_geometry(builtin, context, tmp_path):
    """An old {pos,size} Ellipse entry restores the live ROI; the re-recorded
    entry follows the new schema (which adds an angle)."""
    wf = tmp_path / "wf.json"
    wf.write_text(
        json.dumps(
            [
                {
                    "process_id": "builtin:ROI",
                    "params": {
                        "shape": "Ellipse",
                        "pos": [5.0, 6.0],
                        "size": [30.0, 40.0],
                    },
                }
            ]
        )
    )
    context.workflow.import_workflow(wf)

    controller = builtin.controller("ROI")
    assert controller.toggle.isChecked()
    assert context.image_view.roi.isVisible()
    handler = builtin.controller("ROI").handler
    roi = context.image_view.roi
    assert handler.shape.currentText() == "Ellipse"
    assert isinstance(roi, pg.EllipseROI)
    assert [roi.pos().x(), roi.pos().y()] == [5.0, 6.0]
    assert [roi.size().x(), roi.size().y()] == [30.0, 40.0]

    # The restored state lands back on the entry, so it round-trips again -- now
    # under the new Ellipse schema, which carries an angle (0 from the old entry).
    index = context.workflow.find_process("builtin:ROI")
    assert context.workflow.processes[index].params == {
        "shape": "Ellipse",
        "pos": [5.0, 6.0],
        "size": [30.0, 40.0],
        "angle": 0.0,
    }

    context.workflow.delete_process(index)
    assert context.workflow.find_process("builtin:ROI") is None
    assert not controller.toggle.isChecked()
    assert not context.image_view.roi.isVisible()
