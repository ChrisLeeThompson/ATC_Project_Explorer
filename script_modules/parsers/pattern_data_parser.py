"""
Pattern Data Parser

Module extracts per-activity patterning data from the
``PrecisePositioningLogImages`` directory of each ATC site.
The extracted data is stored in the consolidated metadata JSON
so that the Pattern Viewer groupbox can display pattern
information without re-reading image files at runtime.

For each site the parser:

1. Locates the ``PrecisePositioningLogImages`` directory in the
   site's ``ImageDirectories``.
2. Groups match-information image filenames by activity name
   (parsed from the filename, e.g.
   ``"2025-10-29-14-11-48-Rough-Milling-match-information-image.png"``
   → ``"Rough Milling"``).  Activities that never contain
   patterning data (e.g. Eucentric Tilt, Reference Definition)
   are skipped by keyword matching.
3. Splits an activity that the site ran more than once into its
   runs.  The run count comes from the site's statistics
   (``run_counts``); the images are split at the largest gaps
   between their filename timestamps.  Each run then yields its
   own entry, tagged ``"RunIndex"`` / ``"RunCount"``.
4. Reads the **most recent** image per run (or per activity when
   there is a single run).  A quick byte scan for the
   ``PatterningInformation`` marker is performed before full XML
   parsing to skip files without pattern data.
5. Extracts ``PatterningInformation`` rectangle geometry and
   ``Metrics.MeasuredBeamCurrent`` from the embedded FEI XML
   metadata.

Front/rear splitting for activities with different trench
heights (e.g. Rough Milling with ``FrontTrenchHeight`` /
``RearTrenchHeight``) is handled downstream by the display
layer using project metadata fields, not by the parser.

Usage::

    from script_modules.parsers.pattern_data_parser import (
        extract_site_pattern_data,
    )

    pattern_data = extract_site_pattern_data(
        image_directories=site["ImageDirectories"],
        project_root=Path("/path/to/project"),
        run_counts={"Polishing 2": 3},
    )
"""
import logging
import re
from datetime import datetime
from pathlib import Path

from script_modules.parsers.image_metadata_parser import (
    extract_xml_metadata,
)


logger = logging.getLogger(__name__)


# Directory name within each site that contains the
# match-information images with embedded patterning metadata.
_PRECISE_POS_DIR = "PrecisePositioningLogImages"

# Regex to parse the timestamp and activity name from the filename.
# Format: YYYY-MM-DD-HH-MM-SS-Activity-Name-match-information-image.png
_FILENAME_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2})-"  # timestamp prefix
    r"(.+?)"                                    # activity name
    r"-match-information-image"                 # suffix
    r"\.\w+$",                                  # extension
    re.IGNORECASE,
)
_TIMESTAMP_FORMAT = "%Y-%m-%d-%H-%M-%S"

# Activity name substrings (lowercase) that never contain
# PatterningInformation.  These are skipped during grouping
# to avoid unnecessary file reads and XML parsing.
_SKIP_ACTIVITY_KEYWORDS = frozenset({
    "eucentric tilt",
    "milling angle",
    "reference definition",
    "reference redefinition",
    "electron image",
    "electron reference",
    "image acquisition",
})

# Byte marker used for a quick pre-filter scan before
# committing to full XML parsing.
_PATTERNING_MARKER = b"PatterningInformation"


# -----------------------------------------------------------------
# Public API
# -----------------------------------------------------------------

def extract_site_pattern_data(
    image_directories: list[dict],
    project_root: Path,
    run_counts: dict[str, int] | None = None,
) -> list[dict]:
    """Extract patterning data for a single site.

    Scans the ``PrecisePositioningLogImages`` directory, groups
    images by activity name (skipping activities that never have
    patterns), splits activities run more than once into their
    runs, and extracts patterning rectangle geometry plus
    supplementary metadata from the most recent image per run.

    :param image_directories: The ``"ImageDirectories"`` list
        from a single site entry in the consolidated metadata.
    :param project_root: Absolute path to the ATC project root
        directory, used to resolve relative image paths.
    :param run_counts: Optional ``{activity_name: run_count}`` from
        the site's statistics.  Activities absent from it, or with
        a count of 1, produce a single entry.
    :return: List of pattern data dicts, one per run of each
        activity that has patterning data.  Entries of a split
        activity carry ``"RunIndex"`` (1-based) and ``"RunCount"``.
        Empty list if none found.
    """
    # Locate the PrecisePositioningLogImages directory
    rel_paths = _find_precise_pos_paths(image_directories)
    if not rel_paths:
        return []

    # Group filenames by activity name
    activity_groups = _group_by_activity(rel_paths)
    if not activity_groups:
        return []

    run_counts = run_counts or {}
    result: list[dict] = []

    for activity_name, paths in activity_groups.items():
        entries = _extract_activity_entries(
            activity_name,
            paths,
            project_root,
            run_count=run_counts.get(activity_name, 1),
        )
        result.extend(entries)

    logger.info(
        f"Extracted pattern data: "
        f"{len(result)} pattern(s)"
    )
    return result


# -----------------------------------------------------------------
# Internal Helpers
# -----------------------------------------------------------------

def _find_precise_pos_paths(
    image_directories: list[dict],
) -> list[str]:
    """Find relative image paths from the
    PrecisePositioningLogImages directory.

    :param image_directories: Site's ImageDirectories list.
    :return: Sorted list of relative path strings, or empty list.
    """
    for d in image_directories:
        if d.get("DirectoryName") == _PRECISE_POS_DIR:
            paths = d.get("RelativeImagePaths", [])
            return sorted(paths)
    return []


def _group_by_activity(
    rel_paths: list[str],
) -> dict[str, list[str]]:
    """Group image paths by activity name parsed from filenames.

    Only includes filenames that match the match-information
    naming convention.  Activity names are converted from
    hyphenated form to space-separated (e.g.
    ``"Rough-Milling"`` → ``"Rough Milling"``).

    Activities whose names match any keyword in
    ``_SKIP_ACTIVITY_KEYWORDS`` are excluded, since they never
    contain patterning data.

    :param rel_paths: Sorted list of relative image paths.
    :return: Ordered dict mapping activity names to their
        list of relative paths (preserving sort order).
    """
    groups: dict[str, list[str]] = {}

    for rel_path in rel_paths:
        # Extract just the filename
        fname = rel_path.split("/")[-1]
        if "\\" in fname:
            fname = fname.split("\\")[-1]

        match = _FILENAME_RE.match(fname)
        if not match:
            continue

        # Convert hyphens to spaces for the activity name.
        # Handle triple-hyphens first (e.g.
        # "Polishing-2---Electron-Image"
        # → "Polishing 2 - Electron Image").
        raw_name = match.group(2)
        activity_name = (
            raw_name
            .replace("---", "\x00")
            .replace("-", " ")
            .replace("\x00", " - ")
        )

        # Skip activities that never have patterning data
        name_lower = activity_name.lower()
        if any(kw in name_lower for kw in _SKIP_ACTIVITY_KEYWORDS):
            continue

        if activity_name not in groups:
            groups[activity_name] = []
        groups[activity_name].append(rel_path)

    return groups


def _extract_activity_entries(
    activity_name: str,
    rel_paths: list[str],
    project_root: Path,
    run_count: int = 1,
) -> list[dict]:
    """Extract pattern entries for a single activity.

    Reads the most recent image of each run and extracts
    patterning rectangle geometry plus supplementary metadata.

    :param activity_name: Display name of the activity.
    :param rel_paths: Sorted list of relative image paths for
        this activity.
    :param project_root: Absolute path to the project root.
    :param run_count: Number of times the site ran the activity.
    :return: One pattern data dict per run that yields an entry
        (tagged with ``RunIndex`` / ``RunCount`` when the activity
        was split), or a single untagged dict.  Empty list if
        extraction fails.
    """
    runs = _split_into_runs(rel_paths, run_count)
    if len(runs) == 1:
        entry = _read_last_image(
            rel_paths, project_root, activity_name
        )
        return [entry] if entry is not None else []

    entries: list[dict] = []
    for index, run_paths in enumerate(runs, start=1):
        entry = _read_last_image(
            run_paths, project_root, activity_name
        )
        if entry is None:
            continue
        entry["RunIndex"] = index
        entry["RunCount"] = len(runs)
        entries.append(entry)
    return entries


def _split_into_runs(
    rel_paths: list[str],
    run_count: int,
) -> list[list[str]]:
    """Split an activity's images into its runs.

    A run's images are taken seconds to minutes apart, while runs
    are separated by the other activities in between, so the
    ``run_count - 1`` largest gaps between filename timestamps
    mark the run boundaries.  This is a heuristic: a run that left
    no images, or runs that follow each other without a pause, can
    put a boundary inside a run.

    :param rel_paths: Sorted list of relative image paths for one
        activity.
    :param run_count: Number of runs from the site's statistics.
    :return: ``run_count`` lists in chronological order, or
        ``[rel_paths]`` when there is one run, fewer images than
        runs, or a filename whose timestamp does not parse.
    """
    if run_count <= 1 or len(rel_paths) < run_count:
        return [rel_paths]

    timestamps: list[datetime] = []
    for rel_path in rel_paths:
        stamp = _parse_timestamp(rel_path)
        if stamp is None:
            return [rel_paths]
        timestamps.append(stamp)

    gaps = [
        (timestamps[i + 1] - timestamps[i], i + 1)
        for i in range(len(timestamps) - 1)
    ]
    boundaries = sorted(
        i for _, i in sorted(gaps, reverse=True)[: run_count - 1]
    )

    runs: list[list[str]] = []
    start = 0
    for boundary in boundaries + [len(rel_paths)]:
        runs.append(rel_paths[start:boundary])
        start = boundary
    return runs


def _parse_timestamp(rel_path: str) -> datetime | None:
    """Parse the timestamp prefix of a match-information filename.

    :param rel_path: Relative image path.
    :return: The timestamp, or *None* if the filename does not
        follow the naming convention.
    """
    fname = rel_path.replace("\\", "/").split("/")[-1]
    match = _FILENAME_RE.match(fname)
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), _TIMESTAMP_FORMAT)
    except ValueError:
        return None


def _read_last_image(
    rel_paths: list[str],
    project_root: Path,
    activity_name: str,
) -> dict | None:
    """Read the most recent image for an activity.

    Iterates paths in reverse chronological order and returns
    the first successfully extracted entry.

    :param rel_paths: Sorted list of relative image paths.
    :param project_root: Absolute path to the project root.
    :param activity_name: Activity name for the entry.
    :return: Extracted pattern data dict, or *None*.
    """
    for rel_path in reversed(rel_paths):
        abs_path = project_root / Path(
            rel_path.replace("\\", "/")
        )
        if not abs_path.is_file():
            continue
        entry = _extract_from_image(abs_path, activity_name)
        if entry is not None:
            return entry
    return None


def _extract_from_image(
    image_path: Path,
    activity_name: str,
) -> dict | None:
    """Extract pattern data from a single image file.

    Performs a quick byte scan for the ``PatterningInformation``
    marker before committing to full XML parsing.  Files that
    do not contain the marker are skipped immediately.

    Reads the image's embedded XML metadata and extracts:

    - ``PatterningInformation`` rectangles (type, size)
    - ``ProgressInformation.AutomationMessage``
    - ``Metrics.MeasuredBeamCurrent``

    :param image_path: Absolute path to the PNG image.
    :param activity_name: Activity name (from filename parsing).
    :return: Pattern data dict, or *None* if no patterning
        information is present.
    """
    try:
        raw_bytes = image_path.read_bytes()
    except OSError:
        return None
    if _PATTERNING_MARKER not in raw_bytes:
        return None

    try:
        metadata = extract_xml_metadata(
            image_path, raw_bytes=raw_bytes
        )
    except Exception:
        logger.error(
            f"Failed to extract metadata: {image_path.name}",
            exc_info=True,
        )
        return None

    if not metadata:
        return None
    xml = metadata.get("XMLMetadata")
    if not xml:
        return None

    custom_sections = (
        xml
        .get("CustomSectionGroup", {})
        .get("CustomSection", {})
    )
    if not isinstance(custom_sections, dict):
        return None

    # -- PatterningInformation -----------------------------------
    patterning_info = custom_sections.get(
        "PatterningInformation", {}
    )
    if not isinstance(patterning_info, dict):
        return None

    raw_rects = patterning_info.get("PatternDrawingRectangle")
    if raw_rects is None:
        return None

    # Normalise to list
    if isinstance(raw_rects, dict):
        raw_rects = [raw_rects]
    if not isinstance(raw_rects, list) or not raw_rects:
        return None

    rectangles = _parse_rectangles(raw_rects)
    if not rectangles:
        return None

    # -- AutomationMessage from ProgressInformation --------------
    progress_info = custom_sections.get(
        "ProgressInformation", {}
    )
    automation_message = ""
    if isinstance(progress_info, dict):
        msg = progress_info.get("AutomationMessage", "")
        if isinstance(msg, str):
            automation_message = msg

    # -- MeasuredBeamCurrent from Metrics ------------------------
    metrics = custom_sections.get("Metrics", {})
    measured_beam_current = ""
    if isinstance(metrics, dict):
        mbc = metrics.get("MeasuredBeamCurrent", "")
        if isinstance(mbc, str):
            measured_beam_current = mbc

    return {
        "ActivityName": activity_name,
        "AutomationMessage": automation_message,
        "MeasuredBeamCurrent": measured_beam_current,
        "Rectangles": rectangles,
    }


def _parse_rectangles(
    raw_rects: list[dict],
) -> list[dict]:
    """Parse PatternDrawingRectangle entries into simplified
    dicts containing only the fields needed for the pattern
    viewer.

    :param raw_rects: List of raw rectangle dicts from parsed
        XML metadata.
    :return: List of parsed rectangle dicts.  Entries missing
        required size fields are silently skipped.
    """
    result: list[dict] = []

    for raw in raw_rects:
        if not isinstance(raw, dict):
            continue

        size = raw.get("Size", {})
        if not isinstance(size, dict):
            continue

        width = size.get("Width")
        height = size.get("Height")
        depth = size.get("Depth")

        # Width and Height are required
        if width is None or height is None:
            continue

        entry: dict = {
            "PatternType": str(
                raw.get("RectangularType", "")
            ),
            "Width": str(width),
            "Height": str(height),
        }

        if depth is not None:
            entry["Depth"] = str(depth)

        result.append(entry)

    return result