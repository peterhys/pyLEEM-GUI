"""Application entry point and main window for pyLEEM-GUI.

The main window mainly handles the UI logic, including the session and
process layer loading, plugin tab discovery, process bar rendering.

Most of the imaging and data processing logics are handled by process layer
and session layer.
"""

import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGroupBox,
    QLabel,
    QMainWindow,
    QRadioButton,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage

from .session import ExportOptions, ProcessLayer, SessionLayer
from .plugins import AutoTab, PluginContext, discover_plugins
from .processbar import ProcessBar
from .viewer import Viewer


class ExportDialog(QDialog):
    """Pick export levels (raw / edited / rendered) and the output mode."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Export")
        layout = QVBoxLayout(self)

        levels = QGroupBox("Levels")
        levels_layout = QVBoxLayout(levels)
        self.cb_raw = QCheckBox("Raw")
        self.cb_edited = QCheckBox("Edited")
        self.cb_rendered = QCheckBox("Rendered")
        self.cb_rendered.setChecked(True)
        for cb in (self.cb_raw, self.cb_edited, self.cb_rendered):
            levels_layout.addWidget(cb)
        layout.addWidget(levels)

        mode = QGroupBox("Output")
        mode_layout = QVBoxLayout(mode)
        self.rb_separate = QRadioButton("Separate file per level")
        self.rb_separate.setChecked(True)
        self.rb_composite = QRadioButton("Composite (one image)")
        mode_layout.addWidget(self.rb_separate)
        mode_layout.addWidget(self.rb_composite)
        layout.addWidget(mode)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def options(self):
        return ExportOptions(
            raw=self.cb_raw.isChecked(),
            edited=self.cb_edited.isChecked(),
            rendered=self.cb_rendered.isChecked(),
            composite=self.rb_composite.isChecked(),
        )


def qimage_to_rgb(qimg):
    """Convert a QImage to an ``(H, W, 3)`` uint8 RGB array."""
    import numpy as np

    qimg = qimg.convertToFormat(QImage.Format_RGB888)
    width, height = qimg.width(), qimg.height()
    flat = np.frombuffer(qimg.constBits(), np.uint8)
    return (
        flat.reshape(height, qimg.bytesPerLine())[:, : width * 3]
        .reshape(height, width, 3)
        .copy()
    )


class MainWindow(QMainWindow):
    """The main window: the image viewer, the process bar, and the plugin tabs."""

    def __init__(self, session=None, workflow=None, plugin_specs=None):
        super().__init__()
        # The process layer and session are app-level peers: the workflow
        # outlives any opened dataset (opening new data resets the session in
        # place, never the process list).
        if session is not None:  # For testing purposes
            self.session = session
            self.workflow = workflow or session.workflow
        else:
            self.workflow = workflow or ProcessLayer()
            self.session = SessionLayer(workflow=self.workflow)
        # Discover plugins (built-in + ~/.pyleem/plugins) unless specs are injected.
        plugin_specs = discover_plugins() if plugin_specs is None else plugin_specs
        self.setWindowTitle("pyLEEM-GUI")
        self.resize(1200, 800)

        splitter = QSplitter(Qt.Horizontal)
        self.viewer = Viewer(self.session)
        self.session.bake_rendered_frames(self.bake_rendered_frames)
        splitter.addWidget(self.viewer)

        # Plugins are mounted as tabs; the process bar renders the process
        # layer's list, with each chip linking back to its plugin's tab.
        self.tabs = QTabWidget()
        self.process_bar = ProcessBar()
        self.process_bar.set_tab_widget(self.tabs)
        # Plugin state (e.g. ROI parameters) goes to a permanent status-bar
        # label so it does not clobber transient action messages.
        self._plugin_status = QLabel()
        self.statusBar().addPermanentWidget(self._plugin_status)
        context = PluginContext(
            session=self.session,
            image_view=self.viewer.image_view,
            workflow=self.workflow,
            status=self._plugin_status.setText,
        )
        self.plugins = []
        for spec in plugin_specs:
            tab = AutoTab(context, spec)
            self.plugins.append(tab)
            self.tabs.addTab(tab, tab.title)
            self.process_bar.register_tab(spec.title, tab)
        # Bind after the tabs are registered so the initial render can resolve
        # each chip's source tab.
        self.process_bar.bind(self.workflow)
        splitter.addWidget(self.tabs)
        splitter.setSizes([800, 400])

        # The process bar sits above the status bar.
        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.addWidget(splitter, stretch=1)
        central_layout.addWidget(self.process_bar)
        self.setCentralWidget(central)

        self.build_menu()
        self.statusBar().showMessage("Ready")

    def build_menu(self):
        file_menu = self.menuBar().addMenu("&File")
        self.file_menu = file_menu  # keep a reference for hosts/tests
        file_menu.addAction("Open File...", self.open_file)
        file_menu.addAction("Open Folder...", self.open_folder)
        file_menu.addAction("Import Workflow...", self.import_workflow)
        file_menu.addSeparator()
        file_menu.addAction("Export Image...", self.export_image)
        file_menu.addAction("Export Stack...", self.export_stack)
        file_menu.addAction("Save Workflow...", self.save_workflow)

        # View menu: a checkable item per plugin tab to show/hide it.
        view_menu = self.menuBar().addMenu("&View")
        self.view_menu = view_menu
        for index, plugin in enumerate(self.plugins):
            action = view_menu.addAction(plugin.title)
            action.setCheckable(True)
            action.setChecked(True)
            action.toggled.connect(
                lambda shown, i=index: self.tabs.setTabVisible(i, shown)
            )

    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open .dat file", filter="LEEM data (*.dat)"
        )
        if path:
            self.session.open_file(path)
            self.statusBar().showMessage(f"Opened {path}")

    def open_folder(self):
        path = QFileDialog.getExistingDirectory(self, "Open .dat folder")
        if path:
            self.session.open_folder(path)
            self.statusBar().showMessage(
                f"Opened {path} ({self.session.n_frames} frames)"
            )

    def import_workflow(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Import workflow", filter="JSON (*.json)"
        )
        if path:
            self.workflow.import_workflow(path)
            self.statusBar().showMessage(f"Imported workflow {path}")

    # -- export ----------------------------------------------------------------
    def export_image(self):
        """Export the current frame."""
        self.export([self.session.current_index])

    def export_stack(self):
        """Export every frame."""
        self.export(list(range(self.session.n_frames)))

    def export(self, indices):
        if self.session.n_frames == 0:
            self.statusBar().showMessage("Nothing to export")
            return
        dialog = ExportDialog(self)
        if dialog.exec() != QDialog.Accepted:
            return
        opts = dialog.options()
        if not opts.any():
            self.statusBar().showMessage("No export levels selected")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export TIFF", filter="TIFF (*.tif *.tiff)"
        )
        if not path:
            return
        written = self.session.write_export(Path(path), list(indices), opts)
        self.statusBar().showMessage(f"Exported {', '.join(written)}")

    def bake_rendered_frames(self, indices):
        """Grab RGB frames from the image view for rendered TIFF export.

        The process requires the session to be in the rendered mode for the
        view to be updated. The behavior maybe changed to internal render
        from the view layer.
        """
        view = self.viewer.image_view.ui.graphicsView
        keep_index = self.session.current_index
        keep_mode = self.session.mode
        self.session.set_mode("rendered")
        frames = []
        for i in indices:
            self.session.set_index(i)
            QApplication.processEvents()  # let the view repaint the frame
            frames.append(qimage_to_rgb(view.grab().toImage()))
        self.session.set_index(keep_index)
        self.session.set_mode(keep_mode)
        return frames

    def save_workflow(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save workflow", filter="JSON (*.json)"
        )
        if path:
            self.workflow.save_workflow(path)
            self.statusBar().showMessage(f"Saved workflow {path}")


def main():
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
