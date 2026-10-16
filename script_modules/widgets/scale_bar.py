"""
Scale Bar

Zoom-aware microscopy scale bar shared by the Pattern Viewer and Image
Viewer canvases.

The bar's physical length snaps to a 1/2/5 × 10^n value whose drawn
length is close to ``SCALE_BAR_TARGET_PX``, and its label switches
between nm, µm, and mm.  It is drawn in widget coordinates in the
bottom-left corner, so it stays put while the view pans, on a
translucent plate that keeps the white bar and label legible over any
image.
"""
import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen

from script_modules.app_styles import AppStyles


def nice_length_125(value: float) -> float:
    """Round *value* to the nearest 1/2/5 × 10^n.

    Standard microscopy scale-bar snap: produces values like 0.1, 0.2,
    0.5, 1, 2, 5, 10, 20, 50, ...

    :param value: A positive physical length in µm.
    :return: The nearest 1/2/5 nice number, or 1.0 for a non-positive
        *value*.
    """
    if value <= 0:
        return 1.0
    exp = math.floor(math.log10(value))
    base = value / (10 ** exp)
    if base < 1.5:
        nice = 1.0
    elif base < 3.5:
        nice = 2.0
    elif base < 7.5:
        nice = 5.0
    else:
        nice = 10.0
    return nice * (10 ** exp)


def format_length_um(
    length_um: float, significant: int | None = None,
) -> str:
    """Format a length with the microscopy unit convention.

    Lengths below 1 µm are shown in nm and lengths from 1000 µm in mm.
    With *significant* given, the length is rounded to that many
    significant figures before the unit is chosen, so a value just
    under a unit boundary rounds up into the next unit.

    :param length_um: Length in µm.
    :param significant: Significant figures to keep, or *None* for
        the shortest exact representation.
    :return: Label such as ``"500 nm"``, ``"10 µm"``, or ``"2 mm"``.
    """
    if significant is not None:
        length_um = _round_significant(length_um, significant)
    if length_um >= 1000.0:
        value, unit = length_um / 1000.0, "mm"
    elif length_um >= 1.0:
        value, unit = length_um, "µm"
    else:
        value, unit = length_um * 1000.0, "nm"
    spec = "g" if significant is None else f".{significant}g"
    return f"{value:{spec}} {unit}"


def _round_significant(value: float, digits: int) -> float:
    """Round *value* to *digits* significant figures (0 stays 0)."""
    if value == 0:
        return 0.0
    return round(value, digits - 1 - math.floor(math.log10(abs(value))))


def draw_scale_bar(
    painter: QPainter, canvas_height: int, px_per_um: float,
) -> None:
    """Draw the scale bar in the bottom-left corner of a canvas.

    Drawn at full opacity whatever the painter's current opacity (the
    Image Viewer's cross-fade lowers it), and the painter's state is
    restored afterwards.  Nothing is drawn for a non-positive or
    non-finite scale.

    :param painter: Active QPainter on the canvas widget.
    :param canvas_height: Height of the canvas widget, in pixels.
    :param px_per_um: Widget pixels per µm at the current zoom.
    """
    if not math.isfinite(px_per_um) or px_per_um <= 0:
        return

    dims = AppStyles.Dimensions
    length_um = nice_length_125(dims.SCALE_BAR_TARGET_PX / px_per_um)
    bar_px = round(length_um * px_per_um)
    label = format_length_um(length_um)

    painter.save()
    painter.setOpacity(1.0)

    font = painter.font()
    font.setPointSize(dims.SCALE_BAR_LABEL_FONT_SIZE)
    painter.setFont(font)
    metrics = painter.fontMetrics()
    label_w = metrics.horizontalAdvance(label)

    # Layout, bottom up: padding, bar (with end caps), label pad,
    # label, padding.  The label's cap height sets its visual top.
    pad = dims.SCALE_BAR_PLATE_PADDING
    cap = dims.SCALE_BAR_CAP_HEIGHT
    content_w = max(bar_px, label_w)
    plate_w = content_w + 2 * pad
    plate_h = (
        pad + metrics.capHeight() + dims.SCALE_BAR_LABEL_PAD + cap + pad
    )
    inset = dims.CANVAS_OVERLAY_INSET
    plate = QRectF(
        inset, canvas_height - inset - plate_h, plate_w, plate_h,
    )

    plate_color = QColor(AppStyles.Colors.CANVAS_PLATE_COLOR)
    plate_color.setAlphaF(dims.CANVAS_PLATE_ALPHA)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(plate_color)
    radius = dims.SCALE_BAR_PLATE_RADIUS
    painter.drawRoundedRect(plate, radius, radius)

    # Integer coordinates keep the 2 px strokes crisp.
    x0 = inset + pad + (content_w - bar_px) // 2
    x1 = x0 + bar_px
    y = round(plate.bottom()) - pad - cap // 2
    painter.setPen(QPen(
        QColor(AppStyles.Colors.SCALE_BAR_COLOR),
        dims.SCALE_BAR_LINE_WIDTH,
    ))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawLine(x0, y, x1, y)
    painter.drawLine(x0, y - cap // 2, x0, y + cap // 2)
    painter.drawLine(x1, y - cap // 2, x1, y + cap // 2)

    # Label centered above the bar.
    baseline_y = y - cap // 2 - dims.SCALE_BAR_LABEL_PAD
    label_x = (x0 + x1) / 2 - label_w / 2
    painter.drawText(QPointF(label_x, baseline_y), label)

    painter.restore()
