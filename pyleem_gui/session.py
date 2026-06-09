"""The session layer."""

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .metadata import imagej_info
from .process import REGISTRY, ProcessList, apply_edited, view_spec_of


class Signal:
    """A minimal Qt-free signal: connected callbacks are called on emit."""

    def __init__(self):
        self._slots = []

    def connect(self, slot):
        self._slots.append(slot)

    def disconnect(self, slot):
        """Remove a connected slot; a slot that is not connected is a no-op."""
        if slot in self._slots:
            self._slots.remove(slot)

    def emit(self, *args):
        for slot in list(self._slots):
            slot(*args)


class ReaderCache:
    """Lazy-loading reader cache -- a reader is built only on first access."""

    def __init__(self, paths, reader_factory):
        self.paths = list(paths)
        self._reader_factory = reader_factory
        self._cache = {}

    def __len__(self):
        return len(self.paths)

    def __getitem__(self, index):
        if index not in self._cache:
            self._cache[index] = self._reader_factory(self.paths[index])
        return self._cache[index]


def _default_reader_factory(path):
    # Imported lazily so the module does not require pyleem at import time.
    from pyleem.reader import UViewReader

    return UViewReader(path)


@dataclass
class ExportOptions:
    """What to export: which levels, and whether to combine them."""

    raw: bool  # the raw frames (grayscale)
    edited: bool  # the edited (destructive) frames (grayscale)
    rendered: bool  # the displayed view with ROI/overlays baked in (RGB)
    composite: bool  # one combined image vs. a separate file per level

    def any(self):
        return self.raw or self.edited or self.rendered


def add_suffix(path, tag):
    """Add a suffix to a path: out.tif + raw -> out_raw.tif."""
    path = Path(path)
    return path.with_name(f"{path.stem}_{tag}{path.suffix}")


class ProcessLayer:
    """The process layer: the app-level entity that owns the process list.

    It is separate from (and outlives) the session: opening new data starts a
    new session while this layer and its list persist. Tabs mutate the list
    here; every change emits ``process_update`` with the changed process's
    kind (``edit`` or ``render``), which the session, the process bar, and the
    tab hosts observe. Workflow files are imported and saved here.
    """

    def __init__(self, processes=None):
        self.processes = processes if processes is not None else ProcessList()
        self.process_update = Signal()

    # -- process list ----------------------------------------------------------
    def add_process(self, proc):
        self.processes.add(proc)
        self.process_update.emit(self._kind_of(proc))

    def delete_process(self, index):
        proc = self.processes[index]
        self.processes.delete(index)
        self.process_update.emit(self._kind_of(proc))

    def update_process(self, index, params):
        """Merge new params into the process at ``index`` and notify."""
        proc = self.processes[index]
        proc.params.update(params)
        self.process_update.emit(self._kind_of(proc))

    def find_process(self, proc_id):
        """Return the index of the first process with ``proc_id``, or None."""
        for i, proc in enumerate(self.processes):
            if proc.process_id == proc_id:
                return i
        return None

    def _kind_of(self, proc):
        # An unregistered id (e.g. from an imported workflow) is treated as an
        # edit so subscribers err on the side of recomputing.
        spec = REGISTRY.get(proc.process_id)
        return spec.kind_id if spec is not None else "edit"

    # -- workflow files ----------------------------------------------------------
    def import_workflow(self, path):
        """Load a saved workflow file and replace the process list."""
        self.processes = ProcessList.from_json(Path(path).read_text())
        self.process_update.emit("edit")

    def save_workflow(self, path):
        """Save the process list to a workflow file."""
        Path(path).write_text(self.processes.to_json())


class SessionLayer:
    """The session layer: per-image state over a persistent `ProcessLayer`.

    It owns the dataset, the current frame index, the view mode, and a
    single-frame edited cache (only the current frame's edited result is ever
    held, so a large stack is never kept in memory). It computes the output
    image by applying the process layer's list, and emits ``image_update``
    with a reason -- ``open``, ``frame``, ``mode``, or ``process`` -- whenever
    the displayed image may have changed. The viewer and the output parts
    observe it; plugins read data only through it.

    :param workflow: The shared `ProcessLayer`; a private one is created
        when omitted (handy for scripts and tests).
    :param reader_factory: Callable ``path -> reader`` where ``reader`` exposes
        ``read_image()`` and a ``metadata`` mapping. Defaults to
        ``pyleem.reader.UViewReader``; injectable for testing.
    """

    def __init__(self, workflow=None, reader_factory=None, rendered_frames=None):
        self._reader_factory = reader_factory or _default_reader_factory
        self.workflow = workflow if workflow is not None else ProcessLayer()
        self.dataset = ReaderCache([], self._reader_factory)
        self.current_index = 0
        self.mode = "rendered"
        self.image_update = Signal()
        self._cache_index = None  # the frame the cached edited array belongs to
        self._cache_edited = None  # that frame's edited array
        self._rendered_frames = rendered_frames
        self.workflow.process_update.connect(self._on_process_update)

    def bake_rendered_frames(self, fn):
        """Register a callable ``indices -> list of (H, W, 3) uint8 RGB arrays``.

        The GUI supplies this to export the rendered view (overlays baked in).
        """
        self._rendered_frames = fn

    def _on_process_update(self, kind):
        # A render-kind change never alters the edited array, so the cache
        # survives it (e.g. ROI geometry updates while dragging).
        if kind != "render":
            self.invalidate()
        # With no frames loaded the viewer and outputs have nothing to redraw;
        # the process bar and tabs already listen to process_update directly.
        if self.n_frames > 0:
            self.image_update.emit("process")

    # -- input --------------------------------------------------------------
    def open_folder(self, path):
        """Load a folder of `.dat` frames lazily (sorted by name).

        Starts a new session in place: fresh dataset, index, and cache; the
        process layer (and so the workflow) persists.
        """
        paths = sorted(Path(path).glob("*.dat"))
        self.dataset = ReaderCache(paths, self._reader_factory)
        self.current_index = 0
        self.invalidate()
        self.image_update.emit("open")

    def open_file(self, path):
        """Load a single `.dat` file as a one-frame stack."""
        self.dataset = ReaderCache([Path(path)], self._reader_factory)
        self.current_index = 0
        self.invalidate()
        self.image_update.emit("open")

    # -- frame access ----------------------------------------------------------
    @property
    def n_frames(self):
        return len(self.dataset)

    def raw(self, index):
        """The raw, undecorated image for a frame (re-read every call)."""
        if self.n_frames == 0:
            raise ValueError("no frames loaded")
        return self.dataset[index].read_image()

    def metadata(self, index):
        return self.dataset[index].metadata

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

    def rendered(self, index):
        """``(edited image, view_spec)`` for a frame; the view spec is cheap."""
        out = self.edited(index)
        return out, view_spec_of(self.workflow.processes, out)

    def output(self):
        """The image and view spec to display for the current frame and mode."""
        if self.n_frames == 0:
            raise ValueError("no frames loaded")
        if self.mode == "raw":
            return self.raw(self.current_index), {}
        if self.mode == "edited":
            return self.edited(self.current_index), {}
        return self.rendered(self.current_index)

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

    def set_mode(self, mode):
        """Switch the view mode (raw / edited / rendered), notifying on change.

        The cache is untouched, so toggling modes on a frame is instant.
        """
        if mode != self.mode:
            self.mode = mode
            self.image_update.emit("mode")

    # -- process list (read-only delegates) -------------------------------------
    @property
    def processes(self):
        """The process layer's current list (read-only view for hosts/tests)."""
        return self.workflow.processes

    def find_process(self, proc_id):
        return self.workflow.find_process(proc_id)

    # -- export ---------------------------------------------------------------
    def export_tiff(self, path, indices=None, level="edited"):
        """Export frames as a grayscale TIFF with ImageJ metadata.

        Each frame's metadata is embedded as the ImageJ ``Info`` text -- a single
        frame as ``key = value [unit]`` lines, a stack as ``[Frame N]`` sections --
        so the bundled ImageJ overlay plugins can draw it on each slice.

        :param indices: Frame indices to export; defaults to all frames.
        :param level: ``RAW`` exports the raw frames; ``EDITED`` (default) exports
            the edited (baked) frames. For the rendered RGB view use
            ``export_rendered_tiff`` or ``write_export``.
        """
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

    def export_rendered_tiff(self, path, indices=None):
        """Export the rendered view (overlays baked in) as an RGB TIFF."""
        import tifffile

        if self._rendered_frames is None:
            raise RuntimeError("no rendered frame provider registered")
        if indices is None:
            indices = range(self.n_frames)
        indices = list(indices)
        frames = self._rendered_frames(indices)
        if not frames:
            raise ValueError("no frames to export")
        arr = frames[0] if len(frames) == 1 else np.stack(frames)
        tifffile.imwrite(str(path), arr)

    def write_export(self, path, indices, opts):
        """Write the selected levels; return the file names written."""
        path = Path(path)
        indices = list(indices)
        if opts.composite:
            if opts.rendered:
                self.export_rendered_tiff(path, indices)
            else:
                self.export_tiff(
                    path, indices, level="edited" if opts.edited else "raw"
                )
            return [path.name]

        written = []
        if opts.raw:
            out = add_suffix(path, "raw")
            self.export_tiff(out, indices, level="raw")
            written.append(out.name)
        if opts.edited:
            out = add_suffix(path, "edited")
            self.export_tiff(out, indices, level="edited")
            written.append(out.name)
        if opts.rendered:
            out = add_suffix(path, "rendered")
            self.export_rendered_tiff(out, indices)
            written.append(out.name)
        return written
