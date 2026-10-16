"""
Image Viewer GroupBox

Two-column layout for browsing site images from an ATC project.

Layout::

    ImageViewerGroupBox (titled "Image Viewer")
    ├── Left column (fixed width):
    │   ├── ImageDirectoryComboBox (select image directory)
    │   └── Searchable metadata tree (ImageInfo, MicroscopeMetadata,
    │       and XMLMetadata when the image carries embedded FEI XML)
    └── Right column (expanding):
        ├── Image name + [Show graphics] + [Show histogram] + counter row
        ├── QSplitter:
        │   ├── ImageCanvasWidget (QPainter image display, graphics
        │   │   overlay, ruler, and scale bar)
        │   │   ├── RulerButton floated above the reset-view button
        │   │   └── ResetViewButton floated bottom-right
        │   └── HistogramGroupBox (shown with Show histogram)
        └── Button row: [Opacity] [slider] [Previous] [Next] [slider] [Opacity]

The group box is populated with a site's ``ImageDirectories``
data and requires the project root path to resolve relative image
paths to absolute paths on disk.

The group box starts in a placeholder state and is populated by the
parent panel when a site is selected.

View interaction
~~~~~~~~~~~~~~~~

The canvas uses ``QPainter`` rather than matplotlib so that mouse
zoom and drag pan are the primary view-manipulation gestures (no
separate toolbar required):

- **Wheel zoom** — cursor-anchored, 1.1× per notch, 0.1×–50×
  range.  The point under the cursor stays fixed across zoom
  changes.
- **Left-drag pan** — ``ClosedHandCursor`` while dragging.
- **Reset view** — ``ResetViewButton`` floated in the bottom-right
  corner of the canvas, repositioned via an ``eventFilter`` on
  canvas resize (mirrors the pattern viewer's idiom).
- **Opacity cross-fade** — sliders on either side of the
  Previous/Next buttons blend the current image with its previous
  or next neighbor for comparing consecutive acquisitions.

Across Previous/Next navigation the canvas's ``(zoom, pan_x,
pan_y)`` state is preserved so the user can zoom in once and
browse a directory without losing their view.  Switching
directories explicitly resets the view.

Scale Bar
~~~~~~~~~

Whenever the image records a pixel size (``BinaryResult`` ›
``PixelSize``), the canvas draws a zoom-aware scale bar in its
bottom-left corner (see ``widgets/scale_bar.py``).  It is independent
of **Show graphics**, and during a cross-fade it describes the current
image.

Ruler
~~~~~

The ``RulerButton`` turns on a measuring tool for images with a pixel
size (see ``widgets/ruler.py``).  While it is on, a click places the
first point, a preview line follows the cursor, and a second click
completes the ruler; a label at its midpoint shows the physical
length.  Dragging an endpoint moves it, dragging the label moves the
whole ruler, and Shift or Ctrl locks a placed or dragged endpoint to
the horizontal or vertical.  Dragging anywhere else still pans.  The
endpoints are kept in image pixels, so the line follows zoom and pan
while the label stays the same.  There is one ruler at a time: it is
erased when the image changes or the button is toggled off, while the
button itself stays on across image changes.

Histogram and Levels
~~~~~~~~~~~~~~~~~~~~

Images are loaded with their stored pixel values
(``load_image_native``) and rendered through levels: a black point and
a white point.  Each image starts with auto levels, its own value
range.  Dragging a line on the histogram switches to Manual levels,
which re-render the image (and any cross-faded neighbour) without
resetting the view and carry across Previous/Next.  Picking a
directory, selecting an image from a site preview, or the histogram's
Reset returns to auto levels.  Levels change only the display, never
the file, and color images always use auto levels.

Graphics Overlay
~~~~~~~~~~~~~~~~

When **Show graphics** is checked the canvas draws:

1. A **crosshair** at the ``PatternCenterPositionPx`` from the
   ``MatchInformationCollection`` metadata.
2. **Pattern rectangle outlines** from ``PatterningInformation``
   when pixel size data is available.  The coordinate origin
   depends on the activity type:

   - *Stress Relief Cuts*: rectangles are positioned relative
     to the match center (``PatternCenterPositionPx``).
   - *All other activities* (Rough Milling, polishing, etc.):
     rectangles are positioned relative to the image center.

   The ``<Center><X>`` metadata value points to the pattern's
   anchor point; it is adjusted to the geometric center using
   the ``AnchorPoint`` field before drawing.  The Y axis is
   negated (physical positive-up → image positive-down).

The image-pixel coordinates of the crosshair and rectangles are
pre-computed once per image (in ``_extract_overlay_data``) so the
canvas only has to apply the current display transform at paint
time.  This keeps zoom interactions cheap.
"""
import logging
from pathlib import Path

import numpy as np
from PySide6.QtWidgets import (
    QApplication, QGroupBox, QVBoxLayout, QHBoxLayout, QSplitter,
    QWidget, QLabel, QSizePolicy, QCheckBox, QSlider,
)
from PySide6.QtCore import Qt, QEvent, QRectF, QPointF, Slot, Signal
from PySide6.QtGui import (
    QPixmap, QPainter, QColor, QPen, QCursor,
)
from script_modules.app_styles import AppStyles
from script_modules.value_utils import (
    parse_unit_value,
    to_metres,
)
from script_modules.image_utils import load_image_native, numpy_to_qpixmap
from script_modules.groupboxes.histogram_groupbox import HistogramGroupBox
from script_modules.widgets.combobox_widgets import ImageDirectoryComboBox
from script_modules.widgets.button_widgets import (
    PreviousButton, NextButton, ResetViewButton, RulerButton,
)
from script_modules.widgets.searchable_tree_widget import SearchableTreePanel
from script_modules.widgets.clickable_label import ClickableLabel
from script_modules.widgets.ruler import (
    Ruler, RulerState, ViewTransform, draw_ruler,
)
from script_modules.widgets.scale_bar import draw_scale_bar
from script_modules.file_reveal import reveal_in_file_manager
from script_modules.parsers.image_metadata_parser import (
    extract_image_metadata,
    extract_pixel_size_m,
    pixel_size_from_xml,
)


logger = logging.getLogger(__name__)


# Placeholder text
_PLACEHOLDER_LABEL = "No images available"

# Zoom interaction tuning (matches PatternCanvasWidget)
_ZOOM_FACTOR = 1.1
_ZOOM_MIN = 0.1
_ZOOM_MAX = 50.0

# Sign applied to the physical pattern rotation when drawing the
# overlay outline.  The physical (Site) frame is Y-up with
# CCW-positive rotation; image and widget space are Y-down, so the
# on-screen rotation is the negation of the physical angle (the same
# Y-flip that negates positions above also reverses rotational sense).
# The sign is derived from these conventions and has not been
# validated against a real rotated-pattern image (most patterns have
# zero rotation); flip to +1.0 if a real image shows the opposite
# sense.  ScanRotation is deliberately not folded in here.
_OVERLAY_ROTATION_SIGN = -1.0


# -----------------------------------------------------------------
# Pattern Overlay Helpers
# -----------------------------------------------------------------

def _adjust_anchor_x(
    anchor_x_m: float, anchor_point: str, width_m: float,
) -> float:
    """Adjust pattern X from anchor point to geometric center.

    The metadata ``<Center><X>`` value points to the anchor
    point of the pattern.  This converts to the geometric
    center X coordinate for drawing.

    :param anchor_x_m: X coordinate at the anchor (metres).
    :param anchor_point: ``AnchorPoint`` string from metadata
        (e.g. ``"BottomCenter"``, ``"TopRight"``).
    :param width_m: Pattern width (metres).
    :return: Geometric center X in metres.
    """
    ap = anchor_point.lower()
    if "right" in ap:
        return anchor_x_m - width_m / 2
    elif "left" in ap:
        return anchor_x_m + width_m / 2
    # Center-aligned anchors (BottomCenter, TopCenter, etc.)
    return anchor_x_m


def _parse_pattern_rectangles(
    raw_rects: list[dict],
) -> list[dict]:
    """Parse ``PatternDrawingRectangle`` entries into
    overlay-ready dicts with values in metres and degrees.

    Each output dict contains:

    - ``center_x_m``, ``center_y_m`` — anchor position (metres)
    - ``width_m``, ``height_m`` — rectangle size (metres)
    - ``rotation_deg`` — rotation angle (degrees)
    - ``anchor_point`` — anchor string for X adjustment

    :param raw_rects: List of raw rectangle dicts from the
        parsed XML metadata.
    :return: List of parsed rectangle dicts.  Entries that
        cannot be parsed are silently skipped.
    """
    result: list[dict] = []
    for raw in raw_rects:
        if not isinstance(raw, dict):
            continue

        center = raw.get("Center", {})
        center_x_m = to_metres(center.get("X"))
        center_y_m = to_metres(center.get("Y"))
        if center_x_m is None or center_y_m is None:
            continue

        size = raw.get("Size", {})
        width_m = to_metres(size.get("Width"))
        height_m = to_metres(size.get("Height"))
        if width_m is None or height_m is None:
            continue

        rotation_parsed = parse_unit_value(
            raw.get("Rotation", "0")
        )
        rotation_deg = (
            rotation_parsed[0] if rotation_parsed else 0.0
        )

        anchor_point = raw.get("AnchorPoint", "")

        result.append({
            "center_x_m": center_x_m,
            "center_y_m": center_y_m,
            "width_m": abs(width_m),
            "height_m": abs(height_m),
            "rotation_deg": rotation_deg,
            "anchor_point": anchor_point,
        })

    # Rotated patterns are expected to be rare; log once per image so
    # their occurrence in real projects is visible.
    rotated = [r for r in result if abs(r["rotation_deg"]) > 0.01]
    if rotated:
        logger.info(
            "Overlay: %d pattern rectangle(s) have non-zero rotation "
            "(e.g. %.2f\u00b0); outlines drawn with the derived "
            "screen-rotation sign (see _OVERLAY_ROTATION_SIGN).",
            len(rotated), rotated[0]["rotation_deg"],
        )

    return result


def _rectangles_to_image_px(
    rects: list[dict],
    pixel_size_x_m: float,
    pixel_size_y_m: float,
    origin_x_px: float,
    origin_y_px: float,
) -> list[dict]:
    """Convert parsed pattern rectangles to image-pixel space.

    Applies anchor-to-center adjustment (X), the physical-to-pixel
    conversion, and the Y-axis negation in one pass.  The canvas
    consumes the output directly without needing to know about
    coordinate-system conventions or activity types.

    Each output dict has ``x``, ``y`` (geometric center in image
    pixels), ``w``, ``h`` (size in image pixels), and
    ``rotation_deg`` (carried through unchanged for the canvas to
    apply at draw time).

    :param rects: Output of :func:`_parse_pattern_rectangles`.
    :param pixel_size_x_m: Metres per pixel along X.
    :param pixel_size_y_m: Metres per pixel along Y.
    :param origin_x_px: Image-pixel X corresponding to the
        physical X = 0 reference (image center for regular
        milling, match center for stress relief).
    :param origin_y_px: Image-pixel Y corresponding to the
        physical Y = 0 reference.
    :return: Rectangles in image-pixel space.
    """
    out: list[dict] = []
    for rect in rects:
        # Adjust X from anchor point to geometric center
        cx_m = _adjust_anchor_x(
            rect["center_x_m"],
            rect["anchor_point"],
            rect["width_m"],
        )
        cy_m = rect["center_y_m"]

        # Convert physical position to image-pixel coordinates.
        # X: positive = right in both coordinate systems.
        # Y: negated because the Site coordinate system is
        #    positive-up while image pixels are positive-down.
        cx_px = origin_x_px + (cx_m / pixel_size_x_m)
        cy_px = origin_y_px - (cy_m / pixel_size_y_m)

        w_px = rect["width_m"] / pixel_size_x_m
        h_px = rect["height_m"] / pixel_size_y_m

        out.append({
            "x": cx_px,
            "y": cy_px,
            "w": w_px,
            "h": h_px,
            "rotation_deg": rect["rotation_deg"],
        })
    return out


# -----------------------------------------------------------------
# Image Canvas Widget
# -----------------------------------------------------------------

class ImageCanvasWidget(QWidget):
    """QPainter-based image viewer with wheel zoom and drag pan.

    Holds a single ``QPixmap`` and an optional overlay dictionary
    (with crosshair center and pre-computed image-pixel
    rectangles).  The display transform is recomputed every
    ``paintEvent`` from the widget size, fit-to-widget scale, and
    user-controlled zoom/pan offsets.

    All coordinate math is widget-agnostic from the consumer's
    point of view — the groupbox hands in image-pixel coordinates
    and the canvas applies the current transform at paint time.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        # Content state.  The pixel size (metres, X) sizes the scale
        # bar; None leaves the bar off.
        self._pixmap: QPixmap | None = None
        self._overlay_data: dict | None = None
        self._overlay_visible: bool = False
        self._error_text: str | None = None
        self._pixel_size_m: float | None = None

        # Cross-fade state: an optional neighbour image drawn beneath
        # the current one, revealed as the current image's opacity is
        # lowered via the Previous/Next opacity sliders.  The neighbour
        # carries its own overlay data so its graphics fade in (inverse
        # of the current image) as it is revealed.
        self._neighbor_pixmap: QPixmap | None = None
        self._neighbor_overlay_data: dict | None = None
        self._current_opacity: float = 1.0

        # Zoom / pan / drag state
        self._zoom: float = 1.0
        self._pan_x: float = 0.0
        self._pan_y: float = 0.0
        self._drag_active: bool = False
        self._drag_start_x: float = 0.0
        self._drag_start_y: float = 0.0
        self._drag_start_pan_x: float = 0.0
        self._drag_start_pan_y: float = 0.0

        # Ruler state.  While the tool is on, a left press is routed by
        # ``_press_mode``: "ruler" drags the ruler under the cursor,
        # "maybe_pan" is undecided until the cursor moves past the drag
        # threshold ("pan") or is released in place (a click that
        # places a point).  The label rect is refreshed at paint time
        # for hit-testing.
        self._ruler: Ruler | None = None
        self._ruler_enabled: bool = False
        self._ruler_label_rect: QRectF | None = None
        self._press_mode: str | None = None

        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self.setMinimumHeight(
            AppStyles.Dimensions.IMAGE_VIEWER_CANVAS_MINIMUM_HEIGHT
        )
        self.setStyleSheet(
            f"background-color: {AppStyles.Colors.MAIN_BG};"
        )

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    def set_image(
        self,
        pixmap: QPixmap | None,
        overlay_data: dict | None,
        pixel_size_m: float | None = None,
    ) -> None:
        """Display *pixmap* with optional overlay data.

        Resets the zoom/pan state.  Call :meth:`restore_view`
        immediately after this if you want to preserve the view
        across image changes (the Previous/Next navigation flow).

        :param pixmap: Image to display, or *None* to clear.
        :param overlay_data: Dict with keys ``center_px`` (tuple
            of image pixels) and optional ``rectangles_image_px``
            (list of pre-transformed image-pixel rectangles).
        :param pixel_size_m: Width of one image pixel in metres, for
            the scale bar; *None* draws no scale bar.
        """
        self._pixmap = pixmap
        self._overlay_data = overlay_data
        self._pixel_size_m = pixel_size_m
        self._error_text = None
        self._drop_ruler()
        self.reset_view()
        self._refresh_cursor()
        self.update()

    def update_pixmap(self, pixmap: QPixmap) -> None:
        """Swap in a re-rendered pixmap of the same image (new levels)
        without resetting the view."""
        self._pixmap = pixmap
        self.update()

    def set_overlay_visible(self, visible: bool) -> None:
        """Toggle the overlay without reloading the image."""
        if self._overlay_visible == visible:
            return
        self._overlay_visible = visible
        self.update()

    def set_error_text(self, text: str | None) -> None:
        """Display a centered error message instead of an image."""
        self._pixmap = None
        self._overlay_data = None
        self._pixel_size_m = None
        self._error_text = text
        self._drop_ruler()
        self.reset_view()
        self._refresh_cursor()
        self.update()

    def clear(self) -> None:
        """Reset to an empty state (no image, no overlay, no
        error text)."""
        self._pixmap = None
        self._overlay_data = None
        self._overlay_visible = False
        self._error_text = None
        self._pixel_size_m = None
        self._neighbor_pixmap = None
        self._neighbor_overlay_data = None
        self._current_opacity = 1.0
        self._drop_ruler()
        self.reset_view()
        self._refresh_cursor()
        self.update()

    def set_neighbor(
        self,
        pixmap: QPixmap | None,
        overlay_data: dict | None = None,
    ) -> None:
        """Set the neighbour image (and its overlay) drawn beneath the
        current image.

        Does not trigger a repaint on its own — :meth:`set_current_opacity`
        drives the repaint so that dragging the slider only issues one
        ``update`` per opacity tick.

        :param pixmap: The previous/next image to reveal, or *None*.
        :param overlay_data: The neighbour's overlay dict (same shape as
            the current image's), drawn only when the overlay is visible.
        """
        self._neighbor_pixmap = pixmap
        self._neighbor_overlay_data = overlay_data

    def set_current_opacity(self, value: float) -> None:
        """Set the opacity of the current image and repaint.

        At ``1.0`` the neighbour is fully hidden (behavior identical
        to no cross-fade); at ``0.0`` only the neighbour shows.

        :param value: Opacity in the range ``[0.0, 1.0]`` (clamped).
        """
        self._current_opacity = max(0.0, min(1.0, value))
        self.update()

    def clear_neighbor(self) -> None:
        """Drop any cross-fade: forget the neighbour and restore full
        opacity, then repaint."""
        self._neighbor_pixmap = None
        self._neighbor_overlay_data = None
        self._current_opacity = 1.0
        self.update()

    def reset_view(self) -> None:
        """Reset zoom and pan to the default fit-all state."""
        self._zoom = 1.0
        self._pan_x = 0.0
        self._pan_y = 0.0

    def save_view(self) -> tuple | None:
        """Capture the current zoom/pan state.

        Returns ``None`` when no image is loaded so that
        Previous/Next won't restore a phantom view onto a missing
        image or an error state.

        :return: ``(zoom, pan_x, pan_y)`` tuple or *None*.
        """
        if self._pixmap is None or self._pixmap.isNull():
            return None
        return (self._zoom, self._pan_x, self._pan_y)

    def restore_view(self, saved: tuple | None) -> None:
        """Reapply a previously captured zoom/pan state.

        Pairs with :meth:`save_view`.  No-op if *saved* is *None*.
        """
        if saved is None:
            return
        try:
            zoom, pan_x, pan_y = saved
        except (TypeError, ValueError):
            return
        self._zoom = float(zoom)
        self._pan_x = float(pan_x)
        self._pan_y = float(pan_y)
        self.update()

    # -----------------------------------------------------------------
    # Ruler
    # -----------------------------------------------------------------

    def set_ruler_enabled(self, enabled: bool) -> None:
        """Turn the ruler tool on or off.

        Turning it off erases the ruler.  While it is on, the canvas
        tracks the mouse so the placement preview can follow the
        cursor, and shows a cross cursor over an image with a pixel
        size (the label needs one).
        """
        self._ruler_enabled = bool(enabled)
        self._drop_ruler()
        self.setMouseTracking(self._ruler_enabled)
        self._refresh_cursor()
        self.update()

    def _ruler_active(self) -> bool:
        """Whether the ruler tool applies to the displayed image."""
        has_image = self._pixmap is not None and not self._pixmap.isNull()
        return self._ruler_enabled and has_image and bool(self._pixel_size_m)

    def _drop_ruler(self) -> None:
        """Erase the ruler, including one being placed or dragged."""
        self._ruler = None
        self._ruler_label_rect = None
        self._press_mode = None

    def _refresh_cursor(self) -> None:
        """Cross cursor while the ruler tool applies, else the arrow."""
        shape = (
            Qt.CursorShape.CrossCursor if self._ruler_active()
            else Qt.CursorShape.ArrowCursor
        )
        self.setCursor(QCursor(shape))

    def _view_transform(self) -> ViewTransform | None:
        """The image-to-widget mapping for the current view."""
        disp_rect = self._compute_display_rect()
        if disp_rect is None:
            return None
        return ViewTransform(
            disp_rect.topLeft(), disp_rect.width() / self._pixmap.width(),
        )

    def _to_image(self, position: QPointF) -> QPointF | None:
        """Widget position to image pixels, or *None* without an image."""
        transform = self._view_transform()
        return None if transform is None else transform.to_image(position)

    @staticmethod
    def _axis_lock(event) -> bool:
        """Whether Shift or Ctrl is held on *event*."""
        return bool(event.modifiers() & (
            Qt.KeyboardModifier.ShiftModifier
            | Qt.KeyboardModifier.ControlModifier
        ))

    def _press_ruler(self, position: QPointF) -> None:
        """Route a left press while the ruler tool is on.

        A press on the ruler starts dragging that part at once; any
        other press stays undecided until the cursor moves past the
        drag threshold (a pan) or is released in place (a click).
        """
        self._drag_active = False
        transform = self._view_transform()
        hit = None
        if self._ruler is not None and transform is not None:
            hit = self._ruler.hit_test(
                position, transform, self._ruler_label_rect,
                AppStyles.Dimensions.RULER_HIT_RADIUS_PX,
            )
        if hit is not None:
            self._ruler.begin_drag(hit, transform.to_image(position))
            self._press_mode = "ruler"
        else:
            self._press_mode = "maybe_pan"

    def _click_ruler(self, position: QPointF, axis_lock: bool) -> None:
        """Place the first or second point.  A click beside a complete
        ruler does nothing; toggling the tool off clears it."""
        image_point = self._to_image(position)
        if image_point is None:
            return
        if self._ruler is None or self._ruler.state is RulerState.EMPTY:
            self._ruler = Ruler()
            self._ruler.place_first(image_point)
        elif self._ruler.state is RulerState.PLACING:
            self._ruler.place_second(image_point, axis_lock)

    # -----------------------------------------------------------------
    # Mouse interaction
    # -----------------------------------------------------------------

    def wheelEvent(self, event) -> None:
        """Zoom in/out on scroll wheel, centered on the cursor.

        Scroll up zooms in, scroll down zooms out.  The zoom is
        applied relative to the cursor position so the point
        under the cursor stays fixed.
        """
        delta = event.angleDelta().y()
        if delta == 0:
            return

        # Cursor position relative to widget center
        mouse_x = event.position().x() - self.width() / 2
        mouse_y = event.position().y() - self.height() / 2

        if delta > 0:
            factor = _ZOOM_FACTOR
            if self._zoom * factor > _ZOOM_MAX:
                return
        else:
            factor = 1.0 / _ZOOM_FACTOR
            if self._zoom * factor < _ZOOM_MIN:
                return

        # Adjust pan so the point under the cursor stays fixed
        self._pan_x = mouse_x - factor * (mouse_x - self._pan_x)
        self._pan_y = mouse_y - factor * (mouse_y - self._pan_y)
        self._zoom *= factor

        self.update()

    def mousePressEvent(self, event) -> None:
        """Start drag panning on left-click, or route the press to
        the ruler while the tool is on.

        Ignored when no image is loaded so an empty canvas does
        not show the closed-hand cursor or pan a phantom view.
        """
        has_image = (
            self._pixmap is not None and not self._pixmap.isNull()
        )
        if event.button() == Qt.MouseButton.LeftButton and has_image:
            self._drag_start_x = event.position().x()
            self._drag_start_y = event.position().y()
            self._drag_start_pan_x = self._pan_x
            self._drag_start_pan_y = self._pan_y
            if self._ruler_active():
                self._press_ruler(event.position())
            else:
                self._drag_active = True
                self.setCursor(QCursor(
                    Qt.CursorShape.ClosedHandCursor
                ))
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        """Update the pan offset while dragging; with the ruler on,
        drag the ruler, promote an undecided press to a pan once it
        moves past the drag threshold, or move the placement preview.
        """
        position = event.position()
        if self._press_mode == "ruler":
            image_point = self._to_image(position)
            if image_point is not None:
                self._ruler.drag_to(image_point, self._axis_lock(event))
                self.update()
        elif (
            self._press_mode == "maybe_pan"
            and event.buttons() & Qt.MouseButton.LeftButton
        ):
            threshold = QApplication.startDragDistance()
            if (
                abs(position.x() - self._drag_start_x) > threshold
                or abs(position.y() - self._drag_start_y) > threshold
            ):
                self._press_mode = "pan"
                self._drag_active = True
                self.setCursor(QCursor(
                    Qt.CursorShape.ClosedHandCursor
                ))
        elif (
            self._press_mode is None
            and self._ruler is not None
            and self._ruler.state is RulerState.PLACING
        ):
            image_point = self._to_image(position)
            if image_point is not None:
                self._ruler.set_preview(image_point, self._axis_lock(event))
                self.update()

        if self._drag_active:
            dx = position.x() - self._drag_start_x
            dy = position.y() - self._drag_start_y
            self._pan_x = self._drag_start_pan_x + dx
            self._pan_y = self._drag_start_pan_y + dy
            self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        """End drag panning or a ruler drag; a press released in
        place while the ruler tool is on places a point."""
        if event.button() == Qt.MouseButton.LeftButton:
            if self._press_mode == "ruler":
                self._ruler.end_drag()
            elif self._press_mode == "maybe_pan":
                self._click_ruler(
                    QPointF(self._drag_start_x, self._drag_start_y),
                    self._axis_lock(event),
                )
            self._press_mode = None
            self._drag_active = False
            self._refresh_cursor()
            self.update()
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event) -> None:
        """Hide the placement preview while the cursor is off the
        canvas; the first point stays."""
        if (
            self._press_mode is None
            and self._ruler is not None
            and self._ruler.state is RulerState.PLACING
        ):
            self._ruler.set_preview(None)
            self.update()
        super().leaveEvent(event)

    # -----------------------------------------------------------------
    # Paint
    # -----------------------------------------------------------------

    def paintEvent(self, event) -> None:
        """Render the image and (optionally) the overlay."""
        painter = QPainter(self)
        painter.setRenderHint(
            QPainter.RenderHint.SmoothPixmapTransform
        )
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Background fill behind the image at low zoom levels.
        painter.fillRect(
            self.rect(), QColor(AppStyles.Colors.MAIN_BG)
        )

        if self._pixmap is None or self._pixmap.isNull():
            if self._error_text:
                self._draw_error_text(painter, self._error_text)
            painter.end()
            return

        disp_rect = self._compute_display_rect()
        if disp_rect is None:
            painter.end()
            return

        # Cross-fade: when a neighbor is present and the current image
        # is not fully opaque, draw the neighbor first (opaque) into
        # the same display rect so a same-size before/after pair is
        # pixel-for-pixel aligned and shares the current zoom/pan, then
        # draw the current image on top at the slider opacity.  When no
        # neighbor is set or opacity is 1.0 this path is skipped and the
        # render is identical to a plain single-image draw.
        fade_active = (
            self._neighbor_pixmap is not None
            and not self._neighbor_pixmap.isNull()
            and self._current_opacity < 1.0
        )
        if fade_active:
            painter.drawPixmap(
                disp_rect,
                self._neighbor_pixmap,
                QRectF(self._neighbor_pixmap.rect()),
            )
            # The neighbor's own graphics fade in as it is revealed
            # (inverse of the current image's opacity), so mid-slide
            # both overlays show at their image's strength.
            if (
                self._overlay_visible
                and self._neighbor_overlay_data is not None
            ):
                painter.setOpacity(1.0 - self._current_opacity)
                self._draw_overlay(
                    painter, disp_rect, self._neighbor_overlay_data,
                    self._neighbor_pixmap.width(),
                    self._neighbor_pixmap.height(),
                )
            painter.setOpacity(self._current_opacity)

        painter.drawPixmap(
            disp_rect, self._pixmap, QRectF(self._pixmap.rect())
        )

        # Current overlay draws after setOpacity so the crosshair/
        # rectangles fade in lockstep with the current image they
        # describe.
        if self._overlay_visible and self._overlay_data is not None:
            self._draw_overlay(
                painter, disp_rect, self._overlay_data,
                self._pixmap.width(), self._pixmap.height(),
            )

        if fade_active:
            painter.setOpacity(1.0)

        # Ruler above the image and graphics, below the scale bar.
        self._ruler_label_rect = None
        if self._ruler is not None and self._ruler_active():
            transform = ViewTransform(
                disp_rect.topLeft(),
                disp_rect.width() / self._pixmap.width(),
            )
            self._ruler_label_rect = draw_ruler(
                painter, self._ruler, transform, self._pixel_size_m,
            )

        # Scale bar last, in widget coordinates, describing the current
        # image (a cross-faded neighbor is drawn into the same rect).
        if self._pixel_size_m:
            px_per_um = (
                (disp_rect.width() / self._pixmap.width())
                / (self._pixel_size_m * 1e6)
            )
            draw_scale_bar(painter, self.height(), px_per_um)

        painter.end()

    def _compute_display_rect(self) -> QRectF | None:
        """Compute where the image lands on the widget.

        Combines the fit-to-widget scale (so the image fills the
        widget at zoom=1) with the user's zoom factor and pan
        offsets.  Returns *None* if the widget is too small or the
        pixmap is degenerate.
        """
        if self._pixmap is None or self._pixmap.isNull():
            return None

        img_w = self._pixmap.width()
        img_h = self._pixmap.height()
        if img_w <= 0 or img_h <= 0:
            return None

        avail_w = self.width()
        avail_h = self.height()
        if avail_w <= 0 or avail_h <= 0:
            return None

        fit_scale = min(avail_w / img_w, avail_h / img_h)
        scale = fit_scale * self._zoom

        disp_w = img_w * scale
        disp_h = img_h * scale
        disp_x = (avail_w - disp_w) / 2 + self._pan_x
        disp_y = (avail_h - disp_h) / 2 + self._pan_y

        return QRectF(disp_x, disp_y, disp_w, disp_h)

    def _draw_overlay(
        self,
        painter: QPainter,
        disp_rect: QRectF,
        overlay: dict | None,
        img_w: int,
        img_h: int,
    ) -> None:
        """Draw the crosshair and pattern rectangles for *overlay*.

        Overlay coordinates are in image-pixel space (full
        resolution) relative to an image of size *img_w* × *img_h*.
        The transform to widget coordinates uses the current display
        rect, which already incorporates the fit scale, user zoom, and
        pan offsets — so overlay primitives zoom and pan in lockstep
        with the image.  Passing the overlay and dimensions in (rather
        than reading ``self``) lets this draw either the current image's
        overlay or a revealed neighbour's during a cross-fade.
        """
        if not overlay:
            return

        center_px = overlay.get("center_px")
        if not center_px:
            return

        if img_w <= 0 or img_h <= 0:
            return

        scale_x = disp_rect.width() / img_w
        scale_y = disp_rect.height() / img_h

        # ── Crosshair ────────────────────────────────────────────
        cx, cy = center_px
        cx_w = disp_rect.left() + cx * scale_x
        cy_w = disp_rect.top() + cy * scale_y

        base_color = QColor(
            AppStyles.Colors.IMAGE_VIEWER_CROSSHAIR_COLOR
        )

        # Dashed full-width lines (alpha ~0.7)
        line_color = QColor(base_color)
        line_color.setAlpha(178)
        line_pen = QPen(line_color, 1.0)
        line_pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(line_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(
            QPointF(0.0, cy_w),
            QPointF(float(self.width()), cy_w),
        )
        painter.drawLine(
            QPointF(cx_w, 0.0),
            QPointF(cx_w, float(self.height())),
        )

        # Center "+" glyph (alpha ~0.9, slightly heavier than the
        # crosshair lines so the focus is visible)
        glyph_color = QColor(base_color)
        glyph_color.setAlpha(229)
        glyph_pen = QPen(glyph_color, 1.5)
        glyph_pen.setStyle(Qt.PenStyle.SolidLine)
        painter.setPen(glyph_pen)
        marker_half = 6.0
        painter.drawLine(
            QPointF(cx_w - marker_half, cy_w),
            QPointF(cx_w + marker_half, cy_w),
        )
        painter.drawLine(
            QPointF(cx_w, cy_w - marker_half),
            QPointF(cx_w, cy_w + marker_half),
        )

        # ── Pattern rectangles ───────────────────────────────────
        rectangles = overlay.get("rectangles_image_px") or []
        if not rectangles:
            return

        rect_color = QColor(base_color)
        rect_color.setAlpha(178)
        rect_pen = QPen(rect_color, 1.0)
        rect_pen.setStyle(Qt.PenStyle.SolidLine)
        painter.setPen(rect_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        for rect in rectangles:
            rx = rect.get("x")
            ry = rect.get("y")
            rw = rect.get("w")
            rh = rect.get("h")
            if (
                rx is None or ry is None
                or rw is None or rh is None
            ):
                continue
            rot = rect.get("rotation_deg") or 0.0
            if abs(rot) > 0.01:
                # Rotated pattern: rotate about the rectangle center in
                # widget space.  Widget scaling is uniform
                # (scale_x == scale_y from the fit transform), so the
                # rotated outline is not sheared.  Sign convention: see
                # _OVERLAY_ROTATION_SIGN.
                cx_w = disp_rect.left() + rx * scale_x
                cy_w = disp_rect.top() + ry * scale_y
                w_w = rw * scale_x
                h_w = rh * scale_y
                painter.save()
                painter.translate(cx_w, cy_w)
                painter.rotate(_OVERLAY_ROTATION_SIGN * rot)
                painter.drawRect(
                    QRectF(-w_w / 2, -h_w / 2, w_w, h_w)
                )
                painter.restore()
            else:
                # Axis-aligned (all current data).
                x0 = disp_rect.left() + (rx - rw / 2) * scale_x
                y0 = disp_rect.top() + (ry - rh / 2) * scale_y
                painter.drawRect(
                    QRectF(x0, y0, rw * scale_x, rh * scale_y)
                )

    def _draw_error_text(
        self, painter: QPainter, text: str,
    ) -> None:
        """Render a centered placeholder string (e.g. "Image file
        not found")."""
        painter.setPen(QColor(AppStyles.Colors.TEXT_DISABLED))
        font = painter.font()
        font.setPointSize(10)
        painter.setFont(font)
        painter.drawText(
            self.rect(),
            Qt.AlignmentFlag.AlignCenter,
            text,
        )


# -----------------------------------------------------------------
# Image Viewer GroupBox
# -----------------------------------------------------------------

class ImageViewerGroupBox(QGroupBox):
    """Two-column image viewer with directory selection and
    Previous/Next navigation."""

    # Emitted with a human-readable message when a reveal fails (missing
    # file, or a file manager that would not open). The embedded panel's
    # MainWindow connects this to the status bar; detached windows leave
    # it unconnected (the failure is still logged).
    reveal_failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("Image Viewer")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # State
        self._project_root: Path | None = None
        self._image_directories: list[dict] = []
        self._current_image_paths: list[Path] = []
        self._current_index: int = -1
        self._overlay_data: dict | None = None
        self._pixel_size_m: tuple[float, float] | None = None
        self._preserved_view: tuple | None = None

        # Pixel values of the displayed image, kept so a level change
        # can re-render it, and the Manual levels as (black_point,
        # white_point); None means auto levels.
        self._current_raw: np.ndarray | None = None
        self._levels: tuple[float, float] | None = None
        # Histogram panel width: it opens at its minimum, then restores
        # the width it had when last hidden.
        self._histogram_width: int = (
            AppStyles.Dimensions.HISTOGRAM_PANEL_MINIMUM_WIDTH
        )

        # Decoded neighbour images for the opacity cross-fade, keyed by
        # absolute path — each value is a ``(pixel_values, overlay_data)``
        # pair, with the pixmap rendered through the current levels
        # cached separately.  Populated lazily on first slider
        # interaction and cleared on every image change (see
        # _reset_opacity_sliders); the pixmaps are also cleared on every
        # level change.
        self._neighbor_cache: dict[
            Path, tuple[np.ndarray, dict | None]
        ] = {}
        self._neighbor_pixmaps: dict[Path, QPixmap] = {}
        self._fade_neighbor_path: Path | None = None

        self._create_widgets()
        self._setup_layout()
        self._connect_signals()

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    def set_project_root(self, project_root: Path | None) -> None:
        """Set the project root path for resolving relative image
        paths.

        :param project_root: Absolute path to the ATC project
            root directory, or *None* to clear.
        """
        self._project_root = project_root

    def populate(self, site_data: dict) -> None:
        """Populate the directory combo box from a site's image
        directories.

        :param site_data: A single site entry from the consolidated
            metadata ``"Sites"`` list.
        """
        self._image_directories = site_data.get(
            "ImageDirectories", []
        )
        self._current_image_paths.clear()
        self._current_index = -1
        self._levels = None

        # Populate combo box
        self._directory_combobox.blockSignals(True)
        self._directory_combobox.clear()
        for directory in self._image_directories:
            name = directory.get("DirectoryName", "Unknown")
            count = len(directory.get("RelativeImagePaths", []))
            self._directory_combobox.addItem(
                f"{name} ({count})"
            )
        self._directory_combobox.setCurrentIndex(-1)
        self._directory_combobox.blockSignals(False)

        # Update placeholder
        if not self._image_directories:
            self._info_label.setText(_PLACEHOLDER_LABEL)
            self._info_label.setVisible(True)
        else:
            self._info_label.setVisible(False)

        # Clear display
        self._clear_canvas()
        self._update_nav_button_states()

        site_name = site_data.get("SiteName", "Unknown")
        logger.info(
            f"Image viewer populated for '{site_name}': "
            f"{len(self._image_directories)} image directories"
        )

    def clear(self) -> None:
        """Reset the viewer to its empty state."""
        self._image_directories.clear()
        self._current_image_paths.clear()
        self._current_index = -1
        self._preserved_view = None
        self._levels = None
        self._directory_combobox.blockSignals(True)
        self._directory_combobox.clear()
        self._directory_combobox.blockSignals(False)
        self._info_label.setText(_PLACEHOLDER_LABEL)
        self._info_label.setVisible(True)
        self._image_name_label.setText("")
        self._image_name_label.set_clickable(False)
        self._image_name_label.setToolTip("")
        self._image_counter_label.setText("")
        self._clear_canvas()
        self._clear_metadata()
        self._update_nav_button_states()

    def select_image(
        self, directory_name: str, filename: str
    ) -> None:
        """Programmatically select a directory and navigate to a
        specific image.

        Used by the site preview click-to-navigate feature to
        jump directly to a preview image in the full viewer.

        :param directory_name: The ``DirectoryName`` value to
            match (e.g. ``"LamellaEvaluationImages"``).
        :param filename: The image file name to navigate to
            within that directory.
        """
        # Find the directory index
        dir_index = -1
        for i, directory in enumerate(self._image_directories):
            if directory.get("DirectoryName", "") == directory_name:
                dir_index = i
                break

        if dir_index < 0:
            logger.warning(
                f"select_image: directory '{directory_name}' "
                f"not found"
            )
            return

        # Only re-resolve when the target directory differs from the
        # one already loaded, avoiding a redundant decode of that
        # directory's first image.  The combo box is connected via
        # ``activated`` (user action only), so setCurrentIndex does
        # not fire _on_directory_selected.
        if dir_index != self._directory_combobox.currentIndex():
            self._directory_combobox.setCurrentIndex(dir_index)
            self._preserved_view = None
            self._resolve_directory_paths(dir_index)

        # Navigate to the requested image and display it exactly once,
        # with auto levels.
        for i, path in enumerate(self._current_image_paths):
            if path.name == filename:
                self._current_index = i
                self._levels = None
                self._display_current_image()
                self._update_nav_button_states()
                logger.info(
                    f"select_image: navigated to '{filename}' "
                    f"in '{directory_name}'"
                )
                return

        logger.warning(
            f"select_image: '{filename}' not found in "
            f"'{directory_name}'"
        )

    # -----------------------------------------------------------------
    # Setup
    # -----------------------------------------------------------------

    def _create_widgets(self):
        """Create all child widgets."""
        # -- Left column widgets --
        self._directory_combobox = ImageDirectoryComboBox(parent=self)

        # Metadata panel (searchable tree, hidden until image selected)
        self._meta_panel = SearchableTreePanel("", parent=self)
        self._meta_panel.apply_style(
            AppStyles.GroupBox.embedded_untitled()
        )
        self._meta_panel.setVisible(False)

        # -- Right column widgets --
        # Info label (shown when no images)
        self._info_label = QLabel(_PLACEHOLDER_LABEL, parent=self)
        self._info_label.setStyleSheet(AppStyles.Label.default())
        self._info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Image name label — a "reveal in folder" link whenever a slice
        # image is shown (see _display_current_image): normal text that
        # turns blue on hover, like a hyperlink.
        self._image_name_label = ClickableLabel("", parent=self)

        # Image counter label (e.g. "3 / 15")
        self._image_counter_label = QLabel("", parent=self)
        self._image_counter_label.setStyleSheet(AppStyles.Label.default())
        self._image_counter_label.setAlignment(
            Qt.AlignmentFlag.AlignRight
            | Qt.AlignmentFlag.AlignVCenter
        )

        # Show graphics checkbox (enabled when overlay data is found)
        self._show_graphics_checkbox = QCheckBox(
            "Show graphics", parent=self
        )
        self._show_graphics_checkbox.setStyleSheet(
            AppStyles.CheckBox.default()
        )
        self._show_graphics_checkbox.setChecked(False)
        self._show_graphics_checkbox.setEnabled(False)
        self._show_graphics_checkbox.setFocusPolicy(
            Qt.FocusPolicy.NoFocus
        )

        # Show histogram checkbox (enabled while an image is shown)
        self._show_histogram_checkbox = QCheckBox(
            "Show histogram", parent=self
        )
        self._show_histogram_checkbox.setStyleSheet(
            AppStyles.CheckBox.default()
        )
        self._show_histogram_checkbox.setChecked(False)
        self._show_histogram_checkbox.setEnabled(False)
        self._show_histogram_checkbox.setFocusPolicy(
            Qt.FocusPolicy.NoFocus
        )

        # Histogram side panel, hidden until the checkbox is checked
        self._histogram = HistogramGroupBox(parent=self)
        self._histogram.setVisible(False)

        # QPainter-based image canvas
        self._canvas = ImageCanvasWidget(parent=self)
        # Forward resize events so the corner buttons stay pinned to
        # the bottom-right corner.
        self._canvas.installEventFilter(self)

        # Reset-view button floated over the canvas.  Parented to
        # the canvas so it sits on top in z-order; positioned
        # manually via ``_position_canvas_buttons``.
        self._reset_view_button = ResetViewButton(
            parent=self._canvas
        )
        self._reset_view_button.setFocusPolicy(
            Qt.FocusPolicy.NoFocus
        )

        # Ruler button stacked above it; enabled only while the image
        # has a pixel size (see _set_ruler_available).
        self._ruler_button = RulerButton(parent=self._canvas)
        self._ruler_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._ruler_button.setEnabled(False)

        # Navigation buttons (NoFocus prevents scroll-on-click)
        self._prev_button = PreviousButton(parent=self)
        self._prev_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._next_button = NextButton(parent=self)
        self._next_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        # Opacity cross-fade sliders flanking the nav buttons.  The left
        # slider fades the current image to reveal the previous image; the
        # right slider reveals the next image.  100 = current image fully
        # opaque (no reveal).  Disabled until >= 2 images are available.
        self._prev_opacity_label = QLabel("Opacity", parent=self)
        self._prev_opacity_label.setStyleSheet(AppStyles.Label.default())
        self._prev_opacity_label.setToolTip(
            AppStyles.AppText.OPACITY_PREV_SLIDER
        )
        self._prev_opacity_slider = self._make_opacity_slider()
        self._prev_opacity_slider.setToolTip(
            AppStyles.AppText.OPACITY_PREV_SLIDER
        )

        self._next_opacity_label = QLabel("Opacity", parent=self)
        self._next_opacity_label.setStyleSheet(AppStyles.Label.default())
        self._next_opacity_label.setToolTip(
            AppStyles.AppText.OPACITY_NEXT_SLIDER
        )
        self._next_opacity_slider = self._make_opacity_slider()
        self._next_opacity_slider.setToolTip(
            AppStyles.AppText.OPACITY_NEXT_SLIDER
        )

    def _make_opacity_slider(self) -> QSlider:
        """Build a horizontal opacity slider for the cross-fade feature.

        Range 0-100 with 100 (fully opaque current image) as the rest
        position.  ``NoFocus`` mirrors the nav buttons; a fixed width
        keeps the slider from absorbing horizontal slack so the buttons
        stay centered.
        """
        slider = QSlider(Qt.Orientation.Horizontal, parent=self)
        slider.setRange(0, 100)
        slider.setValue(100)
        slider.setEnabled(False)
        slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        slider.setFixedWidth(
            AppStyles.Dimensions.IMAGE_VIEWER_OPACITY_SLIDER_WIDTH
        )
        slider.setStyleSheet(AppStyles.Slider.default())
        return slider

    def _setup_layout(self):
        """Arrange widgets in a two-column layout."""
        # -- Left column --
        left_column = QVBoxLayout()
        left_column.setContentsMargins(0, 0, 0, 0)
        left_column.setSpacing(AppStyles.Dimensions.LAYOUT_VSPACING)
        left_column.addWidget(self._directory_combobox)
        left_column.addWidget(self._meta_panel, 1)

        left_container = QWidget()
        left_container.setLayout(left_column)
        left_container.setMinimumWidth(
            AppStyles.Dimensions.IMAGE_VIEWER_COMBOBOX_WIDTH
        )

        # -- Right column --
        # Name row: image name (left) + show graphics + counter (right)
        name_row = QHBoxLayout()
        name_row.setContentsMargins(0, 0, 0, 0)
        name_row.setSpacing(AppStyles.Dimensions.LAYOUT_VSPACING)
        name_row.addWidget(self._image_name_label, 1)
        name_row.addWidget(self._show_graphics_checkbox)
        name_row.addWidget(self._show_histogram_checkbox)
        name_row.addWidget(self._image_counter_label)

        # Canvas and histogram side panel, resizable against each other
        self._canvas_splitter = QSplitter(
            Qt.Orientation.Horizontal, parent=self
        )
        self._canvas_splitter.setHandleWidth(
            AppStyles.Dimensions.SPLITTER_HANDLE_WIDTH
        )
        self._canvas_splitter.setStyleSheet(AppStyles.Splitter.horizontal())
        self._canvas_splitter.setChildrenCollapsible(False)
        self._canvas_splitter.addWidget(self._canvas)
        self._canvas_splitter.addWidget(self._histogram)
        self._canvas_splitter.setStretchFactor(0, 1)
        self._canvas_splitter.setStretchFactor(1, 0)

        # Button row: opacity sliders flank the nav buttons (labels on
        # the outer edges, mirrored; sliders inboard).  Labels/sliders
        # are fixed width (stretch 0) so the two buttons absorb all
        # horizontal slack and stay centered.
        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.setSpacing(AppStyles.Dimensions.LAYOUT_VSPACING)
        button_row.addWidget(self._prev_opacity_label)
        button_row.addWidget(self._prev_opacity_slider)
        button_row.addWidget(self._prev_button, 1)
        button_row.addWidget(self._next_button, 1)
        button_row.addWidget(self._next_opacity_slider)
        button_row.addWidget(self._next_opacity_label)

        right_column = QVBoxLayout()
        right_column.setContentsMargins(0, 0, 0, 0)
        right_column.setSpacing(AppStyles.Dimensions.LAYOUT_VSPACING)
        right_column.addLayout(name_row)
        right_column.addWidget(self._info_label)
        right_column.addWidget(self._canvas_splitter, 1)
        right_column.addLayout(button_row)

        right_container = QWidget()
        right_container.setLayout(right_column)

        # -- Main layout --
        self._splitter = QSplitter(Qt.Orientation.Horizontal, parent=self)
        self._splitter.setHandleWidth(
            AppStyles.Dimensions.SPLITTER_HANDLE_WIDTH
        )
        self._splitter.setStyleSheet(AppStyles.Splitter.horizontal())
        self._splitter.addWidget(left_container)
        self._splitter.addWidget(right_container)
        self._splitter.setStretchFactor(0, 0)  # left: don't absorb resize
        self._splitter.setStretchFactor(1, 1)  # right: absorbs resize

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(
            AppStyles.Dimensions.LAYOUT_CONTENTS_MARGIN,
            AppStyles.Dimensions.LAYOUT_CONTENTS_MARGIN,
            AppStyles.Dimensions.LAYOUT_CONTENTS_MARGIN,
            AppStyles.Dimensions.LAYOUT_CONTENTS_MARGIN,
        )
        main_layout.setSpacing(AppStyles.Dimensions.LAYOUT_VSPACING)
        main_layout.addWidget(self._splitter, 1)
        self.setStyleSheet(AppStyles.GroupBox.with_title_bold())

        # Reserve the populated height so the groupbox does not
        # visibly jump when an image directory is first selected.
        self.setMinimumHeight(
            AppStyles.Dimensions.IMAGE_VIEWER_GROUPBOX_MINIMUM_HEIGHT
        )

    def _connect_signals(self):
        """Connect widget signals."""
        self._directory_combobox.activated.connect(
            self._on_directory_selected
        )
        self._prev_button.clicked.connect(self._on_previous)
        self._next_button.clicked.connect(self._on_next)
        self._prev_opacity_slider.valueChanged.connect(
            self._on_prev_opacity_changed
        )
        self._next_opacity_slider.valueChanged.connect(
            self._on_next_opacity_changed
        )
        self._show_graphics_checkbox.toggled.connect(
            self._on_show_graphics_toggled
        )
        self._show_histogram_checkbox.toggled.connect(
            self._on_show_histogram_toggled
        )
        self._histogram.levels_changed.connect(self._on_levels_changed)
        self._histogram.levels_reset.connect(self._on_levels_reset)
        self._reset_view_button.clicked.connect(self._on_reset_view)
        self._ruler_button.toggled.connect(self._canvas.set_ruler_enabled)
        self._image_name_label.clicked.connect(self._on_image_name_clicked)

    # -----------------------------------------------------------------
    # Corner button placement
    # -----------------------------------------------------------------

    def eventFilter(self, obj, event):
        """Reposition the corner buttons when the canvas resizes so
        they stay pinned to the bottom-right corner.
        """
        if (
            obj is self._canvas
            and event.type() == QEvent.Type.Resize
        ):
            self._position_canvas_buttons()
        return super().eventFilter(obj, event)

    def _position_canvas_buttons(self) -> None:
        """Pin the reset-view button to the bottom-right corner of
        the canvas with a small inset margin, and stack the ruler
        button above it."""
        margin = AppStyles.Dimensions.CANVAS_OVERLAY_INSET
        gap = AppStyles.Dimensions.CANVAS_OVERLAY_BUTTON_GAP
        reset = self._reset_view_button
        ruler = self._ruler_button
        x = self._canvas.width() - reset.width() - margin
        y = self._canvas.height() - reset.height() - margin
        reset.move(x, y)
        ruler.move(
            x + reset.width() - ruler.width(), y - gap - ruler.height(),
        )
        reset.raise_()
        ruler.raise_()

    def _set_ruler_available(self, available: bool) -> None:
        """Enable the ruler button while the image has a pixel size.

        The button keeps its checked state while disabled, so the tool
        returns with the next image that can be measured.
        """
        self._ruler_button.setEnabled(available)

    @Slot()
    def _on_reset_view(self) -> None:
        """Reset the canvas zoom and pan to fit all."""
        self._canvas.reset_view()
        self._canvas.update()

    @Slot()
    def _on_image_name_clicked(self):
        """Reveal the current image in the OS file manager.

        The viewer already holds the resolved absolute path, so it
        performs the reveal itself — working the same whether this panel
        is embedded in the main window or popped out into a detached
        window. On failure it emits ``reveal_failed`` for optional
        status-bar feedback and logs.
        """
        if (self._current_index < 0
                or self._current_index >= len(self._current_image_paths)):
            return
        image_path = self._current_image_paths[self._current_index]
        if not reveal_in_file_manager(image_path):
            message = f"Image file not found: {image_path}"
            logger.warning(message)
            self.reveal_failed.emit(message)

    # -----------------------------------------------------------------
    # Directory Selection
    # -----------------------------------------------------------------

    @Slot(int)
    def _on_directory_selected(self, index: int):
        """Handle directory combo box selection.

        Resolves the directory's image paths and displays the
        first image.  Switching directories resets the zoom/pan
        view and returns to auto levels.

        :param index: Selected combo box index.
        """
        if index < 0 or index >= len(self._image_directories):
            return

        # Reset zoom/pan and levels when switching directories
        self._preserved_view = None
        self._levels = None

        self._resolve_directory_paths(index)

        if self._current_image_paths:
            self._current_index = 0
            self._display_current_image()
        else:
            self._current_index = -1
            self._clear_canvas()

        self._update_nav_button_states()

        dir_name = self._image_directories[index].get(
            "DirectoryName", "Unknown"
        )
        logger.info(
            f"Directory selected: '{dir_name}' "
            f"({len(self._current_image_paths)} images)"
        )

    def _resolve_directory_paths(self, index: int) -> None:
        """Resolve the absolute image paths for directory *index*
        and update the info-label placeholder state.

        Pure path resolution: it populates ``_current_image_paths``
        and shows/hides the info label, but does *not* display any
        image, change ``_current_index``, or touch the preserved
        view — callers own those decisions.  This lets
        :meth:`select_image` reuse resolution without triggering a
        redundant decode of the directory's first image.

        :param index: Directory index into ``_image_directories``.
        """
        directory = self._image_directories[index]
        relative_paths = directory.get("RelativeImagePaths", [])

        # Resolve to absolute paths
        self._current_image_paths.clear()
        if self._project_root is not None:
            for rel_path in relative_paths:
                # Handle both forward and backslash separators
                abs_path = self._project_root / Path(
                    rel_path.replace("\\", "/")
                )
                self._current_image_paths.append(abs_path)

        if self._current_image_paths:
            self._info_label.setVisible(False)
        else:
            if self._project_root is None:
                self._info_label.setText(
                    "No project directory available"
                )
            else:
                self._info_label.setText("No images in this directory")
            self._info_label.setVisible(True)

    # -----------------------------------------------------------------
    # Previous / Next Navigation
    # -----------------------------------------------------------------

    @Slot()
    def _on_previous(self):
        """Navigate to the previous image, wrapping to the end."""
        if not self._current_image_paths:
            return
        self._save_view()
        if self._current_index <= 0:
            self._current_index = len(self._current_image_paths) - 1
        else:
            self._current_index -= 1
        self._display_current_image()

    @Slot()
    def _on_next(self):
        """Navigate to the next image, wrapping to the beginning."""
        if not self._current_image_paths:
            return
        self._save_view()
        if self._current_index >= len(self._current_image_paths) - 1:
            self._current_index = 0
        else:
            self._current_index += 1
        self._display_current_image()

    def _update_nav_button_states(self):
        """Enable Previous and Next when images are available."""
        has_images = len(self._current_image_paths) > 0
        self._prev_button.setEnabled(has_images)
        self._next_button.setEnabled(has_images)
        self._update_opacity_slider_states()

    # -----------------------------------------------------------------
    # Opacity Cross-fade
    # -----------------------------------------------------------------

    def _update_opacity_slider_states(self):
        """Enable the opacity sliders when a neighbour exists.

        A cross-fade needs a distinct previous/next image to reveal, so
        the sliders are enabled only with >= 2 images (the nav buttons,
        which wrap onto the same single image, use ``> 0``).  When
        disabled, any active fade is reset.
        """
        enabled = len(self._current_image_paths) >= 2
        self._prev_opacity_slider.setEnabled(enabled)
        self._next_opacity_slider.setEnabled(enabled)
        if not enabled:
            self._reset_opacity_sliders()

    def _reset_opacity_sliders(self):
        """Snap both sliders back to fully-opaque, drop the neighbour
        cache, and clear the canvas cross-fade.

        Called at every image change so a fade never persists across
        Previous/Next, directory switches, or programmatic navigation.
        ``blockSignals`` prevents the reset from re-entering the value
        handlers (which would try to reload a neighbour).
        """
        for slider in (
            self._prev_opacity_slider, self._next_opacity_slider,
        ):
            if slider.value() != 100:
                slider.blockSignals(True)
                slider.setValue(100)
                slider.blockSignals(False)
        self._neighbor_cache.clear()
        self._neighbor_pixmaps.clear()
        self._fade_neighbor_path = None
        self._canvas.clear_neighbor()

    def _get_neighbor(
        self, neighbor_index: int,
    ) -> tuple[np.ndarray, dict | None] | None:
        """Decode (and cache) the pixel values and overlay for
        *neighbor_index*.

        Uses the same native-resolution ``load_image_native`` loader as
        the current image so the fade compares like-for-like, and the
        same guarded overlay extraction so the neighbour's graphics can
        fade in during the cross-fade.  Returns *None* for a missing or
        undecodable file so the caller can cancel the fade cleanly.

        :param neighbor_index: Index into ``_current_image_paths``.
        :return: ``(pixel_values, overlay_data)`` pair, or *None*.
        """
        path = self._current_image_paths[neighbor_index]
        cached = self._neighbor_cache.get(path)
        if cached is not None:
            return cached

        if not path.is_file():
            logger.debug(f"Opacity neighbour not on disk: {path.name}")
            return None

        raw = load_image_native(path)
        if raw is None or raw.size == 0:
            return None

        # Extract the neighbour's overlay so its crosshair/rectangles
        # can fade in as it is revealed.  Guarded exactly like the
        # current image's extraction — a bad metadata shape degrades to
        # "no overlay" rather than cancelling the fade.
        overlay: dict | None = None
        try:
            metadata = extract_image_metadata(path)
            overlay = self._extract_overlay_data(metadata)
        except Exception:
            logger.debug(
                f"Failed to extract neighbour overlay: {path.name}",
                exc_info=True,
            )

        entry = (raw, overlay)
        self._neighbor_cache[path] = entry
        return entry

    def _neighbor_pixmap(
        self, path: Path, raw: np.ndarray,
    ) -> QPixmap | None:
        """Render a neighbour through the current levels, cached until
        the levels or the current image change.

        :param path: The neighbour's path (the cache key).
        :param raw: The neighbour's pixel values.
        :return: ``QPixmap``, or *None* if the array is unusable.
        """
        pixmap = self._neighbor_pixmaps.get(path)
        if pixmap is None:
            pixmap = self._render(raw)
            if pixmap is not None:
                self._neighbor_pixmaps[path] = pixmap
        return pixmap

    @Slot(int)
    def _on_prev_opacity_changed(self, value: int):
        """Fade the current image to reveal the previous image."""
        self._apply_opacity_fade(
            slider=self._prev_opacity_slider,
            other_slider=self._next_opacity_slider,
            offset=-1,
            value=value,
        )

    @Slot(int)
    def _on_next_opacity_changed(self, value: int):
        """Fade the current image to reveal the next image."""
        self._apply_opacity_fade(
            slider=self._next_opacity_slider,
            other_slider=self._prev_opacity_slider,
            offset=+1,
            value=value,
        )

    def _apply_opacity_fade(
        self, slider, other_slider, offset: int, value: int,
    ):
        """Reveal the wrap-around neighbour at *offset* under the
        current image.

        The two sliders are mutually exclusive — you cannot reveal the
        previous and next images at once — so engaging one snaps the
        other back to fully opaque.

        :param slider: The slider being dragged.
        :param other_slider: The opposite slider (reset to 100).
        :param offset: ``-1`` for the previous image, ``+1`` for next.
        :param value: This slider's value (0-100).
        """
        n = len(self._current_image_paths)
        if n < 2 or self._current_index < 0:
            return

        # Mutual exclusivity: return the other slider to fully opaque
        # without re-entering its handler.
        if other_slider.value() != 100:
            other_slider.blockSignals(True)
            other_slider.setValue(100)
            other_slider.blockSignals(False)

        neighbor_index = (self._current_index + offset) % n
        path = self._current_image_paths[neighbor_index]
        entry = self._get_neighbor(neighbor_index)
        pixmap = (
            self._neighbor_pixmap(path, entry[0])
            if entry is not None else None
        )

        if pixmap is None:
            # Missing/failed neighbour: cancel this fade, snap back.
            slider.blockSignals(True)
            slider.setValue(100)
            slider.blockSignals(False)
            self._fade_neighbor_path = None
            self._canvas.clear_neighbor()
            return

        self._fade_neighbor_path = path
        self._canvas.set_neighbor(pixmap, entry[1])
        self._canvas.set_current_opacity(value / 100.0)

    # -----------------------------------------------------------------
    # View Preservation
    # -----------------------------------------------------------------

    def _save_view(self):
        """Capture the canvas zoom/pan state so it can be restored
        after the next image is drawn.

        Delegates to ``ImageCanvasWidget.save_view``, which returns
        *None* when no image is loaded — so this is a no-op on an
        empty canvas.
        """
        self._preserved_view = self._canvas.save_view()

    def _restore_view(self):
        """Reapply a previously saved zoom/pan state, then clear it.

        Called at the end of ``_display_current_image`` so that
        Previous/Next navigation preserves the user's zoom level
        and position across images in the same directory.
        """
        if self._preserved_view is None:
            return
        self._canvas.restore_view(self._preserved_view)
        self._preserved_view = None

    # -----------------------------------------------------------------
    # Image Display
    # -----------------------------------------------------------------

    def _display_current_image(self):
        """Load and render the current image on the canvas."""
        if (
            self._current_index < 0
            or self._current_index >= len(self._current_image_paths)
        ):
            self._clear_canvas()
            self._clear_metadata()
            return

        # Drop any active cross-fade before the new image is drawn so a
        # lowered slider never persists across navigation (covers
        # Previous/Next, directory selection, and select_image).
        self._reset_opacity_sliders()
        self._current_raw = None
        self._set_histogram_available(True)

        image_path = self._current_image_paths[self._current_index]

        # Update labels
        self._image_name_label.setText(image_path.name)
        # The name is a reveal-in-folder link while a slice image is
        # shown; reveal_in_file_manager gracefully handles a
        # since-deleted file.
        self._image_name_label.set_clickable(True)
        self._image_name_label.setToolTip(AppStyles.AppText.IMAGE_NAME_LINK)
        self._image_counter_label.setText(
            f"{self._current_index + 1} / "
            f"{len(self._current_image_paths)}"
        )

        # Update metadata tree and extract overlay data
        self._populate_metadata(image_path)

        if not image_path.is_file():
            self._show_load_failure("Image file not found")
            return

        # Load at native resolution so wheel zoom can inspect full
        # image detail, keeping the stored pixel values for the
        # histogram and levels.
        raw = load_image_native(image_path)
        pixmap = self._render(raw) if raw is not None else None
        if pixmap is None:
            self._show_load_failure("Failed to load image")
            return
        self._current_raw = raw

        # Hand the canvas the pixmap, the (already image-pixel space)
        # overlay dict, and the pixel size for the scale bar.
        # ``set_image`` resets the view; the subsequent
        # ``_restore_view`` reapplies a saved view if Previous/Next is
        # in flight.
        pixel_size_x_m = (
            self._pixel_size_m[0] if self._pixel_size_m else None
        )
        self._canvas.set_image(
            pixmap, self._overlay_data, pixel_size_x_m,
        )
        self._canvas.set_overlay_visible(
            self._show_graphics_checkbox.isChecked()
        )
        self._set_ruler_available(pixel_size_x_m is not None)
        self._restore_view()
        self._refresh_histogram()

        logger.debug(
            f"Image displayed: {image_path.name} "
            f"({pixmap.width()}x{pixmap.height()})"
        )

    def _show_load_failure(self, text: str) -> None:
        """Show *text* in place of the image and empty the histogram."""
        self._current_raw = None
        self._canvas.set_error_text(text)
        self._set_ruler_available(False)
        self._refresh_histogram()

    def _clear_canvas(self):
        """Clear the image canvas."""
        self._canvas.clear()
        self._current_raw = None
        self._set_histogram_available(False)
        self._set_ruler_available(False)
        self._reset_opacity_sliders()
        self._image_name_label.setText("")
        self._image_name_label.set_clickable(False)
        self._image_name_label.setToolTip("")
        self._image_counter_label.setText("")

    # -----------------------------------------------------------------
    # Graphics Overlay
    # -----------------------------------------------------------------

    @staticmethod
    def _extract_overlay_data(metadata: dict) -> dict | None:
        """Guarded entry point for overlay extraction.

        Wraps :meth:`_compute_overlay_data` so that an unexpected
        metadata shape (e.g. ``PatternCenterPositionPx`` parsed as
        a string or list rather than a dict) degrades to *no
        overlay* instead of raising into the image-display slot.

        :param metadata: Full metadata dict from
            ``extract_image_metadata``.
        :return: Overlay dict or *None*.
        """
        try:
            return ImageViewerGroupBox._compute_overlay_data(metadata)
        except Exception:
            logger.debug(
                "Failed to compute overlay data; overlay disabled "
                "for this image",
                exc_info=True,
            )
            return None

    @staticmethod
    def _compute_overlay_data(metadata: dict) -> dict | None:
        """Extract overlay data from image metadata.

        Returns a dict consumed by ``ImageCanvasWidget`` to draw
        the crosshair and pattern rectangles, or *None* if the
        minimum required data is not present.

        The returned dict's keys:

        - ``center_px`` *(required)* — ``PatternCenterPositionPx``
          X/Y from ``MatchInformationCollection`` (image-pixel
          coordinates).
        - ``rectangles_image_px`` *(optional)* — list of
          ``{x, y, w, h}`` dicts in image-pixel space, with anchor
          adjustment, Y-axis negation, and origin selection (image
          center vs match center) all already applied.

        The pre-computation moves the coordinate-system logic from
        paint time to image-load time, keeping the canvas free of
        microscopy-specific conventions.

        :param metadata: Full metadata dict from
            ``extract_image_metadata``.
        :return: Overlay dict or *None*.
        """
        xml = metadata.get("XMLMetadata")
        if not xml:
            return None

        # -- PatternCenterPositionPx (required) ----------------------
        custom_sections = (
            xml
            .get("CustomSectionGroup", {})
            .get("CustomSection", {})
        )
        if not isinstance(custom_sections, dict):
            return None

        match_col = custom_sections.get(
            "MatchInformationCollection", {}
        )
        match_info = match_col.get("MatchInformation", {})
        # Multiple match attempts produce a list; use the first
        # entry to match the atlas widget's behavior.
        if isinstance(match_info, list):
            match_info = match_info[0] if match_info else {}
        if not isinstance(match_info, dict):
            return None
        pattern_center = match_info.get(
            "PatternCenterPositionPx", {}
        )
        center_x = pattern_center.get("X")
        center_y = pattern_center.get("Y")

        if center_x is None or center_y is None:
            return None

        try:
            center_x = float(center_x)
            center_y = float(center_y)
        except (TypeError, ValueError):
            return None

        result: dict = {
            "center_px": (center_x, center_y),
        }

        # -- Image dimensions from BinaryResult ----------------------
        binary_result = xml.get("BinaryResult", {})
        image_size = binary_result.get("ImageSize", {})
        img_w = image_size.get("X")
        img_h = image_size.get("Y")
        image_width: int | None = None
        image_height: int | None = None
        if img_w is not None and img_h is not None:
            try:
                image_width = int(img_w)
                image_height = int(img_h)
            except (TypeError, ValueError):
                pass

        # -- PixelSize from BinaryResult -----------------------------
        pixel_size = pixel_size_from_xml(xml)
        px_x, px_y = pixel_size if pixel_size else (None, None)

        # -- ActivityName from ProgressInformation -------------------
        progress_info = custom_sections.get(
            "ProgressInformation", {}
        )
        activity_name = progress_info.get("ActivityName", "")
        if not isinstance(activity_name, str):
            activity_name = ""

        # -- PatterningInformation rectangles ------------------------
        parsed_rects: list[dict] = []
        patterning_info = custom_sections.get(
            "PatterningInformation", {}
        )
        if isinstance(patterning_info, dict):
            raw_rects = patterning_info.get(
                "PatternDrawingRectangle"
            )
            if raw_rects is not None:
                # Normalise to list (single rect is a dict,
                # multiple rects produce a list)
                if isinstance(raw_rects, dict):
                    raw_rects = [raw_rects]
                if isinstance(raw_rects, list):
                    parsed_rects = _parse_pattern_rectangles(
                        raw_rects
                    )

        # -- Pre-compute image-pixel rectangles ----------------------
        # Combines anchor adjustment, physical→pixel scaling, the
        # Y-axis flip, and origin selection (image center vs match
        # center) so the canvas does not need to know about FEI
        # coordinate-system conventions.
        rectangles_image_px: list[dict] = []
        if parsed_rects and px_x is not None and px_y is not None:
            is_stress_relief = (
                "stress relief" in activity_name.lower()
            )
            if is_stress_relief:
                # Stress relief: origin = match center
                origin_x = center_x
                origin_y = center_y
            elif image_width is not None and image_height is not None:
                # Regular milling / polishing: origin = image center
                origin_x = image_width / 2
                origin_y = image_height / 2
            else:
                # No usable origin — leave the rectangle list empty
                # so the canvas just draws the crosshair.
                origin_x = None
                origin_y = None

            if origin_x is not None and origin_y is not None:
                rectangles_image_px = _rectangles_to_image_px(
                    parsed_rects,
                    pixel_size_x_m=px_x,
                    pixel_size_y_m=px_y,
                    origin_x_px=origin_x,
                    origin_y_px=origin_y,
                )

        if rectangles_image_px:
            result["rectangles_image_px"] = rectangles_image_px

        return result

    @Slot(bool)
    def _on_show_graphics_toggled(self, checked: bool):
        """Toggle the canvas overlay without reloading the image."""
        self._canvas.set_overlay_visible(checked)

    # -----------------------------------------------------------------
    # Histogram and Levels
    # -----------------------------------------------------------------

    def _render(self, raw: np.ndarray) -> QPixmap | None:
        """Render pixel values through the current levels.

        Manual levels apply to grayscale images only; a color image
        (an RGB plot) always shows its first channel with auto levels.

        :param raw: Pixel values from ``load_image_native``.
        :return: ``QPixmap``, or *None* if the array is unusable.
        """
        levels = self._levels if raw.ndim == 2 else None
        return numpy_to_qpixmap(raw, levels)

    @Slot(float, float)
    def _on_levels_changed(self, black: float, white: float):
        """Switch to Manual levels and re-render, keeping the view."""
        self._levels = (black, white)
        self._rerender()

    @Slot()
    def _on_levels_reset(self):
        """Return to auto levels."""
        self._levels = None
        self._rerender()
        self._refresh_histogram()

    def _rerender(self) -> None:
        """Re-render the current image, and any cross-faded neighbour,
        through the current levels without resetting the view."""
        self._neighbor_pixmaps.clear()
        if self._current_raw is not None:
            pixmap = self._render(self._current_raw)
            if pixmap is not None:
                self._canvas.update_pixmap(pixmap)

        path = self._fade_neighbor_path
        entry = self._neighbor_cache.get(path) if path else None
        if entry is not None:
            pixmap = self._neighbor_pixmap(path, entry[0])
            if pixmap is not None:
                self._canvas.set_neighbor(pixmap, entry[1])
                self._canvas.update()

    def _refresh_histogram(self) -> None:
        """Recompute the histogram of the current image while the
        panel is shown; a color image or failed load shows the
        placeholder."""
        if self._histogram.isHidden():
            return
        raw = self._current_raw
        if raw is None or raw.ndim != 2:
            self._histogram.clear()
            return
        self._histogram.set_histogram(raw, self._levels)

    def _set_histogram_available(self, available: bool) -> None:
        """Enable the Show histogram checkbox while an image is shown.

        The checkbox keeps its checked state while disabled, so the
        panel returns with the next image.
        """
        self._show_histogram_checkbox.setEnabled(available)
        self._update_histogram_panel()

    @Slot(bool)
    def _on_show_histogram_toggled(self, checked: bool):
        """Show or hide the histogram panel."""
        self._update_histogram_panel()

    def _update_histogram_panel(self) -> None:
        """Show the histogram panel while its checkbox is checked and
        enabled, restoring the width it had when last hidden."""
        visible = (
            self._show_histogram_checkbox.isChecked()
            and self._show_histogram_checkbox.isEnabled()
        )
        if visible == (not self._histogram.isHidden()):
            return

        sizes = self._canvas_splitter.sizes()
        if not visible:
            if sizes[1] > 0:
                self._histogram_width = sizes[1]
            self._histogram.setVisible(False)
            return

        self._histogram.setVisible(True)
        total = sum(sizes)
        if total > self._histogram_width:
            self._canvas_splitter.setSizes(
                [total - self._histogram_width, self._histogram_width]
            )
        self._refresh_histogram()

    # -----------------------------------------------------------------
    # Metadata Tree
    # -----------------------------------------------------------------

    def _populate_metadata(self, image_path: Path):
        """Extract and display metadata for the current image.

        Also extracts overlay data for the graphics checkbox and the
        pixel size for the scale bar.

        :param image_path: Absolute path to the image file.
        """
        if not image_path.is_file():
            self._clear_metadata()
            return

        try:
            metadata = extract_image_metadata(image_path)
        except Exception:
            logger.error(
                f"Failed to extract metadata: {image_path.name}",
                exc_info=True,
            )
            self._clear_metadata()
            return

        self._meta_panel.setVisible(True)
        self._meta_panel.populate(metadata)

        # Extract overlay data and update checkbox state
        self._overlay_data = self._extract_overlay_data(metadata)
        self._show_graphics_checkbox.setEnabled(
            self._overlay_data is not None
        )

        # The scale bar needs only the pixel size, not the graphics.
        self._pixel_size_m = extract_pixel_size_m(metadata)

    def _clear_metadata(self):
        """Reset the metadata tree to empty."""
        self._meta_panel.clear_tree()
        self._meta_panel.setVisible(False)
        self._overlay_data = None
        self._pixel_size_m = None
        self._show_graphics_checkbox.setEnabled(False)