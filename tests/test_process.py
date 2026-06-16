import json
import subprocess
import sys

import numpy as np
import pytest

from pyleem_gui.image import ImageLayer
from pyleem_gui.process import (
    Process,
    ProcessList,
    ProcessingCoordinator,
    apply_edited,
    get_spec,
    process,
    view_spec_of,
)

from .support import FakeReader


def apply_processes(processes, image):
    """Test combiner: edited image + merged render view spec."""
    out = apply_edited(processes, image)
    return out, view_spec_of(processes, out)


def make_coordinator():
    """A coordinator over a fresh, frame-less image layer with a FakeReader."""
    images = ImageLayer(reader_factory=FakeReader)
    return ProcessingCoordinator(images), images


def record(images):
    """Record the (channel, tag) order across both notification channels."""
    events = []
    images.workflow.process_update.connect(
        lambda kind: events.append(("process", kind))
    )
    images.image_update.connect(lambda reason: events.append(("image", reason)))
    return events


def write_workflow(path, process_id):
    path.write_text(json.dumps([{"process_id": process_id, "params": {}}]))
    return path


@pytest.fixture
def edited_procs():
    @process(
        process_id="test.add",
        version="1.0",
        kind="edit",
        label="add",
        help="add a constant",
        params_schema={"k": {"default": 0}},
    )
    def add(image, params):
        return image + params["k"]

    @process(
        process_id="test.mul",
        version="1.0",
        kind="edit",
        label="mul",
        help="multiply",
        params_schema={"k": {"default": 1}},
    )
    def mul(image, params):
        return image * params["k"]

    yield


@pytest.fixture
def rendered_proc():
    # A self-contained rendered process so these tests do not depend on the
    # built-in (which now registers only when its GUI plugin loads).
    @process(
        process_id="test.levels",
        version="1.0",
        kind="render",
        label="levels",
        help="set display levels to the data range",
        params_schema={"pad": {"type": "int", "default": 0}},
    )
    def levels(image, params):
        return {"levels": (float(image.min()), float(image.max()))}

    yield


def test_process_dict_roundtrip():
    proc = Process(process_id="test.add", params={"k": 2})
    assert Process.from_dict(proc.to_dict()) == proc


def test_edits_apply_in_order(edited_procs):
    image = np.zeros((2, 2), dtype=float)
    # (0 + 1) * 3 = 3
    add_then_mul = ProcessList(
        [
            Process("test.add", {"k": 1}),
            Process("test.mul", {"k": 3}),
        ]
    )
    out, _ = apply_processes(add_then_mul, image)
    assert np.all(out == 3)

    # (0 * 3) + 1 = 1 -- order matters
    mul_then_add = ProcessList(
        [
            Process("test.mul", {"k": 3}),
            Process("test.add", {"k": 1}),
        ]
    )
    out, _ = apply_processes(mul_then_add, image)
    assert np.all(out == 1)


def test_rendered_runs_after_edits_and_does_not_change_pixels(
    edited_procs, rendered_proc
):
    image = np.array([[0, 0], [0, 100]], dtype=np.uint16)
    processes = ProcessList(
        [
            Process("test.add", {"k": 10}),
            Process("test.levels", {}),
        ]
    )
    out, view_spec = apply_processes(processes, image)
    # edit applied
    assert out.min() == 10 and out.max() == 110
    # rendered produced levels without altering pixels
    assert "levels" in view_spec
    lo, hi = view_spec["levels"]
    assert lo == pytest.approx(10) and hi == pytest.approx(110)


def test_filled_params_uses_defaults(rendered_proc):
    spec = get_spec("test.levels")
    assert spec.kind == "render"
    out, view_spec = apply_processes(
        ProcessList([Process("test.levels", {})]),
        np.array([[0, 10], [20, 30]], dtype=np.uint16),
    )
    assert "levels" in view_spec


def test_unknown_process_raises():
    with pytest.raises(KeyError):
        apply_processes(ProcessList([Process("does.not.exist", {})]), np.zeros((2, 2)))


# ProcessList container behavior


def test_process_list_add_appends_in_order():
    pl = ProcessList()
    pl.add(Process("a"))
    pl.add(Process("b"))
    assert len(pl) == 2
    assert [p.process_id for p in pl] == ["a", "b"]
    assert pl[0].process_id == "a"
    assert pl[1].process_id == "b"


def test_process_list_delete_removes_by_index_without_reordering():
    pl = ProcessList([Process("a"), Process("b"), Process("c")])
    pl.delete(1)
    assert [p.process_id for p in pl] == ["a", "c"]
    assert len(pl) == 2
    pl.delete(0)
    assert [p.process_id for p in pl] == ["c"]


def test_process_list_iteration_matches_items():
    procs = [Process("a"), Process("b")]
    pl = ProcessList(procs)
    assert list(iter(pl)) == procs


def test_process_list_getitem_out_of_range_raises():
    pl = ProcessList([Process("a")])
    with pytest.raises(IndexError):
        pl[5]


# ProcessingCoordinator load order (Qt-free)


def test_open_folder_syncs_workflow_then_image(folder):
    coord, images = make_coordinator()
    events = record(images)
    coord.open_folder(folder)
    assert events == [("process", "sync"), ("image", "open")]
    assert images.n_frames == 3


def test_open_file_syncs_workflow_then_image(folder):
    coord, images = make_coordinator()
    events = record(images)
    coord.open_file(folder / "000.dat")
    assert events == [("process", "sync"), ("image", "open")]
    assert images.n_frames == 1


def test_import_workflow_with_images_syncs_then_processes(folder, tmp_path):
    @process(
        process_id="test.coord_add3",
        version="1.0",
        kind="edit",
        label="c3",
        help="add 3",
    )
    def add3(image, params):
        return image + 3

    coord, images = make_coordinator()
    coord.open_folder(folder)
    wf = write_workflow(tmp_path / "wf.json", "test.coord_add3")

    events = record(images)
    coord.import_workflow(wf)

    # Workflow consumers sync first, then the loaded images refresh.
    assert events == [("process", "sync"), ("image", "process")]
    # The workflow applies lazily -- only on a frame request.
    assert np.all(images.edited(0) == images.raw(0) + 3)


def test_import_workflow_without_images_emits_only_process_sync(tmp_path):
    @process(
        process_id="test.coord_add1",
        version="1.0",
        kind="edit",
        label="c1",
        help="add 1",
    )
    def add1(image, params):
        return image + 1

    coord, images = make_coordinator()  # no frames opened
    wf = write_workflow(tmp_path / "wf.json", "test.coord_add1")

    events = record(images)
    coord.import_workflow(wf)

    # No images: workflow consumers still sync, but there is nothing to redraw.
    assert events == [("process", "sync")]
    assert images.workflow.processes[0].process_id == "test.coord_add1"


def test_open_after_workflow_keeps_workflow_and_orders(folder):
    @process(
        process_id="test.coord_add2",
        version="1.0",
        kind="edit",
        label="c2",
        help="add 2",
    )
    def add2(image, params):
        return image + 2

    coord, images = make_coordinator()
    images.workflow.add_process(Process("test.coord_add2", {}))  # before any image

    events = record(images)
    coord.open_folder(folder)

    assert events == [("process", "sync"), ("image", "open")]
    # The workflow survived the open and applies to the new frames.
    assert len(images.workflow.processes) == 1
    assert np.all(images.edited(0) == images.raw(0) + 2)


def test_image_layer_ignores_sync_process_update(folder):
    coord, images = make_coordinator()
    coord.open_folder(folder)
    cached = images.edited(0)

    reasons = []
    images.image_update.connect(reasons.append)
    images.workflow.process_update.emit("sync")

    assert reasons == []  # "sync" drives no image redraw
    assert images.edited(0) is cached  # and does not invalidate the cache


def test_local_frame_flow_unchanged(folder):
    coord, images = make_coordinator()
    coord.open_folder(folder)
    reasons = []
    images.image_update.connect(reasons.append)
    images.set_index(2)
    assert reasons == ["frame"]


def test_local_process_edit_flow_unchanged(folder):
    @process(
        process_id="test.coord_local",
        version="1.0",
        kind="edit",
        label="cl",
        help="add 1",
    )
    def add1(image, params):
        return image + 1

    coord, images = make_coordinator()
    coord.open_folder(folder)

    # An in-tab edit keeps its local reactive path (not routed through the
    # coordinator): the process layer emits "edit" and the image layer reacts with
    # image_update("process"). Recorded on separate channels because that reaction
    # fires mid-dispatch (the image layer is an earlier subscriber), unlike the
    # coordinator's "sync" which the image layer ignores.
    kinds, reasons = [], []
    images.workflow.process_update.connect(kinds.append)
    images.image_update.connect(reasons.append)
    images.workflow.add_process(Process("test.coord_local", {}))

    assert kinds == ["edit"]
    assert reasons == ["process"]


# ProcessLayer workflow serialization and analysis map


def test_workflow_save_and_import_roundtrip(images, tmp_path):
    @process(
        process_id="test.roundtrip",
        version="1.0",
        kind="render",
        label="roundtrip",
        help="round-trip me",
        params_schema={"num_bins": {"type": "int", "default": 256}},
    )
    def roundtrip(image, params):
        return {}

    images.workflow.add_process(Process("test.roundtrip", {"num_bins": 128}))
    wf = tmp_path / "workflow.json"
    images.workflow.save_workflow(wf)

    other = ImageLayer(reader_factory=FakeReader)
    other.workflow.import_workflow(wf)
    assert len(other.workflow.processes) == 1
    assert other.workflow.processes[0].process_id == "test.roundtrip"
    assert other.workflow.processes[0].params == {"num_bins": 128}


def test_save_workflow_writes_versioned_document(images, tmp_path):
    images.workflow.update_analysis("line_profile:line_profile", {"energy": True})
    wf = tmp_path / "workflow.json"
    images.workflow.save_workflow(wf)

    doc = json.loads(wf.read_text())
    assert doc["version"] == 1
    assert isinstance(doc["processes"], list)
    assert doc["analysis"] == {"line_profile:line_profile": {"energy": True}}


def test_workflow_document_roundtrips_analysis(images, tmp_path):
    images.workflow.add_process(Process("test.roundtrip", {"num_bins": 128}))
    images.workflow.update_analysis(
        "line_profile:line_profile", {"energy": True, "peak_shift": 5.0}
    )
    wf = tmp_path / "workflow.json"
    images.workflow.save_workflow(wf)

    other = ImageLayer(reader_factory=FakeReader)
    other.workflow.import_workflow(wf)
    assert other.workflow.analysis == {
        "line_profile:line_profile": {"energy": True, "peak_shift": 5.0}
    }


def test_import_legacy_array_leaves_analysis_empty(images, tmp_path):
    images.workflow.update_analysis("stale", {"a": 1})  # replaced by the import
    wf = tmp_path / "old.json"
    wf.write_text(json.dumps([]))  # the pre-document bare-array format
    images.workflow.import_workflow(wf)
    assert images.workflow.analysis == {}


def test_update_analysis_notifies_without_recomputing_the_image(images):
    kinds = []
    reasons = []
    images.workflow.process_update.connect(kinds.append)
    images.image_update.connect(reasons.append)
    cached = images.edited(0)

    images.workflow.update_analysis("line_profile:line_profile", {"energy": True})
    assert kinds == ["analysis"]  # the bar is notified via the analysis tag
    assert reasons == []  # analysis never reaches the image
    assert images.edited(0) is cached  # the edited cache is not invalidated

    images.workflow.update_analysis("line_profile:line_profile", {"energy": True})
    assert kinds == ["analysis"]  # an unchanged update does not re-emit


def test_update_analysis_clears_entry_when_empty(images):
    images.workflow.update_analysis("line_profile:line_profile", {"energy": True})
    assert "line_profile:line_profile" in images.workflow.analysis
    images.workflow.update_analysis("line_profile:line_profile", {})  # back to default
    assert images.workflow.analysis == {}


def test_analysis_persists_across_open(images, tmp_path):
    images.workflow.update_analysis("line_profile:line_profile", {"energy": True})
    other = tmp_path / "more"
    other.mkdir()
    (other / "000.dat").write_bytes(b"")
    images.open_folder(other)  # a new image layer in place; the process layer persists
    assert images.workflow.analysis == {"line_profile:line_profile": {"energy": True}}


def test_import_keeps_unknown_analysis_ids(images, tmp_path):
    # An analysis id for a component not currently loaded is never applied, so
    # it is kept and round-trips back out on the next save (no data loss).
    wf = tmp_path / "workflow.json"
    wf.write_text(
        json.dumps(
            {"version": 1, "processes": [], "analysis": {"not_loaded:foo": {"a": 1}}}
        )
    )
    images.workflow.import_workflow(wf)
    assert images.workflow.analysis == {"not_loaded:foo": {"a": 1}}

    out = tmp_path / "again.json"
    images.workflow.save_workflow(out)
    assert json.loads(out.read_text())["analysis"] == {"not_loaded:foo": {"a": 1}}


def test_import_workflow_skips_unknown_ids(images, tmp_path):
    """An entry naming a removed or unloaded process (e.g. the retired
    builtin:normalize) is dropped with a warning; the rest still imports."""

    @process(
        process_id="test.survives",
        version="1.0",
        kind="edit",
        label="survives",
        help="kept on import",
    )
    def survives(image, params):
        return image

    wf = tmp_path / "workflow.json"
    wf.write_text(
        json.dumps(
            [
                {"process_id": "builtin:normalize", "params": {}},
                {"process_id": "test.survives", "params": {"k": 1}},
            ]
        )
    )
    images.workflow.import_workflow(wf)
    assert [p.process_id for p in images.workflow.processes] == ["test.survives"]
    assert images.workflow.processes[0].params == {"k": 1}
    # Rendering after the import cannot hit the unknown id.
    assert np.all(images.edited(0) == 0)


def test_find_process_returns_first_index(images):
    @process(
        process_id="test.fp_a",
        version="1.0",
        kind="edit",
        label="a",
        help="find a",
    )
    def fp_a(image, params):
        return image

    @process(
        process_id="test.fp_b",
        version="1.0",
        kind="edit",
        label="b",
        help="find b",
    )
    def fp_b(image, params):
        return image

    images.workflow.add_process(Process("test.fp_a"))
    images.workflow.add_process(Process("test.fp_b"))
    images.workflow.add_process(Process("test.fp_a"))
    assert images.workflow.find_process("test.fp_a") == 0
    assert images.workflow.find_process("test.fp_b") == 1
    assert images.workflow.find_process("test.not_present") is None


# Qt-free framework boundary


def test_framework_modules_are_qt_free():
    # The core data/process framework stays Qt-free and runnable headless. The
    # plugins package now imports PySide6 (the Qt host is re-exported eagerly), so
    # it is intentionally not asserted here.
    code = (
        "import sys\n"
        "import pyleem_gui.process\n"
        "import pyleem_gui.metadata\n"
        "import pyleem_gui.roi\n"
        "import pyleem_gui.view\n"
        "bad = sorted(m for m in sys.modules if 'PySide6' in m or m == 'pyqtgraph')\n"
        "assert not bad, bad\n"
    )
    subprocess.run([sys.executable, "-c", code], check=True)
