import json

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyqtgraph")

from pyleem_gui.process import Process
from pyleem_gui.plugins import AutoTab
from pyleem_gui.plugins.builtin import builtin as builtin_spec

from ..support import _GradientReader, plugin_context_with_viewer, viewer_with_frames

AUTOLEVEL_KEY = "builtin:autolevel"


def drag_levels(hist, lo, hi):
    """Simulate a user drag of the histogram region."""
    hist.region.moving = True
    try:
        hist.setLevels(lo, hi)
    finally:
        hist.region.moving = False


def drag_gradient(hist, tick_index, value):
    """Simulate a user dragging a gradient color stop to a new position."""
    grad = hist.gradient
    ticks = grad.listTicks()
    grad.setTickValue(ticks[tick_index][0], value)  # -> sigLookupTableChanged


def test_autolevel_toggle_adds_and_removes_process(builtin, context, bar):
    controller = builtin.controller("autolevel")
    assert context.workflow.find_process(AUTOLEVEL_KEY) is None
    assert AUTOLEVEL_KEY not in bar.labels("rendered")

    controller.toggle.setChecked(True)
    assert context.workflow.find_process(AUTOLEVEL_KEY) is not None
    assert AUTOLEVEL_KEY in bar.labels("rendered")

    controller.toggle.setChecked(False)
    assert context.workflow.find_process(AUTOLEVEL_KEY) is None
    assert AUTOLEVEL_KEY not in bar.labels("rendered")


def test_levels_drag_adds_manual_level_process(builtin, context, bar):
    """Levels drags activate manual level and update the entry."""
    messages = []
    context.status = messages.append
    hist = context.image_view.getHistogramWidget().item
    assert "builtin:manuallevel" not in bar.labels("rendered")

    drag_levels(hist, 10.0, 50.0)
    index = context.workflow.find_process("builtin:manuallevel")
    assert index is not None
    # The entry carries the levels (and the gradient, checked elsewhere).
    assert context.workflow.processes[index].params["levels"] == [10.0, 50.0]
    assert "builtin:manuallevel" in bar.labels("rendered")
    controller = builtin.controller("manuallevel")
    assert controller.toggle.isChecked() and controller.toggle.text() == "On"
    assert any("builtin:manuallevel levels=(10, 50)" in m for m in messages)

    # A brightness shift (same width, moved region) updates the entry too.
    drag_levels(hist, 20.0, 60.0)
    assert context.workflow.processes[index].params["levels"] == [20.0, 60.0]
    # A contrast change (resized region) as well.
    drag_levels(hist, 5.0, 80.0)
    assert context.workflow.processes[index].params["levels"] == [5.0, 80.0]

    controller.toggle.setChecked(False)
    assert context.workflow.find_process("builtin:manuallevel") is None


def test_manual_level_off_on_open(qtbot, tmp_path):
    """Initial rendering must not activate manual level."""
    ctx, _viewer, images = plugin_context_with_viewer(
        qtbot, tmp_path, _GradientReader, n=2
    )
    tab = AutoTab(ctx, builtin_spec)
    qtbot.addWidget(tab)
    images.set_index(1)  # another render, to be sure nothing latches on

    assert ctx.workflow.find_process("builtin:manuallevel") is None
    controller = tab.controller("manuallevel")
    assert not controller.handler.is_active()
    assert not controller.toggle.isChecked()


def test_gradient_drag_records_manual_level(builtin, context, bar):
    """Dragging the gradient color-stop arrows (the other histogram control)
    records builtin:manuallevel and its gradient state, and round-trips."""
    hist = context.image_view.getHistogramWidget().item
    assert "builtin:manuallevel" not in bar.labels("rendered")

    drag_gradient(hist, 0, 0.35)
    index = context.workflow.find_process("builtin:manuallevel")
    assert index is not None
    assert "builtin:manuallevel" in bar.labels("rendered")
    assert builtin.controller("manuallevel").toggle.isChecked()
    params = context.workflow.processes[index].params
    # The gradient state is recorded (compact, JSON-able) on the entry.
    assert params["gradient"]["ticks"][0][0] == 0.35

    # It is JSON-safe when recorded on the process entry.
    saved = json.loads(
        json.dumps([proc.to_dict() for proc in context.workflow.processes])
    )
    assert saved[0]["params"]["gradient"]["ticks"][0][0] == 0.35


def test_gradient_restored_on_workflow_import(builtin, context, tmp_path):
    """Importing a workflow restores the recorded gradient onto the editor."""
    drag_gradient(context.image_view.getHistogramWidget().item, 0, 0.4)
    wf = tmp_path / "wf.json"
    context.workflow.save_workflow(wf)

    # Wipe the gradient back to default, then import -> it is restored.
    handler = builtin.controller("manuallevel").handler
    handler._apply_gradient(handler._default_gradient)
    grad = context.image_view.getHistogramWidget().item.gradient
    assert grad.listTicks()[0][1] == 0.0

    context.workflow.import_workflow(wf)
    assert grad.listTicks()[0][1] == 0.4
    assert handler.is_active()


def test_manual_level_off_restores_default_gradient(builtin, context):
    """Turning manual level off resets the gradient to its default."""
    hist = context.image_view.getHistogramWidget().item
    drag_gradient(hist, 0, 0.5)
    assert hist.gradient.listTicks()[0][1] == 0.5
    assert context.workflow.find_process("builtin:manuallevel") is not None

    builtin.controller("manuallevel").toggle.setChecked(False)
    assert context.workflow.find_process("builtin:manuallevel") is None
    assert hist.gradient.listTicks()[0][1] == 0.0  # back to the default stop


def test_auto_and_manual_level_are_mutually_exclusive(builtin, context, bar):
    """Auto and manual level both set the display levels, so activating either
    removes the other and the leftover toggle/handler follows off."""
    auto = builtin.controller("autolevel")
    manual = builtin.controller("manuallevel")
    hist = context.image_view.getHistogramWidget().item
    wf = context.workflow

    auto.toggle.setChecked(True)
    assert [p.process_id for p in wf.processes] == ["builtin:autolevel"]

    # A manual drag replaces auto level.
    drag_levels(hist, 10.0, 50.0)
    assert [p.process_id for p in wf.processes] == ["builtin:manuallevel"]
    assert not auto.toggle.isChecked()
    assert manual.toggle.isChecked() and manual.handler.is_active()

    # Turning auto back on (via its toggle) replaces manual level.
    auto.toggle.setChecked(True)
    assert [p.process_id for p in wf.processes] == ["builtin:autolevel"]
    assert not manual.toggle.isChecked()
    assert not manual.handler.is_active()

    # Toggling manual on (not just dragging) also replaces auto level.
    manual.toggle.setChecked(True)
    assert [p.process_id for p in wf.processes] == ["builtin:manuallevel"]
    assert not auto.toggle.isChecked()


def test_level_exclusivity_leaves_roi_untouched(builtin, context):
    """The auto/manual exclusivity only swaps the two level processes; ROI (a
    separate render component) coexists with whichever is active."""
    builtin.controller("autolevel").toggle.setChecked(True)
    builtin.controller("ROI").toggle.click()
    ids = [p.process_id for p in context.workflow.processes]
    assert "builtin:autolevel" in ids and "builtin:ROI" in ids

    # Switching auto -> manual keeps ROI in place.
    drag_levels(context.image_view.getHistogramWidget().item, 10.0, 50.0)
    ids = [p.process_id for p in context.workflow.processes]
    assert ids == ["builtin:ROI", "builtin:manuallevel"]


def test_programmatic_region_move_is_not_recorded(builtin, context):
    """A plain setLevels (pyqtgraph syncing the region to a redraw) must not
    activate or record the component -- only user drags do."""
    context.image_view.getHistogramWidget().item.setLevels(10.0, 50.0)
    assert context.workflow.find_process("builtin:manuallevel") is None


def test_import_workflow_restores_manual_level(builtin, context, tmp_path):
    wf = tmp_path / "wf.json"
    wf.write_text(
        json.dumps(
            [{"process_id": "builtin:manuallevel", "params": {"levels": [12.0, 34.0]}}]
        )
    )
    context.workflow.import_workflow(wf)

    handler = builtin.controller("manuallevel").handler
    assert handler.is_active()
    lo, hi = handler.histogram.getLevels()
    assert [lo, hi] == [12.0, 34.0]

    # The restored state round-trips back through the workflow JSON.
    roundtrip = tmp_path / "roundtrip.json"
    context.workflow.save_workflow(roundtrip)
    saved = json.loads(roundtrip.read_text())
    assert saved["processes"][0]["params"] == {"levels": [12.0, 34.0]}


def test_manual_level_applies_to_view(qtbot, tmp_path):
    """Replaying the workflow entry drives the displayed levels (no handler
    interaction needed), like auto level with remembered parameters."""
    viewer, images = viewer_with_frames(qtbot, tmp_path, _GradientReader, n=2)

    item = viewer.image_view.getImageItem()
    images.workflow.add_process(Process("builtin:manuallevel", {"levels": [10, 20]}))
    assert tuple(item.levels) == (10.0, 20.0)

    # The levels apply only in the rendered view; raw and edited drop them.
    viewer._mode_buttons["raw"].click()
    assert tuple(item.levels) != (10.0, 20.0)
    viewer._mode_buttons["edited"].click()
    assert tuple(item.levels) != (10.0, 20.0)
    viewer._mode_buttons["rendered"].click()
    assert tuple(item.levels) == (10.0, 20.0)

    images.workflow.delete_process(0)  # removing it reverts to auto levels
    lo, hi = item.levels
    assert lo <= 1 and hi >= 98


def test_levels_record_only_in_rendered_view(builtin, context):
    """The adjustment lives in the rendered view: a drag in raw or edited (where
    the levels do not apply) is not recorded; a drag in rendered is."""
    hist = context.image_view.getHistogramWidget().item

    context.view.set_mode("edited")
    drag_levels(hist, 10.0, 50.0)
    assert context.workflow.find_process("builtin:manuallevel") is None

    context.view.set_mode("rendered")
    drag_levels(hist, 10.0, 60.0)
    assert context.workflow.find_process("builtin:manuallevel") is not None


def test_manual_level_off_resets_histogram_region(qtbot, tmp_path):
    """Turning manual level off resets the adjustment: the display reverts to
    auto levels and the histogram region (the control) snaps to match."""
    ctx, viewer, _images = plugin_context_with_viewer(
        qtbot, tmp_path, _GradientReader, n=2
    )
    tab = AutoTab(ctx, builtin_spec)
    qtbot.addWidget(tab)

    hist = viewer.image_view.getHistogramWidget().item
    item = viewer.image_view.getImageItem()
    drag_levels(hist, 30.0, 40.0)  # records and applies
    assert ctx.workflow.find_process("builtin:manuallevel") is not None
    assert tuple(item.levels) == (30.0, 40.0)

    tab.controller("manuallevel").toggle.setChecked(False)
    assert ctx.workflow.find_process("builtin:manuallevel") is None
    lo, hi = item.levels
    assert lo <= 1 and hi >= 98  # the display reverts to auto levels
    assert tuple(hist.getLevels()) == (lo, hi)  # the control follows the display
    # The region following the redraw is not a drag: the component stays off.
    assert ctx.workflow.find_process("builtin:manuallevel") is None
    assert not tab.controller("manuallevel").toggle.isChecked()


def test_leaving_rendered_resets_display_but_keeps_manual_level(qtbot, tmp_path):
    """Leaving rendered mode resets display but keeps manual level."""
    ctx, viewer, _images = plugin_context_with_viewer(
        qtbot, tmp_path, _GradientReader, n=2
    )
    tab = AutoTab(ctx, builtin_spec)
    qtbot.addWidget(tab)

    hist = viewer.image_view.getHistogramWidget().item
    item = viewer.image_view.getImageItem()
    controller = tab.controller("manuallevel")

    # Adjust the levels and the gradient in the rendered view.
    drag_levels(hist, 30.0, 40.0)
    drag_gradient(hist, 0, 0.4)
    assert ctx.workflow.find_process("builtin:manuallevel") is not None
    assert tuple(item.levels) == (30.0, 40.0)
    assert hist.gradient.listTicks()[0][1] == 0.4

    # Switching to edited resets the DISPLAY but keeps the toggle/process on.
    viewer._mode_buttons["edited"].click()
    assert ctx.workflow.find_process("builtin:manuallevel") is not None
    assert controller.handler.is_active()
    assert controller.toggle.isChecked()
    assert hist.gradient.listTicks()[0][1] == 0.0  # gradient display reset
    lo, hi = item.levels
    assert lo <= 1 and hi >= 98  # levels reverted to auto

    # Returning to rendered restores the recorded adjustment.
    viewer._mode_buttons["rendered"].click()
    assert hist.gradient.listTicks()[0][1] == 0.4
    assert tuple(item.levels) == (30.0, 40.0)
    assert ctx.workflow.find_process("builtin:manuallevel") is not None

    # Only clicking the toggle off clears it.
    controller.toggle.setChecked(False)
    assert ctx.workflow.find_process("builtin:manuallevel") is None
    assert hist.gradient.listTicks()[0][1] == 0.0
