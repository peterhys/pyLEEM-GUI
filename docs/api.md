# Plugin API

This page is for plugin authors. It describes the current GUI plugin contract.

## Minimal Plugin

Create a Python module that calls `plugin()` and declares components on it:

```python
from pyleem_gui.plugins import Float, plugin

image_ops = plugin("Image Ops")


@image_ops.edit(
    process_id="gain",
    help="Multiply every pixel by a gain factor.",
    params={"factor": Float(1.0, min=0.0, max=20.0)},
)
def gain(image, params):
    return image * params["factor"]
```

The short id `gain` is registered as `image_ops:gain`. The function remains a
normal importable Python function.

## Component Kinds

Each component is exactly one kind:

| Kind | Declared With | Enters process list | Purpose |
| --- | --- | --- | --- |
| `edit` | `plug.edit(...)` | Yes | Change image data |
| `render` | `plug.render(...)` | Yes | Change display only |
| `analysis` | `plug.analysis(...)` | No | Show a plugin widget |

Edit functions return an image array. Render functions return a view spec dict,
for example `{"levels": (lo, hi)}`. Analysis components are handler classes.

Rules:

- Process functions take `(image, params)`.
- Process functions should not mutate input arrays in place.
- Do not import Qt in plain process functions.
- Give each component a stable `process_id` and useful `help` text.

## Parameters

Declare params in the decorator. The host builds controls automatically.

| Helper | Control | Value |
| --- | --- | --- |
| `Float(default, min=..., max=..., label=...)` | `QDoubleSpinBox` | `float` |
| `Int(default, min=..., max=..., label=...)` | `QSpinBox` | `int` |
| `Bool(default, label=...)` | `QCheckBox` | `bool` |
| `Choice(default, choices, label=...)` | `QComboBox` | selected text |

The raw schema is a dict with `type`, `default`, and optional control metadata.

## Referencing Existing Processes

A plugin can reference an already registered edit or render process:

```python
image_ops.render(spec_id="builtin:autolevel")
```

The referenced process kind must match the registration method.

## Handler Components

Use a `ComponentHandler` subclass when the component touches the image view or
owns a widget.

```python
from pyleem_gui.plugins import Choice, ComponentHandler, plugin

overlays = plugin("Overlays")


class CrosshairHandler(ComponentHandler):
    def set_active(self, on):
        ...

    def is_active(self):
        ...

    def widget(self):
        ...

    def process_params(self):
        ...

    def params_changed(self, params):
        ...


overlays.render(
    CrosshairHandler,
    process_id="crosshair",
    help="Show a crosshair overlay.",
    params={"style": Choice("thin", ["thin", "thick"])},
)
```

Useful hooks:

| Hook | Purpose |
| --- | --- |
| `set_active(on)` | Show or hide the component |
| `is_active()` | Report whether it is active |
| `widget()` | Return extra controls or a plot widget |
| `toggle_button()` | Reuse an existing button instead of the host toggle |
| `params_changed(params)` | Restore state from form edits or workflow import |
| `process_params()` | Return the reproducible state to save |
| `status_text()` | Return persistent status text |
| `changed.emit()` | Ask the host to sync workflow and status |

Render handlers enter the process list, so their state is saved in workflows.
Analysis handlers render in their own widgets and store only non-default
settings in the workflow analysis map.

## Analysis Handler

`AnalysisHandler` is a convenience base for analysis widgets. It owns active
state, widget visibility, and image-update filtering.

```python
class MyPlot(AnalysisHandler):
    refresh_reasons = ("open", "process", "roi")

    def widget(self):
        return self._plot

    def refresh(self):
        ...
```

Use `refresh_reasons` to avoid expensive redraws. Stack-wide analysis should not
refresh on plain frame scrolling unless it really depends on the current frame.

## Shared ROI Notice

Plugins must not import each other. If a plugin needs the active ROI, read the
live ROI from `context.image_view.roi` and use `context.roi.active()` to check
whether one is published. Redraw on `image_update("roi")`.

The ROI service carries only active/inactive state. It does not copy geometry or
pixels.

## Mutual Exclusion

Use `replaces=[...]` when two components cannot be active together:

```python
@builtin.render(process_id="autolevel", replaces=["manuallevel"], help="...")
def autolevel(image, params):
    ...
```

Sibling short ids are qualified to the same plugin. Full `plugin:id` values are
kept as given.

## Discovery

`discover_plugins()` imports built-in plugin modules plus `*.py` files from
`~/.pyleem/plugins` and paths listed in `PYLEEM_PLUGIN_PATH`. A module becomes a
plugin by calling `plugin()`.

Tabs are ordered by pinned core tabs first, then by `(plugin.order,
plugin.title)`.

## Workflow Format

Workflows are versioned JSON:

```json
{
  "version": 1,
  "processes": [
    {"process_id": "builtin:autolevel", "params": {}}
  ],
  "analysis": {
    "line_profile:line_profile": {
      "energy": true,
      "peak_shift": 3.75,
      "pixel_per_ev": 166.0,
      "reverse": false
    }
  }
}
```

Unknown process ids are skipped on import with a logged warning. Unknown
analysis ids are kept because analysis settings are never applied to image data.
A top-level JSON array still loads as the older processes-only format.

## Reference

| Object | Key fields |
| --- | --- |
| `Plugin` | `title`, `version`, `order`, `components` |
| `Component` | `kind`, `id`, `label`, `help`, `handler`, `params_schema`, `always_on`, `fill`, `replaces` |
| `ProcessSpec` | `process_id`, `version`, `kind`, `label`, `help`, `apply`, `params_schema` |
| `Process` | `process_id`, `params` |

Current view spec keys:

| Key | Meaning |
| --- | --- |
| `levels` | `(lo, hi)` display levels |
