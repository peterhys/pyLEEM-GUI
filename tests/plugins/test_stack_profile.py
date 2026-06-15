"""Qt tests for the Stack Profile analysis tab."""

import numpy as np
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyqtgraph")

import pyqtgraph as pg
from PySide6.QtWidgets import QPushButton, QRadioButton

from pyleem_gui.plugins import AutoTab, PluginContext
from pyleem_gui.plugins.builtin import builtin as builtin_spec
from pyleem_gui.plugins.stack_profile import ROI_MEAN_AXIS
from pyleem_gui.plugins.stack_profile import stack_profile as stack_profile_spec
from pyleem_gui.image import ImageLayer
from pyleem_gui.ui.viewer import Viewer

from ..support import RampReader as BaseRampReader
from ..support import activate_roi, curve_pen_color, curve_xy, export_pen_color


class RampReader(BaseRampReader):
    """The shared ramp plus the numeric/label metadata the correlation plot reads."""

    @property
    def metadata(self):
        return {
            "Energy": (1.0 + self._k * 2.0, "eV"),
            "Temperature": (300.0 + self._k, "K"),
            "Label": (f"frame {self._k}", None),
            "ImageHeight": (64, None),
            "ImageWidth": (64, None),
        }


@pytest.fixture
def loaded(qtbot, tmp_path):
    """A context over a 3-frame stack with Builtin ROI and Stack Profile tabs."""
    for i in range(3):
        (tmp_path / f"{i:03d}.dat").write_bytes(b"")
    images = ImageLayer(reader_factory=RampReader)
    images.open_folder(tmp_path)
    viewer = Viewer(images)
    qtbot.addWidget(viewer)
    context = PluginContext(images=images, image_view=viewer.image_view)

    builtin = AutoTab(context, builtin_spec)
    stack = AutoTab(context, stack_profile_spec)
    qtbot.addWidget(builtin)
    qtbot.addWidget(stack)
    return context, builtin, stack


def stack_handler(stack):
    return stack.controller("Stack profile").handler


def correlation_handler(stack):
    return stack.controller("Correlation plot").handler


def data_item(handler):
    items = handler._plot.getPlotItem().listDataItems()
    return None if not items else items[0]


def curve_y(handler):
    data = curve_xy(handler)
    return None if data is None else data[1]


def symbol_pen_color(handler):
    item = data_item(handler)
    if item is None:
        return None
    return item.scatter.opts["pen"].color()


def symbol_brush_color(handler):
    item = data_item(handler)
    if item is None:
        return None
    return item.scatter.opts["brush"].color()


def export_symbol_pen_color(handler):
    item = data_item(handler)
    if item is None:
        return None
    return item.opts["symbolPen"].color()


def export_symbol_brush_color(handler):
    item = data_item(handler)
    if item is None:
        return None
    return pg.mkBrush(item.opts["symbolBrush"]).color()


def combo_items(combo):
    return [combo.itemText(i) for i in range(combo.count())]


def test_stack_profile_plugin_title():
    assert stack_profile_spec.title == "Stack Profile"


def test_stack_profile_components_are_always_on_with_no_toggle(loaded):
    _context, _builtin, stack = loaded
    stack_controller = stack.controller("Stack profile")
    correlation_controller = stack.controller("Correlation plot")
    assert stack_controller.toggle is None
    assert stack_controller.handler.is_active()
    assert correlation_controller.toggle is None
    assert correlation_controller.handler.is_active()


def test_ui_has_no_radios_reset_or_export(loaded):
    _context, _builtin, stack = loaded
    assert stack.findChildren(QRadioButton) == []  # no Profile / Z-Stack radios
    labels = {b.text() for b in stack.findChildren(QPushButton)}
    assert "Reset Zoom" not in labels and "Export CSV" not in labels


def test_no_active_roi_clears_the_stack_plot(loaded):
    context, builtin, stack = loaded
    handler = stack_handler(stack)
    handler.refresh()
    assert curve_y(handler) is None

    roi = activate_roi(builtin, "Rectangle")
    handler.refresh()
    assert curve_y(handler) is not None

    roi.toggle.setChecked(False)
    assert not context.roi.active()
    assert curve_y(handler) is None


@pytest.mark.parametrize("shape", ["Rectangle", "Circle", "Ellipse", "Line"])
def test_each_shape_plots_one_value_per_frame(loaded, shape):
    context, builtin, stack = loaded
    activate_roi(builtin, shape)
    handler = stack_handler(stack)
    handler.refresh()
    y = curve_y(handler)
    assert y is not None
    assert len(y) == context.images.n_frames
    assert np.all(np.isfinite(y))
    # The ramp is offset by 100 per frame, so the per-frame ROI means increase.
    assert y[0] < y[1] < y[2]


def test_profile_plots_use_fixed_screen_and_export_colors(loaded):
    _context, builtin, stack = loaded
    activate_roi(builtin, "Rectangle")
    handler = stack_handler(stack)
    handler.refresh()
    assert curve_pen_color(handler) == pg.mkColor("w")
    assert export_pen_color(handler) == pg.mkColor("k")

    correlation = correlation_handler(stack)
    correlation._x_axis.setCurrentText("Energy [eV]")
    correlation._y_axis.setCurrentText(ROI_MEAN_AXIS)
    correlation.refresh()
    assert symbol_pen_color(correlation) == pg.mkColor("w")
    assert symbol_brush_color(correlation) == pg.mkColor("w")
    assert export_symbol_pen_color(correlation) == pg.mkColor("k")
    assert export_symbol_brush_color(correlation) == pg.mkColor("k")


def test_roi_movement_recomputes_the_stack(loaded):
    context, builtin, stack = loaded
    activate_roi(builtin, "Rectangle")
    handler = stack_handler(stack)
    correlation = correlation_handler(stack)
    correlation._x_axis.setCurrentText("Energy [eV]")
    roi = context.image_view.roi
    roi.setSize([20, 20])
    roi.setPos([5, 5])
    roi.sigRegionChangeFinished.emit(roi)  # drag-end -> image_update("roi")
    near = curve_y(handler).copy()
    _near_x, near_corr = curve_xy(correlation)

    roi.setPos([40, 5])  # slide along the ramp -> a brighter region
    roi.sigRegionChangeFinished.emit(roi)
    far = curve_y(handler)
    _far_x, far_corr = curve_xy(correlation)

    assert far[0] > near[0]  # the moved ROI samples higher ramp values
    assert far_corr[0] > near_corr[0]


def test_invalid_regions_clear_stack_plot(loaded, monkeypatch):
    context, builtin, stack = loaded
    activate_roi(builtin, "Rectangle")
    handler = stack_handler(stack)
    roi = context.image_view.roi

    monkeypatch.setattr(roi, "getArrayRegion", lambda *a, **k: None)
    handler.refresh()  # all frames NaN -> plot cleared, no crash
    assert curve_y(handler) is None

    def boom(*_args, **_kwargs):
        raise IndexError("too many indices for array")

    monkeypatch.setattr(roi, "getArrayRegion", boom)
    handler.refresh()  # frame_mean swallows it -> NaN -> cleared, no crash
    assert curve_y(handler) is None

    # A degenerate ROI can yield a size-0 region; the guard in frame_mean must
    # treat it as NaN (not call np.mean on an empty array).
    monkeypatch.setattr(roi, "getArrayRegion", lambda *a, **k: np.array([]))
    handler.refresh()
    assert curve_y(handler) is None


def test_correlation_axes_populate_from_numeric_metadata(loaded):
    _context, _builtin, stack = loaded
    handler = correlation_handler(stack)
    handler.refresh()
    items = combo_items(handler._x_axis)
    assert "Energy [eV]" in items
    assert "Temperature [K]" in items
    assert ROI_MEAN_AXIS in items
    assert all("Label" not in item for item in items)
    assert handler._y_axis.currentData() == ROI_MEAN_AXIS


def test_no_active_roi_clears_default_correlation_plot(loaded):
    _context, _builtin, stack = loaded
    handler = correlation_handler(stack)
    handler.refresh()
    assert curve_xy(handler) is None


def test_correlation_plots_metadata_against_roi_mean(loaded):
    _context, builtin, stack = loaded
    activate_roi(builtin, "Rectangle")
    handler = correlation_handler(stack)
    handler._x_axis.setCurrentText("Energy [eV]")
    handler._y_axis.setCurrentText(ROI_MEAN_AXIS)
    handler.refresh()

    x, y = curve_xy(handler)
    assert np.array_equal(x, np.array([1.0, 3.0, 5.0]))
    assert len(y) == 3
    assert np.all(np.isfinite(y))
    assert y[0] < y[1] < y[2]


def test_correlation_process_update_recomputes(loaded, monkeypatch):
    context, builtin, stack = loaded
    activate_roi(builtin, "Rectangle")
    handler = correlation_handler(stack)
    roi = context.image_view.roi
    region = [np.array([0, 0, 1], dtype=float)]
    monkeypatch.setattr(roi, "getArrayRegion", lambda *a, **k: region[0])
    handler.refresh()
    _x0, y0 = curve_xy(handler)

    region[0] = np.array([10, 10, 10], dtype=float)
    context.images.image_update.emit("process")
    _x1, y1 = curve_xy(handler)

    assert np.mean(y1) > np.mean(y0)


def test_correlation_axis_change_updates_analysis_map(loaded):
    context, _builtin, stack = loaded
    handler = correlation_handler(stack)
    component_id = stack.controller("Correlation plot").component.id
    workflow = context.workflow

    # At the auto-selected default (x is the first numeric field, y is ROI mean)
    # the component is at its defaults, so nothing is recorded -> no chip.
    assert component_id not in workflow.analysis

    handler._x_axis.setCurrentText("Temperature [K]")
    assert workflow.analysis.get(component_id) == {
        "x": "Temperature",
        "y": ROI_MEAN_AXIS,
    }

    # Returning to the default clears the entry (the chip disappears again).
    handler._x_axis.setCurrentText("Energy [eV]")
    assert component_id not in workflow.analysis


def test_correlation_selection_round_trips(loaded):
    _context, _builtin, stack = loaded
    handler = correlation_handler(stack)
    handler.params_changed({"x": "Temperature", "y": ROI_MEAN_AXIS})
    assert handler._x_axis.currentData() == "Temperature"
    assert handler._y_axis.currentData() == ROI_MEAN_AXIS


def test_correlation_setting_applies_after_files_open(qtbot, tmp_path):
    # The reported bug: a setting restored with no image loaded (the combos are
    # empty, so it cannot be selected yet) must take effect once files are opened.
    images = ImageLayer(reader_factory=RampReader)
    viewer = Viewer(images)
    qtbot.addWidget(viewer)
    context = PluginContext(images=images, image_view=viewer.image_view)
    stack = AutoTab(context, stack_profile_spec)
    qtbot.addWidget(stack)
    handler = correlation_handler(stack)
    component_id = stack.controller("Correlation plot").component.id

    # No stack yet: a workflow import records the setting; the host restores it.
    context.workflow.analysis[component_id] = {"x": "Temperature", "y": ROI_MEAN_AXIS}
    context.workflow.process_update.emit("analysis")
    # The setting is remembered even though the combos cannot offer it yet.
    assert handler.process_params() == {"x": "Temperature", "y": ROI_MEAN_AXIS}

    # Opening files populates the combos and the remembered setting takes effect.
    for i in range(3):
        (tmp_path / f"{i:03d}.dat").write_bytes(b"")
    images.open_folder(tmp_path)
    assert handler._x_axis.currentData() == "Temperature"
    assert handler._y_axis.currentData() == ROI_MEAN_AXIS


def test_correlation_empty_region_clears(loaded, monkeypatch):
    context, builtin, stack = loaded
    activate_roi(builtin, "Rectangle")
    handler = correlation_handler(stack)
    roi = context.image_view.roi
    monkeypatch.setattr(roi, "getArrayRegion", lambda *a, **k: None)

    handler.refresh()

    assert curve_xy(handler) is None
