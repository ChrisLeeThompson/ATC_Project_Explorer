"""
Ruler

The Image Viewer's measuring tool: a line between two points placed on
the image, labeled with its physical length.

The model keeps its endpoints in image pixels, so the line follows the
view's zoom and pan while the label stays the same.  Hit-testing and
drawing go through a ``ViewTransform`` that maps image pixels to widget
pixels for the current display rect.  The painter mirrors the scale
bar's look: the line and handles in the ruler color over a thin dark
edge, and the label on a translucent plate, all at full opacity.
"""
import math
from dataclasses import dataclass
from enum import Enum

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen

from script_modules.app_styles import AppStyles
from script_modules.widgets.scale_bar import format_length_um

# Significant figures shown on the label.
_LABEL_FIGURES = 3


class RulerState(Enum):
    """Where a ruler is in its placement."""

    EMPTY = "empty"
    PLACING = "placing"
    COMPLETE = "complete"


class RulerHit(Enum):
    """The part of a complete ruler under the cursor."""

    START = "start"
    END = "end"
    LABEL = "label"


@dataclass(frozen=True)
class ViewTransform:
    """Map between image pixels and widget pixels.

    :param origin: Widget position of the image's top-left corner.
    :param scale: Widget pixels per image pixel (uniform).
    """

    origin: QPointF
    scale: float

    def to_widget(self, point: QPointF) -> QPointF:
        """Image pixels to widget pixels."""
        return QPointF(
            self.origin.x() + point.x() * self.scale,
            self.origin.y() + point.y() * self.scale,
        )

    def to_image(self, point: QPointF) -> QPointF:
        """Widget pixels to image pixels."""
        return QPointF(
            (point.x() - self.origin.x()) / self.scale,
            (point.y() - self.origin.y()) / self.scale,
        )


def snap_to_axis(fixed: QPointF, moving: QPointF) -> QPointF:
    """Snap *moving* onto the horizontal or vertical line through
    *fixed*, whichever is closer to it."""
    dx = moving.x() - fixed.x()
    dy = moving.y() - fixed.y()
    if abs(dx) >= abs(dy):
        return QPointF(moving.x(), fixed.y())
    return QPointF(fixed.x(), moving.y())


def _distance(a: QPointF, b: QPointF) -> float:
    return math.hypot(a.x() - b.x(), a.y() - b.y())


class Ruler:
    """One ruler: its endpoints in image pixels, its placement state,
    and the bookkeeping for a drag of an endpoint or of the whole line.
    """

    def __init__(self):
        self.start: QPointF | None = None
        self.end: QPointF | None = None
        # Cursor position while the second point is being placed; None
        # hides the preview line (the cursor has left the canvas).
        self.preview: QPointF | None = None
        self._drag_hit: RulerHit | None = None
        self._drag_anchor: QPointF | None = None
        self._drag_start: QPointF | None = None
        self._drag_end: QPointF | None = None

    # -- Placement ----------------------------------------------------

    @property
    def state(self) -> RulerState:
        """Empty, placing (one endpoint), or complete (both)."""
        if self.start is None:
            return RulerState.EMPTY
        if self.end is None:
            return RulerState.PLACING
        return RulerState.COMPLETE

    def place_first(self, point: QPointF) -> None:
        """Set the first endpoint and start the preview there."""
        self.start = QPointF(point)
        self.end = None
        self.preview = QPointF(point)

    def set_preview(
        self, point: QPointF | None, axis_lock: bool = False,
    ) -> None:
        """Move the preview line's free end, or hide it with *None*."""
        if self.state is not RulerState.PLACING:
            return
        self.preview = self._second_point(point, axis_lock)

    def place_second(self, point: QPointF, axis_lock: bool = False) -> None:
        """Set the second endpoint, completing the ruler."""
        if self.state is not RulerState.PLACING:
            return
        self.end = self._second_point(point, axis_lock)
        self.preview = None

    def _second_point(
        self, point: QPointF | None, axis_lock: bool,
    ) -> QPointF | None:
        if point is None:
            return None
        if axis_lock:
            return snap_to_axis(self.start, point)
        return QPointF(point)

    # -- Geometry -----------------------------------------------------

    def line(self) -> tuple[QPointF, QPointF] | None:
        """The drawn segment: start to end, or start to the preview."""
        if self.start is None:
            return None
        other = self.end if self.end is not None else self.preview
        if other is None:
            return None
        return self.start, other

    def length_px(self) -> float | None:
        """Length of :meth:`line` in image pixels."""
        line = self.line()
        if line is None:
            return None
        return _distance(*line)

    def label(self, pixel_size_m: float) -> str | None:
        """The physical length of :meth:`line`, formatted for display.

        :param pixel_size_m: Width of one image pixel in metres.
        """
        length_px = self.length_px()
        if length_px is None:
            return None
        return format_length_um(
            length_px * pixel_size_m * 1e6, significant=_LABEL_FIGURES,
        )

    # -- Hit-testing and dragging -------------------------------------

    def hit_test(
        self,
        widget_point: QPointF,
        transform: ViewTransform,
        label_rect: QRectF | None,
        radius: float,
    ) -> RulerHit | None:
        """The part of a complete ruler at *widget_point*.

        The nearer endpoint wins within *radius* widget pixels; the
        label counts when the point falls inside *label_rect* (as
        returned by :func:`draw_ruler`).
        """
        if self.state is not RulerState.COMPLETE:
            return None
        candidates = (
            (_distance(widget_point, transform.to_widget(self.start)),
             RulerHit.START),
            (_distance(widget_point, transform.to_widget(self.end)),
             RulerHit.END),
        )
        distance, hit = min(candidates, key=lambda item: item[0])
        if distance <= radius:
            return hit
        if label_rect is not None and label_rect.contains(widget_point):
            return RulerHit.LABEL
        return None

    @property
    def dragging(self) -> bool:
        """Whether a drag started by :meth:`begin_drag` is in progress."""
        return self._drag_hit is not None

    def begin_drag(self, hit: RulerHit, image_point: QPointF) -> None:
        """Start dragging *hit* from the press position *image_point*."""
        if self.state is not RulerState.COMPLETE:
            return
        self._drag_hit = hit
        self._drag_anchor = QPointF(image_point)
        self._drag_start = QPointF(self.start)
        self._drag_end = QPointF(self.end)

    def drag_to(self, image_point: QPointF, axis_lock: bool = False) -> None:
        """Move the dragged part to *image_point*.

        An endpoint follows the point (snapped to an axis through the
        other endpoint when *axis_lock* is set); the label moves the
        whole ruler by the offset from the press position, ignoring
        the lock.
        """
        if self._drag_hit is None:
            return
        if self._drag_hit is RulerHit.LABEL:
            dx = image_point.x() - self._drag_anchor.x()
            dy = image_point.y() - self._drag_anchor.y()
            self.start = QPointF(
                self._drag_start.x() + dx, self._drag_start.y() + dy,
            )
            self.end = QPointF(
                self._drag_end.x() + dx, self._drag_end.y() + dy,
            )
            return
        fixed = self.end if self._drag_hit is RulerHit.START else self.start
        moved = (
            snap_to_axis(fixed, image_point) if axis_lock
            else QPointF(image_point)
        )
        if self._drag_hit is RulerHit.START:
            self.start = moved
        else:
            self.end = moved

    def end_drag(self) -> None:
        """Finish the drag; the endpoints keep their dragged positions."""
        self._drag_hit = None
        self._drag_anchor = None
        self._drag_start = None
        self._drag_end = None


# ---------------------------------------------------------------------
# Painting
# ---------------------------------------------------------------------

def draw_ruler(
    painter: QPainter,
    ruler: Ruler,
    transform: ViewTransform,
    pixel_size_m: float,
) -> QRectF | None:
    """Draw *ruler* on a canvas.

    Drawn at full opacity whatever the painter's current opacity, and
    the painter's state is restored afterwards.  While the ruler is
    being placed the line runs to the preview point and only the first
    endpoint has a handle.

    :param painter: Active QPainter on the canvas widget.
    :param ruler: The ruler to draw.
    :param transform: Image-to-widget mapping for the current view.
    :param pixel_size_m: Width of one image pixel in metres.
    :return: The label plate in widget coordinates, for hit-testing, or
        *None* when no label was drawn.
    """
    if ruler.start is None:
        return None

    colors = AppStyles.Colors
    dims = AppStyles.Dimensions
    ruler_color = QColor(colors.RULER_COLOR)
    edge_color = QColor(colors.RULER_EDGE_COLOR)

    painter.save()
    painter.setOpacity(1.0)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    label_rect: QRectF | None = None
    line = ruler.line()
    if line is not None:
        a = transform.to_widget(line[0])
        b = transform.to_widget(line[1])
        for color, width in (
            (edge_color, dims.RULER_EDGE_WIDTH),
            (ruler_color, dims.RULER_LINE_WIDTH),
        ):
            pen = QPen(color, width)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.drawLine(a, b)

    _draw_handle(painter, transform.to_widget(ruler.start), ruler_color, edge_color)
    if ruler.state is RulerState.COMPLETE:
        _draw_handle(painter, transform.to_widget(ruler.end), ruler_color, edge_color)

    if line is not None:
        label_rect = _draw_label(
            painter, ruler.label(pixel_size_m), a, b, ruler_color,
        )

    painter.restore()
    return label_rect


def _draw_handle(
    painter: QPainter, center: QPointF, color: QColor, edge: QColor,
) -> None:
    """A filled circle in the ruler color with a 1 px dark edge."""
    radius = AppStyles.Dimensions.RULER_HANDLE_RADIUS
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(edge)
    painter.drawEllipse(center, radius + 1, radius + 1)
    painter.setBrush(color)
    painter.drawEllipse(center, radius, radius)


def _draw_label(
    painter: QPainter,
    text: str,
    a: QPointF,
    b: QPointF,
    border: QColor,
) -> QRectF:
    """The length label on a translucent plate centered between *a* and
    *b*; returns the plate rect."""
    colors = AppStyles.Colors
    dims = AppStyles.Dimensions

    font = painter.font()
    font.setPointSize(dims.SCALE_BAR_LABEL_FONT_SIZE)
    painter.setFont(font)
    metrics = painter.fontMetrics()

    pad = dims.SCALE_BAR_PLATE_PADDING
    width = metrics.horizontalAdvance(text) + 2 * pad
    height = metrics.capHeight() + 2 * pad
    mid_x = (a.x() + b.x()) / 2
    mid_y = (a.y() + b.y()) / 2
    plate = QRectF(mid_x - width / 2, mid_y - height / 2, width, height)

    plate_color = QColor(colors.CANVAS_PLATE_COLOR)
    plate_color.setAlphaF(dims.CANVAS_PLATE_ALPHA)
    painter.setPen(QPen(border, dims.RULER_LABEL_BORDER_WIDTH))
    painter.setBrush(plate_color)
    radius = dims.SCALE_BAR_PLATE_RADIUS
    painter.drawRoundedRect(plate, radius, radius)

    painter.setPen(QColor(colors.RULER_LABEL_COLOR))
    painter.drawText(
        QPointF(plate.left() + pad, plate.top() + pad + metrics.capHeight()),
        text,
    )
    return plate
