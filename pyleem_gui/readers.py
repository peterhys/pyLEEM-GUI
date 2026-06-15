"""Qt-free frame discovery and default data readers."""

import math
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import numpy as np

TIFF_SUFFIXES = (".tif", ".tiff")
# Rec. 601 luminance weights for RGB to grayscale.
_LUMA = np.array([0.299, 0.587, 0.114])


@dataclass
class TiffFrameRef:
    """One logical frame of a TIFF file: which page/slice and how to read it."""

    path: Path
    frame_index: int
    storage_mode: str  # "single" | "stack" | "single_rgb" | "stack_rgb"
    metadata: dict = field(default_factory=dict)


def tiff_layout(shape, axes):
    """Return ``(n_frames, storage_mode)`` for a TIFF series."""
    axes = axes.upper()
    if axes.endswith("YXS"):
        if shape[-1] not in (3, 4):
            raise ValueError(f"unsupported TIFF sample count {shape[-1]}")
        is_rgb, frame_axes = True, axes[:-3]
    elif axes.endswith("YX"):
        is_rgb, frame_axes = False, axes[:-2]
    else:
        raise ValueError(f"unsupported TIFF axes {axes!r} (shape {shape})")
    n_frames = math.prod(shape[: len(frame_axes)])
    mode = ("stack" if frame_axes else "single") + ("_rgb" if is_rgb else "")
    return n_frames, mode


def to_grayscale(frame):
    """Convert a 2D or RGB/RGBA frame to grayscale."""
    frame = np.asarray(frame)
    if frame.ndim == 2:
        return frame
    if frame.ndim == 3 and frame.shape[-1] in (3, 4):
        gray = frame[..., :3] @ _LUMA
        if np.issubdtype(frame.dtype, np.integer):
            return np.rint(gray).astype(frame.dtype)
        return gray
    raise ValueError(f"unsupported image shape {frame.shape}")


@lru_cache(maxsize=4)
def _read_tiff_array(path_str):
    """The whole TIFF array, cached so a stack is read once per file."""
    import tifffile

    return tifffile.imread(path_str)


def _tiff_series_info(path):
    """The TIFF's ``(shape, axes, imagej_info)`` without reading the pixels."""
    import tifffile

    with tifffile.TiffFile(str(path)) as tf:
        series = tf.series[0]
        shape, axes = tuple(series.shape), series.axes
        info = (tf.imagej_metadata or {}).get("Info")
    return shape, axes, info


class TiffFrameReader:
    """A reader for one TIFF frame, matching the reader contract."""

    def __init__(self, ref):
        self._ref = ref

    @property
    def metadata(self):
        return self._ref.metadata

    def read_image(self):
        arr = _read_tiff_array(str(self._ref.path))
        if "stack" in self._ref.storage_mode:
            # Collapse leading frame axes, keeping spatial/sample axes last.
            spatial = 3 if "rgb" in self._ref.storage_mode else 2
            arr = arr.reshape((-1,) + arr.shape[-spatial:])[self._ref.frame_index]
        # Copy so downstream edits cannot corrupt the cached array.
        return to_grayscale(arr).copy()


def _tiff_frame_refs(path):
    """One :class:`TiffFrameRef` per logical frame of a TIFF file."""
    from .metadata import parse_imagej_info

    shape, axes, info = _tiff_series_info(path)
    n_frames, mode = tiff_layout(shape, axes)
    metas = parse_imagej_info(info, n_frames)
    return [TiffFrameRef(Path(path), i, mode, metas[i]) for i in range(n_frames)]


def discover_file(path):
    """Frame refs for a single file: a ``.dat`` path, or a TIFF's frames."""
    _read_tiff_array.cache_clear()  # a fresh open re-reads from disk
    path = Path(path)
    if path.suffix.lower() in TIFF_SUFFIXES:
        return _tiff_frame_refs(path)
    return [path]


def discover_folder(path):
    """Frame refs for sorted ``.dat`` files, else sorted TIFF frames."""
    _read_tiff_array.cache_clear()  # a fresh open re-reads from disk
    path = Path(path)
    dats = sorted(path.glob("*.dat"))
    if dats:
        return list(dats)
    tiffs = sorted(p for p in path.iterdir() if p.suffix.lower() in TIFF_SUFFIXES)
    refs = []
    for tiff in tiffs:
        refs.extend(_tiff_frame_refs(tiff))
    return refs


def default_reader_factory(ref):
    """Build a reader for a frame ref: a TIFF frame, else a pyleem reader."""
    if isinstance(ref, TiffFrameRef):
        return TiffFrameReader(ref)
    from pyleem.reader import UViewReader  # lazy: keep this module pyleem-free

    return UViewReader(ref)
