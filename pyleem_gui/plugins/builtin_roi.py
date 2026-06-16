"""ROI render handler for the Builtin plugin."""

import logging

import pyqtgraph as pg
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .host import ComponentHandler, as_toggle
from .builtin_roi_editors import (
    SHAPES,
    CircleEditor,
    EllipseEditor,
    LineEditor,
    PolygonEditor,
    RectangleEditor,
)
from ..roi import line_points_width, roi_to_imagej

log = logging.getLogger(__name__)


def roi_pen():
    """The default ROI outline pen."""
    return pg.mkPen("#fff59d")


class ROIHandler(ComponentHandler):
    """Render handler for the live pyqtgraph ROI."""

    def __init__(self, context, component):
        super().__init__(context, component)
        self.image_view = context.image_view
        self.roi_service = context.roi
        self.line_width = 1.0
        # These guards break ROI-control and workflow-sync feedback loops.
        self._writing = False
        self._syncing = False
        # Keep discarded pyqtgraph ROIs alive; early GC can crash Qt.
        self._discarded = []
        self._button = as_toggle(self.image_view.ui.roiBtn, component.help)
        self.image_view.roi.setPen(roi_pen())

        self._shape_widget = QWidget()
        col = QVBoxLayout(self._shape_widget)
        col.setContentsMargins(0, 0, 0, 0)

        shape_row = QHBoxLayout()
        shape_row.addWidget(QLabel("Shape"))
        self.shape = QComboBox()
        self.shape.addItems(SHAPES)
        shape_row.addWidget(self.shape)
        col.addLayout(shape_row)

        self.panel = QStackedWidget()
        self.editors = {}
        for editor in (
            RectangleEditor(),
            EllipseEditor(),
            CircleEditor(),
            PolygonEditor(),
            LineEditor(),
        ):
            self.editors[editor.shape] = editor
            self.panel.addWidget(editor)
            editor.edited.connect(self._on_controls_edited)
        col.addWidget(self.panel)

        self._save_button = QPushButton("Save ROI...")
        self._save_button.clicked.connect(self._save_roi)
        col.addWidget(self._save_button)

        # Connect after populating so the initial item does not swap the ROI.
        self.shape.currentTextChanged.connect(self._set_shape)
        self._button.toggled.connect(self.changed)
        self._button.toggled.connect(self._publish)
        self._wire_roi(self.image_view.roi)
        self._show_editor(self.shape.currentText())  # Rectangle by default

        # Render-only overlay visibility follows view mode and toggle state.
        self._button.clicked.connect(self._apply_mode_visibility)
        self.on_image_reason("mode", self._apply_mode_visibility)
        self._apply_mode_visibility()

    def toggle_button(self):
        return self._button

    def widget(self):
        return self._shape_widget

    def set_active(self, on):
        """Drive the built-in ROI button."""
        if self._button.isChecked() != on:
            self._button.setChecked(on)
            # setChecked fires toggled but not clicked, so call pyqtgraph too.
            self.image_view.roiClicked()
        self._apply_mode_visibility()
        self._publish()

    def is_active(self):
        return self._button.isChecked()

    def status_text(self):
        return self.roi_params_text()

    # geometry panel
    def current_editor(self):
        return self.editors[self.shape.currentText()]

    def _show_editor(self, shape):
        self.panel.setCurrentWidget(self.editors[shape])
        self._sync_controls()  # populate from the live ROI

    def _sync_controls(self):
        """Mirror the live ROI's geometry into the current shape's controls."""
        editor = self.current_editor()
        item = self.image_view.getImageItem()
        editor.set_controls(editor.read_roi(self.image_view.roi, item))
        if isinstance(self.image_view.roi, pg.LineROI):
            self.line_width = float(self.image_view.roi.size().y())

    def _on_controls_edited(self):
        """A control changed: push the new geometry onto the live ROI."""
        if self._syncing:
            return
        self._syncing = True
        try:
            editor = self.current_editor()
            params = editor.read_controls()
            if self.shape.currentText() == "Line":
                self._apply_line(params)  # the swap records geometry + publishes
                return
            editor.write_roi(
                self.image_view.roi,
                self.image_view.getImageItem(),
                params,
                finish=False,
            )
        finally:
            self._syncing = False
        self._write_geometry()

    # process round-trip
    def process_params(self):
        """The ROI placement recorded on its process entry (per-shape schema)."""
        editor = self.current_editor()
        params = {"shape": self.shape.currentText()}
        params.update(
            editor.read_roi(self.image_view.roi, self.image_view.getImageItem())
        )
        return params

    def params_changed(self, params):
        """Restore shape and geometry from workflow params."""
        if self._writing:
            return
        shape = params.get("shape")
        if shape in SHAPES and shape != self.shape.currentText():
            self.shape.blockSignals(True)
            self.shape.setCurrentText(shape)
            self.shape.blockSignals(False)
            self._set_shape(shape)
        self._restore_geometry(params)

    def _restore_geometry(self, params):
        """Apply imported params to the live ROI and the controls."""
        self._syncing = True
        try:
            shape = self.shape.currentText()
            roi = self.image_view.roi
            item = self.image_view.getImageItem()
            if shape == "Line":
                self._apply_line(params, record=False)
            else:
                self.current_editor().write_roi(roi, item, params, finish=False)
            if (
                shape == "Polygon"
                and params.get("points") is None
                and params.get("pos") is not None
            ):
                roi.setPos(params["pos"])  # old {pos}-only entry: position only
            self._sync_controls()
        finally:
            self._syncing = False
        self._write_geometry()

    def _write_geometry(self, *_args):
        # Break the restore -> finished-signal -> restore feedback cycle.
        if self._writing:
            return
        self._writing = True
        try:
            layer = self.context.workflow
            index = layer.find_process(self.component.id)
            if index is not None:
                layer.update_process(index, self.process_params())
        finally:
            self._writing = False
        self._publish()

    def _apply_line(self, params, record=True):
        """Swap in a LineROI for the given endpoints and width."""
        points, width = line_points_width(params)
        self.line_width = float(width)
        (x1, y1), (x2, y2) = points
        self._swap_roi(
            pg.LineROI([x1, y1], [x2, y2], width=self.line_width, pen=roi_pen()),
            record=record,
        )

    # shared ROI service
    def _publish(self, *_args):
        self.roi_service.publish(self if self.is_active() else None)

    def imagej_roi(self):
        """An ImageJ ROI object for the active shape, or None."""
        return roi_to_imagej(
            self.image_view.roi,
            self.shape.currentText(),
            self.image_view.getImageItem(),
            self.line_width,
        )

    def _save_roi(self, *_args):
        if not self.is_active():
            self.context.status("No active ROI to save")
            return
        try:
            roi_obj = self.imagej_roi()
        except Exception:  # noqa: BLE001 - conversion must not crash the app
            log.warning("could not convert ROI for export", exc_info=True)
            roi_obj = None
        if roi_obj is None:
            QMessageBox.information(
                self._shape_widget,
                "Save ROI",
                f"Cannot export a {self.shape.currentText()} ROI to ImageJ.",
            )
            return
        path, _ = QFileDialog.getSaveFileName(
            self._shape_widget, "Save ROI", "", "ImageJ ROI (*.roi)"
        )
        if not path:
            return
        try:
            roi_obj.tofile(path)
            self.context.status(f"Saved ROI to {path}")
        except Exception:  # noqa: BLE001
            log.warning("could not write ROI file %s", path, exc_info=True)
            QMessageBox.warning(
                self._shape_widget, "Save ROI", "Failed to write the ROI file."
            )

    # view-mode visibility
    def _apply_mode_visibility(self, *_args):
        show = self._button.isChecked() and self.context.view.mode == "rendered"
        self.image_view.roi.setVisible(show)

    # shape swapping
    def create(self, name):
        if name == "Rectangle":
            return pg.RectROI([10, 10], [60, 60], pen=roi_pen())
        if name == "Ellipse":
            return pg.EllipseROI([10, 10], [60, 60], pen=roi_pen())
        if name == "Circle":
            return pg.CircleROI([10, 10], [60, 60], pen=roi_pen())
        if name == "Polygon":
            return pg.PolyLineROI(
                [[10, 10], [70, 15], [40, 70]],
                closed=True,
                pen=roi_pen(),
            )
        if name == "Line":
            return pg.LineROI(
                [10, 10], [100, 100], width=self.line_width, pen=roi_pen()
            )
        raise ValueError(f"unknown ROI shape: {name}")

    def _set_shape(self, name):
        self._swap_roi(self.create(name))
        self._show_editor(name)

    def _swap_roi(self, new, record=True):
        """Replace the live ROI and rewire geometry signals."""
        iv = self.image_view
        old = iv.roi

        # Drop all connections; per-slot disconnects warn for missing slots.
        for signal in (old.sigRegionChanged, old.sigRegionChangeFinished):
            try:
                signal.disconnect()
            except (TypeError, RuntimeError):
                pass
        iv.view.removeItem(old)
        self._discarded.append(old)  # keep alive; see __init__

        iv.roi = new
        iv.view.addItem(new)
        self._wire_roi(new)

        self._apply_mode_visibility()
        if record:
            self._write_geometry()  # record the new shape on the process entry
        self.changed.emit()
        self._publish()

    def _wire_roi(self, roi):
        """Wire control-sync and geometry-record signals for the live ROI."""
        roi.sigRegionChanged.connect(self._on_region_changed)
        roi.sigRegionChangeFinished.connect(self._write_geometry)

    def _on_region_changed(self, *_args):
        """A direct ROI drag: update the controls and the host status."""
        self.changed.emit()  # the host re-syncs status/process from the live ROI
        if not self._syncing:
            self._sync_controls()

    def roi_params_text(self):
        name = self.component.id  # namespaced id, e.g. "builtin:ROI"
        roi = self.image_view.roi
        pos = roi.pos()
        if isinstance(roi, pg.CircleROI):
            d = roi.size()[0]
            return (
                f"{name} Circle  center=({pos.x() + d / 2:.0f}, {pos.y() + d / 2:.0f})  "
                f"r={d / 2:.0f}"
            )
        if isinstance(roi, pg.PolyLineROI):
            try:
                vertices = len(roi.getState()["points"])
            except (KeyError, TypeError):
                vertices = len(roi.handles)
            return f"{name} Polygon  pos=({pos.x():.0f}, {pos.y():.0f})  vertices={vertices}"
        if isinstance(roi, pg.LineROI):
            return (
                f"{name} Line  pos=({pos.x():.0f}, {pos.y():.0f})  "
                f"width={self.line_width:.0f}"
            )
        size = roi.size()
        return (
            f"{name} {self.shape.currentText()}  pos=({pos.x():.0f}, {pos.y():.0f})  "
            f"size=({size.x():.0f}, {size.y():.0f})"
        )
