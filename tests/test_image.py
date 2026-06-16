import subprocess
import sys

import numpy as np
import tifffile

from pyleem_gui.image import ImageLayer
from pyleem_gui.process import Process, ProcessLayer, Signal, process
from pyleem_gui.view import ViewLayer

from .support import FakeReader, TimeStampReader, write_tiff


def test_core_imports_without_pyside6():
    # Run in a fresh interpreter so other plugins (e.g. pytest-qt) that import
    # Qt globally do not mask whether the core itself pulls in PySide6.
    code = (
        "import pyleem_gui, pyleem_gui.image, pyleem_gui.process; "
        "import sys; "
        "assert 'PySide6' not in sys.modules, sorted(m for m in sys.modules if 'PySide6' in m)"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


def test_open_folder_lists_sorted_frames(images, tmp_path):
    assert images.n_frames == 3
    assert np.all(images.raw(0) == 0)
    assert np.all(images.raw(2) == 2)

    f = tmp_path / "007.dat"
    f.write_bytes(b"")
    single = ImageLayer(reader_factory=FakeReader)
    single.open_file(f)
    assert single.n_frames == 1
    assert np.all(single.raw(0) == 7)


def test_edited_applies_edits_in_order(images):
    @process(
        process_id="test.plus5",
        version="1.0",
        kind="edit",
        label="plus5",
        help="add 5",
        params_schema={},
    )
    def plus5(image, params):
        return image + 5

    images.workflow.add_process(Process("test.plus5", {}))
    assert np.all(images.edited(1) == 6)  # frame value 1 + 5
    images.workflow.delete_process(0)
    assert np.all(images.edited(0) == 0)


def test_workflow_persists_across_new_data(images, tmp_path):
    """Opening new data keeps the workflow process list."""

    @process(
        process_id="test.plus3",
        version="1.0",
        kind="edit",
        label="plus3",
        help="add 3",
        params_schema={},
    )
    def plus3(image, params):
        return image + 3

    images.workflow.add_process(Process("test.plus3"))
    assert np.all(images.edited(0) == 3)  # frame 0 (value 0) + 3

    other = tmp_path / "other"
    other.mkdir()
    for v in (5, 6):
        (other / f"{v:03d}.dat").write_bytes(b"")
    images.open_folder(other)
    assert len(images.workflow.processes) == 1  # not reset on open_folder
    assert np.all(images.edited(0) == 8)  # new frame 0 (value 5) + 3

    single = tmp_path / "100.dat"
    single.write_bytes(b"")
    images.open_file(single)
    assert len(images.workflow.processes) == 1  # not reset on open_file
    assert np.all(images.edited(0) == 103)  # value 100 + 3


def test_workflow_shared_across_image_layers(folder, tmp_path):
    """One app-level process layer serves any number of image layers; opening new
    data resets only the per-image state."""

    @process(
        process_id="test.plus2",
        version="1.0",
        kind="edit",
        label="plus2",
        help="add 2",
    )
    def plus2(image, params):
        return image + 2

    layer = ProcessLayer()
    first = ImageLayer(workflow=layer, reader_factory=FakeReader)
    second = ImageLayer(workflow=layer, reader_factory=FakeReader)
    first.open_folder(folder)
    second.open_folder(folder)

    reasons = {"first": [], "second": []}
    first.image_update.connect(reasons["first"].append)
    second.image_update.connect(reasons["second"].append)

    layer.add_process(Process("test.plus2"))
    # One list change reaches every image layer as an image_update.
    assert reasons == {"first": ["process"], "second": ["process"]}
    assert np.all(first.edited(0) == 2) and np.all(second.edited(0) == 2)

    # Opening new data is a new image layer in place: fresh index, same workflow.
    first.set_index(2)
    first.open_folder(folder)
    assert first.current_index == 0
    assert len(layer.processes) == 1


def test_processlayer_modes(images):
    @process(
        process_id="test.plus10",
        version="1.0",
        kind="edit",
        label="p10",
        help="add 10",
    )
    def plus10(image, params):
        return image + 10

    @process(
        process_id="test.lvl",
        version="1.0",
        kind="render",
        label="lvl",
        help="levels",
    )
    def lvl(image, params):
        return {"levels": (0.0, 1.0)}

    images.workflow.add_process(Process("test.plus10"))
    images.workflow.add_process(Process("test.lvl"))
    view = ViewLayer(images)

    view.set_mode("raw")  # frame 0 has value 0
    img, spec = view.output()
    assert np.all(img == 0) and spec == {}

    # Display levels apply only in the rendered view; edited drops them.
    view.set_mode("edited")
    img, spec = view.output()
    assert np.all(img == 10) and spec == {}

    view.set_mode("rendered")
    img, spec = view.output()
    assert np.all(img == 10) and spec.get("levels") == (0.0, 1.0)


def test_cache_single_frame_and_mode_toggle_no_recompute(images):
    calls = []

    @process(
        process_id="test.count",
        version="1.0",
        kind="edit",
        label="count",
        help="count",
    )
    def count(image, params):
        calls.append(1)
        return image + 1

    images.workflow.add_process(Process("test.count"))
    view = ViewLayer(images)
    view.set_mode("edited")
    view.output()  # computes edited(0): 1 call
    assert len(calls) == 1

    # Toggling modes on the same frame must not recompute the edit chain.
    view.set_mode("raw")
    view.output()
    view.set_mode("rendered")
    view.output()
    view.set_mode("edited")
    view.output()
    assert len(calls) == 1

    # The cache holds exactly one frame's edited array (a single 2-D array).
    assert images._cache_edited is not None
    assert images._cache_edited.ndim == 2
    assert images._cache_index == 0

    # Moving to another frame recomputes and rebinds the one-frame cache.
    images.set_index(1)
    view.output()
    assert len(calls) == 2
    assert images._cache_index == 1


def test_cache_invalidates_on_process_change(images):
    @process(
        process_id="test.bump",
        version="1.0",
        kind="edit",
        label="bump",
        help="bump",
    )
    def bump(image, params):
        return image + params.get("k", 0)

    images.workflow.add_process(Process("test.bump", {"k": 5}))
    assert np.all(images.edited(0) == 5)  # frame 0 value 0 + 5
    images.workflow.update_process(0, {"k": 9})
    assert np.all(images.edited(0) == 9)  # update clears the cache
    images.workflow.delete_process(0)
    assert np.all(images.edited(0) == 0)


def test_render_update_keeps_edited_cache(images):
    """A render-kind change never touches the edited array, so the one-frame
    cache survives it (e.g. ROI geometry updates while dragging)."""
    calls = []

    @process(
        process_id="test.cached",
        version="1.0",
        kind="edit",
        label="cached",
        help="count edits",
    )
    def cached(image, params):
        calls.append(1)
        return image + 1

    @process(
        process_id="test.deco",
        version="1.0",
        kind="render",
        label="deco",
        help="decorate",
    )
    def deco(image, params):
        return {}

    layer = images.workflow
    layer.add_process(Process("test.cached"))
    layer.add_process(Process("test.deco", {"pos": [1, 1]}))
    view = ViewLayer(images)
    view.output()
    assert len(calls) == 1

    layer.update_process(1, {"pos": [2, 2]})  # render-kind: cache kept
    view.output()
    assert len(calls) == 1

    layer.update_process(0, {})  # edit-kind: cache invalidated
    view.output()
    assert len(calls) == 2


def test_cache_cleared_on_open(images, tmp_path):
    @process(
        process_id="test.add7",
        version="1.0",
        kind="edit",
        label="a7",
        help="add 7",
    )
    def add7(image, params):
        return image + 7

    images.workflow.add_process(Process("test.add7"))
    assert np.all(images.edited(0) == 7)
    assert images._cache_index == 0

    other = tmp_path / "other"
    other.mkdir()
    for v in (5, 6):
        (other / f"{v:03d}.dat").write_bytes(b"")
    images.open_folder(other)
    assert images._cache_index is None  # cache cleared on open
    assert np.all(images.edited(0) == 12)  # new frame 0 (value 5) + 7


def test_mode_change_emits_image_update_only_on_change(images):
    view = ViewLayer(images)
    reasons = []
    images.image_update.connect(reasons.append)
    view.set_mode("rendered")  # already rendered -> no signal
    assert "mode" not in reasons
    view.set_mode("raw")
    assert reasons.count("mode") == 1
    view.set_mode("raw")  # same -> no new signal
    assert reasons.count("mode") == 1


def test_process_update_skips_image_update_without_frames():
    layer = ProcessLayer()
    images = ImageLayer(workflow=layer, reader_factory=FakeReader)
    reasons = []
    images.image_update.connect(reasons.append)
    layer.add_process(Process("builtin:autolevel", {}))
    assert reasons == []


def test_process_update_chains_into_image_update(images):
    """Process updates chain into image updates."""
    kinds = []
    reasons = []
    images.workflow.process_update.connect(kinds.append)
    images.image_update.connect(reasons.append)

    images.workflow.add_process(Process("test.never_registered", {}))
    images.set_index(2)
    assert kinds == ["edit"]  # unregistered id: treated as an edit
    assert reasons == ["process", "frame"]


def test_two_notification_channels_after_consolidation(images):
    # The view layer no longer owns a signal.
    assert not hasattr(images, "add_listener")
    view = ViewLayer(images)
    image_signals = [
        name for name, value in vars(images).items() if isinstance(value, Signal)
    ]
    layer_signals = [
        name
        for name, value in vars(images.workflow).items()
        if isinstance(value, Signal)
    ]
    view_signals = [
        name for name, value in vars(view).items() if isinstance(value, Signal)
    ]
    assert image_signals == ["image_update"]
    assert layer_signals == ["process_update"]
    assert view_signals == []


def test_set_index_clamps(images):
    images.set_index(99)
    assert images.current_index == 2
    images.set_index(-5)
    assert images.current_index == 0


def test_export_tiff_roundtrip(images, tmp_path):
    out = tmp_path / "stack.tif"
    images.export_tiff(out)
    arr = tifffile.imread(str(out))
    assert arr.shape == (3, 4, 4)
    assert np.all(arr[2] == 2)


def test_export_tiff_raw_vs_edited(images, tmp_path):
    @process(
        process_id="test.plus100",
        version="1.0",
        kind="edit",
        label="p100",
        help="add 100",
    )
    def plus100(image, params):
        return image + 100

    images.workflow.add_process(Process("test.plus100", {}))
    raw, edited = tmp_path / "raw.tif", tmp_path / "edited.tif"
    images.export_tiff(raw, level="raw")
    images.export_tiff(edited, level="edited")
    assert np.all(tifffile.imread(str(edited)) == tifffile.imread(str(raw)) + 100)


# time-series metadata
def test_metadata_adds_time_interval_when_timestamp_present(folder):
    images = ImageLayer(reader_factory=TimeStampReader)
    images.open_folder(folder)
    # Elapsed seconds from the first frame, computed by pyleem AnalyzerGroup.
    assert images.time_intervals() == [0.0, 1.0, 2.0]
    assert images.metadata(0)["TimeInterval"] == (0.0, "s")
    assert images.metadata(2)["TimeInterval"] == (2.0, "s")


def test_metadata_omits_time_interval_without_timestamp(images):
    # The default FakeReader has no TimeStamp: no crash, no TimeInterval added.
    assert images.time_intervals() is None
    assert "TimeInterval" not in images.metadata(0)
    meta = images.metadata(0)
    meta["scratch"] = 1  # mutating the returned dict must not affect the reader
    assert "scratch" not in images.dataset[0].metadata


def test_time_series_cache_rebuilds_on_open(folder, tmp_path):
    images = ImageLayer(reader_factory=TimeStampReader)
    images.open_folder(folder)
    assert images.time_intervals() == [0.0, 1.0, 2.0]

    other = tmp_path / "other"
    other.mkdir()
    for v in (0, 5):  # 5 seconds apart
        (other / f"{v:03d}.dat").write_bytes(b"")
    images.open_folder(other)
    assert images.time_intervals() == [0.0, 5.0]


def test_reopen_tiff_preserves_workflow(tmp_path):
    @process(
        process_id="test.plus10",
        version="1.0",
        kind="edit",
        label="plus10",
        help="add 10",
    )
    def plus10(image, params):
        return image + 10

    images = ImageLayer()
    images.workflow.add_process(Process("test.plus10"))
    write_tiff(tmp_path / "a.tif", np.full((4, 4), 1, np.uint16))
    images.open_file(tmp_path / "a.tif")
    assert int(images.edited(0)[0, 0]) == 11  # process applied to the TIFF frame

    write_tiff(tmp_path / "b.tif", np.full((4, 4), 2, np.uint16))
    images.open_file(tmp_path / "b.tif")  # new data; the workflow persists
    assert int(images.edited(0)[0, 0]) == 12
    assert len(images.workflow.processes) == 1
