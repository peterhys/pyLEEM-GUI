"""ROI geometry editor widgets for the Builtin plugin."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..roi import circle_center_radius, line_points_width, line_roi_endpoints_xy

SHAPES = ["Rectangle", "Ellipse", "Circle", "Polygon", "Line"]


# geometry editors
class ShapeEditor(QWidget):
    """Geometry controls for one ROI shape."""

    edited = Signal()
    shape = ""

    def read_roi(self, roi, item):
        """The live ROI's geometry as this shape's param dict (no ``shape`` key)."""
        raise NotImplementedError

    def write_roi(self, roi, item, params, finish=True):
        """Push ``params`` (new or old schema) onto the live ROI."""
        raise NotImplementedError

    def read_controls(self):
        """The current control values as this shape's param dict."""
        raise NotImplementedError

    def set_controls(self, params):
        """Populate the controls from ``params`` without firing ``edited``."""
        raise NotImplementedError


class TableEditor(ShapeEditor):
    """A shape editor backed by one value table row per field."""

    def build(self, fields):
        """Build one table row per field."""
        self.table = QTableWidget(len(fields), 2)
        self.table.setHorizontalHeaderLabels(["Field", "Value"])
        self.table.verticalHeader().setVisible(False)
        for row, field in enumerate(fields):
            name = QTableWidgetItem(field[0])
            name.setFlags(name.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 0, name)
            self.table.setItem(row, 1, QTableWidgetItem(f"{float(field[1]):g}"))
        self.table.cellChanged.connect(self._on_cell_changed)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.table)

    def _on_cell_changed(self, _row, col):
        if col == 1:
            self.edited.emit()

    def values(self):
        out = []
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 1)
            try:
                out.append(float(item.text()) if item is not None else 0.0)
            except ValueError:
                out.append(0.0)
        return out

    def value(self, row):
        """The value in one row (by field index)."""
        return self.values()[row]

    def set_values(self, values):
        self.table.blockSignals(True)
        for row, value in enumerate(values):
            self.table.setItem(row, 1, QTableWidgetItem(f"{float(value):g}"))
        self.table.blockSignals(False)

    def set_value(self, row, value):
        """Set one value cell, firing `edited` like a user table edit."""
        self.table.setItem(row, 1, QTableWidgetItem(f"{float(value):g}"))


class RectangleEditor(TableEditor):
    shape = "Rectangle"

    def __init__(self):
        super().__init__()
        self.build([("x", 0.0), ("y", 0.0), ("width", 1.0), ("height", 1.0)])

    def read_controls(self):
        x, y, w, h = self.values()
        return {"pos": [x, y], "size": [w, h]}

    def set_controls(self, params):
        pos = params.get("pos", [0.0, 0.0])
        size = params.get("size", [1.0, 1.0])
        self.set_values([pos[0], pos[1], size[0], size[1]])

    def read_roi(self, roi, item):
        pos, size = roi.pos(), roi.size()
        return {
            "pos": [round(float(pos.x()), 1), round(float(pos.y()), 1)],
            "size": [round(float(size.x()), 1), round(float(size.y()), 1)],
        }

    def write_roi(self, roi, item, params, finish=True):
        pos, size = params.get("pos"), params.get("size")
        if pos is not None:
            roi.setPos(pos, update=False)
        if size is not None:
            roi.setSize(size, update=False)
        roi.stateChanged(finish=finish)


class EllipseEditor(TableEditor):
    shape = "Ellipse"

    def __init__(self):
        super().__init__()
        self.build(
            [
                ("x", 0.0),
                ("y", 0.0),
                ("width", 1.0),
                ("height", 1.0),
                ("angle", 0.0, -360.0),
            ]
        )

    def read_controls(self):
        x, y, w, h, angle = self.values()
        return {"pos": [x, y], "size": [w, h], "angle": angle}

    def set_controls(self, params):
        pos = params.get("pos", [0.0, 0.0])
        size = params.get("size", [1.0, 1.0])
        angle = params.get("angle", 0.0)
        self.set_values([pos[0], pos[1], size[0], size[1], angle])

    def read_roi(self, roi, item):
        pos, size = roi.pos(), roi.size()
        return {
            "pos": [round(float(pos.x()), 1), round(float(pos.y()), 1)],
            "size": [round(float(size.x()), 1), round(float(size.y()), 1)],
            "angle": round(float(roi.angle()), 1),
        }

    def write_roi(self, roi, item, params, finish=True):
        pos, size, angle = params.get("pos"), params.get("size"), params.get("angle")
        if pos is not None:
            roi.setPos(pos, update=False)
        if size is not None:
            roi.setSize(size, update=False)
        if angle is not None:
            roi.setAngle(float(angle), update=False)
        roi.stateChanged(finish=finish)


class CircleEditor(TableEditor):
    shape = "Circle"

    def __init__(self):
        super().__init__()
        self.build([("center_x", 0.0), ("center_y", 0.0), ("radius", 1.0, 0.0)])

    def read_controls(self):
        cx, cy, radius = self.values()
        return {"center": [cx, cy], "radius": radius}

    def set_controls(self, params):
        center, radius = circle_center_radius(params)
        if center is not None:
            self.set_values([center[0], center[1], radius])

    def read_roi(self, roi, item):
        pos, size = roi.pos(), roi.size()
        radius = float(size.x()) / 2
        return {
            "center": [
                round(float(pos.x()) + radius, 1),
                round(float(pos.y()) + radius, 1),
            ],
            "radius": round(radius, 1),
        }

    def write_roi(self, roi, item, params, finish=True):
        center, radius = circle_center_radius(params)
        if center is None or radius is None:
            return
        roi.setSize([2 * radius, 2 * radius], update=False)
        roi.setPos([center[0] - radius, center[1] - radius], update=False)
        roi.stateChanged(finish=finish)


class LineEditor(TableEditor):
    shape = "Line"

    def __init__(self):
        super().__init__()
        self.build(
            [("x1", 0.0), ("y1", 0.0), ("x2", 1.0), ("y2", 1.0), ("width", 1.0, 0.0)]
        )

    def read_controls(self):
        x1, y1, x2, y2, width = self.values()
        return {"points": [[x1, y1], [x2, y2]], "width": width}

    def set_controls(self, params):
        points, width = line_points_width(params)
        (x1, y1), (x2, y2) = points
        self.set_values([x1, y1, x2, y2, width])

    def read_roi(self, roi, item):
        (x1, y1), (x2, y2) = line_roi_endpoints_xy(roi, item)
        return {
            "points": [[x1, y1], [x2, y2]],
            "width": round(float(roi.size().y()), 1),
        }

    def write_roi(self, roi, item, params, finish=True):
        # Endpoints need a fresh LineROI (the handler swaps); only the width can
        # be set in place on the current LineROI.
        width = line_points_width(params)[1]
        roi.setSize([roi.size().x(), float(width)], update=False)
        roi.stateChanged(finish=finish)


class PolygonEditor(ShapeEditor):
    shape = "Polygon"
    MIN_POINTS = 3

    def __init__(self):
        super().__init__()
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["X", "Y"])
        self.table.cellChanged.connect(self._on_cell_changed)
        col.addWidget(self.table)
        buttons = QHBoxLayout()
        self.add_button = QPushButton("Add Vertex")
        self.add_button.clicked.connect(self._add_vertex)
        self.remove_button = QPushButton("Remove Vertex")
        self.remove_button.clicked.connect(self._remove_vertex)
        buttons.addWidget(self.add_button)
        buttons.addWidget(self.remove_button)
        col.addLayout(buttons)

    def _on_cell_changed(self, *_args):
        self.edited.emit()

    def _add_vertex(self):
        points = self.points()
        last = points[-1] if points else [0.0, 0.0]
        points.append([last[0] + 10.0, last[1] + 10.0])
        self._fill(points)
        self.edited.emit()

    def _remove_vertex(self):
        points = self.points()
        if len(points) <= self.MIN_POINTS:
            return  # a closed polygon needs at least three vertices
        row = self.table.currentRow()
        index = row if 0 <= row < len(points) else len(points) - 1
        del points[index]
        self._fill(points)
        self.edited.emit()

    def points(self):
        points = []
        for r in range(self.table.rowCount()):
            x_item, y_item = self.table.item(r, 0), self.table.item(r, 1)
            if x_item is None or y_item is None:
                continue
            try:
                points.append([float(x_item.text()), float(y_item.text())])
            except ValueError:
                continue
        return points

    def _fill(self, points):
        self.table.blockSignals(True)
        self.table.setRowCount(len(points))
        for r, (x, y) in enumerate(points):
            self.table.setItem(r, 0, QTableWidgetItem(f"{x:g}"))
            self.table.setItem(r, 1, QTableWidgetItem(f"{y:g}"))
        self.table.blockSignals(False)

    def read_controls(self):
        return {"points": self.points(), "closed": True}

    def set_controls(self, params):
        points = params.get("points")
        if not points:
            return  # old pos-only entry: keep live vertices
        self._fill([[float(x), float(y)] for x, y in points])

    def read_roi(self, roi, item):
        state = roi.getState()
        pos = roi.pos()
        points = [
            [
                round(float(p.x()) + float(pos.x()), 1),
                round(float(p.y()) + float(pos.y()), 1),
            ]
            for p in state["points"]
        ]
        # Closed is always true to avoid workflow churn on import.
        return {"points": points, "closed": True}

    def write_roi(self, roi, item, params, finish=True):
        points = params.get("points")
        if not points or len(points) < self.MIN_POINTS:
            return  # old pos-only entry: handler restores position only
        roi.blockSignals(True)
        roi.setPos([0.0, 0.0])  # re-anchor so the points are absolute image coords
        roi.setPoints([[float(x), float(y)] for x, y in points], closed=True)
        roi.blockSignals(False)
        roi.stateChanged(finish=finish)
