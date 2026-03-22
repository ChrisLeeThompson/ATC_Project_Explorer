"""
Site Activity Bar Chart Widget

Horizontal bar chart showing per-activity durations for a single
lamella site. Each bar represents one activity from the Statistics
file, colored by its workflow step (Preparation, Milling, Thinning,
or Delay). Lamella Placement uses a distinct color to match the
global duration chart.

Duration labels appear at the end of each bar in HH:MM:SS format.
Hovering over a bar displays a tooltip with the activity name and
duration, and highlights the bar with a white border.

The x-axis is formatted in HH:MM:SS to match the application's
duration display convention. The widget height adjusts dynamically
based on the number of activities.

The widget wraps a matplotlib ``FigureCanvasQTAgg`` inside a
styled ``QGroupBox`` and follows the standard ``populate`` /
``clear`` interface used by the panel layer.
"""
import logging
from matplotlib.patches import Patch
from matplotlib.ticker import FuncFormatter
from script_modules.app_styles import AppStyles
from script_modules.consolidated_data_reader import (
    build_activity_step_map,
    parse_duration_to_seconds,
    format_seconds,
)
from script_modules.widgets.styled_chart_widget import StyledChartWidget


logger = logging.getLogger(__name__)


# Map workflow step (or special activity) to bar color.
# Lamella Placement gets its own color for consistency with
# the global duration bar chart.
_STEP_COLORS = {
    "Preparation":      AppStyles.Colors.PLOT_PREPARATION_BAR_COLOR,
    "Lamella Placement": AppStyles.Colors.PLOT_LAMELLA_PLACEMENT_BAR_COLOR,
    "Milling":          AppStyles.Colors.PLOT_MILLING_BAR_COLOR,
    "Thinning":         AppStyles.Colors.PLOT_THINNING_BAR_COLOR,
    "Delay":            AppStyles.Colors.PLOT_DELAY_BAR_COLOR,
}

# Legend display order
_LEGEND_ORDER = [
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


class SiteActivityBarChartWidget(StyledChartWidget):
    """Horizontal bar chart of per-activity durations for a single
    site."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._bar_rects: list[dict] = []
        self._connect_events()

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    def populate(self, site_data: dict) -> None:
        """Build the bar chart from a single site's data.

        Extracts activities from the site's ``Statistics`` block
        and colors each bar by its workflow step as determined by
        ``build_activity_step_map``.

        :param site_data: A single site entry from the consolidated
            metadata ``"Sites"`` list.
        """
        site_pd = site_data.get("SiteProjectData", {})
        stats = site_data.get("Statistics", {})
        activities = stats.get("Activities", [])

        if not activities:
            self._clear_axes()
            return

        step_map = build_activity_step_map(site_pd)

        # -- Extract activity data (reverse for top-to-bottom order) --
        act_names: list[str] = []
        act_seconds: list[int] = []
        act_colors: list[str] = []
        # Track which steps appear for the legend
        steps_seen: set[str] = set()

        for activity in reversed(activities):
            name = activity.get("ActivityName", "")
            secs = parse_duration_to_seconds(
                activity.get("Duration", "")
            )
            if secs is None:
                secs = 0

            # Determine color key
            step = step_map.get(name, "")
            if name == "Lamella Placement":
                color_key = "Lamella Placement"
            elif name == "Delay":
                color_key = "Delay"
            else:
                color_key = step

            color = _STEP_COLORS.get(
                color_key, AppStyles.Colors.TEXT_DISABLED
            )

            act_names.append(name)
            act_seconds.append(secs)
            act_colors.append(color)
            if color_key:
                steps_seen.add(color_key)

        # -- Convert to minutes for the axis --------------------------
        act_min = [s / 60 for s in act_seconds]

        # -- Plot -----------------------------------------------------
        self.ax.clear()
        self._style_axes()
        self._bar_rects.clear()

        y_positions = list(range(len(act_names)))
        bar_height = 0.5

        self.ax.barh(
            y_positions,
            act_min,
            height=bar_height,
            color=act_colors,
            zorder=2,
        )

        # Store bar rectangles for hover hit-testing
        for i, (name, secs, minutes) in enumerate(
            zip(act_names, act_seconds, act_min)
        ):
            if minutes <= 0:
                continue
            self._bar_rects.append({
                "y_index": i,
                "left": 0,
                "right": minutes,
                "y_bottom": i - bar_height / 2,
                "y_top": i + bar_height / 2,
                "label": name,
                "seconds": secs,
            })

        # -- Duration labels at bar ends ------------------------------
        x_max = max(act_min) if act_min else 1

        for i, (secs, minutes) in enumerate(
            zip(act_seconds, act_min)
        ):
            label = format_seconds(secs)
            self.ax.text(
                minutes + (x_max * 0.01), i, label,
                va="center", ha="left",
                color=AppStyles.Colors.TEXT_PRIMARY,
                fontsize=AppStyles.Dimensions.PLOT_LABEL_FONT_SIZE,
                zorder=3,
            )

        # -- X-axis formatting (HH:MM:SS) ----------------------------
        self.ax.xaxis.set_major_formatter(
            FuncFormatter(self._format_xaxis_tick)
        )

        # -- Axes labels and title ------------------------------------
        self.ax.set_yticks(y_positions)
        self.ax.set_yticklabels(act_names)
        self.ax.set_xlabel("\nDuration")

        site_name = site_data.get("SiteName", "Site")
        self.ax.set_title(
            f"{site_name} — Activity Durations",
            fontsize=AppStyles.Dimensions.PLOT_TITLE_FONT_SIZE,
        )

        # -- Legend (only steps that appear) --------------------------
        legend_handles = []
        legend_labels = []
        for key in _LEGEND_ORDER:
            if key in steps_seen:
                legend_handles.append(
                    Patch(facecolor=_STEP_COLORS[key])
                )
                legend_labels.append(key)

        if legend_handles:
            self.ax.legend(
                legend_handles,
                legend_labels,
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
            _CHART_PADDING_PX + len(act_names) * _BAR_HEIGHT_PX,
            AppStyles.Dimensions.PLOT_MINIMUM_HEIGHT,
        )
        self.setMinimumHeight(dynamic_height)

        # Create hover annotation (hidden until mouseover)
        self._create_annotation()

        self.canvas.draw_idle()
        logger.info(
            f"Site activity bar chart plotted: "
            f"{len(activities)} activity/activities for "
            f"'{site_name}'"
        )

    def clear(self) -> None:
        """Reset the chart to a blank state."""
        self._bar_rects.clear()
        self._annotation = None
        self._hover_rect = None
        self._clear_axes()

    # -----------------------------------------------------------------
    # Hover Tooltip
    # -----------------------------------------------------------------

    def _connect_events(self):
        """Connect matplotlib canvas events for hover interaction."""
        self.canvas.mpl_connect(
            "motion_notify_event", self._on_mouse_move
        )

    def _on_mouse_move(self, event):
        """Handle mouse movement: show or hide the hover tooltip.

        :param event: Matplotlib motion_notify_event.
        """
        if (
            self._annotation is None
            or event.inaxes != self.ax
            or not self._bar_rects
        ):
            self._hide_annotation()
            return

        hit = self._find_bar(event.xdata, event.ydata)
        if hit is None:
            self._hide_annotation()
            return

        # Build tooltip text
        duration_str = format_seconds(hit["seconds"])
        tooltip = f"{hit['label']}\n{duration_str}"

        # Position annotation at cursor
        self._annotation.xy = (event.xdata, event.ydata)
        self._annotation.set_text(tooltip)
        self._annotation.set_visible(True)

        # Position highlight rectangle around the bar
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

    def _find_bar(
        self, x: float, y: float
    ) -> dict | None:
        """Find the bar under the cursor.

        :param x: Cursor x in data coordinates (minutes).
        :param y: Cursor y in data coordinates.
        :return: Bar info dict, or *None* if no hit.
        """
        for rect in self._bar_rects:
            if (
                rect["left"] <= x <= rect["right"]
                and rect["y_bottom"] <= y <= rect["y_top"]
            ):
                return rect
        return None

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