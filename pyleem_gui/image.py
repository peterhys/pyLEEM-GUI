"""The image layer: per-image data over the persistent process layer."""

import logging

import numpy as np

from .metadata import imagej_info
from .process import ProcessLayer, Signal, apply_edited
from .readers import default_reader_factory, discover_file, discover_folder

log = logging.getLogger(__name__)


class ReaderCache:
    """Cache readers by logical frame."""

    def __init__(self, refs, reader_factory):
        self.refs = list(refs)
        self._reader_factory = reader_factory
        self._cache = {}

    def __len__(self):
        return len(self.refs)

    def __getitem__(self, index):
        if index not in self._cache:
            self._cache[index] = self._reader_factory(self.refs[index])
        return self._cache[index]


class ImageLayer:
    """Per-dataset image state over a persistent workflow."""

    def __init__(self, workflow=None, reader_factory=None):
        self._reader_factory = reader_factory or default_reader_factory
        self.workflow = workflow if workflow is not None else ProcessLayer()
        self.dataset = ReaderCache([], self._reader_factory)
        self.current_index = 0
        self.image_update = Signal()
        self._cache_index = None  # the frame the cached edited array belongs to
        self._cache_edited = None  # that frame's edited array
        self._analyzer_group = None  # cached pyleem time-series, built lazily
        self.workflow.process_update.connect(self._on_process_update)

    def _on_process_update(self, kind):
        # Analysis and sync do not change pixels; their consumers listen upstream.
        if kind in ("analysis", "sync"):
            return
        # Render changes alter display only, so the edited cache survives them.
        if kind != "render":
            self.invalidate()
        if self.n_frames > 0:
            self.image_update.emit("process")

    # input
    def load_folder(self, path):
        """Replace the dataset from a folder without notifying."""
        self.dataset = ReaderCache(discover_folder(path), self._reader_factory)
        self.current_index = 0
        self._analyzer_group = None
        self.invalidate()

    def open_folder(self, path):
        """Load a folder and emit ``image_update("open")``."""
        self.load_folder(path)
        self.image_update.emit("open")

    def load_file(self, path):
        """Replace the dataset from a single file without notifying."""
        self.dataset = ReaderCache(discover_file(path), self._reader_factory)
        self.current_index = 0
        self._analyzer_group = None
        self.invalidate()

    def open_file(self, path):
        """Load a file and emit ``image_update("open")``."""
        self.load_file(path)
        self.image_update.emit("open")

    # frame access
    @property
    def n_frames(self):
        return len(self.dataset)

    def raw(self, index):
        """The raw, undecorated image for a frame (re-read every call)."""
        if self.n_frames == 0:
            raise ValueError("no frames loaded")
        return self.dataset[index].read_image()

    def metadata(self, index):
        """The frame metadata, copied and enriched with ``TimeInterval``."""
        meta = dict(self.dataset[index].metadata)
        seconds = self.time_interval(index)
        if seconds is not None:
            meta["TimeInterval"] = (round(seconds, 3), "s")
        return meta

    # time-series metadata
    @property
    def analyzer_group(self):
        """A cached pyleem time series, or None when metadata cannot build one."""
        if self._analyzer_group is None and self.n_frames > 0:
            from pyleem import AnalyzerGroup

            try:
                self._analyzer_group = AnalyzerGroup(
                    [self.dataset[i] for i in range(self.n_frames)]
                )
            except Exception:  # noqa: BLE001 - bad TimeStamp should not crash
                self._analyzer_group = None
                log.warning(
                    "could not build a time-series for the dataset", exc_info=True
                )
        return self._analyzer_group

    def time_intervals(self):
        """Elapsed seconds from the first frame for each frame, or None."""
        group = self.analyzer_group
        return list(group.time_intervals) if group is not None else None

    def time_interval(self, index):
        """Elapsed seconds from the first frame for ``index``, or None."""
        intervals = self.time_intervals()
        if intervals is None or index >= len(intervals):
            return None
        return intervals[index]

    def edited(self, index):
        """The edited (destructive) result for a frame, cached for one frame."""
        if self.n_frames == 0:
            raise ValueError("no frames loaded")
        if index == self._cache_index and self._cache_edited is not None:
            return self._cache_edited
        out = apply_edited(self.workflow.processes, self.raw(index))
        self._cache_index = index
        self._cache_edited = out
        return out

    def invalidate(self):
        """Clear the one-frame edited cache."""
        self._cache_index = None
        self._cache_edited = None

    def set_index(self, index):
        """Set the current frame, clamped to range, notifying on change."""
        if self.n_frames == 0:
            return
        index = max(0, min(index, self.n_frames - 1))
        if index != self.current_index:
            self.current_index = index
            self.image_update.emit("frame")

    # export
    def export_tiff(self, path, indices=None, level="edited"):
        """Export raw or edited frames as grayscale TIFF with ImageJ metadata."""
        import tifffile

        if indices is None:
            indices = range(self.n_frames)
        indices = list(indices)
        pick = self.raw if level == "raw" else self.edited
        images = [pick(i) for i in indices]
        if not images:
            raise ValueError("no frames to export")
        arr = images[0] if len(images) == 1 else np.stack(images)
        info = imagej_info([self.metadata(i) for i in indices])
        tifffile.imwrite(str(path), arr, imagej=True, metadata={"Info": info})
