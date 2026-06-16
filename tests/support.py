"""Shared Qt-free test scaffolding."""

import numpy as np
import tifffile


class FakeReader:
    """Fake reader keyed by the file-name index."""

    def __init__(self, path):
        self._value = int(path.stem)

    @property
    def metadata(self):
        return {"ImageHeight": (4, None), "ImageWidth": (4, None)}

    def read_image(self):
        return np.full((4, 4), self._value, dtype=np.uint16)


class TimeStampReader(FakeReader):
    """A FakeReader whose frames carry a TimeStamp one second apart."""

    @property
    def metadata(self):
        from datetime import datetime

        return {
            "ImageHeight": (4, None),
            "ImageWidth": (4, None),
            "TimeStamp": (datetime(2024, 1, 1, 0, 0, self._value), None),
        }


class RampReader:
    """A 64x64 diagonal ramp, offset by 100 per frame."""

    def __init__(self, path):
        self._k = int(path.stem)

    @property
    def metadata(self):
        return {"ImageHeight": (64, None), "ImageWidth": (64, None)}

    def read_image(self):
        ramp = np.add.outer(np.arange(64), np.arange(64)).astype(np.float64)
        return (ramp + self._k * 100.0).astype(np.uint16)


class _GradientReader:
    """A 10x10 ramp (values 0..99), for contrast/levels tests."""

    def __init__(self, path):
        pass

    @property
    def metadata(self):
        return {}

    def read_image(self):
        return np.arange(100, dtype=np.uint16).reshape(10, 10)


def activate_roi(builtin, shape):
    """Select a shape on the Builtin ROI controller and toggle it on."""
    roi = builtin.controller("ROI")
    roi.handler.shape.setCurrentText(shape)
    roi.toggle.setChecked(True)
    return roi


def curve_xy(handler):
    """The (x, y) data of a profile handler's first plotted curve, or None."""
    items = handler._plot.getPlotItem().listDataItems()
    if not items:
        return None
    return items[0].getData()


def curve_pen_color(handler):
    """The on-screen pen color of a profile handler's first plotted curve."""
    items = handler._plot.getPlotItem().listDataItems()
    if not items:
        return None
    return items[0].curve.opts["pen"].color()


def export_pen_color(handler):
    """The export pen color of a profile handler's first plotted item."""
    items = handler._plot.getPlotItem().listDataItems()
    if not items:
        return None
    return items[0].opts["pen"].color()


def write_dat_frames(directory, n=3):
    """Create empty numbered ``.dat`` frame paths for fake-reader tests."""
    for i in range(n):
        (directory / f"{i:03d}.dat").write_bytes(b"")
    return directory


def write_tiff(path, arr, info=None):
    """Write a TIFF; with ``info`` it is an ImageJ TIFF carrying that Info text."""
    kw = {"imagej": True, "metadata": {"Info": info}} if info is not None else {}
    tifffile.imwrite(str(path), arr, **kw)
    return path


def image_layer_with_frames(directory, reader_factory=FakeReader, n=3):
    """An ImageLayer opened on fake numbered frames."""
    from pyleem_gui.image import ImageLayer

    write_dat_frames(directory, n)
    images = ImageLayer(reader_factory=reader_factory)
    images.open_folder(directory)
    return images


def viewer_with_frames(qtbot, directory, reader_factory=FakeReader, n=3):
    """A Viewer and opened ImageLayer for GUI tests."""
    from pyleem_gui.ui.viewer import Viewer

    images = image_layer_with_frames(directory, reader_factory, n)
    viewer = Viewer(images)
    qtbot.addWidget(viewer)
    return viewer, images


def plugin_context_with_viewer(qtbot, directory, reader_factory=FakeReader, n=3):
    """A PluginContext backed by a real Viewer."""
    from pyleem_gui.plugins import PluginContext

    viewer, images = viewer_with_frames(qtbot, directory, reader_factory, n)
    context = PluginContext(
        images=images,
        image_view=viewer.image_view,
        view=viewer.view,
    )
    return context, viewer, images
