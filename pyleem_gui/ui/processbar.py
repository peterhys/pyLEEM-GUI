"""Workflow strip for process and analysis chips."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..process import REGISTRY, filled_params

# Fixed heights prevent process changes from resizing rows.
_BUTTON_HEIGHT = 20
_ROW_HEIGHT = 26

# Palette roles keep chips aligned with the active Qt palette.
_BUTTON_STYLE = (
    "QPushButton {"
    "  border: 1px solid palette(mid);"
    f"  border-radius: {_BUTTON_HEIGHT // 2}px;"
    "  padding: 0 10px;"
    "  background: palette(button);"
    "}"
    "QPushButton:hover { background: palette(midlight); }"
    "QPushButton:pressed { background: palette(dark); }"
)


class _Row(QWidget):
    def __init__(self, prefix):
        super().__init__()
        self._prefix = prefix
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(4, 0, 4, 0)
        self._layout.setSpacing(4)
        self.setFixedHeight(_ROW_HEIGHT)
        self.render([], None)

    def render(self, items, on_click):
        while self._layout.count():
            widget = self._layout.takeAt(0).widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        self._layout.addWidget(QLabel(self._prefix))
        for i, item in enumerate(items):
            if i > 0:
                self._layout.addWidget(QLabel(">"))
            button = QPushButton(item["label"])
            button.setToolTip(item["tooltip"])
            button.setFixedHeight(_BUTTON_HEIGHT)
            button.setStyleSheet(_BUTTON_STYLE)
            button.setCursor(Qt.PointingHandCursor)
            if on_click is not None:
                source = item["source"]
                button.clicked.connect(lambda _checked=False, s=source: on_click(s))
            self._layout.addWidget(button)
        self._layout.addStretch(1)


class ProcessBar(QWidget):
    """Workflow label above process and analysis strips."""

    def __init__(self):
        super().__init__()
        self._rows = {
            "edited": _Row("edit:"),
            "rendered": _Row("render:"),
            "analysis": _Row("analysis:"),
        }
        self._items = {"edited": [], "rendered": [], "analysis": []}
        self._layer = None
        self._tabs_by_slug = {}
        self.tab_widget = None

        title = QLabel("Workflow")
        title_font = title.font()
        title_font.setBold(True)
        title.setFont(title_font)

        rows = QWidget()
        rows_layout = QVBoxLayout(rows)
        rows_layout.setContentsMargins(0, 0, 0, 0)
        rows_layout.setSpacing(0)
        rows_layout.addWidget(self._rows["edited"])
        rows_layout.addWidget(self._rows["rendered"])
        rows_layout.addWidget(self._rows["analysis"])

        layout = QVBoxLayout(self)
        layout.addWidget(title)
        layout.addWidget(rows)

    def bind(self, workflow):
        """Render from this layer's list, re-rendering on every process_update."""
        self._layer = workflow
        workflow.process_update.connect(self.refresh)
        self.refresh()

    def register_tab(self, slug, tab):
        """Map a plugin slug (the id prefix before ``:``) to its tab page."""
        self._tabs_by_slug[slug] = tab

    def set_tab_widget(self, tabs):
        """Set the QTabWidget whose tab is selected when a process is clicked."""
        self.tab_widget = tabs

    def refresh(self, *_args):
        """Rebuild strips from workflow process and analysis state."""
        items = {"edited": [], "rendered": [], "analysis": []}
        if self._layer is not None:
            for proc in self._layer.processes:
                spec = REGISTRY.get(proc.process_id)
                if spec is None:
                    continue
                bucket = spec.kind + "ed"
                if bucket not in items:
                    continue
                items[bucket].append(
                    self._chip(proc.process_id, filled_params(spec, proc.params))
                )
            for component_id, params in self._layer.analysis.items():
                items["analysis"].append(self._chip(component_id, params))
        self._items = items
        for bucket, row in self._rows.items():
            row.render(items[bucket], self._on_click)

    def _chip(self, label, params):
        """A chip descriptor: the label, a params tooltip, and its source tab."""
        lines = [label] + [f"{name}: {value}" for name, value in params.items()]
        return {
            "label": label,
            "tooltip": "\n".join(lines),
            "source": self._tabs_by_slug.get(label.split(":", 1)[0]),
        }

    def labels(self, bucket):
        return [it["label"] for it in self._items.get(bucket, [])]

    def _on_click(self, source):
        # Select the top-level tab that owns the chip source.
        if self.tab_widget is None or source is None:
            return
        for i in range(self.tab_widget.count()):
            page = self.tab_widget.widget(i)
            if page is source or (page is not None and page.isAncestorOf(source)):
                self.tab_widget.setCurrentIndex(i)
                return
