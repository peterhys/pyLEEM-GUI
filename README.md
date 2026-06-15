# Welcome to pyLEEM-GUI

[![License: BSD 3-Clause](https://img.shields.io/badge/License-BSD%203--Clause-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

pyLEEM-GUI is a workflow tool for large Low Energy Electron Microscopy (LEEM)
image stacks: data and metadata extraction, visualization, and analysis. It
builds on [pyqtgraph](https://www.pyqtgraph.org/) for visualization and the
[pyLEEM](https://github.com/peterhys/pyLEEM) backend for decoding and analysis.
Features are plugins shown as tabs (autocontrast, ROI, profile, export), and a
processing sequence can be saved as a shareable workflow file.

## Installation

To develop locally, clone and install the package:

```bash
git clone https://github.com/peterhys/pyLEEM-GUI.git
cd pyLEEM-GUI
pip install -e .
```

## Usage

To run the application, use the command:

```bash
pyleem-gui
```

## License

pyLEEM-GUI is distributed under the BSD 3-Clause License, see [LICENSE](LICENSE).

Additional Brookhaven National Laboratory, U.S. Department of Energy, and U.S.
Government rights notices are provided in [NOTICE](NOTICE).

Third-party dependencies are distributed under their own licenses, see
[THIRD_PARTY_LICENSES](THIRD_PARTY_LICENSES).
