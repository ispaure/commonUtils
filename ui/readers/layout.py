"""Toolkit-independent reader chrome metrics and safe-edge calculations.

All coordinates use the caller's logical units. Platform adapters supply live
window geometry; no device names, screen sizes or guessed corner radii belong
here. Media canvases may bleed beyond the region reserved for controls.
"""
from dataclasses import dataclass
from math import sqrt


@dataclass(frozen=True)
class ReaderLayout:
    touch_extent: int = 48
    progress_margin: int = 4
    track_extent: int = 4
    thumb_extent: int = 16
    spacing: int = 4
    desktop_margins: tuple = (8, 2, 8, 3)
    overlay_margin: int = 12
    caption_size: float = 12.75


READER_LAYOUT = ReaderLayout()


def remaining_clearance(edge, safe_edge, *, trailing=True):
    """Reserve only the part of a safe inset not already consumed by a host."""
    return max(0, edge - safe_edge if trailing else safe_edge - edge)


def rounded_clearance(start, stop, corners, *, vertical=False):
    """Return leading/trailing padding for a row crossing rounded corners.

    ``corners`` contains (trailing_axis, trailing_cross_axis, cx, cy, radius),
    relative to the row's host. For horizontal rows start/stop are y coordinates;
    for vertical strips they are x coordinates. Returned values are absolute
    safe edge coordinates; hosts subtract their already applied safe insets.
    Only the cross-axis portion beyond a corner's center can clip the row.
    """
    leading, trailing = None, None
    for far_axis, far_cross, cx, cy, radius in corners:
        if radius <= 0:
            continue
        center, cross = (cy, cx) if vertical else (cx, cy)
        distance = max(0, stop - cross if far_cross else cross - start)
        distance = min(radius, distance)
        reach = sqrt(max(0, radius * radius - distance * distance))
        edge = center - reach if not far_axis else center + reach
        if far_axis:
            trailing = edge if trailing is None else min(trailing, edge)
        else:
            leading = edge if leading is None else max(leading, edge)
    return leading, trailing


def overlay_insets(width, height, safe, corners=(), *, margin=READER_LAYOUT.overlay_margin, extent=READER_LAYOUT.touch_extent):
    """Insets for bottom overlay controls, preserving canvas size and hit areas."""
    left, top, right, bottom = safe
    leading, trailing = rounded_clearance(max(top, height - bottom - extent), height - bottom, corners)
    return (max(left, leading or 0) + margin, top + margin,
            max(right, width - trailing if trailing is not None else 0) + margin, bottom)
