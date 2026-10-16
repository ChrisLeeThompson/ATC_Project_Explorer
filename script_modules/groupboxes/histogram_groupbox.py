"""
Histogram GroupBox

Side panel of the Image Viewer: a vertical histogram of the current
image's pixel values (pixel value on the Y axis, minimum at the bottom;
log-scaled counts extending to the right) with two draggable level lines
that set the displayed black point and white point.

Each line carries a value box at its right edge showing its pixel value;
the box doubles as a drag handle.  The lines may pass each other: the
viewer renders a black point above the white point as an inverted image.
Levels outside the image's value range are drawn where they are, with
the value axis widened to include them.

Per the project convention the groupbox owns only widgets and drag
state and exposes signals; the Image Viewer decides the levels and
applies them to the image:

- ``levels_changed(black_point, white_point)``: emitted live during a
  drag and on release, always in (black, white) order regardless of
  which line is on top.
- ``levels_reset()``: the Reset button was clicked.

All colors and style dimensions come from ``AppStyles``.
"""
import logging
import math

import numpy as np
import matplotlib.transforms as mtransforms
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from PySide6.QtWidgets import (
    QGroupBox, QVBoxLayout, QPushButton, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal

from script_modules.app_styles import AppStyles
from script_modules.widgets.mpl_draw_guard import install_stale_draw_guard


logger = logging.getLogger(__name__)


# Maximum number of bins.  Integer images use integer-aligned bins (one
# or more whole pixel values each), so a narrow value range leaves no
# empty bins between populated ones.
_MAX_BINS = 256

# Fraction of the value range used to keep the two levels from being
# exactly equal while one line passes the other.
_LEVEL_EPSILON_FRACTION = 1.0 / 4096.0

# Horizontal position of the value boxes, as a fraction of the axes
_VALUE_BOX_X = 0.97

_PLACEHOLDER = "No histogram"


def _compute_histogram(
    img: np.ndarray, data_min: float, data_max: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Count an image's pixel values into at most ``_MAX_BINS`` bins.

    :param img: 2-D array of pixel values.
    :param data_min: Lowest pixel value in *img*.
    :param data_max: Highest pixel value in *img*.
    :return: ``(counts, centers)``, with bin centers in pixel values.
    """
    if np.issubdtype(img.dtype, np.integer):
        low = int(data_min)
        n_values = int(data_max) - low + 1
        width = max(1, math.ceil(n_values / _MAX_BINS))
        n_bins = math.ceil(n_values / width)
        if img.dtype in (np.uint8, np.uint16):
            # Count each value once, then sum whole values into bins;
            # about 3x faster than np.histogram on large images.
            per_value = np.bincount(
                img.ravel(), minlength=int(data_max) + 1
            )[low:]
            grouped = np.zeros(n_bins * width, dtype=per_value.dtype)
            grouped[:n_values] = per_value
            counts = grouped.reshape(n_bins, width).sum(axis=1)
        else:
            # Edges on half-integers, so no pixel value sits on an edge.
            counts, _ = np.histogram(
                img, bins=n_bins,
                range=(low - 0.5, low - 0.5 + n_bins * width),
            )
        centers = low + width * np.arange(n_bins) + (width - 1) / 2.0
        return counts, centers

    upper = data_max if data_max > data_min else data_min + 1.0
    counts, edges = np.histogram(
        img, bins=_MAX_BINS, range=(data_min, upper)
    )
    return counts, (edges[:-1] + edges[1:]) / 2.0


class HistogramGroupBox(QGroupBox):
    """Vertical image histogram with draggable black/white level lines.

    The Image Viewer feeds it the current image with
    :meth:`set_histogram`, passing its Manual levels, or *None* for
    auto levels (the image's own value range).
    """

    # Live level updates: (black_point, white_point) in pixel values,
    # in that order regardless of which line is above the other.
    levels_changed = Signal(float, float)

    # Reset button clicked; the viewer returns to auto levels.
    levels_reset = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        # Value axis range (pixel values); None until the first
        # histogram.  It covers the image's values and both levels.
        self._range_min: float | None = None
        self._range_max: float | None = None
        self._integer_values = False

        # Level state (pixel values); None until the first histogram
        self._black: float | None = None
        self._white: float | None = None

        # Artists (recreated per set_histogram)
        self._black_line = None
        self._white_line = None
        self._black_box = None
        self._white_box = None

        # Drag state: None, "black", or "white".  _drag_moved guards the
        # release emit so a motionless click does not switch the viewer
        # to Manual levels.
        self._dragging: str | None = None
        self._drag_moved = False
        # Cursor currently applied to the canvas (avoids re-setting it
        # on every hover motion event).
        self._hover_cursor = None
        # constrained_layout is frozen after the first settled draw so a
        # level drag can't reflow the axes; re-thawed per set_histogram.
        self._layout_frozen = False

        self._create_widgets()
        self._setup_layout()
        self._connect_signals()
        # No draw request at construction: the panel starts hidden
        # (a zero-size canvas breaks constrained_layout), and showing it
        # repaints via the canvas resize event anyway.
        self._show_placeholder(request_draw=False)

    # -----------------------------------------------------------------
    # Setup
    # -----------------------------------------------------------------

    def _create_widgets(self):
        """Create the Reset button and the histogram canvas."""
        self.reset_button = QPushButton("Reset", parent=self)
        self.reset_button.setStyleSheet(AppStyles.Button.default())
        self.reset_button.setEnabled(False)
        self.reset_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self.figure = Figure(
            facecolor=AppStyles.Colors.HISTOGRAM_FIGURE_BG,
            constrained_layout=True,
        )
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.canvas.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.canvas.setStyleSheet(
            f"background-color: {AppStyles.Colors.HISTOGRAM_FIGURE_BG};"
        )
        self.figure.set_dpi(AppStyles.Dimensions.PLOT_NOMINAL_DPI)
        self.ax = self.figure.add_subplot(111)
        self._style_axes()

        # Detached site windows are freed on close, so a draw pending
        # on this canvas at that moment would fire on the freed widget.
        install_stale_draw_guard(self.canvas)

    def _setup_layout(self):
        """Stack the Reset button above the canvas."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(AppStyles.Dimensions.LAYOUT_VSPACING)
        layout.addWidget(self.reset_button)
        layout.addWidget(self.canvas, 1)
        self.setStyleSheet(AppStyles.GroupBox.embedded_untitled())
        self.setMinimumWidth(
            AppStyles.Dimensions.HISTOGRAM_PANEL_MINIMUM_WIDTH
        )

    def _connect_signals(self):
        """Connect the Reset button and the canvas mouse events."""
        self.reset_button.clicked.connect(self.levels_reset)
        self.canvas.mpl_connect("button_press_event", self._on_mouse_press)
        self.canvas.mpl_connect("motion_notify_event", self._on_mouse_move)
        self.canvas.mpl_connect(
            "button_release_event", self._on_mouse_release
        )
        self.canvas.mpl_connect("figure_leave_event", self._on_figure_leave)
        # Freeze constrained_layout after the first settled draw; a
        # panel resize thaws it so the tick-label width re-fits.
        self.canvas.mpl_connect("draw_event", self._freeze_layout_once)
        self.canvas.mpl_connect("resize_event", self._thaw_layout)

    def _style_axes(self):
        """Dark plot styling; the plot area matches the image canvas."""
        ax = self.ax
        ax.set_facecolor(AppStyles.Colors.HISTOGRAM_BG)
        # Counts are log-scaled and not meant to be read off: hide the
        # x ticks and keep small pixel-value ticks on y.
        ax.tick_params(
            axis="y", colors=AppStyles.Colors.PLOT_SPINE_COLOR,
            labelsize=AppStyles.Dimensions.HISTOGRAM_TICK_LABEL_SIZE,
        )
        ax.tick_params(axis="x", bottom=False, labelbottom=False)
        ax.ticklabel_format(axis="y", style="plain", useOffset=False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color(AppStyles.Colors.PLOT_SPINE_COLOR)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    def set_histogram(
        self,
        img: np.ndarray | None,
        levels: tuple[float, float] | None = None,
    ) -> None:
        """Compute and display the histogram of a grayscale image.

        :param img: 2-D array of pixel values; anything else shows the
            placeholder.
        :param levels: Manual ``(black_point, white_point)``, or *None*
            for auto levels at the image's own value range.
        """
        if img is None or img.ndim != 2 or img.size == 0:
            self.clear()
            return

        # Re-fit the axes to this image's tick-label widths, then let
        # the next draw re-freeze the layout.
        self._thaw_layout()

        data_min = float(img.min())
        data_max = float(img.max())
        counts, centers = _compute_histogram(img, data_min, data_max)
        if data_max <= data_min:
            data_max = data_min + 1.0  # flat image: keep a usable range
        self._integer_values = np.issubdtype(img.dtype, np.integer)

        if levels is None:
            self._black, self._white = data_min, data_max
        else:
            self._black, self._white = (float(v) for v in levels)
        self._range_min = min(data_min, self._black, self._white)
        self._range_max = max(data_max, self._black, self._white)

        log_counts = np.log1p(counts)
        self.ax.clear()
        self._style_axes()
        self.ax.plot(
            log_counts, centers,
            color=AppStyles.Colors.HISTOGRAM_TRACE_COLOR,
            linewidth=AppStyles.Dimensions.HISTOGRAM_TRACE_WIDTH,
        )
        self.ax.fill_betweenx(
            centers, 0, log_counts,
            color=AppStyles.Colors.HISTOGRAM_TRACE_COLOR,
            alpha=AppStyles.Dimensions.HISTOGRAM_FILL_ALPHA,
            linewidth=0,
        )
        x_max = float(log_counts.max()) if counts.any() else 1.0
        self.ax.set_xlim(0, x_max * 1.05)
        self.ax.set_ylim(self._range_min, self._range_max)

        self._rebuild_level_artists()
        self.reset_button.setEnabled(True)
        self._request_draw()

    def current_levels(self) -> tuple[float, float] | None:
        """The ``(black_point, white_point)`` levels, or *None* while
        the placeholder is shown."""
        if self._black is None or self._white is None:
            return None
        return (self._black, self._white)

    def clear(self) -> None:
        """Reset to the placeholder state (no image, a color image, or
        a failed load)."""
        self._range_min = None
        self._range_max = None
        self._black = None
        self._white = None
        self._black_line = self._white_line = None
        self._black_box = self._white_box = None
        self._dragging = None
        self._set_cursor(Qt.CursorShape.ArrowCursor)
        self.reset_button.setEnabled(False)
        self._show_placeholder()

    # -----------------------------------------------------------------
    # Level line artists
    # -----------------------------------------------------------------

    def _rebuild_level_artists(self):
        """Create the level lines and value boxes on freshly drawn axes."""
        line_kwargs = dict(
            color=AppStyles.Colors.HISTOGRAM_LEVEL_LINE_COLOR,
            linewidth=AppStyles.Dimensions.HISTOGRAM_LEVEL_LINE_WIDTH,
        )
        self._black_line = self.ax.axhline(self._black, **line_kwargs)
        self._white_line = self.ax.axhline(self._white, **line_kwargs)

        # Value boxes: pinned to the right edge (x in axes coordinates),
        # riding their line (y in data coordinates).  They double as
        # drag handles via the shared y-distance hit test.
        box_transform = mtransforms.blended_transform_factory(
            self.ax.transAxes, self.ax.transData
        )
        text_kwargs = dict(
            transform=box_transform,
            ha="right", va="center",
            fontsize=AppStyles.Dimensions.HISTOGRAM_VALUE_FONT_SIZE,
            color=AppStyles.Colors.HISTOGRAM_VALUE_TEXT_COLOR,
            bbox=dict(
                boxstyle=(
                    f"round,pad="
                    f"{AppStyles.Dimensions.HISTOGRAM_VALUE_BOX_PAD}"
                ),
                facecolor=AppStyles.Colors.HISTOGRAM_VALUE_BOX_BG,
                edgecolor=AppStyles.Colors.HISTOGRAM_LEVEL_LINE_COLOR,
                linewidth=AppStyles.Dimensions.HISTOGRAM_VALUE_BOX_EDGE_WIDTH,
            ),
            zorder=10,
        )
        self._black_box = self.ax.text(
            _VALUE_BOX_X, self._black, self._format_value(self._black),
            **text_kwargs,
        )
        self._white_box = self.ax.text(
            _VALUE_BOX_X, self._white, self._format_value(self._white),
            **text_kwargs,
        )

    def _update_level_artists(self):
        """Move the existing lines and value boxes to the levels."""
        if self._black_line is None:
            return
        self._black_line.set_ydata([self._black, self._black])
        self._white_line.set_ydata([self._white, self._white])
        self._black_box.set_position((_VALUE_BOX_X, self._black))
        self._black_box.set_text(self._format_value(self._black))
        self._white_box.set_position((_VALUE_BOX_X, self._white))
        self._white_box.set_text(self._format_value(self._white))

    def _format_value(self, value: float) -> str:
        if self._integer_values:
            return f"{value:.0f}"
        return f"{value:.4g}"

    def _show_placeholder(self, request_draw: bool = True):
        self.ax.clear()
        self._style_axes()
        self.ax.set_xticks([])
        self.ax.set_yticks([])
        for spine in self.ax.spines.values():
            spine.set_visible(False)
        self.ax.text(
            0.5, 0.5, _PLACEHOLDER,
            ha="center", va="center",
            color=AppStyles.Colors.TEXT_DISABLED,
            fontsize=AppStyles.Dimensions.HISTOGRAM_PLACEHOLDER_FONT_SIZE,
            transform=self.ax.transAxes,
        )
        if request_draw:
            self._request_draw()

    def _freeze_layout_once(self, event):
        """Lock the axes position after the first settled draw so a
        level drag can't trigger a constrained_layout reflow.  No-op
        until the canvas has a real size."""
        if self._layout_frozen:
            return
        if self.canvas.width() <= 1 or self.canvas.height() <= 1:
            return
        self._layout_frozen = True
        self.figure.set_layout_engine("none")

    def _thaw_layout(self, event=None):
        """Re-enable constrained_layout so the axes re-fit (a new
        image's tick labels, or a panel resize); the next draw
        re-freezes."""
        self._layout_frozen = False
        self.figure.set_layout_engine("constrained")

    def _request_draw(self):
        """Redraw unless the canvas has (near-)zero size.

        constrained_layout divides by zero on a zero-width figure, and
        showing the panel triggers a fresh paint via the canvas resize
        event regardless.
        """
        if self.canvas.width() > 1 and self.canvas.height() > 1:
            self.canvas.draw_idle()

    # -----------------------------------------------------------------
    # Line dragging
    # -----------------------------------------------------------------

    def _level_epsilon(self) -> float:
        return (self._range_max - self._range_min) * _LEVEL_EPSILON_FRACTION

    def _hit_test(self, event) -> str | None:
        """Which line (or its value box) the event grabs, if any.

        Works in display pixels so it catches an edge line even when
        the press lands just outside the axes (``event.inaxes`` is None
        but ``event.x``/``y`` are still set).  The vertical radius
        covers the thin line and the value box centered on it; the
        horizontal check keeps tick-label clicks from grabbing.
        """
        if self._black is None or event.x is None or event.y is None:
            return None
        radius = AppStyles.Dimensions.HISTOGRAM_HIT_RADIUS_PX
        bbox = self.ax.get_window_extent()
        if not (bbox.x0 - radius <= event.x <= bbox.x1 + radius):
            return None
        hits = {}
        for which, value in (("black", self._black), ("white", self._white)):
            _, line_y = self.ax.transData.transform((0, value))
            distance = abs(event.y - line_y)
            if distance <= radius:
                hits[which] = distance
        if not hits:
            return None
        return min(hits, key=hits.get)

    def _event_data_y(self, event) -> float | None:
        """Data-space y of an event, even when the cursor has strayed
        past the top or bottom spine (``event.ydata`` is then None)."""
        if event.ydata is not None:
            return float(event.ydata)
        if event.x is None or event.y is None:
            return None
        return float(
            self.ax.transData.inverted().transform((event.x, event.y))[1]
        )

    def _on_mouse_press(self, event):
        # No inaxes check: an edge line sits on a spine, so a valid grab
        # can land just outside the axes (the hit test uses pixels).
        if event.button != 1:
            return
        self._dragging = self._hit_test(event)
        self._drag_moved = False

    def _on_mouse_move(self, event):
        if self._dragging is None:
            self._update_hover_cursor(event)
            return

        data_y = self._event_data_y(event)
        if data_y is None:
            return
        value = min(max(data_y, self._range_min), self._range_max)

        # Lines may pass each other freely (black above white inverts
        # the image); only exact equality is nudged apart so the window
        # never degenerates mid-crossing.  The nudge points toward the
        # interior so the level stays within the axis range.
        other = self._white if self._dragging == "black" else self._black
        if value == other:
            eps = self._level_epsilon() or 1e-9
            midpoint = (self._range_min + self._range_max) / 2
            value = other - eps if other >= midpoint else other + eps

        if self._dragging == "black":
            self._black = value
        else:
            self._white = value

        self._drag_moved = True
        self._update_level_artists()
        self._request_draw()
        self.levels_changed.emit(self._black, self._white)

    def _on_mouse_release(self, event):
        # Only the left button ends a level drag; a stray middle or
        # right release mid-drag must not abort it.  Only a drag that
        # actually moved emits.
        if event.button != 1:
            return
        if self._dragging is not None and self._drag_moved:
            self.levels_changed.emit(self._black, self._white)
        self._dragging = None
        self._drag_moved = False

    # -----------------------------------------------------------------
    # Hover cursor
    # -----------------------------------------------------------------

    def _update_hover_cursor(self, event):
        """Show a vertical double-headed arrow over a draggable line."""
        over_line = self._hit_test(event) is not None
        cursor = (Qt.CursorShape.SizeVerCursor if over_line
                  else Qt.CursorShape.ArrowCursor)
        self._set_cursor(cursor)

    def _on_figure_leave(self, event):
        self._set_cursor(Qt.CursorShape.ArrowCursor)

    def _set_cursor(self, cursor):
        if cursor != self._hover_cursor:
            self._hover_cursor = cursor
            self.canvas.setCursor(cursor)
