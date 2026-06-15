"""Qt-free process registry, workflow state, and load coordination."""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import numpy as np

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProcessSpec:
    """One process type and its registered callable."""

    process_id: str
    version: str
    kind: str
    label: str
    help: str
    apply: Callable[[np.ndarray, dict], Any]
    params_schema: dict = field(default_factory=dict)


# ProcessSpec.process_id -> ProcessSpec.
REGISTRY: dict[str, ProcessSpec] = {}


def register(spec):
    """Add a `ProcessSpec` to the registry (overwriting any same process_id)."""
    REGISTRY[spec.process_id] = spec


def get_spec(spec_id):
    """Look up a registered process spec."""
    try:
        return REGISTRY[spec_id]
    except KeyError:
        raise KeyError(f"unknown process: {spec_id!r}") from None


def process(*, process_id, version, kind, label, help, params_schema=None):
    """Decorator that registers a process function."""
    if kind not in ("edit", "render", "analysis"):
        raise ValueError(f"kind must be 'edit', 'render', or 'analysis', got {kind!r}")

    def decorate(fn):
        register(
            ProcessSpec(
                process_id=process_id,
                version=version,
                kind=kind,
                label=label,
                help=help,
                apply=fn,
                params_schema=params_schema or {},
            )
        )
        return fn

    return decorate


def filled_params(spec, params):
    """Merge supplied params over the schema defaults."""
    params = dict(params or {})
    out = {name: schema.get("default") for name, schema in spec.params_schema.items()}
    out.update(params)
    return out


@dataclass
class Process:
    """One applied process instance: a ProcessSpec process_id and its params."""

    process_id: str
    params: dict = field(default_factory=dict)

    def to_dict(self):
        return {"process_id": self.process_id, "params": self.params}

    @classmethod
    def from_dict(cls, d):
        return cls(process_id=d["process_id"], params=d.get("params", {}))


class ProcessList:
    """The ordered process list. Append or delete only, never reorder."""

    def __init__(self, items=None):
        self.items = list(items or [])

    def add(self, proc):
        self.items.append(proc)

    def delete(self, index):
        del self.items[index]

    def __len__(self):
        return len(self.items)

    def __iter__(self):
        return iter(self.items)

    def __getitem__(self, index):
        return self.items[index]


def apply_edited(processes, image):
    """Run the edit (destructive) processes in order; return the new image."""
    out = image
    for proc in processes:
        spec = get_spec(proc.process_id)
        if spec.kind == "edit":
            out = spec.apply(out, filled_params(spec, proc.params))
    return out


def view_spec_of(processes, image):
    """Merge render-process view specs without changing pixels."""
    view_spec = {}
    for proc in processes:
        spec = get_spec(proc.process_id)
        if spec.kind == "render":
            view_spec.update(spec.apply(image, filled_params(spec, proc.params)))
    return view_spec


class Signal:
    """A minimal Qt-free signal: connected callbacks are called on emit."""

    def __init__(self):
        self._slots = []

    def connect(self, slot):
        self._slots.append(slot)

    def emit(self, *args):
        for slot in list(self._slots):
            slot(*args)


class ProcessLayer:
    """App-level process list and workflow state."""

    def __init__(self, processes=None):
        self.processes = processes if processes is not None else ProcessList()
        self.analysis = {}  # analysis component id -> persisted params
        self.process_update = Signal()  # change kind: "edit" | "render" | "analysis"

    # process list
    def add_process(self, proc):
        self.processes.add(proc)
        self.process_update.emit(self._kind_of(proc))

    def delete_process(self, index):
        proc = self.processes[index]
        self.processes.delete(index)
        self.process_update.emit(self._kind_of(proc))

    def update_process(self, index, params):
        """Replace one process's params and notify."""
        proc = self.processes[index]
        proc.params = dict(params)
        self.process_update.emit(self._kind_of(proc))

    def find_process(self, proc_id):
        """Return the index of the first process with ``proc_id``, or None."""
        for i, proc in enumerate(self.processes):
            if proc.process_id == proc_id:
                return i
        return None

    def _kind_of(self, proc):
        # Unknown ids are treated as edits so subscribers recompute safely.
        spec = REGISTRY.get(proc.process_id)
        return spec.kind if spec is not None else "edit"

    # workflow files
    def update_analysis(self, component_id, params):
        """Record or clear an analysis component's non-default params."""
        params = dict(params)
        if params:
            if self.analysis.get(component_id) == params:
                return
            self.analysis[component_id] = params
        elif component_id in self.analysis:
            del self.analysis[component_id]
        else:
            return
        self.process_update.emit("analysis")

    def load_workflow(self, path):
        """Replace workflow state from disk without notifying."""
        doc = json.loads(Path(path).read_text())
        if isinstance(doc, list):  # legacy bare process array
            raw_processes, analysis = doc, {}
        else:
            raw_processes = doc.get("processes", [])
            analysis = doc.get("analysis", {})
        kept = []
        for proc in (Process.from_dict(d) for d in raw_processes):
            if proc.process_id in REGISTRY:
                kept.append(proc)
            else:
                log.warning(
                    "skipping unknown process %r in workflow %s",
                    proc.process_id,
                    path,
                )
        self.processes = ProcessList(kept)
        self.analysis = dict(analysis)

    def import_workflow(self, path):
        """Load a workflow file and emit ``process_update("edit")``."""
        self.load_workflow(path)
        self.process_update.emit("edit")

    def save_workflow(self, path):
        """Save the process list and analysis settings to a workflow document."""
        doc = {
            "version": 1,
            "processes": [proc.to_dict() for proc in self.processes],
            "analysis": dict(self.analysis),
        }
        Path(path).write_text(json.dumps(doc, indent=2))


class ProcessingCoordinator:
    """Orders workflow sync before image refresh for major loads."""

    def __init__(self, images):
        self.images = images
        self.workflow = images.workflow

    def import_workflow(self, path):
        """Load a workflow file, then reconcile."""
        self.workflow.load_workflow(path)
        self.reconcile("process")

    def open_file(self, path):
        """Open a single file, then reconcile."""
        self.images.load_file(path)
        self.reconcile("open")

    def open_folder(self, path):
        """Open a folder, then reconcile (see `open_file`)."""
        self.images.load_folder(path)
        self.reconcile("open")

    def reconcile(self, image_reason):
        """Sync workflow consumers, then refresh image consumers."""
        self.workflow.process_update.emit("sync")
        self.images.invalidate()
        if image_reason == "open" or self.images.n_frames > 0:
            self.images.image_update.emit(image_reason)
