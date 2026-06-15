"""Builtin plugin entrypoint for levels and ROI."""

import json

import numpy as np

from .builtin_roi import ROIHandler
from .host import ComponentHandler
from .spec import plugin


class ManualLevelHandler(ComponentHandler):
    """Render handler for manual levels and gradient."""

    def __init__(self, context, component):
        super().__init__(context, component)
        self.image_view = context.image_view
        self.histogram = self.image_view.getHistogramWidget().item
        self._on = False
        self._dragging = False  # a user gesture is moving the region
        self._suppress = False  # the handler is restoring the gradient itself
        lo, hi = self.histogram.getLevels()
        self._levels = [round(float(lo), 1), round(float(hi), 1)]
        self._gradient = self._gradient_state()
        self._default_gradient = self._gradient_state()
        # Record only the final drag state.
        self.histogram.sigLevelsChanged.connect(self._on_levels_changing)
        self.histogram.sigLevelChangeFinished.connect(self._on_levels_finished)
        # Ignore per-change LUT recomputes; only drag-end records.
        self.histogram.gradient.sigGradientChangeFinished.connect(
            self._on_gradient_changed
        )
        self.on_image_reason("mode", self._on_mode_changed)

    @staticmethod
    def process_apply(image, params):
        """Apply recorded levels during workflow replay."""
        levels = params.get("levels")
        if levels is None:
            return {}
        return {"levels": (float(levels[0]), float(levels[1]))}

    def set_active(self, on):
        if self._on and not on:
            # Turning off resets the display adjustment.
            self._apply_gradient(self._default_gradient)
        self._on = on

    def is_active(self):
        return self._on

    def process_params(self):
        """The recorded levels and gradient carried on the process entry."""
        return {"levels": list(self._levels), "gradient": self._gradient}

    def params_changed(self, params):
        """Restore the adjustment from workflow params (drives the widgets)."""
        levels = params.get("levels")
        if levels is not None:
            self._levels = [round(float(levels[0]), 1), round(float(levels[1]), 1)]
            if self.context.view.mode == "rendered":
                self.histogram.setLevels(float(levels[0]), float(levels[1]))
        gradient = params.get("gradient")
        if gradient is not None:
            self._apply_gradient(gradient)

    def status_text(self):
        lo, hi = self._levels
        return f"{self.component.id} levels=({lo:g}, {hi:g})"

    # gradient helpers
    def _gradient_state(self):
        """The gradient editor state as a JSON-able dict (stable for compare)."""
        return json.loads(json.dumps(self.histogram.gradient.saveState()))

    def _set_gradient_widget(self, state):
        """Drive the gradient editor without recording it."""
        self._suppress = True
        try:
            self.histogram.gradient.restoreState(json.loads(json.dumps(state)))
        finally:
            self._suppress = False

    def _apply_gradient(self, state):
        """Set the recorded gradient and drive the editor to match."""
        self._gradient = json.loads(json.dumps(state))
        self._set_gradient_widget(self._gradient)

    # user gesture detection
    def _on_levels_changing(self):
        # pyqtgraph sets moving flags only for mouse gestures.
        region = self.histogram.region
        if region.moving or any(line.moving for line in region.lines):
            self._dragging = True

    def _on_levels_finished(self):
        """A levels move ended: record it if it was a user drag."""
        if not self._dragging:
            return  # the region followed a redraw or a restore, not the user
        self._dragging = False
        self._record()

    def _on_gradient_changed(self, *_args):
        """A gradient drag ended: record it unless the handler drove it."""
        if self._suppress:
            return  # our own restore, not the user dragging a color stop
        if self._gradient_state() == self._gradient:
            return  # no actual change (e.g. a passive lookup-table recompute)
        self._record()

    def _on_mode_changed(self):
        """Reset or restore the display when the view mode changes."""
        if not self._on:
            return
        if self.context.view.mode == "rendered":
            self._set_gradient_widget(self._gradient)  # restore the record
        else:
            self._set_gradient_widget(self._default_gradient)  # visual reset only

    def _record(self):
        if self.context.view.mode != "rendered":
            return  # the adjustment lives in the rendered view only
        lo, hi = self.histogram.getLevels()
        self._levels = [round(float(lo), 1), round(float(hi), 1)]
        self._gradient = self._gradient_state()
        self._on = True
        self.changed.emit()  # the host mirrors the entry, toggle, and status
        self._write()

    def _write(self):
        layer = self.context.workflow
        index = layer.find_process(self.component.id)
        if index is not None and layer.processes[index].params != self.process_params():
            layer.update_process(index, self.process_params())


def auto_contrast_levels(image, num_bins=256):
    """Compute ImageJ-style auto-contrast display limits."""
    pixel_count = image.size
    threshold = pixel_count // 5000

    img_min = float(np.min(image))
    img_max = float(np.max(image))

    if img_min == img_max:
        return img_min, img_max

    counts, bin_edges = np.histogram(image, bins=num_bins, range=(img_min, img_max))

    lo = 0
    while lo < num_bins and counts[lo] <= threshold:
        lo += 1

    hi = num_bins - 1
    while hi > 0 and counts[hi] <= threshold:
        hi -= 1

    if lo > hi:
        return img_min, img_max

    return float(bin_edges[lo]), float(bin_edges[hi + 1])


builtin = plugin("Builtin")


@builtin.render(
    process_id="autolevel",  # registered as the namespaced id "builtin:autolevel"
    help="ImageJ-style auto level; sets the display levels (brightness and "
    "contrast) from the image. Replaces manual level.",
    replaces=["manuallevel"],
)
def autolevel(image, params):
    lo, hi = auto_contrast_levels(image)
    return {"levels": (lo, hi)}


builtin.render(
    ManualLevelHandler,
    process_id="manuallevel",
    help="Manual level: drag the viewer histogram -- the levels region for "
    "brightness/contrast, or the gradient color-stop arrows -- to adjust the "
    "display; the levels and gradient are recorded on the process entry and "
    "replayed by the workflow. Replaces auto level.",
    replaces=["autolevel"],
)

builtin.render(
    ROIHandler,
    process_id="ROI",
    help="Place a region of interest; profile and parameters update live.",
)
