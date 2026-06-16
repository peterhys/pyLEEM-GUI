"""Qt-free display mode and export coordination."""

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .process import view_spec_of


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


class ViewLayer:
    """Owns display mode and rendered output."""

    def __init__(self, images):
        self.images = images
        self.mode = "rendered"
        self._rendered_frames = None

    def set_mode(self, mode):
        """Switch raw, edited, or rendered mode and notify on change."""
        if mode != self.mode:
            self.mode = mode
            self.images.image_update.emit("mode")

    def rendered(self, index):
        """``(edited image, view_spec)`` for the frame at ``index``."""
        out = self.images.edited(index)
        return out, view_spec_of(self.images.workflow.processes, out)

    def output(self):
        """The image and view spec for the current frame and mode."""
        images = self.images
        if images.n_frames == 0:
            raise ValueError("no frames loaded")
        if self.mode == "raw":
            return images.raw(images.current_index), {}
        if self.mode == "edited":
            return images.edited(images.current_index), {}
        return self.rendered(images.current_index)

    # rendered export
    def bake_rendered_frames(self, fn):
        """Register the rendered RGB frame provider."""
        self._rendered_frames = fn

    def export_rendered_tiff(self, path, indices=None):
        """Export the rendered view (overlays baked in) as an RGB TIFF."""
        import tifffile

        if self._rendered_frames is None:
            raise RuntimeError("no rendered frame provider registered")
        if indices is None:
            indices = range(self.images.n_frames)
        indices = list(indices)
        frames = self._rendered_frames(indices)
        if not frames:
            raise ValueError("no frames to export")
        arr = frames[0] if len(frames) == 1 else np.stack(frames)
        tifffile.imwrite(str(path), arr)

    def write_export(self, path, indices, opts):
        """Write selected export levels and return written file names."""
        path = Path(path)
        indices = list(indices)
        if opts.composite:
            if opts.rendered:
                self.export_rendered_tiff(path, indices)
            else:
                self.images.export_tiff(
                    path, indices, level="edited" if opts.edited else "raw"
                )
            return [path.name]

        written = []
        for tag, enabled in (
            ("raw", opts.raw),
            ("edited", opts.edited),
            ("rendered", opts.rendered),
        ):
            if not enabled:
                continue
            out = add_suffix(path, tag)
            if tag == "rendered":
                self.export_rendered_tiff(out, indices)
            else:
                self.images.export_tiff(out, indices, level=tag)
            written.append(out.name)
        return written
