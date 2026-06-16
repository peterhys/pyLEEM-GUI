"""Metadata plugin for current-frame metadata."""

from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
)

from ..metadata import metadata_rows
from .host import AnalysisHandler
from .spec import plugin


class MetadataHandler(AnalysisHandler):
    """Current-frame metadata table."""

    refresh_reasons = ("frame", "open")

    def __init__(self, context, component):
        super().__init__(context, component)
        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["Key", "Value", "Unit"])
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setMinimumHeight(260)
        self._table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self._table.setVisible(False)

    def widget(self):
        return self._table

    def refresh(self):
        images = self.context.images
        if images.n_frames == 0:
            self._table.setRowCount(0)
            return
        rows = metadata_rows(images.metadata(images.current_index))
        self._table.setRowCount(len(rows))
        for r, (key, value, unit) in enumerate(rows):
            self._table.setItem(r, 0, QTableWidgetItem(key))
            self._table.setItem(r, 1, QTableWidgetItem(value))
            self._table.setItem(r, 2, QTableWidgetItem(unit))


metadata = plugin("Metadata")

metadata.analysis(
    MetadataHandler,
    process_id="metadata",
    always_on=True,
    fill=True,
    help="Show the current frame's metadata (key, value, unit).",
)
