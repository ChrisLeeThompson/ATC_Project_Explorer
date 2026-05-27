"""
Pattern Viewer GroupBox

Three-column layout for viewing pattern sizes and positions
relative to the lamella.

Layout::

    PatternViewerGroupBox (titled "Pattern Viewer")
    ├── Left column (fixed width):
    │   └── QGridLayout with QLabels:
    │       Activity Name, Pattern Type, Width, Height, Depth,
    │       Depth Correction, Overlap %, Beam Current,
    │       Measured Beam Current, Duration
    ├── Centre column (expanding):
    │   └── PatternCanvasWidget — custom QWidget with QPainter
    │       schematic showing the lamella and pattern rectangles
    └── Right column (fixed width):
        └── QScrollArea with PatternToggleButtons, one per
            activity that has patterning data, plus a "Lamella"
            button at the end

The group box is populated from consolidated metadata via
``populate(site_data)``.  Pattern rectangle geometry comes
from ``PatternData`` (pre-extracted during consolidation).
Recipe parameters (DepthCorrection, Overlap, BeamCurrent)
and statistics (Duration) are read from
``SiteProjectData`` and ``Statistics``.

Stress relief cut patterns are drawn as horizontal flanking
rectangles (left/right of the lamella), while all other
activity patterns are drawn as vertical rectangles
(above/below the lamella).

Activities with separate front and rear patterns (e.g. Rough
Milling) produce distinct entries with ``"(Front)"`` or
``"(Rear)"`` suffixed to the activity name.
"""
import logging
import math
from PySide6.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QGridLayout,
    QWidget, QLabel, QSizePolicy, QSplitter,
    QScrollArea, QButtonGroup, QApplication,
)
from PySide6.QtCore import Qt, QEvent, QRectF, Signal, Slot
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QCursor
from script_modules.app_styles import AppStyles
from script_modules.consolidated_data_reader import (
    build_activity_step_map,
    parse_numeric_value,
)
from script_modules.widgets.button_widgets import (
    PatternToggleButton,
    ResetViewButton,
)


logger = logging.getLogger(__name__)


# Placeholder text
_PLACEHOLDER_LABEL = "No pattern data available"
_NA = "N/A"

# Workflow step → colour mapping for the canvas
_STEP_COLORS: dict[str, str] = {
    "Preparation": AppStyles.Colors.PLOT_PREPARATION_BAR_COLOR,
    "Milling": AppStyles.Colors.PLOT_MILLING_BAR_COLOR,
    "Thinning": AppStyles.Colors.PLOT_THINNING_BAR_COLOR,
}
_DEFAULT_PATTERN_COLOR = AppStyles.Colors.PLOT_MILLING_BAR_COLOR
_LAMELLA_COLOR = AppStyles.Colors.PLOT_LAMELLA_PLACEMENT_BAR_COLOR


# -----------------------------------------------------------------
# Data helpers
# -----------------------------------------------------------------

def _find_activity_in_recipes(
    site_project_data: dict, activity_name: str,
) -> dict:
    """Find the recipe activity dict matching the given name.

    Walks the recipe tree recursively to locate the activity
    with a ``Name`` field matching *activity_name*.

    :param site_project_data: A single site's SiteProjectData.
    :param activity_name: Display name to find.
    :return: The activity dict, or empty dict if not found.
    """
    workflow = site_project_data.get("Workflow", {})
    recipes = workflow.get("Recipe", [])
    if isinstance(recipes, dict):
        recipes = [recipes]
    for recipe in recipes:
        activities = recipe.get("Activities", {})
        result = _search_activity(activities, activity_name)
        if result is not None:
            return result
    return {}


def _search_activity(obj, target_name: str) -> dict | None:
    """Recursively search for an activity with the given Name."""
    if isinstance(obj, dict):
        if obj.get("Name") == target_name:
            return obj
        for key, val in obj.items():
            if key != "Name":
                found = _search_activity(val, target_name)
                if found is not None:
                    return found
    elif isinstance(obj, list):
        for item in obj:
            found = _search_activity(item, target_name)
            if found is not None:
                return found
    return None


def _strip_front_rear_suffix(name: str) -> str:
    """Remove ``" (Front)"`` or ``" (Rear)"`` suffix from an
    activity name to get the base name for recipe/statistics
    lookups.

    :param name: Activity name, possibly with suffix.
    :return: Base activity name.
    """
    for suffix in (" (Front)", " (Rear)"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def _find_duration(
    statistics: dict, activity_name: str,
) -> str:
    """Find the duration string for an activity from Statistics.

    Tries the exact name first, then strips any (Front)/(Rear)
    suffix to match the base activity name.

    :param statistics: The ``Statistics`` dict from site data.
    :param activity_name: Activity name to match.
    :return: Duration string (e.g. ``"00:07:24"``) or ``"N/A"``.
    """
    for entry in statistics.get("Activities", []):
        if entry.get("ActivityName") == activity_name:
            return entry.get("Duration", _NA)
    # Try base name without front/rear suffix
    base_name = _strip_front_rear_suffix(activity_name)
    if base_name != activity_name:
        for entry in statistics.get("Activities", []):
            if entry.get("ActivityName") == base_name:
                return entry.get("Duration", _NA)
    return _NA


def _format_value(raw) -> str:
    """Format a raw metadata value for display."""
    if raw is None:
        return _NA
    s = str(raw).strip()
    return s if s else _NA


def _format_value_rounded(raw, decimals: int = 2) -> str:
    """Parse a value+unit string, round the numeric part, and
    return with the original unit preserved.

    :param raw: Value string (e.g. ``"7.7774934 pA"``).
    :param decimals: Number of decimal places.
    :return: Formatted string like ``"7.78 pA"`` or ``"N/A"``.
    """
    if raw is None:
        return _NA
    raw_str = str(raw).strip()
    if not raw_str:
        return _NA
    result = parse_numeric_value(raw_str)
    if result is None:
        return raw_str
    value, unit = result
    rounded = round(value, decimals)
    if unit:
        return f"{rounded} {unit}"
    return str(rounded)


def _format_um_rounded(raw, decimals: int = 2) -> str:
    """Parse a value+unit string, convert to µm, round, and
    format for display.

    :param raw: Value string (e.g. ``"398.207 nm"``).
    :param decimals: Number of decimal places.
    :return: Formatted string like ``"0.40 µm"`` or ``"N/A"``.
    """
    raw_str = str(raw).strip()
    if not raw_str:
        return _NA
    um = PatternCanvasWidget._parse_um(raw_str)
    if um == 0.0:
        # Check if the input was genuinely zero or unparseable
        parsed = parse_numeric_value(raw_str)
        if parsed is None:
            return _format_value(raw)
        if parsed[0] != 0.0:
            # Non-zero value but _parse_um returned 0 (unknown unit)
            return _format_value(raw)
    return f"{round(um, decimals)} µm"


def _is_stress_relief(activity_name: str) -> bool:
    """Check if an activity name refers to stress relief cuts."""
    return "stress relief" in activity_name.lower()


def _is_front_pattern(activity_name: str) -> bool:
    """Check if an activity name is a front-only pattern."""
    return activity_name.endswith("(Front)")


def _is_rear_pattern(activity_name: str) -> bool:
    """Check if an activity name is a rear-only pattern."""
    return activity_name.endswith("(Rear)")


def _build_display_entries(site_data: dict) -> list[dict]:
    """Build the display data for all pattern activities.

    Combines PatternData, recipe parameters, and statistics
    into a list of dicts ready for the UI.

    :param site_data: A single site entry from consolidated
        metadata.
    :return: List of display entry dicts.
    """
    pattern_data = site_data.get("PatternData", [])
    if not pattern_data:
        return []

    site_pd = site_data.get("SiteProjectData", {})
    statistics = site_data.get("Statistics", {})
    step_map = build_activity_step_map(site_pd)

    # Lamella parameters
    params = site_pd.get("Parameters", {})
    lamella_width = _format_value(params.get("LamellaWidth"))
    final_thickness = _format_value(params.get("FinalThickness"))

    # Numeric lamella width (µm) for recipe-derived per-side
    # pattern widths.  ATC guarantees a non-zero LamellaWidth.
    lamella_width_um = PatternCanvasWidget._parse_um(
        str(params.get("LamellaWidth", "0"))
    )

    entries: list[dict] = []

    for pd in pattern_data:
        activity_name = pd.get("ActivityName", "")
        if not activity_name:
            continue

        # Strip suffix for recipe lookup
        base_name = _strip_front_rear_suffix(activity_name)

        # Find matching recipe activity for extra fields
        recipe_act = _find_activity_in_recipes(
            site_pd, base_name
        )

        # Workflow step for colour assignment
        workflow_step = step_map.get(base_name, "")
        color = _STEP_COLORS.get(
            workflow_step, _DEFAULT_PATTERN_COLOR
        )

        # Rectangle info (use first rectangle for type display)
        rects = pd.get("Rectangles", [])
        pattern_type = _NA
        rect_width = _NA
        rect_height = _NA
        rect_depth = _NA
        if rects:
            first = rects[0]
            pattern_type = _format_value(
                first.get("PatternType")
            )
            rect_width = _format_um_rounded(
                first.get("Width", "")
            )
            rect_height = _format_um_rounded(
                first.get("Height", "")
            )
            rect_depth = _format_um_rounded(
                first.get("Depth", "")
            )

        # Recipe parameters
        depth_correction = _format_value(
            recipe_act.get("DepthCorrection")
        )
        overlap = _format_value(
            recipe_act.get("ThinningPatternsOverlapFactor")
        )
        # Pattern offset: OffsetFromLamella for milling/polishing,
        # TrenchOffset for stress relief cuts.
        offset_raw = recipe_act.get("OffsetFromLamella")
        if offset_raw is None or offset_raw == "":
            offset_raw = recipe_act.get("TrenchOffset")
        offset_from_lamella = _format_um_rounded(
            offset_raw if offset_raw else ""
        )

        # Stress relief uses TrenchOffset for canvas positioning
        trench_offset = _format_value(
            recipe_act.get("TrenchOffset")
        )

        # Width overlap values (extend pattern beyond lamella)
        front_left_overlap = _format_um_rounded(
            recipe_act.get("LamellaFrontLeftWidthOverlap", "")
        )
        front_right_overlap = _format_um_rounded(
            recipe_act.get("LamellaFrontRightWidthOverlap", "")
        )
        rear_left_overlap = _format_um_rounded(
            recipe_act.get("LamellaRearLeftWidthOverlap", "")
        )
        rear_right_overlap = _format_um_rounded(
            recipe_act.get("LamellaRearRightWidthOverlap", "")
        )

        # Raw overlap values in µm for canvas drawing
        flo_um = PatternCanvasWidget._parse_um(
            str(recipe_act.get(
                "LamellaFrontLeftWidthOverlap", "0"
            ))
        )
        fro_um = PatternCanvasWidget._parse_um(
            str(recipe_act.get(
                "LamellaFrontRightWidthOverlap", "0"
            ))
        )
        rlo_um = PatternCanvasWidget._parse_um(
            str(recipe_act.get(
                "LamellaRearLeftWidthOverlap", "0"
            ))
        )
        rro_um = PatternCanvasWidget._parse_um(
            str(recipe_act.get(
                "LamellaRearRightWidthOverlap", "0"
            ))
        )

        # Beam current (configured from recipe)
        milling_preset = recipe_act.get("MillingPreset", {})
        configured_beam = _format_value(
            milling_preset.get("BeamCurrent")
        )

        # Measured beam current (from image metadata)
        measured_beam = _format_value_rounded(
            pd.get("MeasuredBeamCurrent")
        )

        # Overtilt (thinning activities only)
        overtilt = _format_value(
            recipe_act.get("Overtilt")
        )

        # DCM rescan interval
        dcm_params = recipe_act.get(
            "DriftCorrectionParameters", {}
        )
        dcm_interval = _format_value(
            dcm_params.get("DcmRescanInterval")
            if isinstance(dcm_params, dict) else None
        )

        # Duration from statistics
        duration = _find_duration(statistics, activity_name)

        # Check for front/rear trench heights in recipe
        # (e.g. Rough Milling has FrontTrenchHeight and
        # RearTrenchHeight with different values).
        front_height_raw = recipe_act.get("FrontTrenchHeight")
        rear_height_raw = recipe_act.get("RearTrenchHeight")

        # Determine whether to split into front/rear entries.
        # Activities with non-zero width overlaps have distinct
        # front and rear patterns (all Milling recipe activities).
        has_nonzero_overlaps = any(
            v > 0 for v in (flo_um, fro_um, rlo_um, rro_um)
        )

        # Common fields shared by both single and split entries
        common = {
            "is_lamella": False,
            "workflow_step": workflow_step,
            "color": color,
            "pattern_type": pattern_type,
            "width": rect_width,
            "depth": rect_depth,
            "depth_correction": depth_correction,
            "overlap": overlap,
            "overtilt": overtilt,
            "offset_from_lamella": offset_from_lamella,
            "trench_offset": trench_offset,
            "configured_beam_current": configured_beam,
            "measured_beam_current": measured_beam,
            "dcm_interval": dcm_interval,
            "duration": duration,
            "rectangles": rects,
            "lamella_width": lamella_width,
            "final_thickness": final_thickness,
        }

        if has_nonzero_overlaps:
            # Split into front and rear entries.
            # Front entry: front overlaps, front height if available.
            front_entry = dict(common)
            front_entry["activity_name"] = (
                f"{activity_name} (Front)"
            )
            front_entry["front_left_overlap"] = front_left_overlap
            front_entry["front_right_overlap"] = front_right_overlap
            front_entry["rear_left_overlap"] = _NA
            front_entry["rear_right_overlap"] = _NA
            front_entry["front_left_overlap_um"] = flo_um
            front_entry["front_right_overlap_um"] = fro_um
            front_entry["rear_left_overlap_um"] = 0.0
            front_entry["rear_right_overlap_um"] = 0.0
            # Per-side width: pattern = lamella + front_left + front_right.
            # Override both the info-panel `width` field and per-rectangle
            # `Width` so canvas drawing reflects the front overlaps.
            front_w_um = lamella_width_um + flo_um + fro_um
            front_w_str = f"{front_w_um} µm"
            front_entry["width"] = _format_um_rounded(front_w_str)
            if front_height_raw is not None:
                front_entry["height"] = _format_um_rounded(
                    front_height_raw
                )
                front_entry["rectangles"] = [
                    {**r,
                     "Width": front_w_str,
                     "Height": str(front_height_raw)}
                    for r in rects
                ]
            else:
                front_entry["height"] = rect_height
                front_entry["rectangles"] = [
                    {**r, "Width": front_w_str}
                    for r in rects
                ]
            entries.append(front_entry)

            # Rear entry: rear overlaps, rear height if available.
            rear_entry = dict(common)
            rear_entry["activity_name"] = (
                f"{activity_name} (Rear)"
            )
            rear_entry["front_left_overlap"] = _NA
            rear_entry["front_right_overlap"] = _NA
            rear_entry["rear_left_overlap"] = rear_left_overlap
            rear_entry["rear_right_overlap"] = rear_right_overlap
            rear_entry["front_left_overlap_um"] = 0.0
            rear_entry["front_right_overlap_um"] = 0.0
            rear_entry["rear_left_overlap_um"] = rlo_um
            rear_entry["rear_right_overlap_um"] = rro_um
            # Per-side width: pattern = lamella + rear_left + rear_right.
            rear_w_um = lamella_width_um + rlo_um + rro_um
            rear_w_str = f"{rear_w_um} µm"
            rear_entry["width"] = _format_um_rounded(rear_w_str)
            if rear_height_raw is not None:
                rear_entry["height"] = _format_um_rounded(
                    rear_height_raw
                )
                rear_entry["rectangles"] = [
                    {**r,
                     "Width": rear_w_str,
                     "Height": str(rear_height_raw)}
                    for r in rects
                ]
            else:
                rear_entry["height"] = rect_height
                rear_entry["rectangles"] = [
                    {**r, "Width": rear_w_str}
                    for r in rects
                ]
            entries.append(rear_entry)
        else:
            # Single entry — no overlaps or all zeros
            entries.append({
                "activity_name": activity_name,
                "height": rect_height,
                "front_left_overlap": front_left_overlap,
                "front_right_overlap": front_right_overlap,
                "rear_left_overlap": rear_left_overlap,
                "rear_right_overlap": rear_right_overlap,
                "front_left_overlap_um": flo_um,
                "front_right_overlap_um": fro_um,
                "rear_left_overlap_um": rlo_um,
                "rear_right_overlap_um": rro_um,
                **common,
            })

    # Append a lamella entry at the end
    entries.append({
        "activity_name": "Lamella",
        "is_lamella": True,
        "workflow_step": "",
        "color": _LAMELLA_COLOR,
        "pattern_type": _NA,
        "width": _format_um_rounded(
            params.get("LamellaWidth", "")
        ),
        "height": _format_um_rounded(
            params.get("ActualChunkThickness", "")
        ),
        "depth": _format_um_rounded(
            params.get("LamellaDepth", "")
        ),
        "front_left_overlap": _NA,
        "front_right_overlap": _NA,
        "rear_left_overlap": _NA,
        "rear_right_overlap": _NA,
        "offset_from_lamella": _NA,
        "depth_correction": _NA,
        "overlap": _NA,
        "overtilt": _NA,
        "trench_offset": _NA,
        "configured_beam_current": _NA,
        "measured_beam_current": _NA,
        "dcm_interval": _NA,
        "duration": _NA,
        "rectangles": [],
        "lamella_width": lamella_width,
        "final_thickness": final_thickness,
    })

    return entries


# -----------------------------------------------------------------
# Pattern Canvas Widget
# -----------------------------------------------------------------

class PatternCanvasWidget(QWidget):
    """Custom QWidget that draws a schematic cross-section of the
    lamella and pattern rectangles using QPainter.

    All dimensions are in physical units (µm) and auto-scaled to
    fit the widget area.

    - **Regular activities** (milling, polishing): patterns are
      drawn above (front) and below (rear) the lamella.
    - **Stress relief cuts**: patterns are drawn to the left and
      right of the lamella (horizontal flanking).
    """

    # Emitted on a left-click (not a drag) over a pattern or the
    # lamella, carrying the entry index that was hit (or the next
    # one in cycle order, for overlapping rectangles).
    entry_clicked = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._entries: list[dict] = []
        self._selected_index: int = -1
        # Index of the lamella entry in ``_entries`` (always the
        # last one by construction in ``_build_display_entries``).
        # Cached at ``set_data`` time so paintEvent and hit-testing
        # don't need to scan.
        self._lamella_index: int = -1
        self._lamella_width_um: float = 0.0
        self._final_thickness_um: float = 0.0

        # Zoom / pan state.  ``_drag_start_x/y`` record the press
        # position on every left-press; the drag is not actually
        # activated until the cursor moves beyond
        # ``QApplication.startDragDistance()``, so these double as
        # the click position for hit-testing.
        self._zoom: float = 1.0
        self._pan_x: float = 0.0
        self._pan_y: float = 0.0
        self._drag_active: bool = False
        self._drag_start_x: float = 0.0
        self._drag_start_y: float = 0.0
        self._drag_start_pan_x: float = 0.0
        self._drag_start_pan_y: float = 0.0

        # Click hit-map: populated by paintEvent (one entry per
        # drawn rectangle, in paint order), consumed by
        # mouseReleaseEvent.  Rectangles are in widget coordinates
        # (post zoom and pan).  An entry can appear more than once
        # if it draws multiple rectangles (front + rear, stress-
        # relief left + right); cycling dedups by entry index.
        self._hit_map: list[tuple[int, QRectF]] = []

        self.setMinimumHeight(AppStyles.Dimensions.PATTERN_VIEWER_CANVAS_MINIMUM_HEIGHT)
        self.setMinimumWidth(200)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )

    def set_data(
        self,
        entries: list[dict],
        lamella_width_um: float,
        final_thickness_um: float,
    ) -> None:
        """Set the pattern data for drawing.

        :param entries: Display entry dicts from
            ``_build_display_entries``.
        :param lamella_width_um: Lamella width in µm.
        :param final_thickness_um: Final thickness in µm (used
            as lamella height in the schematic).
        """
        self._entries = entries
        self._lamella_width_um = lamella_width_um
        self._final_thickness_um = final_thickness_um
        # Lamella entry is always last by construction; verify and
        # cache the index for paintEvent / hit-test consumers.
        self._lamella_index = (
            len(self._entries) - 1
            if self._entries
            and self._entries[-1].get("is_lamella")
            else -1
        )
        # Stale hit-map from previous data must not match clicks
        # against the new entries; cleared as cheap insurance even
        # though paintEvent rebuilds it on the next paint.
        self._hit_map.clear()
        self.reset_view()
        self.update()

    def set_selected(self, index: int) -> None:
        """Set the highlighted pattern index.

        :param index: Index into the entries list, or -1 for
            no selection.
        """
        self._selected_index = index
        self.update()

    def clear(self) -> None:
        """Reset the canvas."""
        self._entries.clear()
        self._selected_index = -1
        self._lamella_index = -1
        self._lamella_width_um = 0.0
        self._final_thickness_um = 0.0
        self._hit_map.clear()
        self.reset_view()
        self.update()

    def reset_view(self) -> None:
        """Reset zoom and pan to the default fit-all state."""
        self._zoom = 1.0
        self._pan_x = 0.0
        self._pan_y = 0.0

    def wheelEvent(self, event) -> None:
        """Zoom in/out on scroll wheel, centred on the cursor.

        Scroll up zooms in, scroll down zooms out.  The zoom is
        applied relative to the cursor position so the point
        under the cursor stays fixed.
        """
        zoom_factor = 1.1
        delta = event.angleDelta().y()
        if delta == 0:
            return

        # Cursor position relative to widget centre
        mouse_x = event.position().x() - self.width() / 2
        mouse_y = event.position().y() - self.height() / 2

        if delta > 0:
            # Zoom in
            factor = zoom_factor
        else:
            # Zoom out (clamp at 0.1× to prevent inversion)
            factor = 1.0 / zoom_factor
            if self._zoom * factor < 0.1:
                return

        # Adjust pan so the point under the cursor stays fixed
        self._pan_x = mouse_x - factor * (mouse_x - self._pan_x)
        self._pan_y = mouse_y - factor * (mouse_y - self._pan_y)
        self._zoom *= factor

        self.update()

    def mousePressEvent(self, event) -> None:
        """Record the press position.

        Pan is not activated here; it only starts once the cursor
        moves beyond ``QApplication.startDragDistance()`` (see
        ``mouseMoveEvent``).  This lets a press-release-without-
        movement remain a click for selection.  Cursor change to
        :attr:`Qt.CursorShape.ClosedHandCursor` is also deferred
        to the drag-activation moment.
        """
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_x = event.position().x()
            self._drag_start_y = event.position().y()
            self._drag_start_pan_x = self._pan_x
            self._drag_start_pan_y = self._pan_y
            # Defensive reset: if mouseReleaseEvent was missed (alt-
            # tab during a previous drag, focus loss, etc.) a stale
            # True would cause this press to skip the threshold
            # check and immediately pan instead of click.
            self._drag_active = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        """Activate the pan drag on threshold crossing, then
        update the pan offset.

        Below the threshold, motion is ignored — the press could
        still resolve as a click on release.
        """
        if event.buttons() & Qt.MouseButton.LeftButton:
            dx = event.position().x() - self._drag_start_x
            dy = event.position().y() - self._drag_start_y
            if not self._drag_active:
                threshold = QApplication.startDragDistance()
                if abs(dx) > threshold or abs(dy) > threshold:
                    self._drag_active = True
                    self.setCursor(QCursor(
                        Qt.CursorShape.ClosedHandCursor
                    ))
            if self._drag_active:
                self._pan_x = self._drag_start_pan_x + dx
                self._pan_y = self._drag_start_pan_y + dy
                self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        """Resolve a left-release as either pan-end or click.

        If pan activated during the drag, just clean up.  Otherwise
        treat as a click and dispatch to ``_handle_click`` using
        the *press* position (not the release position) — micro
        drift below the drag threshold should not retarget the
        hit-test away from what the user aimed at.
        """
        if event.button() == Qt.MouseButton.LeftButton:
            if self._drag_active:
                self._drag_active = False
                self.setCursor(QCursor(
                    Qt.CursorShape.ArrowCursor
                ))
            else:
                self._handle_click(
                    self._drag_start_x, self._drag_start_y
                )
        super().mouseReleaseEvent(event)

    def _handle_click(self, x: float, y: float) -> None:
        """Hit-test a click at *(x, y)* and emit ``entry_clicked``.

        Walks the paint-event-populated hit-map for rectangles
        containing the point, dedups by entry index, sorts
        ascending (workflow / button order — Rough → Polish →
        Lamella), and advances from the currently selected entry
        if it is among the candidates (otherwise starts at
        ``candidates[0]``).  Empty-space clicks are no-ops; the
        current selection is preserved.

        :param x: Click x in widget coordinates (press position).
        :param y: Click y in widget coordinates (press position).
        """
        candidates: list[int] = []
        seen: set[int] = set()
        for entry_index, rect in self._hit_map:
            if entry_index in seen:
                continue
            if rect.contains(x, y):
                candidates.append(entry_index)
                seen.add(entry_index)

        if not candidates:
            return  # empty-space click is a no-op

        candidates.sort()
        if self._selected_index in candidates:
            i = candidates.index(self._selected_index)
            next_i = (i + 1) % len(candidates)
        else:
            next_i = 0

        self.entry_clicked.emit(candidates[next_i])

    def paintEvent(self, event):
        """Draw the schematic cross-section."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Hit-map is rebuilt every paint so it always reflects the
        # current zoom, pan, and entry set.  Drawing methods
        # append to it inline alongside each ``drawRect`` call.
        self._hit_map.clear()

        # Background
        bg_color = QColor(AppStyles.Colors.MAIN_BG)
        painter.fillRect(self.rect(), bg_color)

        if not self._entries or self._lamella_width_um <= 0:
            painter.setPen(QColor(AppStyles.Colors.TEXT_DISABLED))
            painter.drawText(
                self.rect(), Qt.AlignmentFlag.AlignCenter,
                _PLACEHOLDER_LABEL,
            )
            painter.end()
            return

        # Compute the physical extents to determine scale
        margin_px = 30
        available_w = self.width() - 2 * margin_px
        available_h = self.height() - 2 * margin_px
        if available_w <= 0 or available_h <= 0:
            painter.end()
            return

        extents = self._compute_extents()
        max_width_um = extents[0]
        max_height_um = extents[1]

        if max_width_um <= 0 or max_height_um <= 0:
            painter.end()
            return

        # Scale factor: physical µm → widget pixels
        scale_x = available_w / max_width_um
        scale_y = available_h / max_height_um
        scale = min(scale_x, scale_y)

        # Apply user zoom
        scale *= self._zoom

        # Centre of the widget, offset by user pan
        cx = self.width() / 2 + self._pan_x
        cy = self.height() / 2 + self._pan_y

        # Draw all entries (unselected first, then selected)
        for draw_pass in (0, 1):
            for i, entry in enumerate(self._entries):
                if entry.get("is_lamella"):
                    continue  # lamella drawn separately
                is_selected = (i == self._selected_index)
                if draw_pass == 0 and is_selected:
                    continue
                if draw_pass == 1 and not is_selected:
                    continue
                self._draw_entry(
                    painter, entry, i, cx, cy, scale,
                    is_selected,
                )

        # Draw lamella (always on top).  ``_lamella_index`` is
        # cached at ``set_data`` time; guard against -1 in case
        # a future entry-building path omits it.
        if self._lamella_index >= 0:
            lamella_selected = (
                self._selected_index == self._lamella_index
            )
            self._draw_lamella(
                painter, self._lamella_index,
                cx, cy, scale, lamella_selected,
            )

        # Scale bar (widget-coordinate overlay, after all geometry)
        self._draw_scale_bar(painter, scale)

        painter.end()

    def _compute_extents(self) -> tuple[float, float]:
        """Compute the total physical extents needed to show
        all patterns plus the lamella.

        :return: ``(total_width_um, total_height_um)``
        """
        max_w = self._lamella_width_um
        max_h = self._final_thickness_um
        lamella_half_w = self._lamella_width_um / 2
        lamella_half_t = self._final_thickness_um / 2

        for entry in self._entries:
            if entry.get("is_lamella"):
                continue
            name = entry.get("activity_name", "")

            if _is_stress_relief(name):
                # Horizontal: width extends outward
                trench_off = self._parse_um(
                    entry.get("trench_offset", "0")
                )
                for rect in entry.get("rectangles", []):
                    rw = self._parse_um(rect.get("Width", "0"))
                    rh = self._parse_um(rect.get("Height", "0"))
                    total_w = (
                        lamella_half_w + trench_off + rw
                    ) * 2
                    if total_w > max_w:
                        max_w = total_w
                    if rh > max_h:
                        max_h = rh
            else:
                # Vertical: height extends above/below
                offset = self._parse_um(
                    entry.get("offset_from_lamella", "0")
                )
                for rect in entry.get("rectangles", []):
                    rw = self._parse_um(rect.get("Width", "0"))
                    rh = self._parse_um(rect.get("Height", "0"))
                    if rw > max_w:
                        max_w = rw
                    total_h = lamella_half_t + offset + rh
                    if total_h > max_h:
                        max_h = total_h

        # Double the height for symmetric above/below
        max_h = max_h * 2
        return max_w, max_h

    def _draw_lamella(
        self, painter: QPainter, entry_index: int,
        cx: float, cy: float, scale: float,
        is_selected: bool = False,
    ) -> None:
        """Draw the lamella rectangle at the centre.

        Also records the drawn rect in ``_hit_map`` so the lamella
        can be selected by clicking on it.  Hit rect equals drawn
        rect — no inflation; if the lamella is too small to click
        at the current zoom, the user can wheel-zoom to enlarge it.
        """
        w_px = self._lamella_width_um * scale
        h_px = self._final_thickness_um * scale

        color = QColor(_LAMELLA_COLOR)
        line_width = 2.5 if is_selected else 1.5
        alpha = 180 if is_selected else 80
        painter.setPen(QPen(color, line_width))
        fill = QColor(color)
        fill.setAlpha(alpha)
        painter.setBrush(QBrush(fill))
        rx, ry = int(cx - w_px / 2), int(cy - h_px / 2)
        rw, rh = int(w_px), int(h_px)
        painter.drawRect(rx, ry, rw, rh)
        self._hit_map.append(
            (entry_index, QRectF(rx, ry, rw, rh))
        )

    def _draw_scale_bar(
        self, painter: QPainter, scale: float,
    ) -> None:
        """Draw a microscopy scale bar in the bottom-left corner.

        The bar's physical length adapts to the current scale
        (zoom-aware) by snapping to a 1/2/5 × 10^n "nice" value
        whose drawn length is closest to
        :attr:`AppStyles.Dimensions.SCALE_BAR_TARGET_PX`.  The
        bar is drawn in widget coordinates so it stays anchored
        to the corner regardless of pan.

        :param painter: Active QPainter on this widget.
        :param scale: Effective pixels-per-µm at current zoom
            (``base_scale * self._zoom``, the value used to draw
            patterns and the lamella in this paint pass).
        """
        if scale <= 0:
            return

        # Choose the nicest physical length whose drawn width is
        # close to the target pixel count.
        target_px = AppStyles.Dimensions.SCALE_BAR_TARGET_PX
        desired_um = target_px / scale
        nice_um = self._nice_number_125(desired_um)
        bar_px = nice_um * scale

        # Format label using microscopy convention: µm at >= 1 µm,
        # otherwise nm.
        if nice_um >= 1.0:
            label = f"{nice_um:g} µm"
        else:
            label = f"{nice_um * 1000:g} nm"

        # Anchor: bottom-left.  y is the centreline of the bar.
        margin = AppStyles.Dimensions.SCALE_BAR_MARGIN
        x0 = margin
        x1 = margin + bar_px
        y = self.height() - margin

        color = QColor(AppStyles.Colors.SCALE_BAR_COLOR)
        painter.setPen(
            QPen(color, AppStyles.Dimensions.SCALE_BAR_LINE_WIDTH)
        )

        # Main horizontal bar
        painter.drawLine(int(x0), int(y), int(x1), int(y))

        # End caps (short vertical lines)
        cap_half = AppStyles.Dimensions.SCALE_BAR_CAP_HEIGHT / 2
        painter.drawLine(
            int(x0), int(y - cap_half),
            int(x0), int(y + cap_half),
        )
        painter.drawLine(
            int(x1), int(y - cap_half),
            int(x1), int(y + cap_half),
        )

        # Label, centred above the bar.  Set the font size from
        # AppStyles before measuring so horizontalAdvance() reflects
        # the actual rendered width.  This is the last drawing in
        # paintEvent, so we don't restore the painter's prior font.
        font = painter.font()
        font.setPointSize(
            AppStyles.Dimensions.SCALE_BAR_LABEL_FONT_SIZE
        )
        painter.setFont(font)
        fm = painter.fontMetrics()
        label_w = fm.horizontalAdvance(label)
        label_x = int((x0 + x1) / 2 - label_w / 2)
        label_y = int(
            y - cap_half
            - AppStyles.Dimensions.SCALE_BAR_LABEL_PAD
        )
        painter.drawText(label_x, label_y, label)

    @staticmethod
    def _nice_number_125(value: float) -> float:
        """Round *value* to the nearest 1/2/5 × 10^n.

        Standard microscopy scale-bar snap: produces values like
        0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, ...

        :param value: A positive physical length in µm.
        :return: The nearest 1/2/5 nice number.
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

    def _draw_entry(
        self, painter: QPainter, entry: dict, entry_index: int,
        cx: float, cy: float, scale: float,
        is_selected: bool,
    ) -> None:
        """Draw pattern rectangles for one activity entry."""
        name = entry.get("activity_name", "")

        if _is_stress_relief(name):
            self._draw_stress_relief(
                painter, entry, entry_index,
                cx, cy, scale, is_selected,
            )
        else:
            self._draw_regular(
                painter, entry, entry_index,
                cx, cy, scale, is_selected,
            )

    def _draw_regular(
        self, painter: QPainter, entry: dict, entry_index: int,
        cx: float, cy: float, scale: float,
        is_selected: bool,
    ) -> None:
        """Draw regular (above/below) pattern rectangles.

        For entries with a ``"(Front)"`` suffix, only the front
        (above) rectangle is drawn.  For ``"(Rear)"``, only the
        rear (below).  Otherwise both front and rear are drawn
        with the same dimensions.

        Dashed vertical lines are drawn at the lamella edge
        positions to indicate the width overlap zones.

        Each drawn rectangle is also recorded in ``_hit_map`` for
        click-to-select hit testing.
        """
        color = QColor(entry.get("color", _DEFAULT_PATTERN_COLOR))
        offset_um = self._parse_um(
            entry.get("offset_from_lamella", "0")
        )
        # Pattern positions reference the true lamella half-height so
        # the pattern-to-lamella gap matches the recipe's
        # OffsetFromLamella exactly, at all scales.
        lamella_half_px = (self._final_thickness_um * scale) / 2
        lamella_half_w_px = (self._lamella_width_um / 2) * scale

        line_width = 2.0 if is_selected else 1.0
        alpha = 180 if is_selected else 60
        name = entry.get("activity_name", "")
        draw_front = not _is_rear_pattern(name)
        draw_rear = not _is_front_pattern(name)

        # Check if overlaps exist for drawing indicators
        has_overlaps = (
            entry.get("front_left_overlap_um", 0) > 0
            or entry.get("front_right_overlap_um", 0) > 0
            or entry.get("rear_left_overlap_um", 0) > 0
            or entry.get("rear_right_overlap_um", 0) > 0
        )

        for rect in entry.get("rectangles", []):
            w_um = self._parse_um(rect.get("Width", "0"))
            h_um = self._parse_um(rect.get("Height", "0"))
            if w_um <= 0 or h_um <= 0:
                continue

            w_px = w_um * scale
            h_px = h_um * scale
            gap_px = lamella_half_px + offset_um * scale

            pen = QPen(color, line_width)
            painter.setPen(pen)
            fill = QColor(color)
            fill.setAlpha(alpha)
            painter.setBrush(QBrush(fill))

            if draw_front:
                y_top = cy - gap_px - h_px
                rx, ry = int(cx - w_px / 2), int(y_top)
                rw, rh = int(w_px), int(h_px)
                painter.drawRect(rx, ry, rw, rh)
                self._hit_map.append(
                    (entry_index, QRectF(rx, ry, rw, rh))
                )
                # Overlap indicator lines at lamella edges
                if has_overlaps:
                    self._draw_overlap_lines(
                        painter, color, cx,
                        lamella_half_w_px,
                        int(y_top), int(h_px),
                    )

            if draw_rear:
                y_bot = cy + gap_px
                rx, ry = int(cx - w_px / 2), int(y_bot)
                rw, rh = int(w_px), int(h_px)
                painter.drawRect(rx, ry, rw, rh)
                self._hit_map.append(
                    (entry_index, QRectF(rx, ry, rw, rh))
                )
                # Overlap indicator lines at lamella edges
                if has_overlaps:
                    self._draw_overlap_lines(
                        painter, color, cx,
                        lamella_half_w_px,
                        int(y_bot), int(h_px),
                    )

    def _draw_overlap_lines(
        self, painter: QPainter, color: QColor,
        cx: float, lamella_half_w_px: float,
        rect_y: int, rect_h: int,
    ) -> None:
        """Draw dashed vertical lines at lamella edge positions
        within a pattern rectangle to indicate the overlap zones.

        :param painter: Active QPainter.
        :param color: Pattern colour for the lines.
        :param cx: Centre X of the drawing area (pixels).
        :param lamella_half_w_px: Half lamella width in pixels.
        :param rect_y: Top Y of the pattern rectangle (pixels).
        :param rect_h: Height of the pattern rectangle (pixels).
        """
        # Save current pen to restore after drawing
        saved_pen = painter.pen()

        overlap_pen = QPen(color, 1.0, Qt.PenStyle.DashLine)
        overlap_pen.setDashPattern([4, 4])
        painter.setPen(overlap_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        # Left lamella edge
        left_x = int(cx - lamella_half_w_px)
        painter.drawLine(
            left_x, rect_y,
            left_x, rect_y + rect_h,
        )

        # Right lamella edge
        right_x = int(cx + lamella_half_w_px)
        painter.drawLine(
            right_x, rect_y,
            right_x, rect_y + rect_h,
        )

        # Restore pen
        painter.setPen(saved_pen)

    def _draw_stress_relief(
        self, painter: QPainter, entry: dict, entry_index: int,
        cx: float, cy: float, scale: float,
        is_selected: bool,
    ) -> None:
        """Draw stress relief cut rectangles (left/right of
        lamella).

        The inner edge of each rectangle is positioned at
        ``lamella_width / 2 + TrenchOffset`` from the centre.

        Each drawn rectangle is recorded in ``_hit_map`` for
        click-to-select hit testing.  Both the left and right
        rectangle map to the same ``entry_index``; cycling logic
        dedups.
        """
        color = QColor(entry.get("color", _DEFAULT_PATTERN_COLOR))
        trench_offset_um = self._parse_um(
            entry.get("trench_offset", "0")
        )
        lamella_half_w = self._lamella_width_um / 2

        line_width = 2.0 if is_selected else 1.0
        alpha = 180 if is_selected else 60

        for rect in entry.get("rectangles", []):
            w_um = self._parse_um(rect.get("Width", "0"))
            h_um = self._parse_um(rect.get("Height", "0"))
            if w_um <= 0 or h_um <= 0:
                continue

            w_px = w_um * scale
            h_px = h_um * scale

            # Distance from centre to inner edge of rectangle
            inner_edge_um = lamella_half_w + trench_offset_um
            inner_edge_px = inner_edge_um * scale

            pen = QPen(color, line_width)
            painter.setPen(pen)
            fill = QColor(color)
            fill.setAlpha(alpha)
            painter.setBrush(QBrush(fill))

            # Right side
            x_right = cx + inner_edge_px
            rx, ry = int(x_right), int(cy - h_px / 2)
            rw, rh = int(w_px), int(h_px)
            painter.drawRect(rx, ry, rw, rh)
            self._hit_map.append(
                (entry_index, QRectF(rx, ry, rw, rh))
            )

            # Left side
            x_left = cx - inner_edge_px - w_px
            rx, ry = int(x_left), int(cy - h_px / 2)
            painter.drawRect(rx, ry, rw, rh)
            self._hit_map.append(
                (entry_index, QRectF(rx, ry, rw, rh))
            )

    @staticmethod
    def _parse_um(raw) -> float:
        """Parse a value string to µm.

        Handles ``"17 µm"``, ``"398 nm"``, ``"1.5 μm"``,
        ``"0 m"``, etc.  Returns 0.0 on failure.
        """
        result = parse_numeric_value(str(raw))
        if result is None:
            return 0.0
        value, unit = result
        unit_lower = unit.lower().strip()
        if unit_lower in ("nm",):
            return value / 1000.0
        if unit_lower in (
            "µm", "\u00b5m", "\u03bcm", "um", "μm",
        ):
            return value
        if unit_lower in ("mm",):
            return value * 1000.0
        if unit_lower in ("m",):
            return value * 1e6
        # Unitless — assume µm
        return value


# -----------------------------------------------------------------
# Pattern Viewer GroupBox
# -----------------------------------------------------------------

class PatternViewerGroupBox(QGroupBox):
    """Three-column pattern viewer with info panel, schematic
    canvas, and activity toggle buttons."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("Pattern Viewer")

        # State
        self._entries: list[dict] = []
        self._selected_index: int = -1

        self._create_widgets()
        self._setup_layout()

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    def populate(self, site_data: dict) -> None:
        """Populate the pattern viewer from a single site's data.

        :param site_data: A single site entry from the
            consolidated metadata ``"Sites"`` list.
        """
        self._entries = _build_display_entries(site_data)

        if not self._entries:
            self._info_label.setVisible(True)
            self._clear_info_panel()
            self._canvas.clear()
            self._clear_buttons()
            return

        self._info_label.setVisible(False)

        # Parse lamella dimensions for the canvas
        params = site_data.get("SiteProjectData", {}).get(
            "Parameters", {}
        )
        lamella_w = self._parse_um_safe(
            params.get("LamellaWidth", "0")
        )
        final_t = self._parse_um_safe(
            params.get("FinalThickness", "0")
        )

        # Set canvas data
        self._canvas.set_data(
            self._entries, lamella_w, final_t
        )

        # Build toggle buttons
        self._build_buttons()

        # Auto-select the first entry
        if self._entries:
            self._select_entry(0)

        site_name = site_data.get("SiteName", "Unknown")
        logger.info(
            f"Pattern viewer populated for '{site_name}': "
            f"{len(self._entries)} pattern(s)"
        )

    def clear(self) -> None:
        """Reset the viewer to its empty state."""
        self._entries.clear()
        self._selected_index = -1
        self._info_label.setVisible(True)
        self._clear_info_panel()
        self._canvas.clear()
        self._clear_buttons()

    # -----------------------------------------------------------------
    # Setup
    # -----------------------------------------------------------------

    def _create_widgets(self):
        """Create all child widgets."""
        # -- Info placeholder --
        self._info_label = QLabel(
            _PLACEHOLDER_LABEL, parent=self
        )
        self._info_label.setStyleSheet(AppStyles.Label.default())
        self._info_label.setVisible(True)

        # -- Left column: info panel --
        self._info_labels: dict[str, tuple[QLabel, QLabel]] = {}
        self._info_container = QWidget(parent=self)
        info_layout = QGridLayout(self._info_container)
        info_layout.setContentsMargins(
            AppStyles.Dimensions.LAYOUT_CONTENTS_MARGIN,
            AppStyles.Dimensions.LAYOUT_CONTENTS_MARGIN,
            AppStyles.Dimensions.LAYOUT_CONTENTS_MARGIN,
            AppStyles.Dimensions.LAYOUT_CONTENTS_MARGIN,
        )
        info_layout.setSpacing(
            AppStyles.Dimensions.LAYOUT_VSPACING
        )

        fields = [
            ("activity_name", "Activity"),
            ("pattern_type", "Pattern type"),
            ("width", "Width"),
            ("height", "Height"),
            ("depth", "Depth"),
            ("front_left_overlap", "Front left overlap"),
            ("front_right_overlap", "Front right overlap"),
            ("rear_left_overlap", "Rear left overlap"),
            ("rear_right_overlap", "Rear right overlap"),
            ("offset_from_lamella", "Pattern offset"),
            ("overlap", "Overlap"),
            ("overtilt", "Overtilt"),
            ("depth_correction", "Depth correction"),
            ("configured_beam_current", "Beam current"),
            ("measured_beam_current", "Measured current"),
            ("dcm_interval", "DCM"),
            ("duration", "Duration"),
        ]

        for row, (key, label_text) in enumerate(fields):
            name_label = QLabel(label_text, parent=self)
            name_label.setStyleSheet(AppStyles.Label.default())
            value_label = QLabel("", parent=self)
            value_label.setStyleSheet(AppStyles.Label.default())
            value_label.setWordWrap(True)
            info_layout.addWidget(name_label, row, 0)
            info_layout.addWidget(value_label, row, 1, alignment=Qt.AlignmentFlag.AlignRight)
            self._info_labels[key] = (name_label, value_label)

        info_layout.setRowStretch(len(fields), 1)

        # -- Centre column: canvas --
        self._canvas = PatternCanvasWidget(parent=self)
        self._canvas.entry_clicked.connect(
            self._on_canvas_entry_clicked
        )
        self._reset_view_button = ResetViewButton(
            parent=self._canvas
        )
        self._reset_view_button.setFocusPolicy(
            Qt.FocusPolicy.NoFocus
        )
        self._reset_view_button.clicked.connect(
            self._on_reset_view
        )
        self._canvas.installEventFilter(self)

        # -- Right column: button scroll area --
        self._button_group = QButtonGroup(self)
        self._button_group.setExclusive(True)
        # Track whether idClicked is connected, so _clear_buttons
        # can skip the disconnect on the first populate.  Calling
        # disconnect() on an unconnected signal emits a noisy
        # RuntimeWarning before raising RuntimeError in PySide6.
        self._button_signal_connected = False

        self._button_container = QWidget(parent=self)
        self._button_layout = QVBoxLayout(
            self._button_container
        )
        self._button_layout.setContentsMargins(0, 0, 0, 0)
        self._button_layout.setSpacing(0)
        self._button_layout.addStretch(1)

        self._button_scroll = QScrollArea(parent=self)
        self._button_scroll.setWidget(self._button_container)
        self._button_scroll.setWidgetResizable(True)
        self._button_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._button_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self._button_scroll.setStyleSheet(
            AppStyles.ScrollArea.default()
        )

    def _setup_layout(self):
        """Arrange widgets in a three-column layout.

        A horizontal ``QSplitter`` separates the left info panel
        from the centre+right area, allowing the user to drag the
        boundary to expand or contract the info panel.
        """
        # Left column
        left_column = QVBoxLayout()
        left_column.setContentsMargins(0, 0, 0, 0)
        left_column.setSpacing(0)
        left_column.addWidget(self._info_container)
        left_column.addStretch(1)

        left_container = QWidget()
        left_container.setLayout(left_column)
        left_container.setMinimumWidth(
            AppStyles.Dimensions.PATTERN_VIEWER_LEFT_COLUMN_WIDTH
        )

        # Right column (toggle buttons)
        right_container = QWidget()
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        right_layout.addWidget(self._button_scroll)
        right_container.setFixedWidth(
            AppStyles.Dimensions.PATTERN_VIEWER_RIGHT_COLUMN_WIDTH
        )

        # Centre column: canvas (reset button overlaid as child)
        centre_column = QVBoxLayout()
        centre_column.setContentsMargins(0, 0, 0, 0)
        centre_column.setSpacing(0)
        centre_column.addWidget(self._canvas, 1)

        centre_container = QWidget()
        centre_container.setLayout(centre_column)

        # Centre + right in a regular layout
        centre_right_layout = QHBoxLayout()
        centre_right_layout.setContentsMargins(0, 0, 0, 0)
        centre_right_layout.setSpacing(
            AppStyles.Dimensions.LAYOUT_VSPACING
        )
        centre_right_layout.addWidget(centre_container, 1)
        centre_right_layout.addWidget(right_container)

        centre_right_container = QWidget()
        centre_right_container.setLayout(centre_right_layout)

        # Splitter: left info panel | centre+right area
        self._splitter = QSplitter(
            Qt.Orientation.Horizontal, parent=self
        )
        self._splitter.setHandleWidth(
            AppStyles.Dimensions.SPLITTER_HANDLE_WIDTH
        )
        self._splitter.setStyleSheet(
            AppStyles.Splitter.horizontal()
        )
        self._splitter.addWidget(left_container)
        self._splitter.addWidget(centre_right_container)
        self._splitter.setChildrenCollapsible(False)
        # Left: don't absorb resize
        self._splitter.setStretchFactor(0, 0)
        # Right: absorbs resize
        self._splitter.setStretchFactor(1, 1)

        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(
            AppStyles.Dimensions.LAYOUT_CONTENTS_MARGIN,
            AppStyles.Dimensions.LAYOUT_CONTENTS_MARGIN,
            AppStyles.Dimensions.LAYOUT_CONTENTS_MARGIN,
            AppStyles.Dimensions.LAYOUT_CONTENTS_MARGIN,
        )
        main_layout.setSpacing(
            AppStyles.Dimensions.LAYOUT_VSPACING
        )
        main_layout.addWidget(self._info_label)
        main_layout.addWidget(self._splitter, 1)

        self.setStyleSheet(AppStyles.GroupBox.with_title_bold())
        self.setMinimumHeight(
            AppStyles.Dimensions.PATTERN_VIEWER_MINIMUM_HEIGHT
        )

    # -----------------------------------------------------------------
    # Info Panel
    # -----------------------------------------------------------------

    def _update_info_panel(self, entry: dict) -> None:
        """Update the left-column labels from a display entry."""
        for key, (_, value_label) in self._info_labels.items():
            value_label.setText(
                str(entry.get(key, _NA))
            )

    def _clear_info_panel(self) -> None:
        """Clear all value labels in the info panel."""
        for _, (_, value_label) in self._info_labels.items():
            value_label.setText("")

    # -----------------------------------------------------------------
    # Toggle Buttons
    # -----------------------------------------------------------------

    def _build_buttons(self) -> None:
        """Create toggle buttons for each pattern entry."""
        self._clear_buttons()

        for i, entry in enumerate(self._entries):
            btn = PatternToggleButton(
                parent=self._button_container,
                button_text=entry["activity_name"],
            )
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            self._button_group.addButton(btn, i)
            # Insert before the stretch
            self._button_layout.insertWidget(
                self._button_layout.count() - 1, btn
            )

        self._button_group.idClicked.connect(
            self._on_button_clicked
        )
        self._button_signal_connected = True

    def _clear_buttons(self) -> None:
        """Remove all toggle buttons."""
        if self._button_signal_connected:
            self._button_group.idClicked.disconnect(
                self._on_button_clicked
            )
            self._button_signal_connected = False

        for btn in self._button_group.buttons():
            self._button_group.removeButton(btn)
            self._button_layout.removeWidget(btn)
            btn.deleteLater()

    @Slot(int)
    def _on_button_clicked(self, button_id: int) -> None:
        """Handle toggle button selection."""
        self._select_entry(button_id)

    @Slot(int)
    def _on_canvas_entry_clicked(self, entry_index: int) -> None:
        """Handle a click-to-select event from the canvas.

        Routes to the same selection path as a toggle button so
        the info panel, canvas highlight, and button group stay
        in sync.
        """
        self._select_entry(entry_index)

    @Slot()
    def _on_reset_view(self) -> None:
        """Reset the canvas zoom and pan to fit all."""
        self._canvas.reset_view()
        self._canvas.update()

    def eventFilter(self, obj, event):
        """Reposition the reset-view button when the canvas
        resizes so it stays pinned to the bottom-right corner.
        """
        if (
            obj is self._canvas
            and event.type() == QEvent.Type.Resize
        ):
            self._position_reset_button()
        return super().eventFilter(obj, event)

    def _position_reset_button(self) -> None:
        """Pin the reset-view button to the bottom-right corner
        of the canvas with a small inset margin."""
        margin = 8
        btn = self._reset_view_button
        x = self._canvas.width() - btn.width() - margin
        y = self._canvas.height() - btn.height() - margin
        btn.move(x, y)
        btn.raise_()

    # -----------------------------------------------------------------
    # Selection
    # -----------------------------------------------------------------

    def _select_entry(self, index: int) -> None:
        """Select a pattern entry by index.

        Updates the info panel, highlights the canvas, and
        checks the corresponding button.
        """
        if index < 0 or index >= len(self._entries):
            return

        self._selected_index = index
        entry = self._entries[index]

        # Update info panel
        self._update_info_panel(entry)

        # Update canvas highlight
        self._canvas.set_selected(index)

        # Ensure button is checked
        btn = self._button_group.button(index)
        if btn is not None and not btn.isChecked():
            btn.setChecked(True)

    # -----------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------

    @staticmethod
    def _parse_um_safe(raw) -> float:
        """Parse a value string to µm, returning 0.0 on failure."""
        return PatternCanvasWidget._parse_um(raw)