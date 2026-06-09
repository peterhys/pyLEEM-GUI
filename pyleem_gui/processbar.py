"""Show the applied image processes.

Two rows of applied image processes: ``edited`` (destructive image processes) and
``rendered`` (non-destructive: contrast, ROI/annotation). The process
layer drives the bar: ``bind`` subscribes it to ``process_update`` and both
rows re-render from the canonical process list, so the bar always matches the
workflow (including after an import).

Hovering a process shows its parameters, and clicking it switches to
the tab of the plugin that registered it.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

# Canonical bucket names live in the Qt-free core; re-exported here.
from .process import REGISTRY, filled_params

# Fixed button and row heights keep every strip the same height whether or not
# it holds any (a button is taller than the bare prefix label).
_BUTTON_HEIGHT = 20
_ROW_HEIGHT = 26

# Rounded buttons; palette roles keep them theme-correct in light and dark.
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
        # Fixed height so adding/removing processes never changes the line height.
        self.setFixedHeight(_ROW_HEIGHT)
        self.render([], None)

    def render(self, items, on_click):
        while self._layout.count():
            widget = self._layout.takeAt(0).widget()
            if widget is not None:
                widget.setParent(None)  # detach now so it stops painting immediately
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
    """Two stacked rows of applied edited and rendered processes.

    Rendered from the canonical process list of the bound `ProcessLayer`; the
    bar holds no state of its own beyond the tab mapping for chip clicks.
    """

    def __init__(self):
        super().__init__()
        self._rows = {"edited": _Row("edited:"), "rendered": _Row("rendered:")}
        self._items = {"edited": [], "rendered": []}
        self._layer = None
        self._tabs_by_slug = {}
        self.tab_widget = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._rows["edited"])
        layout.addWidget(self._rows["rendered"])

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
        """Rebuild both rows from the bound layer's process list."""
        items = {"edited": [], "rendered": []}
        if self._layer is not None:
            for proc in self._layer.processes:
                spec = REGISTRY.get(proc.process_id)
                if spec is None:
                    continue  # an imported workflow may name an unloaded plugin
                bucket = spec.kind_id + "ed"
                if bucket not in items:
                    continue  # outputs render in the plugin widget, not here
                params = filled_params(spec, proc.params)
                lines = [proc.process_id]
                lines += [f"{name}: {value}" for name, value in params.items()]
                items[bucket].append(
                    {
                        "id": proc.process_id,
                        "label": proc.process_id,
                        "tooltip": "\n".join(lines),
                        "source": self._tabs_by_slug.get(
                            proc.process_id.split(":", 1)[0]
                        ),
                    }
                )
        self._items = items
        for bucket, row in self._rows.items():
            row.render(items[bucket], self._on_click)

    def labels(self, bucket):
        return [it["label"] for it in self._items.get(bucket, [])]

    def _on_click(self, source):
        # Select the top-level tab page that is the source or contains it, so a
        # process from a nested sub-plugin still highlights its hosting tab.
        if self.tab_widget is None or source is None:
            return
        for i in range(self.tab_widget.count()):
            page = self.tab_widget.widget(i)
            if page is source or (page is not None and page.isAncestorOf(source)):
                self.tab_widget.setCurrentIndex(i)
                return
