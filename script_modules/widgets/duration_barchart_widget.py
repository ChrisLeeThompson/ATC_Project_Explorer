"""
Duration Bar Chart Widget

Horizontal stacked bar chart showing per-site milling durations
broken down by workflow step. Each bar has up to five segments
in execution order:

    1. Preparation (without lamella placement)
    2. Lamella placement
    3. Milling
    4. Thinning
    5. Delay

Hovering over a segment displays a tooltip with the segment name
and duration. Total duration labels appear at the end of each bar.

The x-axis is formatted in HH:MM:SS to match the duration display
used throughout the application.

The widget wraps a matplotlib ``FigureCanvasQTAgg`` inside a
styled ``QGroupBox`` and follows the standard ``populate`` /
``clear`` interface used by the panel layer.
"""
import logging
from matplotlib.ticker import FuncFormatter
from PySide6.QtWidgets import QMenu
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCursor
from script_modules.app_styles import AppStyles
from script_modules.consolidated_data_reader import (
    categorize_site_durations,
    format_seconds,
)
from script_modules.widgets.styled_chart_widget import StyledChartWidget


logger = logging.getLogger(__name__)


# Bar segment colors
_COLORS = {
    "Preparation":          AppStyles.Colors.PLOT_PREPARATION_BAR_COLOR,
    "Lamella Placement":    AppStyles.Colors.PLOT_LAMELLA_PLACEMENT_BAR_COLOR,
    "Milling":              AppStyles.Colors.PLOT_MILLING_BAR_COLOR,
    "Thinning":             AppStyles.Colors.PLOT_THINNING_BAR_COLOR,
    "Delay":                AppStyles.Colors.PLOT_DELAY_BAR_COLOR,
}

# Segment keys in execution order
_SEGMENT_ORDER = [
    "Preparation",
    "Lamella Placement",
    "Milling",
    "Thinning",
    "Delay",
]

# Dynamic height: per-bar height + fixed padding for title, axis,
# legend, and margins.
_BAR_HEIGHT_PX = 28
_CHART_PADDING_PX = 140


class DurationBarChartWidget(StyledChartWidget):
    """Horizontal stacked bar chart for per-site milling durations."""

    # Emitted when the user chooses "Open site" from the bar
    # context menu.  Carries the site name string.
    site_selected = Signal(str)

    # Emitted when the user chooses "Open site in new window"
    # from the bar context menu.  Carries the site name string.
    site_open_new_window = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._segment_rects: list[dict] = []
        # Site names indexed by bar position (the "y_index" stored in
        # each segment rect).  Built in reversed metadata order, so it
        # is navigated by name rather than index elsewhere.
        self._site_names: list[str] = []
        self._connect_events()

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    def populate(self, metadata: dict) -> None:
        """Build the bar chart from consolidated metadata.

        Uses ``build_activity_step_map`` to categorise each
        Statistics activity into its workflow step, then plots
        stacked horizontal bars per site.

        :param metadata: Consolidated metadata dictionary.
        """
        sites = metadata.get("Sites", [])
        if not sites:
            self._clear_axes()
            return

        # -- Extract per-site segment durations (seconds) -------------
        site_names: list[str] = []
        # Each entry is a dict: {segment_key: seconds}
        site_segments: list[dict[str, int]] = []

        for site in reversed(sites):
            name = site.get("SiteName", "Unknown")
            cat = categorize_site_durations(site)

            segments = {
                "Preparation":      cat.preparation_without_placement_s,
                "Lamella Placement": cat.lamella_placement_s,
                "Milling":          cat.milling_s,
                "Thinning":         cat.thinning_s,
                "Delay":            cat.delay_s,
            }

            site_names.append(name)
            site_segments.append(segments)

        # -- Plot -----------------------------------------------------
        self.ax.clear()
        self._style_axes()
        self._segment_rects.clear()

        # Retain the per-bar site names so a click can be resolved to
        # a site.  Segment rects store a "y_index" into this list.
        self._site_names = site_names

        y_positions = list(range(len(site_names)))
        bar_height = 0.5

        # Track which segments have non-zero data for the legend
        legend_segments: list[str] = []

        # Pre-compute segment index for efficient left-offset calculation
        _seg_index = {k: i for i, k in enumerate(_SEGMENT_ORDER)}

        # Draw each segment layer
        for seg_key in _SEGMENT_ORDER:
            values_min = [
                segs[seg_key] / 60 for segs in site_segments
            ]
            # Skip entirely empty segments (e.g. Delay = 0 for all)
            if all(v == 0 for v in values_min):
                continue

            legend_segments.append(seg_key)

            # Compute left offsets (sum of all prior segments)
            seg_idx = _seg_index[seg_key]
            lefts = []
            for segs in site_segments:
                left_s = sum(
                    segs[k] for k in _SEGMENT_ORDER[:seg_idx]
                )
                lefts.append(left_s / 60)

            self.ax.barh(
                y_positions,
                values_min,
                height=bar_height,
                left=lefts,
                color=_COLORS[seg_key],
                label=seg_key,
                zorder=1,
            )

            # Store segment rectangles for hover hit-testing
            for i, (left, width) in enumerate(
                zip(lefts, values_min)
            ):
                if width <= 0:
                    continue
                self._segment_rects.append({
                    "y_index": i,
                    "left": left,
                    "right": left + width,
                    "y_bottom": i - bar_height / 2,
                    "y_top": i + bar_height / 2,
                    "label": seg_key,
                    "seconds": site_segments[i][seg_key],
                })

        # -- Total duration labels at bar ends ------------------------
        totals_min = [
            sum(segs.values()) / 60 for segs in site_segments
        ]
        x_max = max(totals_min) if totals_min else 1

        for i, total_min in enumerate(totals_min):
            total_s = sum(site_segments[i].values())
            label = format_seconds(total_s)
            self.ax.text(
                total_min + (x_max * 0.01), i, label,
                va="center", ha="left",
                color=AppStyles.Colors.TEXT_PRIMARY,
                fontsize=AppStyles.Dimensions.PLOT_LABEL_FONT_SIZE,
                zorder=2,
            )

        # -- X-axis formatting (HH:MM:SS) ----------------------------
        self.ax.xaxis.set_major_formatter(
            FuncFormatter(self._format_xaxis_tick)
        )

        # -- Axes labels and legend -----------------------------------
        self.ax.set_yticks(y_positions)
        self.ax.set_yticklabels(site_names)
        self.ax.set_xlabel("\nDuration")
        self.ax.set_title(
            "Site Durations\n",
            fontsize=AppStyles.Dimensions.PLOT_TITLE_FONT_SIZE,
        )

        if legend_segments:
            self.ax.legend(
                loc="upper right",
                fontsize=AppStyles.Dimensions.PLOT_LABEL_FONT_SIZE,
                facecolor=AppStyles.Colors.INPUT_BG,
                edgecolor=AppStyles.Colors.PLOT_SPINE_COLOR,
                labelcolor=AppStyles.Colors.TEXT_PRIMARY,
            )

        # Pad x-axis so labels aren't clipped
        self.ax.set_xlim(0, x_max * 1.18 if x_max > 0 else 1)

        # Adjust widget height based on number of bars
        dynamic_height = max(
            _CHART_PADDING_PX + len(site_names) * _BAR_HEIGHT_PX,
            AppStyles.Dimensions.PLOT_MINIMUM_HEIGHT,
        )
        self.setMinimumHeight(dynamic_height)

        # Create hover annotation (hidden until mouseover)
        self._create_annotation()

        self.canvas.draw_idle()
        logger.info(
            f"Duration bar chart plotted: {len(sites)} site(s)"
        )

    def clear(self) -> None:
        """Reset the chart to a blank state."""
        self._segment_rects.clear()
        self._site_names = []
        self._annotation = None
        self._hover_rect = None
        self._clear_axes()

    # -----------------------------------------------------------------
    # Hover Tooltip
    # -----------------------------------------------------------------

    def _connect_events(self):
        """Connect matplotlib canvas events for hover and click."""
        self.canvas.mpl_connect(
            "motion_notify_event", self._on_mouse_move
        )
        self.canvas.mpl_connect(
            "button_press_event", self._on_mouse_click
        )

    def _on_mouse_move(self, event):
        """Handle mouse movement: show or hide the hover tooltip.

        :param event: Matplotlib motion_notify_event.
        """
        if (
            self._annotation is None
            or event.inaxes != self.ax
            or not self._segment_rects
        ):
            self.canvas.unsetCursor()
            self._hide_annotation()
            return

        hit = self._find_segment(event.xdata, event.ydata)
        if hit is None:
            self.canvas.unsetCursor()
            self._hide_annotation()
            return

        # A bar is under the cursor: signal that it is clickable.
        self.canvas.setCursor(
            QCursor(Qt.CursorShape.PointingHandCursor)
        )

        # Build tooltip text
        duration_str = format_seconds(hit["seconds"])
        tooltip = f"{hit['label']}\n{duration_str}"

        # Position annotation at cursor
        self._annotation.xy = (event.xdata, event.ydata)
        self._annotation.set_text(tooltip)
        self._annotation.set_visible(True)

        # Position highlight rectangle around the segment
        if self._hover_rect:
            self._hover_rect.set_xy(
                (hit["left"], hit["y_bottom"])
            )
            self._hover_rect.set_width(
                hit["right"] - hit["left"]
            )
            self._hover_rect.set_height(
                hit["y_top"] - hit["y_bottom"]
            )
            self._hover_rect.set_visible(True)

        self.canvas.draw_idle()

    def _find_segment(
        self, x: float, y: float
    ) -> dict | None:
        """Find the bar segment under the cursor.

        :param x: Cursor x in data coordinates (minutes).
        :param y: Cursor y in data coordinates.
        :return: Segment info dict, or *None* if no hit.
        """
        for rect in self._segment_rects:
            if (
                rect["left"] <= x <= rect["right"]
                and rect["y_bottom"] <= y <= rect["y_top"]
            ):
                return rect
        return None

    # -----------------------------------------------------------------
    # Click Navigation
    # -----------------------------------------------------------------

    def _on_mouse_click(self, event):
        """Show a context menu when a site bar is left-clicked.

        :param event: Matplotlib button_press_event.
        """
        if (
            event.inaxes != self.ax
            or not self._segment_rects
            or event.button != 1  # left click only
        ):
            return

        hit = self._find_segment(event.xdata, event.ydata)
        if hit is None:
            return

        y_index = hit["y_index"]
        if not 0 <= y_index < len(self._site_names):
            return

        site_name = self._site_names[y_index]
        self._show_context_menu(site_name)

    def _show_context_menu(self, site_name: str) -> None:
        """Display a context menu at the cursor with actions for
        the clicked site.

        :param site_name: Name of the clicked site.
        """
        menu = QMenu(self)
        menu.setStyleSheet(AppStyles.ComboBox.context_menu())

        go_to_action = menu.addAction(f"Open {site_name}")
        open_new_action = menu.addAction(
            f"Open {site_name} in new window"
        )

        chosen = menu.exec(QCursor.pos())

        if chosen == go_to_action:
            logger.info(f"Duration chart menu: open '{site_name}'")
            self.site_selected.emit(site_name)
        elif chosen == open_new_action:
            logger.info(
                f"Duration chart menu: open '{site_name}' "
                f"in new window"
            )
            self.site_open_new_window.emit(site_name)

    # -----------------------------------------------------------------
    # Formatting Helpers
    # -----------------------------------------------------------------

    @staticmethod
    def _format_xaxis_tick(value_min: float, _pos) -> str:
        """Format an x-axis tick value from minutes to ``HH:MM:SS``.

        :param value_min: Tick value in minutes.
        :param _pos: Tick position (unused, required by matplotlib).
        :return: Formatted duration string.
        """
        total_seconds = max(int(round(value_min * 60)), 0)
        return format_seconds(total_seconds)