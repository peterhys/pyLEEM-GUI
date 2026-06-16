"""Qt-free plugin declarations and registry."""

from dataclasses import dataclass, field
from typing import Callable

from ..process import get_spec
from ..process import process as _register_process


class ComponentHandlerMark:
    """Marker base for component handler classes."""


def is_handler(obj):
    """True when ``obj`` is a handler class (a `ComponentHandlerMark` subclass)."""
    return isinstance(obj, type) and issubclass(obj, ComponentHandlerMark)


# parameter helpers
# Keep None bounds so the form factory can supply defaults.


def Float(default, *, min=None, max=None, label=None):
    return {"type": "float", "default": default, "min": min, "max": max, "label": label}


def Int(default, *, min=None, max=None, label=None):
    return {"type": "int", "default": default, "min": min, "max": max, "label": label}


def Bool(default, *, label=None):
    return {"type": "bool", "default": default, "label": label}


def Choice(default, choices, *, label=None):
    return {
        "type": "choice",
        "default": default,
        "choices": list(choices),
        "label": label,
    }


def format_plugin_id(text):
    """Turn a plugin title into its id segment: ``Auto Contrast`` -> ``auto_contrast``."""
    return text.strip().lower().replace(" ", "_")


# spec dataclasses
@dataclass
class Component:
    """One typed component of a plugin."""

    kind: str  # "edit" | "render" | "analysis"
    id: str  # plugin-namespaced process id, e.g. "builtin:ROI"
    label: str  # chip label / header text
    help: str = ""  # toggle tooltip
    handler: Callable | None = None  # ComponentHandler subclass, or None
    params_schema: dict = field(default_factory=dict)
    always_on: bool = False  # active with no On/Off toggle (e.g. an analysis)
    fill: bool = False  # widget expands to fill the tab
    # Sibling ids are qualified to this plugin; full plugin:id ids are kept.
    replaces: tuple = ()


@dataclass
class Plugin:
    """A tab: an ordered list of typed components. Registered into `PLUGINS`."""

    title: str
    version: str = "0.1"
    order: int = 0  # tab order across discovered plugins; ties break on title
    components: list[Component] = field(default_factory=list)

    def qualify(self, short):
        """Namespace a short id with this plugin: ``<plugin>:<short>``."""
        return f"{format_plugin_id(self.title)}:{short}"

    def edit(
        self,
        func=None,
        *,
        process_id=None,
        spec_id=None,
        version="1.0",
        label=None,
        help="",
        params=None,
        always_on=False,
        replaces=None,
    ):
        """Register an edit component."""
        return self._register(
            "edit",
            func,
            process_id=process_id,
            spec_id=spec_id,
            version=version,
            label=label,
            help=help,
            params=params,
            always_on=always_on,
            fill=False,
            replaces=replaces,
        )

    def render(
        self,
        target=None,
        *,
        process_id=None,
        spec_id=None,
        version="1.0",
        label=None,
        help="",
        params=None,
        always_on=False,
        fill=False,
        replaces=None,
    ):
        """Register a render component."""
        return self._register(
            "render",
            target,
            process_id=process_id,
            spec_id=spec_id,
            version=version,
            label=label,
            help=help,
            params=params,
            always_on=always_on,
            fill=fill,
            replaces=replaces,
        )

    def analysis(
        self,
        handler=None,
        *,
        process_id=None,
        label=None,
        help="",
        params=None,
        always_on=False,
        fill=False,
    ):
        """Register an analysis component."""
        return self._register(
            "analysis",
            handler,
            process_id=process_id,
            spec_id=None,
            version="1.0",
            label=label,
            help=help,
            params=params,
            always_on=always_on,
            fill=fill,
        )

    def _register(
        self,
        kind,
        target,
        *,
        process_id,
        spec_id,
        version,
        label,
        help,
        params,
        always_on,
        fill,
        replaces=None,
    ):
        # Sibling ids are qualified to this plugin; full ids are kept.
        replaces = tuple(r if ":" in r else self.qualify(r) for r in (replaces or ()))
        if spec_id is not None:
            process_spec = get_spec(spec_id)
            if process_spec.kind != kind:
                raise ValueError(
                    f"{spec_id!r} is a {process_spec.kind} process, not {kind}"
                )
            self.components.append(
                Component(
                    kind=kind,
                    id=spec_id,
                    label=process_spec.label,
                    help=process_spec.help,
                    params_schema=dict(process_spec.params_schema),
                    always_on=always_on,
                    fill=fill,
                    replaces=replaces,
                )
            )
            return target

        if process_id is None:
            raise ValueError(f"inline {kind} component needs process_id")

        def decorate(target):
            if kind == "analysis":
                if not is_handler(target):
                    raise TypeError(
                        "analysis() requires a ComponentHandler subclass, "
                        f"got {target!r}"
                    )
                handler = target
            elif is_handler(target):
                if kind == "edit":
                    raise TypeError(
                        "edit() accepts a plain fn(image, params), "
                        f"not a handler class ({target!r})"
                    )
                handler = target
            else:
                handler = None

            full_id = self.qualify(process_id)
            chip_label = label or process_id
            if kind != "analysis":
                # Handler-backed render components still register process entries.
                if handler is None:
                    fn = target
                else:
                    fn = getattr(handler, "process_apply", None) or (
                        lambda image, params: {}
                    )
                _register_process(
                    process_id=full_id,
                    version=version,
                    kind=kind,
                    label=chip_label,
                    help=help,
                    params_schema=params or {},
                )(fn)
            self.components.append(
                Component(
                    kind=kind,
                    id=full_id,
                    label=chip_label,
                    help=help,
                    handler=handler,
                    params_schema=params or {},
                    always_on=always_on,
                    fill=fill,
                    replaces=replaces,
                )
            )
            return target

        return decorate(target) if target is not None else decorate


# registry
PLUGINS: list[Plugin] = []


def plugin(title, *, order=0, version="0.1"):
    """Create and register a plugin spec."""
    plug = Plugin(title=title, version=version, order=order)
    PLUGINS.append(plug)
    return plug
