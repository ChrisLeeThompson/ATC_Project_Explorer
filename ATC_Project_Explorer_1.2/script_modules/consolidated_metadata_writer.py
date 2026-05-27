"""
Consolidated Metadata Writer

Module handles building, saving, loading, and validating the
consolidated ATC project metadata JSON file. The consolidated
file merges data from four sources into a single structure:

    1. ProjectData.dat (XML) — instrument info, project-level
       metadata, and per-site parameters/workflow data.
    2. Statistics.txt — per-site activity timing data.
    3. Directory scan — per-site image directory paths.
    4. PrecisePositioningLogImages — per-activity patterning
       rectangle geometry and measured beam current, extracted
       by ``pattern_data_parser``.

The output structure follows the ConsolidatedMetadataConfig
template from the configuration file:

    {
        "ProjectData": { ... },
        "Sites": [
            {
                "SiteName": "Lamella (4)",
                "RelativeSiteDirectoryPath": "Sites/Lamella (4)",
                "SiteProjectData": { ... },
                "Statistics": {
                    "TotalDuration": "01:40:59",
                    "DurationWithoutLamellaPlacement": "01:03:02",
                    "Activities": [ ... ]
                },
                "ImageDirectories": [ ... ],
                "PatternData": [ ... ]
            },
            ...
        ]
    }

Usage:
    metadata = build_consolidated_metadata(
        project_data=project_parser.parse(),
        statistics_data=statistics_parser.parse(),
        directory_data=directory_parser.parse(),
    )
    save_consolidated_metadata(metadata, output_path)
    loaded = load_consolidated_metadata(output_path)
"""
import json
import logging
from pathlib import Path

from script_modules.parsers.pattern_data_parser import (
    extract_site_pattern_data,
)


logger = logging.getLogger(__name__)


# Required top-level keys for validating a consolidated JSON file.
_REQUIRED_KEYS = {"ProjectData", "Sites"}


# -----------------------------------------------------------------
# Build
# -----------------------------------------------------------------

def build_consolidated_metadata(
    project_data: dict,
    statistics_data: dict,
    directory_data: list[dict],
    project_root_path: str | Path | None = None,
) -> dict:
    """
    Build the consolidated metadata dictionary by merging the
    parsed data sources.

    Sites are matched by name across all sources. If a site
    exists in the project data but not in the statistics or
    directory scan, the corresponding section is populated with
    empty defaults.

    When ``project_root_path`` is provided and image directories
    are available, patterning data is extracted from the
    ``PrecisePositioningLogImages`` PNG files for each site.

    :param project_data: Parsed output from ProjectDataParser.parse().
    :param statistics_data: Parsed output from StatisticsParser.parse().
    :param directory_data: Parsed output from ATCDirectoryParser.parse().
    :param project_root_path: Absolute path to the ATC project root
        directory. Stored in the output so that image paths can be
        resolved when loading from a saved JSON file.  Also used
        to resolve image paths for pattern data extraction.
    :return: Consolidated metadata dictionary.
    """
    # Extract project-level info (instrument + project metadata)
    project_info = _extract_project_level_data(project_data)

    # Build lookup maps keyed by site name
    site_project_data_map = _build_site_project_data_map(project_data)
    statistics_map = _build_statistics_map(statistics_data)
    directory_map = _build_directory_map(directory_data)

    # Use site names from project data as the canonical site list,
    # since ProjectData.dat is the authoritative source.
    site_names = list(site_project_data_map.keys())

    sites = []
    for site_name in site_names:
        # Site project data (parameters, workflow, etc.)
        site_pd = site_project_data_map.get(site_name, {})

        # Statistics for this site
        stats = statistics_map.get(site_name)
        if stats:
            statistics_entry = {
                "TotalDuration": stats.get("TotalDuration", "00:00:00"),
                "DurationWithoutLamellaPlacement": stats.get(
                    "DurationWithoutLamellaPlacement", "00:00:00"
                ),
                "Activities": stats.get("Activities", []),
            }
        else:
            statistics_entry = {
                "TotalDuration": "00:00:00",
                "DurationWithoutLamellaPlacement": "00:00:00",
                "Activities": [],
            }

        # Directory / image data for this site
        dir_entry = directory_map.get(site_name, {})
        image_directories = dir_entry.get("ImageDirectories", [])
        relative_site_path = dir_entry.get(
            "RelativeSiteDirectoryPath", ""
        )

        # Pattern data from PrecisePositioningLogImages
        pattern_data: list[dict] = []
        if project_root_path is not None and image_directories:
            pattern_data = extract_site_pattern_data(
                image_directories=image_directories,
                project_root=Path(project_root_path),
            )

        sites.append({
            "SiteName": site_name,
            "RelativeSiteDirectoryPath": relative_site_path,
            "SiteProjectData": site_pd,
            "Statistics": statistics_entry,
            "ImageDirectories": image_directories,
            "PatternData": pattern_data,
        })

    result = {
        "ProjectRootPath": str(project_root_path) if project_root_path else "",
        "ProjectData": project_info,
        "Sites": sites,
    }

    logger.info(
        f"Built consolidated metadata: {len(sites)} site(s)"
    )
    return result


# -----------------------------------------------------------------
# Save / Load / Validate
# -----------------------------------------------------------------

def save_consolidated_metadata(
    metadata: dict,
    output_path: str | Path,
    minify: bool = False,
) -> Path:
    """
    Save consolidated metadata to a JSON file.

    Creates parent directories if they do not exist.

    :param metadata: Consolidated metadata dictionary.
    :param output_path: Destination file path.
    :param minify: If True, write compact JSON with no indentation
        or extra whitespace. If False, write with 2-space indentation.
    :return: The resolved output Path.
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    indent = None if minify else 2
    separators = (",", ":") if minify else None

    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            metadata, f,
            indent=indent,
            separators=separators,
            ensure_ascii=False,
        )

    logger.info(f"Consolidated metadata saved to: {path}")
    return path


def load_consolidated_metadata(file_path: str | Path) -> dict | None:
    """
    Load and validate a consolidated metadata JSON file.

    :param file_path: Path to the JSON file.
    :return: Parsed metadata dictionary, or None if validation
             fails or the file cannot be read.
    """
    path = Path(file_path)
    if not path.exists():
        logger.error(f"Metadata file not found: {path}")
        return None

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        logger.error(f"Failed to read metadata file: {path}", exc_info=True)
        return None

    if not validate_consolidated_json(data):
        logger.warning(f"Invalid metadata format: {path}")
        return None

    logger.info(
        f"Loaded consolidated metadata: {path.name} "
        f"({len(data.get('Sites', []))} sites)"
    )
    return data


def validate_consolidated_json(data: dict | Path) -> bool:
    """
    Validate that a dictionary or JSON file has the required
    structure for consolidated ATC metadata.

    Checks for the presence of the required top-level keys
    ('ProjectData' and 'Sites') and that 'Sites' is a list.

    :param data: Either a parsed dictionary or a Path to a JSON
                 file to validate.
    :return: True if valid, False otherwise.
    """
    # If given a path, load it first
    if isinstance(data, (str, Path)):
        path = Path(data)
        if not path.exists():
            return False
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return False

    if not isinstance(data, dict):
        return False
    if not _REQUIRED_KEYS.issubset(data.keys()):
        return False
    if not isinstance(data.get("Sites"), list):
        return False
    return True


# -----------------------------------------------------------------
# Internal Helpers
# -----------------------------------------------------------------

def _extract_project_level_data(project_data: dict) -> dict:
    """
    Extract project-level data (instrument info and project
    metadata without the Sites list) from the parsed XML.

    :param project_data: Full parsed output from ProjectDataParser.
    :return: Dictionary with 'Instrument' and project-level fields.
    """
    result = {}

    # Instrument info
    instrument = project_data.get("Instrument")
    if instrument:
        result["Instrument"] = instrument

    # Project-level fields (excluding Sites)
    project = project_data.get("Project", {})
    if isinstance(project, dict):
        project_fields = {
            k: v for k, v in project.items()
            if k != "Sites"
        }
        result["Project"] = project_fields

    return result


def _build_site_project_data_map(
    project_data: dict,
) -> dict[str, dict]:
    """
    Build a mapping of site name → site project data from the
    parsed ProjectData.dat output.

    :param project_data: Full parsed output from ProjectDataParser.
    :return: Dict mapping site names to their project data dicts.
    """
    result = {}
    project = project_data.get("Project", {})
    if not isinstance(project, dict):
        return result

    sites_container = project.get("Sites", {})

    # Handle Sites as dict with Site key or as list
    if isinstance(sites_container, dict):
        site_list = sites_container.get("Site", [])
        if isinstance(site_list, dict):
            site_list = [site_list]
    elif isinstance(sites_container, list):
        site_list = sites_container
    else:
        site_list = []

    for site in site_list:
        name = site.get("Name", "")
        if name:
            result[name] = site
        else:
            logger.warning(
                "Skipping site with empty Name in ProjectData"
            )

    return result


def _build_statistics_map(
    statistics_data: dict,
) -> dict[str, dict]:
    """
    Build a mapping of lamella name → statistics entry from
    the parsed Statistics.txt output.

    :param statistics_data: Parsed output from StatisticsParser.
    :return: Dict mapping lamella names to their statistics dicts.
    """
    result = {}
    for lamella in statistics_data.get("Lamellae", []):
        name = lamella.get("Name", "")
        if name:
            result[name] = lamella
        else:
            logger.warning(
                "Skipping lamella with empty Name in Statistics"
            )
    return result


def _build_directory_map(
    directory_data: list[dict],
) -> dict[str, dict]:
    """
    Build a mapping of site name → directory scan entry from
    the ATCDirectoryParser output.

    :param directory_data: Parsed output from ATCDirectoryParser.
    :return: Dict mapping site names to their directory data dicts.
    """
    result = {}
    for site_entry in directory_data:
        name = site_entry.get("SiteName", "")
        if name:
            result[name] = site_entry
        else:
            logger.warning(
                "Skipping site with empty SiteName in "
                "directory data"
            )
    return result