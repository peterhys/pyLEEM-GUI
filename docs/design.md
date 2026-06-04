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

## Architecture

The architecture is designed to be modular and extensible.
The core of the architecture is the interaction layer, where
each plugins can access and modify. The plugins communicate through
the interaction layer.

```text
               image + metadata 
                     |                     
            [ interaction layer ]
                     |                  
        +------------+------------+
metadata reader   profiler    other plugins
```

Because most of the dataset are large data stacks, we cannot store
all files in memory. Instead, we create a sequential modification
registry to keep track of the plugin modifications, and applies to
the image when the image is accessed. The modifications are applied
in order and an indicator of the modification is displayed. Two
types of modifications are supported: display and edit. Edit can modify
the data, and display only changes the appearance and is applied after the edit.

## Plugins

The plugins are the core of the architecture and community support.
All the modifications are done through plugins, which shows as tabs.
We provide several default plugins such as autocontrast, ROI, profile, and
export.

To speed up the plugin development, we provide basic plugin template for
user to add additional functionalities to the GUI, without coding
the GUI components but rather focusing on the data processing logic.
The approach allows CLI usage and jupyter notebook usage of the
plugin functionalities.

The plugin API are documented in [api.md](api.md).

## Workflow

As a user facility oriented software, we provide workflow file that can
apply the image processing directly. This allows staff and user to share
and standardize the image processing workflow.

