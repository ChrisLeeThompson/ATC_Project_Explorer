"""
Consolidated Data Reader

Functions for extracting computed values from the consolidated ATC
project metadata JSON structure.  This is the data-access layer
between the consolidated metadata (built by
``consolidated_metadata_writer``) and the UI components that display
project statistics, per-site details, and plot data.

``get_global_stats()`` and ``get_activity_duration_means()`` compute
project-wide means for the global stats panel; ``get_site_stats()``
extracts per-site values for the site stats panel;
``group_site_activities_by_segment()`` lists a site's activity runs
for the duration chart.
"""
import logging
from dataclasses import dataclass

# Imported for this module's own use and re-exported for existing
# importers (e.g. the bar-chart widgets).
from script_modules.value_utils import (
    format_seconds,
    parse_duration_to_seconds,
    parse_numeric_value,
)


logger = logging.getLogger(__name__)


# =====================================================================
# Data Structures
# =====================================================================

@dataclass
class GlobalStats:
    """Pre-formatted global statistics for direct display in the UI.

    All fields are strings ready for ``QLabel.setText()``.
    """
    num_sites: str
    mean_target_thickness: str
    mean_milling_angle: str
    mean_lamella_width: str
    mean_total_duration: str
    mean_duration_without_placement: str
    mean_preparation_duration_without_placement: str
    mean_lamella_placement_duration: str
    mean_total_milling_duration: str
    mean_total_thinning_duration: str
    mean_total_delay_duration: str


@dataclass
class SiteStats:
    """Pre-formatted statistics for a single site, ready for direct
    display in the UI.  All fields are strings for ``QLabel.setText()``.
    """
    target_thickness: str
    milling_angle: str
    lamella_width: str
    total_duration: str
    duration_without_placement: str
    lamella_placement_duration: str
    preparation_duration_without_placement: str
    milling_duration: str
    thinning_duration: str
    delay_duration: str


@dataclass
class CategorizedDurations:
    """Per-site activity durations bucketed by workflow step.

    All values are in seconds.
    """
    preparation_s: int = 0
    lamella_placement_s: int = 0
    milling_s: int = 0
    thinning_s: int = 0
    delay_s: int = 0

    @property
    def preparation_without_placement_s(self) -> int:
        """Preparation duration excluding lamella placement."""
        return self.preparation_s - self.lamella_placement_s


@dataclass
class ActivityMean:
    """Mean duration of one activity across sites, for the global
    stats panel.

    ``mean_duration`` is the mean over sites of each site's total for
    the activity (all runs summed), formatted ``HH:MM:SS``;
    ``site_count`` is the number of sites in that mean.
    """
    name: str
    mean_duration: str
    site_count: int


@dataclass
class SegmentActivity:
    """One activity run within a duration-chart segment.

    ``label`` carries the run marker (see :func:`format_run_label`),
    ``run_count`` is how many times the site ran the activity.
    """
    label: str
    seconds: int
    run_count: int


# Segment keys of the global duration chart.  "Preparation" excludes
# lamella placement, which is its own segment.
SEGMENT_PREPARATION = "Preparation"
SEGMENT_LAMELLA_PLACEMENT = "Lamella Placement"
SEGMENT_MILLING = "Milling"
SEGMENT_THINNING = "Thinning"
SEGMENT_DELAY = "Delay"
SEGMENT_KEYS = (
    SEGMENT_PREPARATION,
    SEGMENT_LAMELLA_PLACEMENT,
    SEGMENT_MILLING,
    SEGMENT_THINNING,
    SEGMENT_DELAY,
)


# =====================================================================
# Public API
# =====================================================================

def get_global_stats(metadata: dict) -> GlobalStats:
    """Compute project-wide statistics from consolidated metadata.

    Extracts per-site values and computes averages. Sites that are
    missing a particular value are excluded from that value's average
    (i.e. they do not drag the mean toward zero).

    :param metadata: Consolidated metadata dictionary with
        top-level keys ``"ProjectData"`` and ``"Sites"``.
    :return: A ``GlobalStats`` dataclass with pre-formatted strings.
    """
    sites = metadata.get("Sites", [])
    num_sites = len(sites)

    if num_sites == 0:
        return GlobalStats(
            num_sites="0",
            mean_target_thickness="N/A",
            mean_milling_angle="N/A",
            mean_lamella_width="N/A",
            mean_total_duration="N/A",
            mean_duration_without_placement="N/A",
            mean_preparation_duration_without_placement="N/A",
            mean_lamella_placement_duration="N/A",
            mean_total_milling_duration="N/A",
            mean_total_thinning_duration="N/A",
            mean_total_delay_duration="N/A",
        )

    # Collect per-site values
    thicknesses: list[float] = []
    thickness_unit: str = ""
    milling_angles: list[float] = []
    angle_unit: str = ""
    lamella_widths: list[float] = []
    width_unit: str = ""
    total_durations_s: list[int] = []
    durations_no_placement_s: list[int] = []
    placement_durations_s: list[int] = []
    prep_without_placement_durations_s: list[int] = []
    milling_durations_s: list[int] = []
    thinning_durations_s: list[int] = []
    delay_durations_s: list[int] = []

    for site in sites:
        site_name = site.get("SiteName", "Unknown")
        site_pd = site.get("SiteProjectData", {})

        # FinalThickness (e.g. "150 nm")
        thickness_result = extract_final_thickness(site_pd)
        if thickness_result is not None:
            value, unit = thickness_result
            thicknesses.append(value)
            if not thickness_unit and unit:
                thickness_unit = unit
        else:
            logger.debug(f"No FinalThickness for site '{site_name}'")

        # MillingAngle (e.g. "12 °")
        angle_result = extract_milling_angle(site_pd)
        if angle_result is not None:
            value, unit = angle_result
            milling_angles.append(value)
            if not angle_unit and unit:
                angle_unit = unit
        else:
            logger.debug(f"No MillingAngle for site '{site_name}'")

        # LamellaWidth (e.g. "10 µm")
        width_result = extract_lamella_width(site_pd)
        if width_result is not None:
            value, unit = width_result
            lamella_widths.append(value)
            if not width_unit and unit:
                width_unit = unit
        else:
            logger.debug(f"No LamellaWidth for site '{site_name}'")

        # Statistics durations (e.g. "01:40:59")
        stats = site.get("Statistics", {})

        td_seconds = parse_duration_to_seconds(
            stats.get("TotalDuration", "")
        )
        if td_seconds is not None:
            total_durations_s.append(td_seconds)

        dwp_seconds = parse_duration_to_seconds(
            stats.get("DurationWithoutLamellaPlacement", "")
        )
        if dwp_seconds is not None:
            durations_no_placement_s.append(dwp_seconds)

        # Lamella placement = total - without placement
        if td_seconds is not None and dwp_seconds is not None:
            placement_s = max(td_seconds - dwp_seconds, 0)
            if placement_s > 0:
                placement_durations_s.append(placement_s)

        cat = categorize_site_durations(site)
        if cat.preparation_without_placement_s > 0:
            prep_without_placement_durations_s.append(
                cat.preparation_without_placement_s
            )
        if cat.milling_s > 0:
            milling_durations_s.append(cat.milling_s)
        if cat.thinning_s > 0:
            thinning_durations_s.append(cat.thinning_s)
        if cat.delay_s > 0:
            delay_durations_s.append(cat.delay_s)

    stats = GlobalStats(
        num_sites=str(num_sites),
        mean_target_thickness=format_mean_with_unit(
            thicknesses, thickness_unit
        ),
        mean_milling_angle=format_mean_with_unit(
            milling_angles, angle_unit
        ),
        mean_lamella_width=format_mean_with_unit(
            lamella_widths, width_unit
        ),
        mean_total_duration=format_mean_duration(total_durations_s),
        mean_duration_without_placement=format_mean_duration(
            durations_no_placement_s
        ),
        mean_preparation_duration_without_placement=format_mean_duration(
            prep_without_placement_durations_s
        ),
        mean_lamella_placement_duration=format_mean_duration(
            placement_durations_s
        ),
        mean_total_milling_duration=format_mean_duration(
            milling_durations_s
        ),
        mean_total_thinning_duration=format_mean_duration(
            thinning_durations_s
        ),
        mean_total_delay_duration=format_mean_duration(
            delay_durations_s
        ),
    )

    logger.info(
        f"Global stats computed: {num_sites} site(s), "
        f"{len(thicknesses)} thickness value(s), "
        f"{len(milling_angles)} milling angle value(s), "
        f"{len(lamella_widths)} lamella width value(s)"
    )

    return stats


def get_site_stats(site_data: dict) -> SiteStats:
    """Compute statistics for a single site from its consolidated
    metadata entry.

    :param site_data: A single site entry from the consolidated
        metadata ``"Sites"`` list, containing keys such as
        ``"SiteName"``, ``"SiteProjectData"``, ``"Statistics"``.
    :return: A ``SiteStats`` dataclass with pre-formatted strings.
    """
    site_name = site_data.get("SiteName", "Unknown")
    site_pd = site_data.get("SiteProjectData", {})
    stats = site_data.get("Statistics", {})

    na = "N/A"

    # -- Target thickness ---------------------------------------------
    thickness_result = extract_final_thickness(site_pd)
    if thickness_result is not None:
        value, unit = thickness_result
        target_thickness = format_value_with_unit(value, unit)
    else:
        target_thickness = na

    # -- Milling angle ------------------------------------------------
    angle_result = extract_milling_angle(site_pd)
    if angle_result is not None:
        value, unit = angle_result
        milling_angle = format_value_with_unit(value, unit)
    else:
        milling_angle = na

    # -- Lamella width ------------------------------------------------
    width_result = extract_lamella_width(site_pd)
    if width_result is not None:
        value, unit = width_result
        lamella_width = format_value_with_unit(value, unit)
    else:
        lamella_width = na

    # -- Durations from Statistics block ------------------------------
    td_seconds = parse_duration_to_seconds(
        stats.get("TotalDuration", "")
    )
    dwp_seconds = parse_duration_to_seconds(
        stats.get("DurationWithoutLamellaPlacement", "")
    )

    total_duration = format_seconds(td_seconds) if td_seconds else na
    duration_without_placement = (
        format_seconds(dwp_seconds) if dwp_seconds else na
    )

    # Lamella placement = total - without placement
    if td_seconds is not None and dwp_seconds is not None:
        lp_s = max(td_seconds - dwp_seconds, 0)
        lamella_placement_duration = (
            format_seconds(lp_s) if lp_s > 0 else na
        )
    else:
        lamella_placement_duration = na

    # -- Categorize activities by workflow step ------------------------
    cat = categorize_site_durations(site_data)

    result = SiteStats(
        target_thickness=target_thickness,
        milling_angle=milling_angle,
        lamella_width=lamella_width,
        total_duration=total_duration,
        duration_without_placement=duration_without_placement,
        lamella_placement_duration=lamella_placement_duration,
        preparation_duration_without_placement=(
            format_seconds(cat.preparation_without_placement_s)
            if cat.preparation_without_placement_s > 0 else na
        ),
        milling_duration=(
            format_seconds(cat.milling_s)
            if cat.milling_s > 0 else na
        ),
        thinning_duration=(
            format_seconds(cat.thinning_s)
            if cat.thinning_s > 0 else na
        ),
        delay_duration=(
            format_seconds(cat.delay_s)
            if cat.delay_s > 0 else na
        ),
    )

    logger.info(f"Site stats computed for '{site_name}'")
    return result


# =====================================================================
# Data Extraction Helpers
# =====================================================================

def categorize_site_durations(
    site_data: dict,
) -> CategorizedDurations:
    """Categorize a single site's activity durations by workflow
    step.

    Sums the segments of :func:`group_site_activities_by_segment`
    into Preparation (including lamella placement), Lamella
    Placement, Milling, Thinning, and Delay.

    :param site_data: A single site entry from the consolidated
        metadata ``"Sites"`` list.
    :return: A ``CategorizedDurations`` dataclass with bucketed
        seconds.
    """
    segments = group_site_activities_by_segment(site_data)

    def total(key: str) -> int:
        return sum(a.seconds for a in segments[key])

    lp_s = total(SEGMENT_LAMELLA_PLACEMENT)
    return CategorizedDurations(
        preparation_s=total(SEGMENT_PREPARATION) + lp_s,
        lamella_placement_s=lp_s,
        milling_s=total(SEGMENT_MILLING),
        thinning_s=total(SEGMENT_THINNING),
        delay_s=total(SEGMENT_DELAY),
    )


def group_site_activities_by_segment(
    site_data: dict,
) -> dict[str, list[SegmentActivity]]:
    """List a site's activity runs under their duration-chart
    segment.

    Builds the activity-to-step mapping from the site's recipe tree
    and walks the Statistics activities in order.  ``Delay`` rows go
    to their own segment regardless of recipe (so they don't inflate
    the parent step); ``Lamella Placement`` is split out of
    Preparation.  Rows with an unparseable or zero duration, and
    activities the recipe doesn't know, are left out.

    :param site_data: A single site entry from the consolidated
        metadata ``"Sites"`` list.
    :return: ``{segment_key: [SegmentActivity, ...]}`` with every
        key of ``SEGMENT_KEYS`` present.
    """
    site_pd = site_data.get("SiteProjectData", {})
    activities = site_data.get("Statistics", {}).get("Activities", [])
    step_map = build_activity_step_map(site_pd)

    segments: dict[str, list[SegmentActivity]] = {
        key: [] for key in SEGMENT_KEYS
    }
    for activity, (run_index, run_count) in zip(
        activities, number_activity_runs(activities)
    ):
        act_name = activity.get("ActivityName", "")
        act_seconds = parse_duration_to_seconds(
            activity.get("Duration", "")
        )
        if act_seconds is None:
            continue

        if act_name == "Delay":
            key = SEGMENT_DELAY
        else:
            step = step_map.get(act_name, "")
            if step == "Preparation":
                key = (
                    SEGMENT_LAMELLA_PLACEMENT
                    if act_name == "Lamella Placement"
                    else SEGMENT_PREPARATION
                )
            elif step in (SEGMENT_MILLING, SEGMENT_THINNING):
                key = step
            else:
                logger.debug(
                    f"Unmatched activity '{act_name}' in "
                    f"site '{site_data.get('SiteName', 'Unknown')}'"
                )
                continue

        segments[key].append(SegmentActivity(
            label=format_run_label(act_name, run_index, run_count),
            seconds=act_seconds,
            run_count=run_count,
        ))

    return segments


def build_activity_step_map(
    site_project_data: dict,
) -> dict[str, str]:
    """Build a mapping of activity name to workflow step by
    recursively walking the recipe tree.

    The XML recipe structure nests sub-activities inside parent
    activities (e.g. ``CryoReferenceDefinitionActivity`` contains
    ``Reference Redefinition 1`` and ``2``). The Statistics file
    uses these nested names as flat activity entries, so we must
    collect *all* ``Name`` fields at every depth within each
    recipe step.

    :param site_project_data: A single site's SiteProjectData dict.
    :return: Dict mapping activity display names to their workflow
        step (e.g. ``{"Rough Milling": "Milling"}``).
    """
    result: dict[str, str] = {}
    workflow = site_project_data.get("Workflow", {})
    recipes = workflow.get("Recipe", [])
    if isinstance(recipes, dict):
        recipes = [recipes]
    for recipe in recipes:
        step = recipe.get("WorkflowStep", "")
        activities = recipe.get("Activities", {})
        for _act_key, act_val in activities.items():
            names = _collect_activity_names(act_val)
            for name in names:
                result[name] = step
    return result


def _collect_activity_names(obj) -> list[str]:
    """Recursively collect all ``Name`` string values from a
    nested activity dictionary or list.

    :param obj: A dict, list, or scalar from the parsed XML.
    :return: List of activity name strings found at any depth.
    """
    names: list[str] = []
    if isinstance(obj, dict):
        name = obj.get("Name")
        if name and isinstance(name, str):
            names.append(name)
        for key, val in obj.items():
            if key != "Name":
                names.extend(_collect_activity_names(val))
    elif isinstance(obj, list):
        for item in obj:
            names.extend(_collect_activity_names(item))
    return names


def extract_final_thickness(
    site_project_data: dict,
) -> tuple[float, str] | None:
    """Extract the numeric FinalThickness from SiteProjectData.

    Path: ``SiteProjectData.Parameters.FinalThickness``
    Expected format: ``"150 nm"``

    :param site_project_data: A single site's SiteProjectData dict.
    :return: ``(value, unit)`` tuple, or *None* if unavailable.
    """
    try:
        raw = (
            site_project_data
            .get("Parameters", {})
            .get("FinalThickness", "")
        )
        return parse_numeric_value(raw)
    except Exception:
        logger.debug(
            "Failed to extract FinalThickness",
            exc_info=True,
        )
        return None


def extract_milling_angle(
    site_project_data: dict,
) -> tuple[float, str] | None:
    """Extract the numeric MillingAngle from SiteProjectData.

    Path: ``SiteProjectData.Workflow.Recipe[*].Activities
    .MillingAngleActivity.MillingAngle``

    The Recipe node is a list of workflow steps; the value comes
    from the first step that contains a MillingAngleActivity.

    Expected format: ``"12 °"``

    :param site_project_data: A single site's SiteProjectData dict.
    :return: ``(value, unit)`` tuple, or *None* if unavailable.
    """
    try:
        workflow = site_project_data.get("Workflow", {})
        recipes = workflow.get("Recipe", [])
        # Recipe may be a single dict or a list of dicts
        if isinstance(recipes, dict):
            recipes = [recipes]
        for recipe in recipes:
            activities = recipe.get("Activities", {})
            milling_activity = activities.get(
                "MillingAngleActivity", {}
            )
            raw = milling_activity.get("MillingAngle", "")
            if raw:
                result = parse_numeric_value(raw)
                if result is not None:
                    return result
    except Exception:
        logger.debug(
            "Failed to extract MillingAngle",
            exc_info=True,
        )
    return None


def extract_lamella_width(
    site_project_data: dict,
) -> tuple[float, str] | None:
    """Extract the numeric LamellaWidth from SiteProjectData.

    Path: ``SiteProjectData.Parameters.LamellaWidth``
    Expected format: ``"10 µm"``

    :param site_project_data: A single site's SiteProjectData dict.
    :return: ``(value, unit)`` tuple, or *None* if unavailable.
    """
    try:
        raw = (
            site_project_data
            .get("Parameters", {})
            .get("LamellaWidth", "")
        )
        return parse_numeric_value(raw)
    except Exception:
        logger.debug(
            "Failed to extract LamellaWidth",
            exc_info=True,
        )
        return None


# =====================================================================
# Activity Runs
# =====================================================================
#
# A site can run the same activity more than once (e.g. "Polishing 2"
# three times).  Statistics.txt records each run as its own row, in
# chronological order, so an activity's runs are the rows sharing its
# name, numbered by position.

def number_activity_runs(
    activities: list[dict],
) -> list[tuple[int, int]]:
    """Number the runs of each activity name.

    :param activities: A site's ``Statistics.Activities`` list.
    :return: One ``(run_index, run_count)`` per entry, in list order,
        with ``run_index`` 1-based within the entry's name.
    """
    counts: dict[str, int] = {}
    for activity in activities:
        name = activity.get("ActivityName", "")
        counts[name] = counts.get(name, 0) + 1

    seen: dict[str, int] = {}
    result: list[tuple[int, int]] = []
    for activity in activities:
        name = activity.get("ActivityName", "")
        seen[name] = seen.get(name, 0) + 1
        result.append((seen[name], counts[name]))
    return result


def format_run_label(
    name: str, run_index: int, run_count: int,
) -> str:
    """Label one run of an activity for display.

    Shared by the site activity chart and the pattern viewer so a
    repeated activity reads the same everywhere.

    :param name: Activity name.
    :param run_index: 1-based run number.
    :param run_count: Number of runs of this activity at the site.
    :return: ``name`` alone for a single run, otherwise
        ``"name (run_index/run_count)"``.
    """
    if run_count <= 1:
        return name
    return f"{name} ({run_index}/{run_count})"


def group_activity_durations(
    activities: list[dict],
) -> dict[str, list[str]]:
    """Group duration strings by activity name, in run order.

    :param activities: A site's ``Statistics.Activities`` list.
    :return: Mapping ``{name: [duration, ...]}``.
    """
    result: dict[str, list[str]] = {}
    for activity in activities:
        name = activity.get("ActivityName", "")
        result.setdefault(name, []).append(
            activity.get("Duration", "")
        )
    return result


def get_activity_duration_means(metadata: dict) -> list[ActivityMean]:
    """Mean duration of every activity across the given sites.

    Each site contributes its total for an activity (all runs summed);
    sites where that total is zero or missing are left out of the
    mean, matching :func:`get_global_stats`.  Activities are listed in
    workflow order, merged across sites (see
    :func:`_merge_activity_order`).

    :param metadata: Consolidated metadata dictionary (the ``"Sites"``
        list is the only key used).
    :return: One ``ActivityMean`` per activity name found.
    """
    totals: dict[str, list[int]] = {}
    order: list[str] = []

    for site in metadata.get("Sites", []):
        activities = site.get("Statistics", {}).get("Activities", [])
        site_seconds: dict[str, int] = {}
        for activity in activities:
            name = activity.get("ActivityName", "")
            if not name:
                continue
            seconds = parse_duration_to_seconds(
                activity.get("Duration", "")
            ) or 0
            site_seconds[name] = site_seconds.get(name, 0) + seconds

        order = _merge_activity_order(order, list(site_seconds))
        for name, seconds in site_seconds.items():
            if seconds > 0:
                totals.setdefault(name, []).append(seconds)

    return [
        ActivityMean(
            name=name,
            mean_duration=format_mean_duration(totals.get(name, [])),
            site_count=len(totals.get(name, [])),
        )
        for name in order
    ]


def _merge_activity_order(
    order: list[str], sequence: list[str],
) -> list[str]:
    """Merge one site's activity sequence into the running order.

    A name not yet listed is inserted right after its nearest
    predecessor (in ``sequence``) that is already listed, or appended
    when none of its predecessors is.  Sites run their activities in
    workflow order, so this keeps a name that only some sites have
    (e.g. ``Reference Redefinition 1``) in its workflow position.

    :param order: Names merged so far (not mutated).
    :param sequence: One site's activity names, first occurrences in
        chronological order.
    :return: The merged order.
    """
    merged = list(order)
    for i, name in enumerate(sequence):
        if name in merged:
            continue
        insert_at = len(merged)
        for predecessor in reversed(sequence[:i]):
            if predecessor in merged:
                insert_at = merged.index(predecessor) + 1
                break
        merged.insert(insert_at, name)
    return merged


# =====================================================================
# Parsing / Formatting Helpers
# =====================================================================

# The formatting helpers below consume the reader's own schema-derived
# value/unit lists, so they live here rather than in value_utils.
def format_value_with_unit(value: float, unit: str) -> str:
    """Format a single numeric value with a unit string.

    :param value: Numeric value.
    :param unit: Unit label to append (e.g. ``"nm"``, ``"°"``).
    :return: Formatted string like ``"150 nm"`` or ``"12.5 °"``.
    """
    if value == int(value):
        return f"{int(value)} {unit}"
    return f"{value:.1f} {unit}"


def format_mean_with_unit(
    values: list[float], unit: str
) -> str:
    """Compute the mean of a list and format with a unit string.

    :param values: List of numeric values.
    :param unit: Unit label to append (e.g. ``"nm"``, ``"°"``).
    :return: Formatted string like ``"150.0 nm"``, or ``"N/A"``
        if the list is empty.
    """
    if not values:
        return "N/A"
    mean = sum(values) / len(values)
    # Use integer display when the mean is whole
    if mean == int(mean):
        return f"{int(mean)} {unit}"
    return f"{mean:.1f} {unit}"


def format_mean_duration(seconds_list: list[int]) -> str:
    """Compute the mean duration and format as ``HH:MM:SS``.

    :param seconds_list: List of durations in seconds.
    :return: Formatted mean duration, or ``"N/A"`` if empty.
    """
    if not seconds_list:
        return "N/A"
    mean_seconds = round(sum(seconds_list) / len(seconds_list))
    return format_seconds(mean_seconds)