"""The pyqtgraph view layer."""

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QRadioButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ..roi import array_axes
from ..view import ViewLayer

pg.setConfigOptions(imageAxisOrder="row-major")


class _StackViewBox(pg.ViewBox):
    """ViewBox where wheel scroll steps frames and Ctrl+wheel zooms."""

    wheelScrolled = Signal(int)
    _NOTCH = 120

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._wheel_accum = 0

    def wheelEvent(self, ev, axis=None):
        if ev.modifiers() & Qt.ControlModifier:
            super().wheelEvent(ev, axis)
            return
        if ev.orientation() == Qt.Vertical:
            self._wheel_accum += ev.delta()
            steps = int(self._wheel_accum / self._NOTCH)
            if steps:
                self._wheel_accum -= steps * self._NOTCH
                self.wheelScrolled.emit(-steps)
        ev.accept()


class _StackImageView(pg.ImageView):
    """ImageView with the pyqtgraph profile pane disabled."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ui.roiPlot.hide()

    def roiClicked(self):
        self.roi.setVisible(self.ui.roiBtn.isChecked())
        self.ui.roiPlot.setVisible(False)

    def roiChanged(self):
        pass


class Viewer(QWidget):
    """Image display, frame navigation, and the raw|edited|rendered selector."""

    def __init__(self, images):
        super().__init__()
        self._images = images
        self.view = ViewLayer(images)
        self.setFocusPolicy(Qt.StrongFocus)

        self._viewbox = _StackViewBox()
        self._viewbox.wheelScrolled.connect(self.step)
        self._image_view = _StackImageView(view=self._viewbox)
        self._image_view.ui.menuBtn.hide()

        self._slider = QSlider(Qt.Horizontal)
        self._slider.setMinimum(0)
        self._slider.setMaximum(0)
        self._slider.valueChanged.connect(self._images.set_index)

        self._frame_input = QLineEdit()
        self._frame_input.setFixedWidth(48)
        self._frame_input.setAlignment(Qt.AlignRight)
        self._frame_input.editingFinished.connect(self._on_frame_input)
        self._frame_total = QLabel("/0")

        frame_row = QHBoxLayout()
        frame_row.addWidget(QLabel("Frame"))
        frame_row.addWidget(self._slider, stretch=1)
        frame_row.addWidget(self._frame_input)
        frame_row.addWidget(self._frame_total)

        nav_layout = QVBoxLayout()
        nav_layout.addLayout(frame_row)
        nav_layout.addWidget(self.build_mode_selector())
        nav_widget = QWidget()
        nav_widget.setLayout(nav_layout)

        layout = QVBoxLayout(self)
        layout.addWidget(self._image_view, stretch=1)
        layout.addWidget(nav_widget)

        images.image_update.connect(self.on_image_update)
        self.refresh_all()

    def build_mode_selector(self):
        """Build the raw, edited, and rendered mode selector."""
        widget = QWidget()
        row = QHBoxLayout(widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(QLabel("View"))
        self._mode_group = QButtonGroup(self)
        self._mode_group.setExclusive(True)
        self._mode_buttons = {}
        for mode in ("raw", "edited", "rendered"):
            button = QRadioButton(mode.capitalize())
            button.toggled.connect(
                lambda checked, m=mode: self._on_mode_radio(m, checked)
            )
            self._mode_group.addButton(button)
            row.addWidget(button)
            self._mode_buttons[mode] = button
        row.addStretch(1)
        self._mode_buttons["rendered"].setChecked(True)
        return widget

    def _on_mode_radio(self, mode, checked):
        # QButtonGroup toggles the old button off before the new one on.
        if checked:
            self.view.set_mode(mode)

    @property
    def image_view(self):
        """The pyqtgraph image view, for plugins that add overlays."""
        return self._image_view

    def step(self, delta):
        self._images.set_index(self._images.current_index + delta)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Left:
            self.step(-1)
        elif event.key() == Qt.Key_Right:
            self.step(1)
        else:
            super().keyPressEvent(event)

    def on_image_update(self, reason):
        if reason == "open":
            self.refresh_all()
        elif reason in ("process", "mode"):
            self.refresh_image(auto_levels=True)
        elif reason == "frame":
            self._sync_frame_controls()
            self.refresh_image()

    def refresh_all(self):
        self._sync_frame_controls()
        self.refresh_image(auto_levels=True)

    def _sync_frame_controls(self):
        """Reflect the current frame in the slider and the [index]/total box."""
        n = self._images.n_frames
        index = self._images.current_index
        self._slider.blockSignals(True)
        self._slider.setMaximum(max(0, n - 1))
        self._slider.setValue(index)
        self._slider.blockSignals(False)
        self._frame_input.setText(str(index + 1) if n else "0")
        self._frame_total.setText(f"/{n}")

    def _on_frame_input(self):
        """Jump to the frame typed in the box (1-based); clamp and re-sync."""
        text = self._frame_input.text().strip()
        if text.isdigit():
            self._images.set_index(int(text) - 1)
        self._sync_frame_controls()

    def refresh_image(self, auto_levels=False):
        """Render the current frame through pyqtgraph."""
        if self._images.n_frames == 0:
            return
        image, view_spec = self.view.output()
        arr = np.asarray(image)
        self.sync_image_view_data(arr)
        item = self._image_view.getImageItem()
        levels = view_spec.get("levels")
        if levels is not None:
            item.updateImage(arr, levels=levels, autoLevels=False)
        else:
            item.updateImage(arr, autoLevels=auto_levels)

    def sync_image_view_data(self, arr):
        """Mirror displayed pixels into ImageView's backing store."""
        iv = self._image_view
        iv.image = arr
        iv.imageDisp = None
        if iv.axes.get("x") is None:
            x, y = array_axes(iv.imageItem)
            iv.axes = {"t": None, "x": x, "y": y, "c": None}
