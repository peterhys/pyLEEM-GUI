"""Application entry point and main window."""

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

from .image import ImageLayer
from .process import ProcessingCoordinator, ProcessLayer
from .view import ExportOptions
from .plugins import AutoTab, PluginContext, discover_plugins, format_plugin_id
from .ui.processbar import ProcessBar
from .ui.viewer import Viewer


class ExportDialog(QDialog):
    """Export level and output-mode picker."""

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
    """Image viewer, process bar, plugin tabs, and File menu."""

    def __init__(self, images=None, workflow=None, plugin_specs=None):
        super().__init__()
        # The workflow outlives any opened dataset.
        if images is not None:
            self.images = images
            self.workflow = workflow or images.workflow
        else:
            self.workflow = workflow or ProcessLayer()
            self.images = ImageLayer(workflow=self.workflow)
        self.coordinator = ProcessingCoordinator(self.images)
        plugin_specs = discover_plugins() if plugin_specs is None else plugin_specs
        self.setWindowTitle("pyLEEM-GUI")
        self.resize(1200, 800)

        splitter = QSplitter(Qt.Horizontal)
        self.viewer = Viewer(self.images)
        self.viewer.view.bake_rendered_frames(self.bake_rendered_frames)
        splitter.addWidget(self.viewer)

        self.tabs = QTabWidget()
        self.process_bar = ProcessBar()
        self.process_bar.set_tab_widget(self.tabs)
        # Plugin readouts should not overwrite transient action messages.
        self._plugin_status = QLabel()
        self.statusBar().addPermanentWidget(self._plugin_status)
        context = PluginContext(
            images=self.images,
            image_view=self.viewer.image_view,
            workflow=self.workflow,
            status=self._plugin_status.setText,
            view=self.viewer.view,
        )
        self.plugins = []
        for spec in plugin_specs:
            tab = AutoTab(context, spec)
            self.plugins.append(tab)
            self.tabs.addTab(tab, tab.title)
            self.process_bar.register_tab(format_plugin_id(spec.title), tab)
        self.process_bar.bind(self.workflow)
        splitter.addWidget(self.tabs)
        splitter.setSizes([800, 400])

        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.addWidget(splitter, stretch=1)
        central_layout.addWidget(self.process_bar)
        self.setCentralWidget(central)

        self.build_menu()
        self.statusBar().showMessage("Ready")

    def build_menu(self):
        file_menu = self.menuBar().addMenu("&File")
        self.file_menu = file_menu
        file_menu.addAction("Open File...", self.open_file)
        file_menu.addAction("Open Folder...", self.open_folder)
        file_menu.addAction("Import Workflow...", self.import_workflow)
        file_menu.addSeparator()
        file_menu.addAction("Export Image...", self.export_image)
        file_menu.addAction("Export Stack...", self.export_stack)
        file_menu.addAction("Save Workflow...", self.save_workflow)

    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open data file", filter="Data (*.dat *.tif *.tiff)"
        )
        if path:
            self.coordinator.open_file(path)
            self.statusBar().showMessage(f"Opened {path}")

    def open_folder(self):
        path = QFileDialog.getExistingDirectory(self, "Open data folder")
        if path:
            self.coordinator.open_folder(path)
            self.statusBar().showMessage(
                f"Opened {path} ({self.images.n_frames} frames)"
            )

    def import_workflow(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Import workflow", filter="JSON (*.json)"
        )
        if path:
            self.coordinator.import_workflow(path)
            self.statusBar().showMessage(f"Imported workflow {path}")

    # export
    def export_image(self):
        """Export the current frame."""
        self.export([self.images.current_index])

    def export_stack(self):
        """Export every frame."""
        self.export(list(range(self.images.n_frames)))

    def export(self, indices):
        if self.images.n_frames == 0:
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
        written = self.viewer.view.write_export(Path(path), list(indices), opts)
        self.statusBar().showMessage(f"Exported {', '.join(written)}")

    def bake_rendered_frames(self, indices):
        """Grab rendered RGB frames from the image view."""
        view = self.viewer.image_view.ui.graphicsView
        keep_index = self.images.current_index
        keep_mode = self.viewer.view.mode
        self.viewer.view.set_mode("rendered")
        frames = []
        for i in indices:
            self.images.set_index(i)
            # Redraw even when the starting index did not change.
            self.viewer.refresh_image()
            QApplication.processEvents()
            frames.append(qimage_to_rgb(view.grab().toImage()))
        self.images.set_index(keep_index)
        self.viewer.view.set_mode(keep_mode)
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
