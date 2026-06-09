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

pg.setConfigOptions(imageAxisOrder="row-major")


class _StackViewBox(pg.ViewBox):
    """Image view box: a plain mouse wheel scrolls through the stack, and
    Ctrl+wheel zooms.

    pyqtgraph's default is wheel-to-zoom; for a stack viewer it is more natural to
    step frames with the wheel and reserve zoom for Ctrl+wheel. Vertical wheel
    deltas are accumulated and one frame is stepped per notch (120 units), so a
    mouse wheel advances a frame per click while a trackpad's stream of small
    deltas does not race through the stack.
    """

    wheelScrolled = Signal(int)  # signed number of frames to advance
    _NOTCH = 120  # Qt wheel delta for one detent (15 degrees)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._wheel_accum = 0

    def wheelEvent(self, ev, axis=None):
        if ev.modifiers() & Qt.ControlModifier:
            super().wheelEvent(ev, axis)  # Ctrl+wheel: zoom (default)
            return
        if ev.orientation() == Qt.Vertical:  # ignore horizontal scrolling
            self._wheel_accum += ev.delta()
            steps = int(self._wheel_accum / self._NOTCH)
            if steps:
                self._wheel_accum -= steps * self._NOTCH
                self.wheelScrolled.emit(-steps)  # wheel up (delta>0) -> previous
        ev.accept()


class Viewer(QWidget):
    """Image display, frame navigation, and the raw|edited|rendered selector."""

    # Emitted to request an image redraw; the bool asks the slot to re-derive
    # (auto) display levels (a structural change) rather than keep them (browsing).
    image_updated = Signal(bool)

    def __init__(self, session):
        super().__init__()
        self._session = session
        self.setFocusPolicy(Qt.StrongFocus)

        # A plain wheel scrolls the stack; Ctrl+wheel zooms (see _StackViewBox).
        self._viewbox = _StackViewBox()
        self._viewbox.wheelScrolled.connect(self.step)
        self._image = pg.ImageView(view=self._viewbox)
        # The built-in ROI button and normalization group are relocated into the
        # ROI and Normalization plugin tabs; the Menu button (which only toggled
        # the normalization group) is no longer needed.
        self._image.ui.menuBtn.hide()

        # Top nav row: the frame slider plus a current/total frame box.
        self._slider = QSlider(Qt.Horizontal)
        self._slider.setMinimum(0)
        self._slider.setMaximum(0)
        self._slider.valueChanged.connect(self._session.set_index)

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

        # Two stacked rows: frame controls on top, view-mode selector below.
        nav_layout = QVBoxLayout()
        nav_layout.addLayout(frame_row)
        nav_layout.addWidget(self.build_mode_selector())
        nav_widget = QWidget()
        nav_widget.setLayout(nav_layout)

        layout = QVBoxLayout(self)
        layout.addWidget(self._image, stretch=1)
        layout.addWidget(nav_widget)

        self.image_updated.connect(self.update_image)
        session.image_update.connect(self.on_image_update)
        self.refresh_all()

    def build_mode_selector(self):
        """A mutually-exclusive raw|edited|rendered radio selector.

        Backed by an exclusive QButtonGroup with rendered checked by default, so
        exactly one mode is always selected.
        """
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
                lambda checked, m=mode: self._session.set_mode(m) if checked else None
            )
            self._mode_group.addButton(button)
            row.addWidget(button)
            self._mode_buttons[mode] = button
        row.addStretch(1)
        self._mode_buttons["rendered"].setChecked(True)
        return widget

    @property
    def image_view(self):
        """The pyqtgraph image view, for plugins that add overlays."""
        return self._image

    def step(self, delta):
        self._session.set_index(self._session.current_index + delta)

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
            # The process list or the view mode changed: re-derive the display
            # levels so dropping a rendered process (or switching to raw/edited)
            # reverts to auto levels instead of leaving the ones a rendered op set.
            # An active rendered op still supplies its own levels, which win below.
            self.refresh_image(auto_levels=True)
        elif reason == "frame":
            self._sync_frame_controls()
            self.refresh_image()  # browsing keeps levels stable across frames

    def refresh_all(self):
        self._sync_frame_controls()
        # Auto-level once when a folder is loaded; preserve levels afterwards.
        self.refresh_image(auto_levels=True)

    def _sync_frame_controls(self):
        """Reflect the current frame in the slider and the [index]/total box."""
        n = self._session.n_frames
        index = self._session.current_index
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
            self._session.set_index(int(text) - 1)
        self._sync_frame_controls()

    def refresh_image(self, auto_levels=False):
        """Request a redraw of the current frame via the image_updated signal."""
        if self._session.n_frames == 0:
            return
        self.image_updated.emit(auto_levels)

    def sync_image_view_data(self, arr):
        """Keep ImageView's backing store in sync for ROI profiling.

        The viewer pushes pixels through the image item directly, but
        pyqtgraph's profile plot reads ``ImageView.image`` inside
        ``roiChanged``. Without this sync the ROI toggle shows an empty plot.
        """
        iv = self._image
        iv.image = arr
        iv.imageDisp = None
        if iv.axes.get("x") is None:
            x, y = (0, 1) if iv.imageItem.axisOrder == "col-major" else (1, 0)
            iv.axes = {"t": None, "x": x, "y": y, "c": None}

    def update_image(self, auto_levels=False):
        """Re-render the current frame through pyqtgraph's image-item update.

        Connected to image_updated. A rendered process can set explicit levels in
        the view spec; otherwise the levels are re-derived when ``auto_levels`` is
        set (load / process / mode change) and kept stable while browsing frames.
        """
        if self._session.n_frames == 0:
            return
        image, view_spec = self._session.output()
        arr = np.asarray(image)
        self.sync_image_view_data(arr)
        item = self._image.getImageItem()
        levels = view_spec.get("levels")
        if levels is not None:
            item.updateImage(arr, levels=levels, autoLevels=False)
        else:
            item.updateImage(arr, autoLevels=auto_levels)
        if self._image.ui.roiBtn.isChecked():
            self._image.roiChanged()
