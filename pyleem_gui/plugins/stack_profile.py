"""Stack Profile plugin for ROI mean and metadata plots."""

import numpy as np
import pyqtgraph as pg
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ..metadata import axis_label, numeric_metadata_fields, numeric_metadata_value
from ..roi import sample_roi
from .host import AnalysisHandler, plot_profile_points, plot_profile_trace
from .spec import plugin

ROI_MEAN_AXIS = "ROI mean intensity"


def roi_mean(context, roi, item, index):
    """Mean intensity inside the ROI for one frame, or NaN."""
    region = sample_roi(context.images.edited(index), roi, item)
    if region is None:
        return np.nan
    return float(np.mean(region))


def roi_mean_series(context):
    """Per-frame ROI mean intensities, or all-NaN when no ROI is active."""
    images = context.images
    if not context.roi.active():
        return np.full(images.n_frames, np.nan)
    roi = context.image_view.roi
    item = context.image_view.getImageItem()
    return np.asarray([roi_mean(context, roi, item, i) for i in range(images.n_frames)])


class StackProfileHandler(AnalysisHandler):
    """ROI mean intensity per frame."""

    # Frame browsing does not change this stack-wide curve.
    refresh_reasons = ("open", "process", "roi")

    def __init__(self, context, component):
        super().__init__(context, component)
        self._plot = pg.PlotWidget()
        self._plot.setLabel("left", "Mean intensity")
        self._plot.setLabel("bottom", "Frame")
        self._plot.setVisible(False)

    def widget(self):
        return self._plot

    def refresh(self):
        images = self.context.images
        if images.n_frames == 0 or not self.context.roi.active():
            self._plot.clear()
            return
        intensities = roi_mean_series(self.context)
        self._plot.clear()
        if not np.any(np.isfinite(intensities)):
            return  # a degenerate ROI gave no usable region on any frame
        frames = np.arange(images.n_frames)
        plot_profile_trace(self._plot, frames, intensities)
        self._plot.autoRange()


class CorrelationPlotHandler(AnalysisHandler):
    """Analysis handler: metadata and ROI mean correlation."""

    refresh_reasons = ("open", "process", "roi")

    def __init__(self, context, component):
        super().__init__(context, component)
        self._default_x = None  # the auto-selected x for the current stack
        self._wanted = {}  # the desired x/y selection, kept until a stack offers it
        self._root = QWidget()
        layout = QVBoxLayout(self._root)
        controls = QHBoxLayout()
        controls.addWidget(QLabel("X"))
        self._x_axis = QComboBox()
        controls.addWidget(self._x_axis)
        controls.addWidget(QLabel("Y"))
        self._y_axis = QComboBox()
        controls.addWidget(self._y_axis)
        controls.addStretch(1)
        layout.addLayout(controls)
        self._plot = pg.PlotWidget()
        self._plot.setLabel("left", ROI_MEAN_AXIS)
        self._plot.setLabel("bottom", "Metadata")
        layout.addWidget(self._plot, 1)
        self._root.setVisible(False)

        self._x_axis.currentTextChanged.connect(self._on_axis_changed)
        self._y_axis.currentTextChanged.connect(self._on_axis_changed)

    def widget(self):
        return self._root

    def _on_axis_changed(self):
        """Remember a user x/y selection and notify the host."""
        x = self.current_axis(self._x_axis)
        y = self.current_axis(self._y_axis)
        if x is not None and (x != self._default_x or y != ROI_MEAN_AXIS):
            self._wanted = {"x": x, "y": y}
        else:
            self._wanted = {}
        self.refresh_if_active()
        self.changed.emit()

    def params_changed(self, params):
        """Restore the saved x/y axis selection."""
        self._wanted = {key: params[key] for key in ("x", "y") if params.get(key)}
        self.refresh_if_active()

    def process_params(self):
        """The non-default x/y selection for workflow analysis params."""
        return dict(self._wanted)

    def refresh(self):
        self.rebuild_axis_choices()  # reads n_frames itself; safe with no frames
        if self.context.images.n_frames == 0:
            self._plot.clear()
            return

        x_key = self.current_axis(self._x_axis)
        y_key = self.current_axis(self._y_axis)
        if x_key is None or y_key is None:
            self._plot.clear()
            return

        x_values = self.axis_values(x_key)
        y_values = self.axis_values(y_key)
        finite = np.isfinite(x_values) & np.isfinite(y_values)
        self._plot.clear()
        if not np.any(finite):
            return

        self._plot.setLabel("bottom", self._x_axis.currentText())
        self._plot.setLabel("left", self._y_axis.currentText())
        plot_profile_points(self._plot, x_values[finite], y_values[finite])
        self._plot.autoRange()

    def rebuild_axis_choices(self):
        """Refresh selector choices from current stack metadata."""
        images = self.context.images
        metas = [images.metadata(i) for i in range(images.n_frames)]
        choices = numeric_metadata_fields(metas)
        choices.append((ROI_MEAN_AXIS, ""))
        self._default_x = self.default_x(choices)
        pref_x = self._wanted.get("x") or self.current_axis(self._x_axis)
        pref_y = self._wanted.get("y") or self.current_axis(self._y_axis)
        self.populate_axis(self._x_axis, choices, pref_x, self._default_x)
        self.populate_axis(self._y_axis, choices, pref_y, ROI_MEAN_AXIS)

    def default_x(self, choices):
        """Default x-axis key for the current choices."""
        keys = [key for key, _unit in choices]
        if "TimeInterval" in keys:
            return "TimeInterval"
        for key in keys:
            if key != ROI_MEAN_AXIS:
                return key
        return ROI_MEAN_AXIS if ROI_MEAN_AXIS in keys else None

    def populate_axis(self, combo, choices, previous, fallback):
        """Populate one axis combo while preserving selection."""
        keys = [key for key, _unit in choices]
        selected = previous if previous in keys else fallback
        if selected not in keys and keys:
            selected = keys[0]

        combo.blockSignals(True)
        try:
            combo.clear()
            for key, unit in choices:
                combo.addItem(axis_label(key, unit), key)
            if selected in keys:
                combo.setCurrentIndex(keys.index(selected))
        finally:
            combo.blockSignals(False)

    def current_axis(self, combo):
        """Current axis key for a selector, or None."""
        if combo.count() == 0:
            return None
        return combo.currentData()

    def axis_values(self, key):
        """Stack values for one selected axis."""
        if key == ROI_MEAN_AXIS:
            return roi_mean_series(self.context)
        images = self.context.images
        values = [
            numeric_metadata_value(images.metadata(i), key)
            for i in range(images.n_frames)
        ]
        return np.asarray([np.nan if v is None else v for v in values], dtype=float)


stack_profile = plugin("Stack Profile")

stack_profile.analysis(
    StackProfileHandler,
    process_id="stack_profile",
    label="Stack profile",
    always_on=True,
    fill=True,
    help="Plot the ROI mean intensity for each frame (a Z-stack profile).",
)

stack_profile.analysis(
    CorrelationPlotHandler,
    process_id="correlation_plot",
    label="Correlation plot",
    always_on=True,
    fill=True,
    help="Plot correlations between numeric metadata and ROI mean intensity.",
)
