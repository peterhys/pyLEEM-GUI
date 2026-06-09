"""The process registry and process list."""

import json
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np


@dataclass(frozen=True)
class ProcessSpec:
    """One process type: a function bundled with its metadata.

    The allowed kind_id are: ``edit``, ``render``, ``output``.
    ``edit``: destructive processes
    ``render``: non-destructive processes
    ``output``: analysis related processes
    """

    process_id: str
    version: str
    kind_id: str
    display_id: str
    description: str
    apply: Callable[[np.ndarray, dict], Any]
    params_schema: dict = field(default_factory=dict)


# Module-level registry, keyed by ProcessSpec.process_id.
REGISTRY: dict[str, ProcessSpec] = {}


def register(spec):
    """Add a `ProcessSpec` to the registry (overwriting any same process_id)."""
    REGISTRY[spec.process_id] = spec


def get_spec(spec_id):
    """Look up a registered `ProcessSpec` by process_id.

    :raises KeyError: if no process with that process_id is registered.
    """
    try:
        return REGISTRY[spec_id]
    except KeyError:
        raise KeyError(f"unknown process: {spec_id!r}") from None


def process(*, process_id, version, kind_id, display_id, help, params_schema=None):
    """Decorator that registers a function as a process.

    Returns the function unchanged so it stays a normal importable callable.
    """
    if kind_id not in ("edit", "render", "output"):
        raise ValueError(
            f"kind_id must be 'edit', 'render', or 'output', got {kind_id!r}"
        )

    def decorate(fn):
        register(
            ProcessSpec(
                process_id=process_id,
                version=version,
                kind_id=kind_id,
                display_id=display_id,
                description=help,
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

    def to_json(self):
        """Serialize the process list to a workflow document."""
        return json.dumps([proc.to_dict() for proc in self.items], indent=2)

    @classmethod
    def from_json(cls, text):
        """Load a workflow document into a process list."""
        return cls([Process.from_dict(d) for d in json.loads(text)])


def apply_edited(processes, image):
    """Run the edit (destructive) processes in order; return the new image."""
    out = image
    for proc in processes:
        spec = get_spec(proc.process_id)
        if spec.kind_id == "edit":
            out = spec.apply(out, filled_params(spec, proc.params))
    return out


def view_spec_of(processes, image):
    """Merge the view specs of the render (non-destructive) processes."""
    view_spec = {}
    for proc in processes:
        spec = get_spec(proc.process_id)
        if spec.kind_id == "render":
            view_spec.update(spec.apply(image, filled_params(spec, proc.params)))
    return view_spec


def apply_processes(processes, image):
    """Apply a process list to one slice.

    Edit processes run in order to produce the modified image; render processes
    then run on that image, their view specs merged. Returns
    ``(image, view_spec)``.
    """
    out = apply_edited(processes, image)
    return out, view_spec_of(processes, out)
