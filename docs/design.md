# Design

pyLEEM-GUI is a GUI workflow tool for experimental, image-based
low-energy electron microscopy (LEEM) data stacks.
The tool aims to provide a user-friendly interface for large
data extraction, metadata extraction, visualization, and analysis.
We provide LEEM specific workflows, and further analysis can be done
with existing analysis tools such as ImageJ.

The GUI is built upon [pyqtgraph](https://www.pyqtgraph.org/)
for the visualization and
[`pyleem`](https://github.com/peterhys/pyLEEM) as the analysis backend.
We provide APIs for extending the GUI with custom plugins and
preconfigured workflows.

The architecture is designed to be modular and extensible. Plugins
can be added to the GUI with provided [APIs](api.md).


## Layers

There are three layers that interact with the data:

| Layer | Owns | Does not own |
| --- | --- | --- |
| `ProcessLayer` | Process list, analysis settings, workflow import/export | Image files or frame index |
| `ImageLayer` | Dataset, current frame, metadata, one-frame edited cache | Display mode |
| `ViewLayer` | Raw/edited/rendered display mode and rendered output | Dataset or workflow |

`ProcessLayer` is app-level state. It persists when new images are opened.
`ImageLayer` is per-dataset state. Opening data replaces its dataset, resets the
frame index, and clears the edited cache. `ViewLayer` is owned by the viewer and
asks the image layer for the current output.

## Signals

There are two update channels:

| Channel | Owner | Tags |
| --- | --- | --- |
| `process_update(kind)` | `ProcessLayer` | `edit`, `render`, `analysis`, `sync` |
| `image_update(reason)` | `ImageLayer` | `open`, `frame`, `process`, `mode`, `roi` |

The image layer subscribes to `process_update`. It ignores `analysis` and
`sync`, invalidates the edited cache for edit changes, and emits
`image_update("process")` when loaded frames need redraw.

The view layer owns no signal. A mode change emits `image_update("mode")`.
The shared ROI service also uses `image_update("roi")`.


## Workflow

A workflow is an ordered list of `Process(process_id, params)` plus an analysis
settings map. Processes are appended and deleted; they are not reordered.

| Kind | Meaning | Output |
| --- | --- | --- |
| `edit` | Changes image data | New image array |
| `render` | Changes display only | View spec such as levels |
| `analysis` | Plugin widget settings | Stored in the analysis map |

For display purposes:

```text
raw frame -> edit processes -> rendered image -> viewer
```

For analysis purposes:

```text
raw frame -> edit processes -> analysis components -> plugins
```

The complete workflow process can be saved and loaded as a JSON file.

## Plugins

Plugins provide necessary functionality for the workflow.

Plugins are tabs built from declarative specs. A plugin module calls `plugin()`
and declares edit, render, or analysis components. `AutoTab` builds the Qt
controls, toggles, parameter forms, process-list wiring, and status updates.

Plugins read image data through `PluginContext.images`, submit workflow changes
through `PluginContext.workflow`, and must not import each other. Shared
cross-plugin state, such as the active ROI notice, belongs in shared services.
