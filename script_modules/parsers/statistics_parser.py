"""
Statistics Parser

Module handles parsing the Statistics.txt file from an AutoTEM
Cryo (ATC) project directory. The Statistics.txt file is a
tab-delimited text file with no header row. Each line contains
three fields:

    LamellaName<TAB>ActivityName<TAB>Duration (HH:MM:SS)

The parser groups activities by lamella name and calculates
total durations per lamella, as well as duration excluding the
Lamella Placement activity (which is often dominated by user
interaction time rather than automated processing).

Usage:
    parser = StatisticsParser(Path("path/to/Statistics.txt"))
    data = parser.parse()
    lamella_names = parser.get_lamella_names()
"""
import logging
from pathlib import Path
from script_modules.value_utils import (
    parse_duration_to_seconds as _parse_duration_or_none,
    format_seconds,
)


logger = logging.getLogger(__name__)


class StatisticsParser:

    # Column indices in the tab-delimited file
    _LAMELLA_COL = 0
    _ACTIVITY_COL = 1
    _DURATION_COL = 2
    _MIN_COLUMNS = 3

    def __init__(self, file_path: str | Path):
        """
        Initialize the parser with the path to a Statistics.txt file.

        :param file_path: Path to the Statistics.txt file.
        :raises FileNotFoundError: If the file does not exist.
        """
        self._file_path = Path(file_path)
        if not self._file_path.exists():
            raise FileNotFoundError(
                f"Statistics.txt not found: {self._file_path}"
            )
        self._parsed_data: dict | None = None

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    def parse(self) -> dict:
        """
        Parse the Statistics.txt file and return a structured
        dictionary.

        The returned dictionary has the structure:
        {
            "Lamellae": [
                {
                    "Name": "Lamella (4)",
                    "TotalDuration": "01:40:25",
                    "DurationWithoutLamellaPlacement": "01:02:28",
                    "Activities": [
                        {"ActivityName": "Eucentric Tilt",
                         "Duration": "00:01:42"},
                        ...
                    ]
                },
                ...
            ]
        }

        :return: Dictionary of parsed statistics data.
        """
        if self._parsed_data is not None:
            return self._parsed_data

        lines = self._read_file()
        if not lines:
            logger.warning("Statistics.txt is empty")
            self._parsed_data = {"Lamellae": []}
            return self._parsed_data

        # Group activities by lamella name (preserving order)
        lamella_order: list[str] = []
        lamella_activities: dict[str, list[dict]] = {}

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            parts = stripped.split("\t")
            if len(parts) < self._MIN_COLUMNS:
                logger.warning(f"Skipping malformed line: {stripped}")
                continue

            lamella_name = parts[self._LAMELLA_COL]
            activity_name = parts[self._ACTIVITY_COL]
            duration_str = parts[self._DURATION_COL]

            total_seconds = _parse_duration_or_none(duration_str) or 0
            duration_formatted = format_seconds(total_seconds)

            if lamella_name not in lamella_activities:
                lamella_order.append(lamella_name)
                lamella_activities[lamella_name] = []

            lamella_activities[lamella_name].append({
                "ActivityName": activity_name,
                "Duration": duration_formatted,
                "TotalSeconds": total_seconds,
            })

        result = {"Lamellae": []}

        for lamella_name in lamella_order:
            activities = lamella_activities[lamella_name]
            total_seconds = sum(a["TotalSeconds"] for a in activities)
            placement_seconds = sum(
                a["TotalSeconds"] for a in activities
                if a["ActivityName"] == "Lamella Placement"
            )
            without_placement = total_seconds - placement_seconds

            activities_clean = [
                {
                    "ActivityName": a["ActivityName"],
                    "Duration": a["Duration"],
                }
                for a in activities
            ]

            result["Lamellae"].append({
                "Name": lamella_name,
                "TotalDuration": format_seconds(total_seconds),
                "DurationWithoutLamellaPlacement": format_seconds(
                    without_placement
                ),
                "Activities": activities_clean,
            })

        self._parsed_data = result
        logger.info(
            f"Parsed Statistics.txt: {len(result['Lamellae'])} lamella(e)"
        )
        return self._parsed_data

    def get_lamella_names(self) -> list[str]:
        """
        Extract the list of lamella names from the parsed data.

        :return: List of lamella name strings in the order they
                 appear in the file.
        """
        data = self._ensure_parsed()
        return [
            lamella["Name"]
            for lamella in data.get("Lamellae", [])
        ]

    # -----------------------------------------------------------------
    # Internal Helpers
    # -----------------------------------------------------------------

    def _ensure_parsed(self) -> dict:
        """Parse if not already parsed and return the data."""
        if self._parsed_data is None:
            self.parse()
        return self._parsed_data

    def _read_file(self) -> list[str]:
        """
        Read the Statistics.txt file and return its lines.

        :return: List of lines from the file.
        """
        with open(self._file_path, "r", encoding="utf-8") as f:
            return f.readlines()