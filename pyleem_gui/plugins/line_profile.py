"""Line Profile plugin for intensity along a Line ROI."""

import numpy as np
import pyqtgraph as pg

from ..roi import line_roi_profile
from .host import AnalysisHandler, plot_profile_trace
from .spec import Bool, Float, plugin

# pyleem energy-calibration defaults from pyleem/config.py.
DEFAULT_ENERGY_OFF = False
DEFAULT_PEAK_SHIFT = 3.75
DEFAULT_PIXEL_PER_EV = 166.0
DEFAULT_REVERSE = False


class LineProfileHandler(AnalysisHandler):
    """Intensity plot for the active Line ROI."""

    refresh_reasons = ("frame", "open", "process", "roi")

    def __init__(self, context, component):
        super().__init__(context, component)
        self.energy_on = DEFAULT_ENERGY_OFF
        self.peak_shift = DEFAULT_PEAK_SHIFT
        self.pixel_per_ev = DEFAULT_PIXEL_PER_EV
        self.reverse = DEFAULT_REVERSE
        self._plot = pg.PlotWidget()
        self._plot.setLabel("left", "Intensity")
        self._plot.setVisible(False)
        self.apply_axis()

    def widget(self):
        return self._plot

    def params_changed(self, params):
        """Update x-axis mode, calibration, and direction."""
        self.energy_on = bool(params.get("energy", self.energy_on))
        self.reverse = bool(params.get("reverse", self.reverse))
        self.peak_shift = float(params.get("peak_shift", self.peak_shift))
        pixel_per_ev = float(params.get("pixel_per_ev", self.pixel_per_ev))
        if pixel_per_ev > 0:
            self.pixel_per_ev = pixel_per_ev
        self.apply_axis()
        self.refresh_if_active()

    def process_params(self):
        """The persisted x-axis mode and calibration (round-trips via workflow)."""
        return {
            "energy": self.energy_on,
            "peak_shift": self.peak_shift,
            "pixel_per_ev": self.pixel_per_ev,
            "reverse": self.reverse,
        }

    def apply_axis(self):
        """Sync the bottom axis label and direction to the current mode."""
        self._plot.setLabel("bottom", self.axis_label())
        self._plot.getPlotItem().invertX(self.reverse)

    def axis_label(self):
        """The bottom-axis label for the current x-axis mode."""
        return "Energy [eV]" if self.energy_on else "Sample"

    def energy_axis(self, size):
        """The energy [eV] x-axis for a profile of ``size`` pixels."""
        return self.peak_shift + np.arange(size) / self.pixel_per_ev

    def refresh(self):
        images = self.context.images
        if images.n_frames == 0 or not self.context.roi.active():
            self._plot.clear()
            return

        profile = self.line_profile()
        if profile is None:
            self._plot.clear()
            return

        size = profile.size
        x = self.energy_axis(size) if self.energy_on else np.arange(size)
        self._plot.clear()
        plot_profile_trace(self._plot, x, profile)
        self._plot.autoRange()

    def line_profile(self):
        """Finite current-frame Line ROI profile, or None."""
        images = self.context.images
        roi = self.context.image_view.roi
        if not isinstance(roi, pg.LineROI):
            return None

        item = self.context.image_view.getImageItem()
        return line_roi_profile(images.edited(images.current_index), roi, item)


line_profile = plugin("Line Profile")

line_profile.analysis(
    LineProfileHandler,
    process_id="line_profile",
    always_on=True,
    fill=True,
    params={
        "energy": Bool(DEFAULT_ENERGY_OFF, label="Energy axis"),
        "peak_shift": Float(DEFAULT_PEAK_SHIFT, label="Peak shift [eV]"),
        "pixel_per_ev": Float(DEFAULT_PIXEL_PER_EV, min=0.001, label="Pixel per eV"),
        "reverse": Bool(DEFAULT_REVERSE, label="Reverse axis"),
    },
    help="Plot intensity along the active Line ROI.",
)
