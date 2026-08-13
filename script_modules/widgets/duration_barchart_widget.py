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

Each site row also carries a drawn checkbox left of the site title,
used to include or exclude the site from the Global Statistics
selection; the site title itself is clickable and opens the same
context menu as the bars. A labelled tri-state master checkbox
sits at the top of the checkbox column (solid = all checked,
empty = none, dash = partial) and toggles the whole selection. The
widget owns no selection truth: it reports user intent through
Signals and is restyled via ``set_site_selection`` by the owning
panel.

The x-axis is formatted in HH:MM:SS to match the duration display
used throughout the application.

The widget wraps a matplotlib ``FigureCanvasQTAgg`` inside a
styled ``QGroupBox`` and follows the standard ``populate`` /
``clear`` interface used by the panel layer.
"""
import logging
from matplotlib.offsetbox import AnnotationBbox, DrawingArea
from matplotlib.patches import FancyBboxPatch, Rectangle
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

# Dynamic height: per-bar height + fixed padding for the title, the
# horizontal legend band above the axes (which also hosts the master
# checkbox), the x-axis, and margins.
_BAR_HEIGHT_PX = 28
_CHART_PADDING_PX = 160

# Label beside the master checkbox.  Names the control (checking it
# selects every site); the box itself shows the current state.
_MASTER_LABEL = "Select All"


def _px_to_pt(px: float) -> float:
    """Convert logical pixels at the nominal figure dpi to points.

    Deliberately uses ``PLOT_NOMINAL_DPI`` instead of the runtime
    figure dpi: Qt multiplies the figure dpi by the screen's
    devicePixelRatio, and matplotlib already scales points by that
    same factor at render time, so converting with the runtime dpi
    would double-count the scaling (shrunken checkboxes on scaled
    Windows displays).
    """
    return px * 72.0 / AppStyles.Dimensions.PLOT_NOMINAL_DPI


class DurationBarChartWidget(StyledChartWidget):
    """Horizontal stacked bar chart for per-site milling durations."""

    # Emitted when the user chooses "Open site" from the bar
    # context menu.  Carries the site name string.
    site_selected = Signal(str)

    # Emitted when the user chooses "Open site in new window"
    # from the bar context menu.  Carries the site name string.
    site_open_new_window = Signal(str)

    # Emitted when the user toggles one row checkbox.  Carries the
    # site name and the new checked state.
    site_check_toggled = Signal(str, bool)

    # Emitted by the master checkbox.  Stateless requests: the
    # owning panel updates the canonical selection and pushes it
    # back through set_site_selection().
    select_all_requested = Signal()
    deselect_all_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._segment_rects: list[dict] = []
        # Site names indexed by bar position (the "y_index" stored in
        # each segment rect).  Built in reversed metadata order, so it
        # is navigated by name rather than index elsewhere.
        self._site_names: list[str] = []
        # Drawn checkbox artists, one dict per bar row (parallel to
        # _site_names): {"name", "ab", "box"}.
        self._checkbox_rows: list[dict] = []
        # Checked state per bar row (parallel to _checkbox_rows).
        self._row_checked: list[bool] = []
        # Tri-state master checkbox atop the column:
        # {"ab", "box", "dash"} or None.
        self._master_checkbox: dict | None = None
        # Column anchor offset (points left of the spine), set by
        # _create_row_checkboxes and shared with the master.
        self._column_offset_pt = 0.0
        # Site title label currently hover-highlighted, if any.
        self._hovered_tick_label = None
        # Window extents are only trustworthy after a completed
        # draw; between (re)populate and the next paint the fresh
        # checkbox artists would all hit-test at the canvas origin.
        self._layout_ready = False
        self._connect_events()

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    def populate(self, metadata: dict) -> None:
        """Build the bar chart from consolidated metadata.

        Uses ``build_activity_step_map`` to categorise each
        Statistics activity into its workflow step, then plots
        stacked horizontal bars per site. Every row gets a drawn
        checkbox (all checked by default); no selection signal is
        emitted from here.

        :param metadata: Consolidated metadata dictionary.
        """
        sites = metadata.get("Sites", [])
        if not sites:
            # Reset the interactive state too — without this, a
            # re-populate with no sites would leave stale hit-test
            # targets and ghost checkbox state behind.
            self._reset_interactive_state()
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
        self._reset_interactive_state()

        # Retain the per-bar site names so a click can be resolved to
        # a site.  Segment rects store a "y_index" into this list.
        self._site_names = site_names

        y_positions = list(range(len(site_names)))
        bar_height = 0.5

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

        # -- Axes labels ----------------------------------------------
        self.ax.set_yticks(y_positions)
        self.ax.set_yticklabels(site_names)
        self.ax.set_xlabel("\nDuration")

        # Site titles sit right-aligned against the axis with a
        # small pad; the checkbox column goes left of the widest
        # title (see _create_row_checkboxes).
        self.ax.tick_params(
            axis="y",
            pad=_px_to_pt(AppStyles.Dimensions.PLOT_CHECKBOX_GAP_PX),
        )
        self._create_row_checkboxes()
        self._create_master_checkbox()

        # -- Title and legend ------------------------------------------
        # Legend entries auto-collect from the labelled barh calls;
        # all-zero segments were skipped above, so they get none.
        self._set_title_and_top_legend("Site Durations")

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
        self._reset_interactive_state()
        self._annotation = None
        self._hover_rect = None
        self._clear_axes()

    def set_site_selection(self, selected: set[str]) -> None:
        """Programmatically set the row checkbox states.

        Restyles every row whose site name matches, so duplicate
        site names stay visually coherent. Never emits a signal —
        this is the panel's push-back path, and emitting here
        would loop.

        :param selected: Names of the sites to show as checked.
            Names without a chart row are ignored.
        """
        changed = False
        for i, row in enumerate(self._checkbox_rows):
            want = row["name"] in selected
            if self._row_checked[i] != want:
                self._row_checked[i] = want
                self._apply_row_visual(i)
                changed = True
        if changed:
            self._update_master_visual()
            self.canvas.draw_idle()

    def checked_sites(self) -> list[str]:
        """Names of the sites whose row checkbox is checked, in
        chart row order (reversed metadata order)."""
        return [
            row["name"]
            for row, checked in zip(
                self._checkbox_rows, self._row_checked
            )
            if checked
        ]

    # -----------------------------------------------------------------
    # Row Checkboxes
    # -----------------------------------------------------------------

    def _reset_interactive_state(self) -> None:
        """Forget all hit-test targets and per-row checkbox state.

        The artists themselves die with ``ax.clear()``; this drops
        the references so stale rows can never be hit-tested or
        reported after a re-populate or clear.
        """
        self._segment_rects.clear()
        self._site_names = []
        self._checkbox_rows = []
        self._row_checked = []
        self._master_checkbox = None
        self._column_offset_pt = 0.0
        self._hovered_tick_label = None
        self._layout_ready = False

    def _create_row_checkboxes(self) -> None:
        """Create one drawn checkbox per bar row, all checked.

        The checkboxes form a vertical column to the LEFT of the
        site titles: every box anchors at the same fixed offset
        from the left spine, chosen to clear the widest title
        (titles are right-aligned, so their left edges are ragged).
        Each checkbox is an ``AnnotationBbox`` holding a rounded
        ``FancyBboxPatch`` in a ``DrawingArea`` (fixed physical
        size, specified in points). Checked/unchecked is a
        fill/edge colour flip matching the application's QCheckBox
        indicator style.
        """
        gap_pt = _px_to_pt(AppStyles.Dimensions.PLOT_CHECKBOX_GAP_PX)
        name_gap_pt = _px_to_pt(
            AppStyles.Dimensions.PLOT_CHECKBOX_NAME_GAP_PX
        )

        # Text width depends only on font and dpi — never on the
        # layout — so the widest title can be measured before the
        # first draw. The extent is in physical pixels at the
        # RUNTIME dpi, so this one conversion uses the runtime dpi
        # (the devicePixelRatio cancels between the measurement
        # and the point-based offset).
        renderer = self.canvas.get_renderer()
        max_label_w_px = max(
            (
                label.get_window_extent(renderer).width
                for label in self.ax.get_yticklabels()
            ),
            default=0.0,
        )
        max_label_w_pt = (
            max_label_w_px * 72.0 / self.figure.get_dpi()
        )
        # Spine -> tick mark -> label pad -> widest label ->
        # name gap -> checkbox. The outward tick mark length is
        # part of the label offset (get_tick_padding returns it
        # in points).
        self._column_offset_pt = (
            self.ax.yaxis.get_tick_padding()
            + gap_pt          # the tick_params pad set in populate
            + max_label_w_pt
            + name_gap_pt
        )

        for i, name in enumerate(self._site_names):
            area, box = self._build_checkbox_body()
            ab = AnnotationBbox(
                area,
                xy=(0.0, i),
                # x in axes fraction (0 = left spine), y in data
                # (integer row centres) — survives resizes because
                # the transform re-evaluates every draw.
                xycoords=self.ax.get_yaxis_transform(),
                xybox=(-self._column_offset_pt, 0.0),
                boxcoords="offset points",
                box_alignment=(1.0, 0.5),
                frameon=False,
                pad=0.0,
                annotation_clip=False,
                zorder=10,
            )
            # Left in-layout deliberately: constrained_layout
            # includes the box in the axes tight bbox and widens
            # the left margin to fit the checkbox column beyond
            # the widest site title.
            self.ax.add_artist(ab)
            self._checkbox_rows.append(
                {"name": name, "ab": ab, "box": box}
            )
            self._row_checked.append(True)
            self._apply_row_visual(i)

    def _build_checkbox_body(self):
        """One checkbox body: a fixed-size ``DrawingArea`` (points)
        holding a rounded ``FancyBboxPatch``. Shared by the row
        checkboxes and the master checkbox."""
        size_pt = _px_to_pt(AppStyles.Dimensions.PLOT_CHECKBOX_SIZE_PX)
        radius_pt = _px_to_pt(
            AppStyles.Dimensions.PLOT_CHECKBOX_RADIUS_PX
        )
        line_pt = _px_to_pt(1)
        area = DrawingArea(size_pt, size_pt, 0, 0)
        box = FancyBboxPatch(
            (line_pt / 2, line_pt / 2),
            size_pt - line_pt,
            size_pt - line_pt,
            boxstyle=f"round,pad=0,rounding_size={radius_pt}",
            linewidth=line_pt,
        )
        area.add_artist(box)
        return area, box

    def _create_master_checkbox(self) -> None:
        """Create the tri-state master checkbox atop the column.

        Same drawn-artist construction as the row checkboxes,
        anchored one gap above the axes top with its right edge
        flush with the column (the centered legend shares that
        band but cannot reach the far left), plus a "Select All"
        label to its right. Clicking either requests select-all
        when any site is unchecked, deselect-all when everything
        is checked.
        """
        if not self._checkbox_rows:
            return

        size_pt = _px_to_pt(AppStyles.Dimensions.PLOT_CHECKBOX_SIZE_PX)
        gap_pt = _px_to_pt(AppStyles.Dimensions.PLOT_CHECKBOX_GAP_PX)
        name_gap_pt = _px_to_pt(
            AppStyles.Dimensions.PLOT_CHECKBOX_NAME_GAP_PX
        )
        dash_w_pt = _px_to_pt(
            AppStyles.Dimensions.PLOT_CHECKBOX_DASH_WIDTH_PX
        )
        dash_h_pt = _px_to_pt(
            AppStyles.Dimensions.PLOT_CHECKBOX_DASH_HEIGHT_PX
        )

        area, box = self._build_checkbox_body()
        # Partial-state dash, centered; hidden unless partial.
        dash = Rectangle(
            ((size_pt - dash_w_pt) / 2, (size_pt - dash_h_pt) / 2),
            dash_w_pt,
            dash_h_pt,
            facecolor=AppStyles.Colors.BUTTON_HOVER,
            edgecolor="none",
            visible=False,
        )
        area.add_artist(dash)

        ab = AnnotationBbox(
            area,
            xy=(0.0, 1.0),
            # Axes top-left corner; the offset hangs the box into
            # the title band, right edge flush with the column.
            xycoords=self.ax.transAxes,
            xybox=(-self._column_offset_pt, gap_pt),
            boxcoords="offset points",
            box_alignment=(1.0, 0.0),
            frameon=False,
            pad=0.0,
            annotation_clip=False,
            zorder=10,
        )
        # Out of layout: the row checkboxes already reserve the
        # horizontal margin and the title pad reserves the band —
        # in-layout here would double-reserve top margin.
        ab.set_in_layout(False)
        self.ax.add_artist(ab)

        # Label to the right of the box, one name gap away — the
        # same offset the widest site title sits at, so it reads
        # as the header of the site-name column.  Part of the
        # click target (see _master_hit).
        label = self.ax.annotate(
            _MASTER_LABEL,
            xy=(0.0, 1.0),
            xycoords=self.ax.transAxes,
            xytext=(
                -(self._column_offset_pt - name_gap_pt),
                gap_pt + size_pt / 2,
            ),
            textcoords="offset points",
            ha="left",
            va="center",
            fontsize=AppStyles.Dimensions.PLOT_LABEL_FONT_SIZE,
            color=AppStyles.Colors.PLOT_SPINE_COLOR,
            annotation_clip=False,
            zorder=10,
        )
        label.set_in_layout(False)

        self._master_checkbox = {
            "ab": ab, "box": box, "dash": dash, "label": label,
        }
        self._update_master_visual()

    def _update_master_visual(self) -> None:
        """Restyle the master checkbox from the row states.

        Solid accent = all checked, plain box = none checked,
        plain box + accent dash = partial selection.
        """
        if self._master_checkbox is None:
            return
        box = self._master_checkbox["box"]
        dash = self._master_checkbox["dash"]
        checked = sum(self._row_checked)
        if checked and checked == len(self._row_checked):
            box.set_facecolor(AppStyles.Colors.BUTTON_HOVER)
            box.set_edgecolor(AppStyles.Colors.BUTTON_HOVER)
            dash.set_visible(False)
        else:
            box.set_facecolor(AppStyles.Colors.INPUT_BG)
            box.set_edgecolor(AppStyles.Colors.INPUT_BORDER)
            dash.set_visible(checked > 0)

    def _toggle_master(self) -> None:
        """Master click: request select-all unless every site is
        already checked, then request deselect-all.

        No local state change — the owning panel updates the
        canonical selection and pushes it back through
        ``set_site_selection``, which restyles rows and master.
        """
        if self._master_checkbox is None:
            return
        if all(self._row_checked):
            logger.info("Duration chart master checkbox: deselect all")
            self.deselect_all_requested.emit()
        else:
            logger.info("Duration chart master checkbox: select all")
            self.select_all_requested.emit()

    def _apply_row_visual(self, row_index: int) -> None:
        """Restyle one row checkbox from its checked state.

        Mirrors ``AppStyles.CheckBox.default()``: checked is a
        solid BUTTON_HOVER square, unchecked an INPUT_BG square
        with an INPUT_BORDER border (no checkmark glyph, exactly
        like the Qt indicator).
        """
        box = self._checkbox_rows[row_index]["box"]
        if self._row_checked[row_index]:
            box.set_facecolor(AppStyles.Colors.BUTTON_HOVER)
            box.set_edgecolor(AppStyles.Colors.BUTTON_HOVER)
        else:
            box.set_facecolor(AppStyles.Colors.INPUT_BG)
            box.set_edgecolor(AppStyles.Colors.INPUT_BORDER)

    def _toggle_row(self, row_index: int) -> None:
        """Flip one row checkbox and report the user toggle."""
        checked = not self._row_checked[row_index]
        self._row_checked[row_index] = checked
        self._apply_row_visual(row_index)
        self._update_master_visual()
        self.canvas.draw_idle()
        name = self._checkbox_rows[row_index]["name"]
        logger.info(
            f"Duration chart checkbox: '{name}' -> "
            f"{'checked' if checked else 'unchecked'}"
        )
        self.site_check_toggled.emit(name, checked)

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
        self.canvas.mpl_connect(
            "draw_event", self._on_canvas_draw
        )
        self.canvas.mpl_connect(
            "figure_leave_event", self._on_figure_leave
        )

    def _on_canvas_draw(self, _event) -> None:
        """A completed draw makes the artist extents trustworthy."""
        self._layout_ready = True

    def _on_figure_leave(self, _event) -> None:
        """Restore hover state when the pointer leaves the canvas.

        Without this, moving straight off the canvas edge (out of
        the window, or onto surrounding widgets) would leave the
        last-hovered site title accent-colored and the pointing-
        hand cursor stuck until the next motion event.
        """
        self._set_hovered_tick_label(None)
        self.canvas.unsetCursor()
        self._hide_annotation()

    def _on_mouse_move(self, event):
        """Handle mouse movement: hover cues for the checkboxes and
        site title links, and the bar segment tooltip.

        :param event: Matplotlib motion_notify_event.
        """
        # Checkboxes and site titles live left of the axes, where
        # event.inaxes is None — handle them before the axes guard.
        if (
            self._master_hit(event)
            or self._find_checkbox_row(event) is not None
        ):
            self._set_hovered_tick_label(None)
            self.canvas.setCursor(
                QCursor(Qt.CursorShape.PointingHandCursor)
            )
            self._hide_annotation()
            return

        label_index = self._find_tick_label_index(event)
        if label_index is not None:
            # Site titles behave like the project-title link:
            # accent colour + pointing hand while hovered.
            self._set_hovered_tick_label(
                self.ax.get_yticklabels()[label_index]
            )
            self.canvas.setCursor(
                QCursor(Qt.CursorShape.PointingHandCursor)
            )
            self._hide_annotation()
            return

        self._set_hovered_tick_label(None)

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

    def _set_hovered_tick_label(self, label) -> None:
        """Hover-highlight *label*, or restore when *None*.

        Redraws only when the hovered label actually changes, so
        calling this on every mouse move is cheap.
        """
        if label is self._hovered_tick_label:
            return
        if self._hovered_tick_label is not None:
            self._hovered_tick_label.set_color(
                AppStyles.Colors.PLOT_SPINE_COLOR
            )
        self._hovered_tick_label = label
        if label is not None:
            label.set_color(AppStyles.Colors.BUTTON_HOVER)
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

    def _master_hit(self, event) -> bool:
        """True when the cursor is over the master checkbox or its
        label (both are one click target)."""
        if (
            not self._layout_ready
            or self._master_checkbox is None
            or event.x is None
        ):
            return False
        # The master sits left of the axes, like the row boxes.
        if event.x >= self.ax.bbox.x0:
            return False
        try:
            for key in ("ab", "label"):
                hit, _ = self._master_checkbox[key].contains(event)
                if hit:
                    return True
        except Exception:
            return False
        return False

    def _find_checkbox_row(self, event) -> int | None:
        """Row index of the checkbox under the cursor, or *None*.

        Uses display coordinates via ``Artist.contains`` — the
        checkboxes sit outside the axes, where data coordinates
        are unavailable.
        """
        if (
            not self._layout_ready
            or not self._checkbox_rows
            or event.x is None
        ):
            return None
        # Both new hit targets live left of the axes; skip the
        # per-artist extent checks while the cursor is over the
        # plot area (the common case).
        if event.x >= self.ax.bbox.x0:
            return None
        for i, row in enumerate(self._checkbox_rows):
            try:
                hit, _ = row["ab"].contains(event)
            except Exception:
                # Extents only exist after the first draw.
                return None
            if hit:
                return i
        return None

    def _find_tick_label_index(self, event) -> int | None:
        """Index of the site title label under the cursor, or
        *None*.  Tick labels are index-aligned with
        ``_site_names`` (``set_yticks``/``set_yticklabels``)."""
        if (
            not self._layout_ready
            or not self._site_names
            or event.x is None
        ):
            return None
        if event.x >= self.ax.bbox.x0:
            return None
        labels = self.ax.get_yticklabels()
        for i, label in enumerate(labels[: len(self._site_names)]):
            try:
                hit, _ = label.contains(event)
            except Exception:
                return None
            if hit:
                return i
        return None

    # -----------------------------------------------------------------
    # Click Navigation
    # -----------------------------------------------------------------

    def _on_mouse_click(self, event):
        """Route a left click: row checkbox toggle, site title
        menu, or bar segment menu.

        :param event: Matplotlib button_press_event.
        """
        if event.button != 1:  # left click only
            return

        if self._master_hit(event):
            self._toggle_master()
            return

        row_index = self._find_checkbox_row(event)
        if row_index is not None:
            # A checkbox click must not also open the menu.
            self._toggle_row(row_index)
            return

        label_index = self._find_tick_label_index(event)
        if label_index is not None:
            self._show_context_menu(self._site_names[label_index])
            return

        if event.inaxes != self.ax or not self._segment_rects:
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
