import json

import numpy as np
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyqtgraph")

import pyqtgraph as pg


def _active_roi(builtin, context, shape):
    """An active ROI of ``shape`` over a blank image; returns (handler, editor)."""
    context.image_view.setImage(np.zeros((200, 200)))
    controller = builtin.controller("ROI")
    controller.toggle.setChecked(True)
    handler = controller.handler
    handler.shape.setCurrentText(shape)
    return handler, handler.editors[shape]


def test_shape_panel_shows_the_editor_for_the_selected_shape(builtin):
    """The geometry panel shows each shape's own editor; the Line editor has a
    width control, the Polygon editor a vertex table."""
    from pyleem_gui.plugins.builtin_roi_editors import (
        LineEditor,
        PolygonEditor,
        RectangleEditor,
    )

    handler = builtin.controller("ROI").handler
    rows = {"Rectangle": 4, "Ellipse": 5, "Circle": 3, "Line": 5}
    for shape, n in rows.items():
        editor = handler.editors[shape]
        assert editor.table.columnCount() == 2  # field name + value
        assert editor.table.rowCount() == n
    assert handler.editors["Polygon"].table.columnCount() == 2

    handler.shape.setCurrentText("Rectangle")
    assert isinstance(handler.panel.currentWidget(), RectangleEditor)
    handler.shape.setCurrentText("Line")
    line = handler.panel.currentWidget()
    assert isinstance(line, LineEditor)
    assert line.table.rowCount() == 5  # x1, y1, x2, y2, width
    handler.shape.setCurrentText("Polygon")
    assert isinstance(handler.panel.currentWidget(), PolygonEditor)


def test_line_roi_records_width_in_process_params(builtin, context):
    handler = builtin.controller("ROI").handler
    context.image_view.setImage(np.zeros((120, 120)))
    handler.shape.setCurrentText("Line")
    handler.editors["Line"].set_value(4, 7)  # editing the width cell recreates the line
    params = handler.process_params()
    assert params["shape"] == "Line" and params["width"] == 7
    # A non-line shape carries no width key.
    handler.shape.setCurrentText("Rectangle")
    assert "width" not in handler.process_params()


def test_workflow_import_restores_line_width(builtin, context, tmp_path):
    wf = tmp_path / "wf.json"
    wf.write_text(
        json.dumps(
            [
                {
                    "process_id": "builtin:ROI",
                    "params": {
                        "shape": "Line",
                        "pos": [5.0, 5.0],
                        "size": [10.0, 10.0],
                        "width": 4,
                    },
                }
            ]
        )
    )
    context.workflow.import_workflow(wf)
    handler = builtin.controller("ROI").handler
    assert handler.is_active()
    assert handler.line_width == 4 and handler.editors["Line"].value(4) == 4


def test_workflow_import_without_width_defaults_to_one(builtin, context, tmp_path):
    """An old ROI entry (predating the width param) loads with width 1."""
    wf = tmp_path / "wf.json"
    wf.write_text(
        json.dumps(
            [
                {
                    "process_id": "builtin:ROI",
                    "params": {
                        "shape": "Line",
                        "pos": [5.0, 5.0],
                        "size": [10.0, 10.0],
                    },
                }
            ]
        )
    )
    context.workflow.import_workflow(wf)
    handler = builtin.controller("ROI").handler
    assert handler.is_active()
    assert handler.line_width == 1


def test_rectangle_editor_moves_the_roi(builtin, context):
    handler, editor = _active_roi(builtin, context, "Rectangle")
    editor.table.item(0, 1).setText("42")  # a user edits the x value cell
    assert context.image_view.roi.pos().x() == 42.0
    for row, value in enumerate([20.0, 30.0, 40.0, 50.0]):
        editor.set_value(row, value)
    roi = context.image_view.roi
    assert [roi.pos().x(), roi.pos().y()] == [20.0, 30.0]
    assert [roi.size().x(), roi.size().y()] == [40.0, 50.0]
    assert handler.process_params() == {
        "shape": "Rectangle",
        "pos": [20.0, 30.0],
        "size": [40.0, 50.0],
    }


def test_circle_editor_sets_center_and_radius(builtin, context):
    handler, editor = _active_roi(builtin, context, "Circle")
    for row, value in enumerate([100.0, 80.0, 25.0]):
        editor.set_value(row, value)
    roi = context.image_view.roi
    assert roi.size().x() == 50.0 and roi.size().y() == 50.0  # diameter
    assert [roi.pos().x(), roi.pos().y()] == [75.0, 55.0]  # center - radius
    assert handler.process_params() == {
        "shape": "Circle",
        "center": [100.0, 80.0],
        "radius": 25.0,
    }


def test_ellipse_editor_sets_angle(builtin, context):
    handler, editor = _active_roi(builtin, context, "Ellipse")
    editor.set_value(4, 30.0)  # the angle field (row 4), in degrees
    assert round(context.image_view.roi.angle(), 1) == 30.0
    assert handler.process_params()["angle"] == 30.0


def test_line_editor_sets_endpoints_and_width(builtin, context):
    handler, editor = _active_roi(builtin, context, "Line")
    for row, value in enumerate([20.0, 20.0, 120.0, 60.0, 8.0]):
        editor.set_value(row, value)
    params = handler.process_params()
    assert params["shape"] == "Line"
    assert params["points"] == [[20.0, 20.0], [120.0, 60.0]]
    assert params["width"] == 8.0


def test_direct_roi_change_updates_controls_and_workflow(builtin, context):
    handler, editor = _active_roi(builtin, context, "Rectangle")
    roi = context.image_view.roi
    roi.setPos([15.0, 25.0])
    roi.setSize([35.0, 45.0])
    # A direct drag/resize syncs the controls...
    assert editor.values() == [15.0, 25.0, 35.0, 45.0]
    # ...and records the geometry on the process entry.
    index = context.workflow.find_process("builtin:ROI")
    assert context.workflow.processes[index].params == {
        "shape": "Rectangle",
        "pos": [15.0, 25.0],
        "size": [35.0, 45.0],
    }


def test_line_width_syncs_from_a_roi_resize(builtin, context):
    handler, editor = _active_roi(builtin, context, "Line")
    roi = context.image_view.roi
    roi.setSize([roi.size().x(), 12.0])  # widen the line through the ROI
    assert editor.value(4) == 12.0
    assert handler.process_params()["width"] == 12.0
    index = context.workflow.find_process("builtin:ROI")
    assert context.workflow.processes[index].params["width"] == 12.0


def test_polygon_editor_adds_removes_and_edits_vertices(builtin, context):
    handler, editor = _active_roi(builtin, context, "Polygon")
    roi = context.image_view.roi
    assert editor.table.rowCount() == 3  # the default polygon

    editor._add_vertex()
    assert editor.table.rowCount() == 4
    assert len(roi.getState()["points"]) == 4  # the live ROI grew a vertex

    editor._remove_vertex()
    assert editor.table.rowCount() == 3
    editor._remove_vertex()  # a closed polygon keeps a minimum of three
    assert editor.table.rowCount() == 3

    editor.table.item(0, 0).setText("150")  # editing a cell moves the vertex
    assert handler.process_params()["points"][0][0] == 150.0


def test_workflow_import_new_circle_schema(builtin, context, tmp_path):
    wf = tmp_path / "wf.json"
    wf.write_text(
        json.dumps(
            [
                {
                    "process_id": "builtin:ROI",
                    "params": {
                        "shape": "Circle",
                        "center": [100.0, 80.0],
                        "radius": 25.0,
                    },
                }
            ]
        )
    )
    context.workflow.import_workflow(wf)
    handler = builtin.controller("ROI").handler
    roi = context.image_view.roi
    assert isinstance(roi, pg.CircleROI)
    assert roi.size().x() == 50.0 and [roi.pos().x(), roi.pos().y()] == [75.0, 55.0]
    assert handler.process_params() == {
        "shape": "Circle",
        "center": [100.0, 80.0],
        "radius": 25.0,
    }


def test_workflow_import_old_circle_pos_size_converts_to_center_radius(
    builtin, context, tmp_path
):
    wf = tmp_path / "wf.json"
    wf.write_text(
        json.dumps(
            [
                {
                    "process_id": "builtin:ROI",
                    "params": {
                        "shape": "Circle",
                        "pos": [10.0, 20.0],
                        "size": [40.0, 40.0],
                    },
                }
            ]
        )
    )
    context.workflow.import_workflow(wf)
    handler = builtin.controller("ROI").handler
    roi = context.image_view.roi
    # old pos/size restores the same geometry, re-recorded as center/radius.
    assert [roi.pos().x(), roi.pos().y()] == [10.0, 20.0]
    expected = {"shape": "Circle", "center": [30.0, 40.0], "radius": 20.0}
    assert handler.process_params() == expected
    # The PERSISTED entry must carry only the new schema -- no stale pos/size
    # keys left behind by a merge (update_process replaces, so the saved
    # workflow file stays clean).
    index = context.workflow.find_process("builtin:ROI")
    assert context.workflow.processes[index].params == expected
