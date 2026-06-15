"""Qt-free ROI geometry, params, and ImageJ conversion helpers."""

import numpy as np


# array-axis and pyqtgraph ROI geometry
def array_axes(item):
    """The ``(x, y)`` array-axis pair for pyqtgraph ROI sampling."""
    return (1, 0) if item.axisOrder == "row-major" else (0, 1)


def sample_roi(arr, roi, item):
    """Pixels under ``roi``, or None for an unusable region."""
    axes = array_axes(item)
    try:
        region = roi.getArrayRegion(np.asarray(arr), img=item, axes=axes)
    except (IndexError, ValueError, TypeError):
        return None
    if region is None or region.size == 0:
        return None
    return region


def line_roi_handle_points(roi, item):
    """The Line ROI endpoint handles in image-item local coordinates."""
    return tuple(item.mapFromScene(roi.getSceneHandlePositions(i)[1]) for i in (0, 1))


def line_roi_endpoints_yx(roi, item):
    """The Line ROI endpoints as ``(row, col)`` image-array coordinates."""
    row_major = item.axisOrder == "row-major"
    ends = []
    for local in line_roi_handle_points(roi, item):
        data = item.mapToData(local)
        x, y = float(data.x()), float(data.y())
        ends.append((x, y) if row_major else (y, x))
    return ends[0], ends[1]


def line_roi_endpoints_xy(roi, item):
    """The Line ROI endpoints as display ``(x, y)`` coordinates."""
    return tuple(
        (round(float(p.x()), 1), round(float(p.y()), 1))
        for p in line_roi_handle_points(roi, item)
    )


def line_roi_width(roi):
    """A Line ROI's profile width in whole pixels (at least 1)."""
    return max(1, int(round(float(roi.size().y()))))


def line_roi_profile(image, roi, item):
    """Intensity profile along a Line ROI, or None if unusable."""
    from pyleem.roi import LineROI  # lazy: keep this module import-light/Qt-free

    try:
        src, dst = line_roi_endpoints_yx(roi, item)
        profile = LineROI(src=src, dst=dst, linewidth=line_roi_width(roi)).read_profile(
            np.asarray(image)
        )
    except (IndexError, ValueError, TypeError):
        return None
    profile = np.asarray(profile, dtype=float).ravel()
    profile = profile[np.isfinite(profile)]
    if profile.size == 0:
        return None
    return profile


# ROI workflow-param normalization
# Accept current params and older pos/size workflows.
def circle_center_radius(params):
    """Center and radius from current or old Circle params."""
    if params.get("center") is not None and params.get("radius") is not None:
        return list(params["center"]), float(params["radius"])
    pos, size = params.get("pos"), params.get("size")
    if pos is not None and size is not None:
        radius = float(size[0]) / 2
        return [pos[0] + radius, pos[1] + radius], radius
    return None, None


def line_points_width(params):
    """Endpoints and width from current or old Line params."""
    width = params.get("width")
    width = float(width) if width is not None else 1.0
    points = params.get("points")
    if points is not None and len(points) >= 2:
        return [list(points[0]), list(points[1])], width
    return [[10.0, 10.0], [100.0, 100.0]], width


# live ROI -> ImageJ ROI
def roi_to_imagej(roi, shape, item, line_width):
    """An ImageJ ROI object for the active ROI shape, or None."""
    if shape == "Line":
        from pyleem.roi import LineROI

        (x1, y1), (x2, y2) = line_roi_endpoints_xy(roi, item)
        return LineROI(
            src=(y1, x1), dst=(y2, x2), linewidth=int(round(line_width))
        ).to_roi_object()
    if shape in ("Circle", "Ellipse", "Rectangle"):
        from roifile import ROI_TYPE, ImagejRoi

        pos, size = roi.pos(), roi.size()
        left, top = float(pos.x()), float(pos.y())
        roitype = ROI_TYPE.OVAL if shape != "Rectangle" else ROI_TYPE.RECT
        return ImagejRoi(
            roitype=roitype,
            left=int(round(left)),
            top=int(round(top)),
            right=int(round(left + float(size.x()))),
            bottom=int(round(top + float(size.y()))),
        )
    return None  # Polygon
