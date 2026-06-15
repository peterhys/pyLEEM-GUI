import subprocess
import sys

import numpy as np
import pytest

from pyleem_gui.image import ImageLayer

from .support import write_tiff


def test_open_single_grayscale_tiff(tmp_path):
    p = write_tiff(tmp_path / "img.tif", np.full((6, 8), 42, np.uint16))
    images = ImageLayer()
    images.open_file(p)
    assert images.n_frames == 1
    assert images.raw(0).shape == (6, 8)
    assert images.raw(0).dtype == np.uint16
    assert int(images.raw(0)[0, 0]) == 42
    assert images.metadata(0) == {}  # no ImageJ Info -> no metadata


def test_open_multiframe_tiff_stack(tmp_path):
    arr = np.stack([np.full((6, 8), i * 5, np.uint16) for i in range(5)])
    p = write_tiff(tmp_path / "stack.tif", arr)
    images = ImageLayer()
    images.open_file(p)
    assert images.n_frames == 5
    assert [int(images.raw(i)[0, 0]) for i in range(5)] == [0, 5, 10, 15, 20]
    assert images.raw(2).dtype == np.uint16


def test_open_folder_of_tiffs_sorted(tmp_path):
    for i in (2, 0, 1):  # written out of order
        write_tiff(tmp_path / f"{i:03d}.tif", np.full((4, 4), i, np.uint16))
    images = ImageLayer()
    images.open_folder(tmp_path)
    assert images.n_frames == 3
    assert [int(images.raw(i)[0, 0]) for i in range(3)] == [0, 1, 2]


def test_tiff_metadata_parses_per_frame_info(tmp_path):
    info = "[Frame 0]\nEnergy = 1.0 [eV]\n[Frame 1]\nEnergy = 2.0 [eV]"
    arr = np.stack([np.zeros((4, 4), np.uint16), np.zeros((4, 4), np.uint16)])
    p = write_tiff(tmp_path / "s.tif", arr, info=info)
    images = ImageLayer()
    images.open_file(p)
    assert images.metadata(0)["Energy"] == (1.0, "eV")
    assert images.metadata(1)["Energy"] == (2.0, "eV")


def test_reopen_modified_tiff_reads_fresh(tmp_path):
    # Reopening the same path after the file changed re-reads from disk (the
    # whole-array cache is cleared on open).
    p = tmp_path / "x.tif"
    write_tiff(p, np.full((4, 4), 1, np.uint16))
    images = ImageLayer()
    images.open_file(p)
    assert int(images.raw(0)[0, 0]) == 1

    write_tiff(p, np.full((4, 4), 9, np.uint16))  # same path, new content
    images.open_file(p)
    assert int(images.raw(0)[0, 0]) == 9


def test_rgb_tiff_converts_to_grayscale_and_ignores_alpha(tmp_path):
    cases = [
        ("rgb.tif", (4, 4, 3), 1, round(0.587 * 255)),
        ("rgba.tif", (4, 4, 4), 0, round(0.299 * 255)),
    ]
    for name, shape, channel, expected in cases:
        arr = np.zeros(shape, np.uint8)
        arr[..., channel] = 255
        if shape[-1] == 4:
            arr[..., 3] = 0  # alpha is ignored
        p = write_tiff(tmp_path / name, arr)
        images = ImageLayer()
        images.open_file(p)
        frame = images.raw(0)
        assert frame.ndim == 2
        assert int(frame[0, 0]) == expected


def test_tiff_layout_uses_axes():
    from pyleem_gui.readers import tiff_layout

    assert tiff_layout((6, 8), "YX") == (1, "single")
    assert tiff_layout((3, 6, 8), "CYX") == (3, "stack")  # narrow stack is not RGB
    assert tiff_layout((6, 8, 3), "YXS") == (1, "single_rgb")
    assert tiff_layout((3, 6, 8, 3), "QYXS") == (3, "stack_rgb")
    assert tiff_layout((2, 3, 6, 8), "TZYX") == (6, "stack")  # frame axes flatten
    # A leading sample axis (planar, e.g. tifffile guessing SYX for a narrow
    # stack) is treated as frames -- only a trailing S is RGB.
    assert tiff_layout((4, 6, 8), "SYX") == (4, "stack")


def test_unsupported_tiff_layout_raises():
    from pyleem_gui.readers import tiff_layout

    with pytest.raises(ValueError):
        tiff_layout((6, 8, 5), "YXS")  # 5 samples -- not RGB/RGBA
    with pytest.raises(ValueError):
        tiff_layout((4, 4), "QT")  # no spatial Y/X axes


def test_to_grayscale_rejects_unsupported_shape():
    from pyleem_gui.readers import to_grayscale

    with pytest.raises(ValueError):
        to_grayscale(np.zeros((4, 4, 5)))  # not 2D or 3/4-channel


def test_readers_module_is_qt_free():
    code = (
        "import sys, pyleem_gui.readers\n"
        "bad = sorted(m for m in sys.modules if 'PySide6' in m or m == 'pyqtgraph')\n"
        "assert not bad, bad\n"
    )
    subprocess.run([sys.executable, "-c", code], check=True)
