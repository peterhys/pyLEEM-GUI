"""Qt tests for the Line Profile analysis tab."""

import numpy as np
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyqtgraph")

from PySide6.QtWidgets import QCheckBox, QDoubleSpinBox

from pyleem.roi import LineROI

from pyleem_gui.plugins import AutoTab, PluginContext
from pyleem_gui.plugins.builtin import builtin as builtin_spec
from pyleem_gui.plugins.line_profile import DEFAULT_PEAK_SHIFT, DEFAULT_PIXEL_PER_EV
from pyleem_gui.plugins.line_profile import line_profile as line_profile_spec
from pyleem_gui.ui.processbar import ProcessBar
from pyleem_gui.roi import (
    line_roi_endpoints_xy,
    line_roi_endpoints_yx,
    line_roi_handle_points,
    line_roi_width,
)
from pyleem_gui.image import ImageLayer
from pyleem_gui.ui.viewer import Viewer

from ..support import (
    RampReader,
    activate_roi,
    curve_pen_color,
    curve_xy,
    export_pen_color,
)


class ColumnRampReader:
    """img[row, col] = col: intensity rises left-to-right with the column index."""

    H = 32
    W = 48

    def __init__(self, path):
        self._k = int(path.stem)

    @property
    def metadata(self):
        return {"ImageHeight": (self.H, None), "ImageWidth": (self.W, None)}

    def read_image(self):
        return np.tile(np.arange(self.W, dtype=np.uint16), (self.H, 1))


class RowRampReader:
    """img[row, col] = row: intensity rises top-to-bottom with the row index."""

    H = 40
    W = 32

    def __init__(self, path):
        self._k = int(path.stem)

    @property
    def metadata(self):
        return {"ImageHeight": (self.H, None), "ImageWidth": (self.W, None)}

    def read_image(self):
        column = np.arange(self.H, dtype=np.uint16).reshape(self.H, 1)
        return np.tile(column, (1, self.W))


class StripeReader:
    """A single bright row at mid-height; widening a line through it dilutes it."""

    H = 33
    W = 40

    def __init__(self, path):
        self._k = int(path.stem)

    @property
    def metadata(self):
        return {"ImageHeight": (self.H, None), "ImageWidth": (self.W, None)}

    def read_image(self):
        img = np.zeros((self.H, self.W), dtype=np.uint16)
        img[self.H // 2, :] = 1000
        return img


def make_loaded(qtbot, tmp_path, reader_cls):
    """Context with Builtin ROI and Line Profile tabs over a 3-frame stack."""
    for i in range(3):
        (tmp_path / f"{i:03d}.dat").write_bytes(b"")
    images = ImageLayer(reader_factory=reader_cls)
    images.open_folder(tmp_path)
    viewer = Viewer(images)
    qtbot.addWidget(viewer)
    context = PluginContext(images=images, image_view=viewer.image_view)

    builtin = AutoTab(context, builtin_spec)
    profile = AutoTab(context, line_profile_spec)
    qtbot.addWidget(builtin)
    qtbot.addWidget(profile)
    return context, builtin, profile


@pytest.fixture
def loaded(qtbot, tmp_path):
    """Context over a 3-frame diagonal ramp (offset +100 per frame)."""
    return make_loaded(qtbot, tmp_path, RampReader)


def line_handler(profile):
    return profile.controller("line_profile").handler


def set_line(builtin, x1, y1, x2, y2, width=1.0):
    """Activate a Line ROI and drive its endpoint/width table."""
    controller = activate_roi(builtin, "Line")
    editor = controller.handler.editors["Line"]
    for row, value in enumerate([x1, y1, x2, y2, width]):
        editor.set_value(row, float(value))
    return controller


def test_line_profile_is_always_on_with_no_toggle(loaded):
    _context, _builtin, profile = loaded
    controller = profile.controller("line_profile")
    assert controller.toggle is None
    assert controller.handler.is_active()


def test_no_active_roi_clears_the_plot(loaded):
    _context, _builtin, profile = loaded
    handler = line_handler(profile)
    handler.refresh()
    assert curve_xy(handler) is None


@pytest.mark.parametrize("shape", ["Rectangle", "Circle", "Ellipse", "Polygon"])
def test_non_line_roi_clears_the_plot(loaded, shape):
    _context, builtin, profile = loaded
    activate_roi(builtin, shape)
    handler = line_handler(profile)
    handler.refresh()
    assert curve_xy(handler) is None


def test_line_roi_plots_current_frame_profile(loaded):
    _context, builtin, profile = loaded
    activate_roi(builtin, "Line")
    handler = line_handler(profile)
    handler.refresh()

    x, y = curve_xy(handler)
    assert len(x) == len(y)
    assert len(y) > 0
    assert np.array_equal(x, np.arange(len(y)))  # pixel axis by default
    assert np.all(np.isfinite(y))


def test_energy_axis_defaults_params_and_form(loaded):
    _context, builtin, profile = loaded
    activate_roi(builtin, "Line")
    controller = profile.controller("line_profile")
    handler = controller.handler

    assert handler.energy_on is False
    assert handler.axis_label() == "Sample"
    x0, y0 = curve_xy(handler)
    assert np.array_equal(x0, np.arange(len(y0)))

    handler.params_changed({"energy": True})
    x1, y1 = curve_xy(handler)
    expected = DEFAULT_PEAK_SHIFT + np.arange(len(y1)) / DEFAULT_PIXEL_PER_EV
    assert np.allclose(x1, expected)
    assert "Energy" in handler._plot.getPlotItem().getAxis("bottom").labelText

    handler.params_changed({"peak_shift": DEFAULT_PEAK_SHIFT + 2.0})
    x2, _y2 = curve_xy(handler)
    assert np.allclose(x2 - x1, 2.0)

    handler.params_changed({"energy": True, "peak_shift": 0.0, "pixel_per_ev": 100.0})
    x3, y3 = curve_xy(handler)
    assert np.allclose(x3, np.arange(len(y3)) / 100.0)

    handler.params_changed(
        {
            "energy": False,
            "peak_shift": handler.peak_shift,
            "pixel_per_ev": handler.pixel_per_ev,
        }
    )
    x4, y4 = curve_xy(handler)
    assert np.array_equal(x4, np.arange(len(y4)))
    assert handler._plot.getPlotItem().getAxis("bottom").labelText == "Sample"

    assert list(controller.form.values().keys()) == [
        "energy",
        "peak_shift",
        "pixel_per_ev",
        "reverse",
    ]
    box = controller.form.findChildren(QCheckBox)[0]
    box.setChecked(True)
    peak_box, pixel_per_ev_box = controller.form.findChildren(QDoubleSpinBox)
    peak_box.setValue(10.0)
    pixel_per_ev_box.setValue(50.0)
    x5, y5 = curve_xy(handler)
    assert np.allclose(x5, 10.0 + np.arange(len(y5)) / 50.0)


def test_reverse_axis_defaults_params_and_form(loaded):
    _context, builtin, profile = loaded
    activate_roi(builtin, "Line")
    controller = profile.controller("line_profile")
    handler = controller.handler
    vb = handler._plot.getPlotItem().getViewBox()

    assert handler.reverse is False
    assert not vb.xInverted()

    handler.params_changed({"reverse": True})
    assert vb.xInverted()
    handler.params_changed({"reverse": False})
    assert not vb.xInverted()

    boxes = controller.form.findChildren(QCheckBox)
    assert len(boxes) == 2  # energy then reverse (schema order)
    reverse_box = boxes[1]
    reverse_box.setChecked(True)
    assert vb.xInverted()

    reverse_box.setChecked(False)
    assert not vb.xInverted()


def test_non_positive_pixel_per_ev_is_ignored(loaded):
    # A non-positive dispersion is rejected (kept at the previous value) so the
    # energy axis stays well defined; peak_shift still updates.
    _context, builtin, profile = loaded
    activate_roi(builtin, "Line")
    handler = line_handler(profile)
    handler.params_changed({"energy": True, "peak_shift": 0.0, "pixel_per_ev": 0.0})

    x, y = curve_xy(handler)
    assert handler.pixel_per_ev == DEFAULT_PIXEL_PER_EV  # unchanged
    assert np.allclose(x, np.arange(len(y)) / DEFAULT_PIXEL_PER_EV)  # peak_shift=0
    assert np.all(np.isfinite(x))


def test_line_profile_process_params_roundtrips(loaded):
    _context, builtin, profile = loaded
    activate_roi(builtin, "Line")
    handler = line_handler(profile)
    handler.params_changed(
        {"energy": True, "peak_shift": 5.0, "pixel_per_ev": 200.0, "reverse": True}
    )
    assert handler.process_params() == {
        "energy": True,
        "peak_shift": 5.0,
        "pixel_per_ev": 200.0,
        "reverse": True,
    }


def make_bar(qtbot, context, profile):
    bar = ProcessBar()
    qtbot.addWidget(bar)
    bar.register_tab("line_profile", profile)
    bar.bind(context.workflow)
    return bar


def test_analysis_edit_updates_bar_without_touching_the_image(qtbot, tmp_path):
    # A live analysis edit rides process_update("analysis"): the bar chip updates,
    # but the image layer never recomputes the image (analysis config is image-free).
    context, _builtin, profile = make_loaded(qtbot, tmp_path, RampReader)
    bar = make_bar(qtbot, context, profile)
    component_id = "line_profile:line_profile"
    assert component_id not in context.workflow.analysis
    assert bar.labels("analysis") == []

    kinds = []
    reasons = []
    context.workflow.process_update.connect(kinds.append)
    context.images.image_update.connect(reasons.append)

    energy_box = profile.controller("line_profile").form.findChildren(QCheckBox)[0]
    energy_box.setChecked(True)

    assert kinds == ["analysis"]  # one process_update carrying the analysis tag
    assert reasons == []  # the image is never recomputed
    assert bar.labels("analysis") == [component_id]
    tooltip = bar._items["analysis"][0]["tooltip"]
    assert component_id in tooltip
    assert "energy: True" in tooltip
    assert "peak_shift" in tooltip

    energy_box.setChecked(False)
    assert kinds == ["analysis", "analysis"]
    assert reasons == []
    assert context.workflow.analysis == {}
    assert bar.labels("analysis") == []


def test_import_default_workflow_resets_line_profile(qtbot, tmp_path):
    # Importing a workflow where the Line Profile is absent (at default) resets a
    # non-default handler back to its defaults.
    context, _builtin, profile = make_loaded(qtbot, tmp_path, RampReader)
    wf = tmp_path / "default.json"
    context.workflow.save_workflow(wf)  # analysis empty (all default)

    controller = profile.controller("line_profile")
    controller.form.findChildren(QCheckBox)[0].setChecked(True)  # energy on
    handler = controller.handler
    assert handler.energy_on is True

    context.workflow.import_workflow(wf)
    assert handler.process_params() == {
        "energy": False,
        "peak_shift": DEFAULT_PEAK_SHIFT,
        "pixel_per_ev": DEFAULT_PIXEL_PER_EV,
        "reverse": False,
    }


def test_line_profile_settings_persist_through_workflow(qtbot, tmp_path):
    # Drive the form (so the workflow analysis map is collected), save, then
    # import into a fresh tab and confirm the handler and axis restore.
    ctx1, _builtin1, profile1 = make_loaded(qtbot, tmp_path, RampReader)
    controller = profile1.controller("line_profile")
    energy_box, reverse_box = controller.form.findChildren(QCheckBox)
    peak_box, pixel_per_ev_box = controller.form.findChildren(QDoubleSpinBox)
    energy_box.setChecked(True)
    peak_box.setValue(5.0)
    pixel_per_ev_box.setValue(200.0)
    reverse_box.setChecked(True)

    wf = tmp_path / "wf.json"
    ctx1.workflow.save_workflow(wf)

    ctx2, _builtin2, profile2 = make_loaded(qtbot, tmp_path, RampReader)
    handler2 = profile2.controller("line_profile").handler
    assert handler2.energy_on is False  # fresh defaults before the import

    ctx2.workflow.import_workflow(wf)
    expected = {
        "energy": True,
        "peak_shift": 5.0,
        "pixel_per_ev": 200.0,
        "reverse": True,
    }
    assert handler2.process_params() == expected
    assert handler2._plot.getPlotItem().getViewBox().xInverted()
    assert handler2._plot.getPlotItem().getAxis("bottom").labelText == "Energy [eV]"

    # Restore is idempotent: a second import (another process_update) is a no-op.
    ctx2.workflow.import_workflow(wf)
    assert handler2.process_params() == expected


def test_line_roi_endpoints_xy_matches_rounded_handle_points(qtbot, tmp_path):
    # line_roi_endpoints_xy (the relocated old line_endpoints) is the handle
    # points rounded to one decimal in display (x, y).
    context, builtin, _profile = make_loaded(qtbot, tmp_path, RampReader)
    set_line(builtin, 2.0, 16.0, 46.0, 16.0)
    roi = context.image_view.roi
    item = context.image_view.getImageItem()
    expected = tuple(
        (round(float(p.x()), 1), round(float(p.y()), 1))
        for p in line_roi_handle_points(roi, item)
    )
    assert line_roi_endpoints_xy(roi, item) == expected


def test_displayed_line_maps_to_row_column_axes(qtbot, tmp_path):
    cases = [
        ("column", ColumnRampReader, (2, 16, 46, 16)),
        ("row", RowRampReader, (16, 2, 16, 38)),
    ]
    for name, reader_cls, endpoints in cases:
        case_dir = tmp_path / name
        case_dir.mkdir()
        _context, builtin, profile = make_loaded(qtbot, case_dir, reader_cls)
        set_line(builtin, *endpoints)
        _x, y = curve_xy(line_handler(profile))
        assert len(y) > 5
        assert np.all(np.isfinite(y))
        assert y[0] < y[-1]
        assert np.all(np.diff(y) >= -1e-9)


def test_plotted_profile_matches_pyleem_read_profile(qtbot, tmp_path):
    # The plotted curve is exactly skimage's profile for the converted endpoints
    # and width; the plugin adds no resampling of its own.
    context, builtin, profile = make_loaded(qtbot, tmp_path, ColumnRampReader)
    set_line(builtin, 2, 10, 40, 25, width=3)  # slanted, 3 px wide
    handler = line_handler(profile)

    _x, y = curve_xy(handler)
    roi = context.image_view.roi
    item = context.image_view.getImageItem()
    src, dst = line_roi_endpoints_yx(roi, item)
    frame = context.images.edited(context.images.current_index)
    ref = LineROI(src=src, dst=dst, linewidth=line_roi_width(roi)).read_profile(
        np.asarray(frame)
    )
    ref = np.asarray(ref, dtype=float)
    ref = ref[np.isfinite(ref)]
    assert np.allclose(y, ref)


def test_line_profile_independent_of_pyqtgraph_slicing(loaded, monkeypatch):
    # Line Profile must not call the ROI's getArrayRegion at all: break it and
    # the profile still plots from the skimage path.
    context, builtin, profile = loaded
    activate_roi(builtin, "Line")
    handler = line_handler(profile)
    roi = context.image_view.roi

    def boom(*_args, **_kwargs):
        raise IndexError("Line Profile must not use getArrayRegion")

    monkeypatch.setattr(roi, "getArrayRegion", boom)
    handler.refresh()

    _x, y = curve_xy(handler)
    assert y is not None
    assert len(y) > 0
    assert np.all(np.isfinite(y))


def test_line_profile_trace_uses_fixed_screen_and_export_colors(loaded):
    import pyqtgraph as pg

    _context, builtin, profile = loaded
    activate_roi(builtin, "Line")
    handler = line_handler(profile)
    handler.refresh()
    assert curve_pen_color(handler) == pg.mkColor("w")
    assert export_pen_color(handler) == pg.mkColor("k")


def test_frame_change_recomputes_the_profile(loaded):
    context, builtin, profile = loaded
    activate_roi(builtin, "Line")
    handler = line_handler(profile)
    handler.refresh()
    _x0, y0 = curve_xy(handler)

    context.images.set_index(1)
    _x1, y1 = curve_xy(handler)

    assert np.mean(y1) > np.mean(y0)


def test_line_movement_recomputes_the_profile(loaded):
    context, builtin, profile = loaded
    controller = activate_roi(builtin, "Line")
    editor = controller.handler.editors["Line"]
    for row, value in enumerate([0.0, 0.0, 20.0, 20.0, 1.0]):
        editor.set_value(row, value)
    handler = line_handler(profile)
    roi = context.image_view.roi
    roi.setPos([0, 0])
    roi.sigRegionChangeFinished.emit(roi)
    _near_x, near_y = curve_xy(handler)

    roi.setPos([20, 0])
    roi.sigRegionChangeFinished.emit(roi)
    _far_x, far_y = curve_xy(handler)

    assert np.mean(far_y) > np.mean(near_y)


def test_width_change_redraws_and_changes_values(qtbot, tmp_path):
    # Widening the line averages more rows; over a single bright stripe that
    # dilutes the profile, so the values change.
    _context, builtin, profile = make_loaded(qtbot, tmp_path, StripeReader)
    controller = set_line(builtin, 2, 16, 38, 16, width=1)  # along the stripe
    handler = line_handler(profile)
    _x1, y_narrow = curve_xy(handler)
    narrow_mean = float(np.mean(y_narrow))

    controller.handler.editors["Line"].set_value(4, 7.0)  # widen to 7 px
    _x2, y_wide = curve_xy(handler)
    wide_mean = float(np.mean(y_wide))

    assert wide_mean < narrow_mean


def test_process_update_recomputes_the_profile(loaded, monkeypatch):
    # An image_update("process") redraws from the new edited frame data, which
    # is what Line Profile samples.
    context, builtin, profile = loaded
    activate_roi(builtin, "Line")
    handler = line_handler(profile)
    frame = [np.zeros((64, 64), dtype=float)]
    monkeypatch.setattr(context.images, "edited", lambda *_a, **_k: frame[0])
    handler.refresh()
    _x0, y0 = curve_xy(handler)

    frame[0] = np.full((64, 64), 50.0)
    context.images.image_update.emit("process")
    _x1, y1 = curve_xy(handler)

    assert np.mean(y1) > np.mean(y0)


def test_line_profile_invalid_inputs_clear_the_plot(loaded, monkeypatch):
    context, builtin, profile = loaded
    activate_roi(builtin, "Line")
    handler = line_handler(profile)
    roi = context.image_view.roi

    def boom(*_args, **_kwargs):
        raise IndexError("no handle")

    monkeypatch.setattr(roi, "getSceneHandlePositions", boom)
    handler.refresh()

    assert curve_xy(handler) is None

    monkeypatch.undo()
    activate_roi(builtin, "Line")
    monkeypatch.setattr(
        context.images, "edited", lambda *_a, **_k: np.full((64, 64), np.nan)
    )
    handler.refresh()

    assert curve_xy(handler) is None
