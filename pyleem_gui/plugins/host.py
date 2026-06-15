"""Qt plugin host classes and generated tab runtime."""

from dataclasses import dataclass
from typing import Callable

import pyqtgraph as pg
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..image import ImageLayer
from ..process import Process, ProcessLayer, filled_params
from ..view import ViewLayer
from .spec import ComponentHandlerMark


# context, ROI service, and toggles
class ROIService:
    """Shared active-ROI notice published by the ROI component."""

    def __init__(self, notify):
        self._provider = None
        self._notify = notify

    def publish(self, provider):
        """Set the active ROI provider (or None) and notify subscribers."""
        self._provider = provider
        self._notify("roi")

    def active(self):
        return self._provider is not None


def as_toggle(button, tooltip=""):
    """Configure a button as a uniform On/Off toggle."""
    button.setCheckable(True)
    button.setText("Off")
    if tooltip:
        button.setToolTip(tooltip)
    button.toggled.connect(lambda on: button.setText("On" if on else "Off"))
    return button


def make_toggle_button(tooltip=""):
    """Create a uniform On/Off toggle button."""
    return as_toggle(QPushButton(), tooltip)


def set_toggle_silently(button, checked):
    """Set a toggle without firing ``toggled``."""
    button.blockSignals(True)
    button.setChecked(checked)
    button.blockSignals(False)
    button.setText("On" if checked else "Off")


def _ignore_status(_message):
    """Drop status text when no status bar is wired."""


@dataclass
class PluginContext:
    """Runtime objects passed to a mounted plugin."""

    images: ImageLayer
    image_view: pg.ImageView
    workflow: ProcessLayer = None
    status: Callable[[str], None] = _ignore_status
    roi: ROIService = None
    view: ViewLayer = None

    def __post_init__(self):
        if self.workflow is None:
            self.workflow = self.images.workflow
        if self.roi is None:
            self.roi = ROIService(self.images.image_update.emit)
        if self.view is None:
            self.view = ViewLayer(self.images)


class TabPlugin(QWidget):
    """Base class for plugin tabs."""

    title = "Plugin"

    def __init__(self, context):
        super().__init__()
        self.context = context
        self.images = context.images
        self.image_view = context.image_view


# handler base classes
class ComponentHandler(QObject, ComponentHandlerMark):
    """Base for handler-backed render and analysis components."""

    changed = Signal()

    def __init__(self, context, component):
        super().__init__()
        self.context = context
        self.component = component

    def on_image_reason(self, reason, slot):
        """Call ``slot`` only for one ``image_update`` reason."""
        self.context.images.image_update.connect(
            lambda r: slot() if r == reason else None
        )

    def toggle_button(self):
        """Return a self-wired toggle button, or None for host-created toggle."""
        return None

    def widget(self):
        """Extra controls shown below the generated form."""
        return None

    def set_active(self, on):
        """Enable or disable the component."""

    def is_active(self):
        return False

    def params_changed(self, params):
        """Apply params from a form edit or workflow import."""

    def process_params(self):
        """Params recorded on this component's process entry."""
        return {}

    def status_text(self):
        """Permanent status-bar text while active, or None to leave it alone."""
        return None


class AnalysisHandler(ComponentHandler):
    """Base for analysis widgets with guarded refresh wiring."""

    refresh_reasons = None

    def __init__(self, context, component):
        super().__init__(context, component)
        self._on = False
        context.images.image_update.connect(self._on_image_update)

    def set_active(self, on):
        self._on = on
        widget = self.widget()
        if widget is not None:
            widget.setVisible(on)
        if on:
            self.refresh()

    def is_active(self):
        return self._on

    def _on_image_update(self, reason):
        if self._on and (
            self.refresh_reasons is None or reason in self.refresh_reasons
        ):
            self.refresh()

    def refresh(self):
        """Redraw the widget from the image layer; only called while active."""

    def refresh_if_active(self):
        """Refresh only while active."""
        if self._on:
            self.refresh()


# profile plot appearance
# Colors only; image pixels, LUTs, levels, and workflow data are untouched.
def plot_profile_trace(plot, x, y):
    """Plot a profile trace with separate screen and Matplotlib export colors."""
    item = plot.plot(x, y, pen=pg.mkPen("k"))
    # MatplotlibExporter reads PlotDataItem.opts["pen"], while pyqtgraph draws
    # PlotDataItem.curve. Keep the on-screen trace white but export it black on
    # Matplotlib's default white figure.
    item.curve.setPen(pg.mkPen("w"))
    return item


def plot_profile_points(plot, x, y, symbol="o"):
    """Plot profile points with separate screen and Matplotlib export colors."""
    item = plot.plot(
        x,
        y,
        pen=None,
        symbol=symbol,
        symbolPen=pg.mkPen("k"),
        symbolBrush=pg.mkColor("k"),
    )
    # MatplotlibExporter reads PlotDataItem symbol opts, while pyqtgraph draws
    # PlotDataItem.scatter.
    item.scatter.setPen(pg.mkPen("w"))
    item.scatter.setBrush(pg.mkColor("w"))
    return item


# parameter form
# Fallback spin-box bounds when a schema omits min/max (QSpinBox is 32-bit).
_INT_LIMIT = 2_147_483_647
_FLOAT_LIMIT = 1e12


def _humanize(name):
    return name.replace("_", " ").capitalize()


class ParamForm(QWidget):
    """Generated parameter controls for a component schema."""

    changed = Signal()

    def __init__(self, schema, parent=None):
        super().__init__(parent)
        self._getters = {}
        self._setters = {}

        layout = QFormLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        for name, entry in schema.items():
            widget, getter, setter, signal = self.build(entry)
            self._getters[name] = getter
            self._setters[name] = setter
            signal.connect(self.changed)
            layout.addRow(entry.get("label") or _humanize(name), widget)

    def build(self, entry):
        kind = entry.get("type", "float")
        if kind == "int":
            w = QSpinBox()
            w.setRange(
                _as_int(entry.get("min"), -_INT_LIMIT),
                _as_int(entry.get("max"), _INT_LIMIT),
            )
            w.setValue(_as_int(entry.get("default"), 0))
            return w, w.value, w.setValue, w.valueChanged
        if kind == "bool":
            w = QCheckBox()
            w.setChecked(bool(entry.get("default", False)))
            return w, w.isChecked, w.setChecked, w.toggled
        if kind == "choice":
            w = QComboBox()
            w.addItems([str(c) for c in entry.get("choices", [])])
            default = entry.get("default")
            if default is not None:
                w.setCurrentText(str(default))
            return w, w.currentText, w.setCurrentText, w.currentTextChanged
        # default float control
        w = QDoubleSpinBox()
        w.setDecimals(3)
        w.setRange(
            _as_float(entry.get("min"), -_FLOAT_LIMIT),
            _as_float(entry.get("max"), _FLOAT_LIMIT),
        )
        w.setValue(_as_float(entry.get("default"), 0.0))
        return w, w.value, w.setValue, w.valueChanged

    def values(self):
        """Current parameter values, keyed by name."""
        return {name: getter() for name, getter in self._getters.items()}

    def set_values(self, params):
        """Set controls from ``params`` without emitting ``changed``."""
        self.blockSignals(True)
        try:
            for name, value in params.items():
                setter = self._setters.get(name)
                if setter is not None:
                    setter(value)
        finally:
            self.blockSignals(False)

    def is_empty(self):
        return not self._getters


def _as_int(value, fallback):
    return int(value) if value is not None else fallback


def _as_float(value, fallback):
    return float(value) if value is not None else fallback


# auto-generating host
class ComponentController:
    """Runtime wiring for one component."""

    def __init__(self, tab, component):
        self.tab = tab
        self.component = component
        self.layer = tab.context.workflow
        self.form = ParamForm(component.params_schema)
        self.handler = None
        self.toggle = None
        self.extra = None
        if component.handler is None:
            self.wire_process_component()
        else:
            self.wire_handler_component()

    def wire_process_component(self):
        """Wire a process-backed component."""
        self.form.changed.connect(self._on_process_params)
        if self.component.always_on:
            self.activate_process()
        else:
            self.toggle = make_toggle_button(self.component.help)
            self.toggle.toggled.connect(self._on_process_toggle)

    def wire_handler_component(self):
        """Wire a handler-backed component."""
        self.handler = self.component.handler(self.tab.context, self.component)
        self.extra = self.handler.widget()
        self.handler.changed.connect(self._sync)
        self.form.changed.connect(self._on_handler_params)
        if self.component.always_on:
            self.handler.set_active(True)
            self._sync()
        else:
            button = self.handler.toggle_button()
            if button is None:
                self.toggle = make_toggle_button(self.component.help)
                self.toggle.toggled.connect(self.handler.set_active)
            else:
                self.toggle = button
            self.toggle.toggled.connect(self._sync)

    def place_process(self, params):
        """Add this component's process, then remove replacements."""
        self.layer.add_process(Process(self.component.id, params))
        for other in self.component.replaces:
            index = self.layer.find_process(other)
            if index is not None:
                self.layer.delete_process(index)

    def activate_process(self):
        if self.layer.find_process(self.component.id) is None:
            self.place_process(self.form.values())

    # process wiring
    def _on_process_toggle(self, on):
        index = self.layer.find_process(self.component.id)
        if on and index is None:
            self.place_process(self.form.values())
        elif not on and index is not None:
            self.layer.delete_process(index)

    def _on_process_params(self):
        index = self.layer.find_process(self.component.id)
        if index is not None:
            self.layer.update_process(index, self.form.values())

    # handler wiring
    def _on_handler_params(self):
        self.handler.params_changed(self.form.values())
        self._sync()

    def default_params(self):
        """The component's params at their schema defaults."""
        return filled_params(self.component, {})

    def _sync(self, *_args):
        """Mirror a handler component into workflow state."""
        if self.handler is None:
            return
        if self.component.kind == "analysis":
            self.sync_analysis_entry()
        else:
            self.sync_process_entry()
        self.push_status()

    def sync_analysis_entry(self):
        """Record or clear the handler's analysis-map entry."""
        params = self.handler.process_params()
        self.layer.update_analysis(
            self.component.id,
            {} if params == self.default_params() else params,
        )

    def sync_process_entry(self):
        """Match the render entry to the handler's active state."""
        index = self.layer.find_process(self.component.id)
        if self.handler.is_active() and index is None:
            self.place_process(self.handler.process_params())
        elif not self.handler.is_active() and index is not None:
            self.layer.delete_process(index)

    def push_status(self):
        """Push the handler's status text to the permanent status label."""
        text = self.handler.status_text() if self.handler.is_active() else ""
        if text is not None:
            self.tab.context.status(text)

    # canonical-list sync
    def sync_state(self):
        """Align this component with the canonical process list."""
        if self.component.kind == "analysis":
            self.restore_analysis()
            return
        index = self.layer.find_process(self.component.id)
        present = index is not None
        if self.handler is not None:
            self.restore_handler(present, index)
        elif self.component.always_on:
            if not present:  # an imported workflow dropped an always-on entry
                self.activate_process()
        elif present:
            self.restore_form(self.layer.processes[index].params)
        if self.toggle is not None and self.toggle.isChecked() != present:
            set_toggle_silently(self.toggle, present)

    def restore_analysis(self):
        """Restore an analysis handler from workflow analysis params."""
        if self.handler is None:
            return
        target = self.layer.analysis.get(self.component.id, self.default_params())
        if target != self.handler.process_params():
            self.form.set_values(target)
            self.handler.params_changed(target)

    def restore_handler(self, present, index):
        """Restore a render handler from the canonical process list."""
        if self.handler.is_active() != present:
            self.handler.set_active(present)
        if present:
            # Copy before restore; some handlers write back during restore.
            params = dict(self.layer.processes[index].params)
            if params != self.handler.process_params():
                self.handler.params_changed(params)

    def restore_form(self, params):
        """Reload a process-backed component's form from its entry params."""
        values = self.form.values()
        if any(values.get(name) != value for name, value in params.items()):
            self.form.set_values(params)


class AutoTab(TabPlugin):
    """A tab generated from a declarative plugin spec."""

    def __init__(self, context, spec):
        super().__init__(context)
        self.title = spec.title
        self.spec = spec
        self.controllers = []

        layout = QVBoxLayout(self)
        filled = False
        for component in spec.components:
            box, fill = self.build_component(component)
            layout.addWidget(box, 1 if fill else 0)
            filled = filled or fill
        if not filled:  # top-align the controls when nothing fills the tab
            layout.addStretch(1)

        context.workflow.process_update.connect(self.sync_from_processes)
        # Late-mounted plugins must reflect the current workflow immediately.
        self.sync_from_processes()

    def build_component(self, component):
        controller = ComponentController(self, component)
        self.controllers.append(controller)

        box = QGroupBox()
        box_layout = QVBoxLayout(box)

        header = QHBoxLayout()
        header.addWidget(QLabel(component.label))
        id_label = QLabel(component.id)
        id_label.setStyleSheet("color: #aaaaaa;")
        font = id_label.font()
        font.setPointSize(font.pointSize() - 2)
        id_label.setFont(font)
        header.addWidget(id_label)
        header.addStretch(1)
        if controller.toggle is not None:
            header.addWidget(controller.toggle)
        box_layout.addLayout(header)

        if not controller.form.is_empty():
            box_layout.addWidget(controller.form)
        if controller.extra is not None:
            box_layout.addWidget(controller.extra, 1 if component.fill else 0)
        return box, component.fill

    def sync_from_processes(self, *_args):
        """Align every component's widgets with the canonical process list."""
        for controller in self.controllers:
            controller.sync_state()

    def controller(self, label):
        """Look up a component controller by its label (for tests/hosts)."""
        for controller in self.controllers:
            if controller.component.label == label:
                return controller
        return None
