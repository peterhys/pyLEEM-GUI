import numpy as np
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyqtgraph")

import pyqtgraph as pg
from PySide6.QtCore import Qt

from pyleem_gui.image import ImageLayer
from pyleem_gui.process import Process

from ..support import FakeReader, _GradientReader


class _FakeWheel:
    """Minimal stand-in for a QGraphicsSceneWheelEvent."""

    def __init__(self, delta, ctrl=False, orientation=Qt.Vertical):
        self._delta, self._ctrl, self._orientation = delta, ctrl, orientation
        self.accepted = False

    def delta(self):
        return self._delta

    def modifiers(self):
        return Qt.ControlModifier if self._ctrl else Qt.NoModifier

    def orientation(self):
        return self._orientation

    def accept(self):
        self.accepted = True


def _viewer_with_frames(qtbot, tmp_path, n=3):
    from pyleem_gui.ui.viewer import Viewer

    for i in range(n):
        (tmp_path / f"{i:03d}.dat").write_bytes(b"")
    images = ImageLayer(reader_factory=FakeReader)
    images.open_folder(tmp_path)
    viewer = Viewer(images)
    qtbot.addWidget(viewer)
    return viewer, images


# viewer and main window
def test_menu_button_hidden_on_image(context, qtbot):
    from pyleem_gui.ui.viewer import Viewer

    viewer = Viewer(context.images)
    qtbot.addWidget(viewer)
    assert viewer.image_view.ui.menuBtn.isHidden()


def test_viewer_step_navigation(qtbot, tmp_path):
    from pyleem_gui.ui.viewer import Viewer

    for i in range(3):
        (tmp_path / f"{i:03d}.dat").write_bytes(b"")
    images = ImageLayer(reader_factory=FakeReader)
    images.open_folder(tmp_path)

    viewer = Viewer(images)
    qtbot.addWidget(viewer)

    # step() is what the arrow keys and mouse wheel call to move through frames.
    viewer.step(1)
    assert images.current_index == 1
    viewer.step(1)
    assert images.current_index == 2
    viewer.step(1)  # clamped at last frame
    assert images.current_index == 2
    viewer.step(-1)
    assert images.current_index == 1


def test_wheel_scrolls_through_stack(qtbot, tmp_path):
    viewer, images = _viewer_with_frames(qtbot, tmp_path, n=5)
    vb = viewer.image_view.view

    # Wheel down advances the stack; wheel up steps back.
    down = _FakeWheel(delta=-120)
    vb.wheelEvent(down)
    assert images.current_index == 1 and down.accepted
    vb.wheelEvent(_FakeWheel(delta=120))
    assert images.current_index == 0

    # Small trackpad deltas accumulate until they reach one full notch.
    vb.wheelEvent(_FakeWheel(delta=-40))
    vb.wheelEvent(_FakeWheel(delta=-40))
    assert images.current_index == 0
    vb.wheelEvent(_FakeWheel(delta=-40))
    assert images.current_index == 1

    vb.wheelEvent(_FakeWheel(delta=-240))  # two notches in one event
    assert images.current_index == 3

    vb.wheelEvent(_FakeWheel(delta=-240, orientation=Qt.Horizontal))
    assert images.current_index == 3  # horizontal wheel does not step


def test_ctrl_wheel_zooms_instead_of_scrolling(qtbot, tmp_path, monkeypatch):
    viewer, images = _viewer_with_frames(qtbot, tmp_path)
    vb = viewer.image_view.view

    # Ctrl+wheel routes to the default (zoom) handler and leaves the frame put.
    zoomed = []
    monkeypatch.setattr(
        pg.ViewBox, "wheelEvent", lambda self, ev, axis=None: zoomed.append(True)
    )
    vb.wheelEvent(_FakeWheel(delta=-120, ctrl=True))
    assert zoomed == [True]
    assert images.current_index == 0


def test_mode_selector_switches_view_mode(qtbot, tmp_path):
    from PySide6.QtWidgets import QRadioButton

    viewer, images = _viewer_with_frames(qtbot, tmp_path)
    reasons = []
    images.image_update.connect(reasons.append)
    buttons = viewer._mode_buttons
    assert all(isinstance(b, QRadioButton) for b in buttons.values())
    assert buttons["rendered"].isChecked()
    assert sum(b.isChecked() for b in buttons.values()) == 1

    assert viewer.view.mode == "rendered"  # rendered by default
    viewer._mode_buttons["raw"].click()
    assert viewer.view.mode == "raw" and "mode" in reasons
    assert sum(b.isChecked() for b in buttons.values()) == 1
    viewer._mode_buttons["edited"].click()
    assert viewer.view.mode == "edited"
    viewer._mode_buttons["rendered"].click()
    assert viewer.view.mode == "rendered"


def test_frame_box_shows_index_over_total_and_follows_navigation(qtbot, tmp_path):
    viewer, images = _viewer_with_frames(qtbot, tmp_path, n=5)
    # 1-based current frame over the total; the slider tracks the same index.
    assert viewer._frame_input.text() == "1"
    assert viewer._frame_total.text() == "/5"
    viewer.step(2)
    assert images.current_index == 2
    assert viewer._frame_input.text() == "3"
    assert viewer._slider.value() == 2

    viewer._frame_input.setText("4")
    viewer._frame_input.editingFinished.emit()
    assert images.current_index == 3  # 1-based 4 -> 0-based 3
    # Out-of-range input clamps to the last frame and the box re-syncs.
    viewer._frame_input.setText("99")
    viewer._frame_input.editingFinished.emit()
    assert images.current_index == 4
    assert viewer._frame_input.text() == "5"


def test_raw_mode_drops_contrast_levels(qtbot, tmp_path):
    from pyleem_gui.ui.viewer import Viewer

    for i in range(2):
        (tmp_path / f"{i:03d}.dat").write_bytes(b"")
    images = ImageLayer(reader_factory=_GradientReader)
    images.open_folder(tmp_path)
    viewer = Viewer(images)
    qtbot.addWidget(viewer)

    item = viewer.image_view.getImageItem()
    # Auto contrast is a rendered process; rendered mode applies its levels.
    images.workflow.add_process(Process("builtin:autolevel"))
    rendered = tuple(item.levels)

    # Switching to raw mode drops the rendered view spec -> auto (full-range) levels.
    viewer._mode_buttons["raw"].click()
    raw = tuple(item.levels)
    assert raw[0] <= 1 and raw[1] >= 98

    # Back to rendered re-applies the contrast levels.
    viewer._mode_buttons["rendered"].click()
    assert tuple(item.levels) == rendered
    item.setLevels([40, 60])  # a narrowed view it left behind
    images.workflow.delete_process(0)  # remove it from the workflow
    lo, hi = item.levels
    assert lo <= 1 and hi >= 98  # the view reverts to the auto (full-data) levels


def test_refresh_image_drives_redraw(qtbot, tmp_path):
    from pyleem_gui.ui.viewer import Viewer

    for i in range(2):
        (tmp_path / f"{i:03d}.dat").write_bytes(b"")
    images = ImageLayer(reader_factory=_GradientReader)
    images.open_folder(tmp_path)
    viewer = Viewer(images)
    qtbot.addWidget(viewer)
    item = viewer.image_view.getImageItem()

    # Changing the displayed frame redraws through the image layer's image_update.
    images.set_index(1)
    assert np.asarray(item.image).max() == 99

    # refresh_image re-renders the current frame: clobber the item, then redraw.
    item.updateImage(np.zeros((10, 10), dtype=np.uint16))
    assert np.asarray(item.image).max() == 0
    viewer.refresh_image(auto_levels=True)
    assert np.asarray(item.image).max() == 99  # restored from the image layer's frame
