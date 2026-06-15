import json

import numpy as np
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyqtgraph")

from PySide6.QtWidgets import QGroupBox, QLabel, QPushButton, QSpinBox


# auto-generated host
def test_builtin_tab_auto_generates_components(builtin):
    labels = [c.component.label for c in builtin.controllers]
    assert labels == ["autolevel", "manuallevel", "ROI"]
    ids = [c.component.id for c in builtin.controllers]
    assert ids == ["builtin:autolevel", "builtin:manuallevel", "builtin:ROI"]

    boxes = builtin.findChildren(QGroupBox)
    assert len(boxes) == 3  # one group box per component
    for box, component in zip(boxes, builtin.spec.components):
        texts = [label.text() for label in box.findChildren(QLabel)]
        assert component.label in texts
        assert component.id in texts  # the dim qualified id label

    controller = builtin.controller("autolevel")
    assert controller.form.is_empty()
    assert controller.form.findChild(QSpinBox) is None
    for label in ("autolevel", "manuallevel", "ROI"):
        button = builtin.controller(label).toggle
        assert isinstance(button, QPushButton)
        assert button.isCheckable()
        assert button.text() == "Off"
    controller.toggle.setChecked(True)
    assert controller.toggle.text() == "On"


def test_param_widget_is_auto_generated(tunable, context):
    controller = tunable.controller("gain")
    spin = controller.form.findChild(QSpinBox)
    # Auto-generated from the ProcessSpec's params_schema (k int, default 3).
    assert spin is not None
    assert spin.value() == 3

    controller.toggle.setChecked(True)
    spin.setValue(9)  # editing the widget updates the process in the list in place
    index = context.workflow.find_process("tunable:gain")
    assert context.workflow.processes[index].params["k"] == 9


def test_roi_service_publishes_active_state(builtin, context):
    """ROIService publishes active state and roi image updates."""
    context.image_view.setImage(np.zeros((120, 120)))
    notifications = []
    context.images.image_update.connect(
        lambda reason: (
            notifications.append(context.roi.active()) if reason == "roi" else None
        )
    )
    assert not context.roi.active()  # nothing published until the ROI is on

    roi = builtin.controller("ROI")
    roi.toggle.setChecked(True)
    assert context.roi.active()
    assert notifications and notifications[-1] is True  # publish notified

    roi.handler.shape.setCurrentText("Circle")  # a shape swap republishes
    assert context.roi.active()

    roi.toggle.setChecked(False)
    assert not context.roi.active()
    assert notifications[-1] is False  # deactivation notified


# canonical process list
def test_import_workflow_updates_bar_and_toggles(
    builtin, tunable, context, bar, tmp_path
):
    """Importing a workflow re-renders the bar and re-syncs the tab widgets."""
    wf = tmp_path / "wf.json"
    wf.write_text(
        json.dumps(
            [
                {"process_id": "builtin:autolevel", "params": {}},
                {"process_id": "tunable:gain", "params": {"k": 7}},
            ]
        )
    )
    context.workflow.import_workflow(wf)

    assert "builtin:autolevel" in bar.labels("rendered")
    controller = builtin.controller("autolevel")
    assert controller.toggle.isChecked()
    assert controller.toggle.text() == "On"
    # The parameterized entry loads its value into the auto-generated form.
    assert tunable.controller("gain").form.findChild(QSpinBox).value() == 7
    assert len(context.workflow.processes) == 2  # the resync added no duplicate
