"""
Configuration Manager

Module handles loading and accessing the ATC Project Explorer
configuration file. The configuration file is a JSON file that
contains settings for directory parsing, validation, and
consolidated metadata output.

The ConfigManager class loads the JSON file once at startup and
provides typed property accessors for each configuration section.
All downstream consumers (parsers, groupboxes, widgets) should
obtain their settings through this class rather than reading
the JSON directly or hardcoding values.
"""
import json
import logging
from pathlib import Path


logger = logging.getLogger(__name__)


class ConfigManager:

    def __init__(self, config_path: str | Path):
        """
        Initialize the ConfigManager and load the configuration file.

        :param config_path: Path to the JSON configuration file.
        :raises FileNotFoundError: If the configuration file does not exist.
        :raises json.JSONDecodeError: If the configuration file is not valid JSON.
        """
        self.config_path = Path(config_path)
        self._config: dict = {}
        self._load_config()

    def _load_config(self):
        """Load and parse the JSON configuration file."""
        if not self.config_path.exists():
            raise FileNotFoundError(
                f"Configuration file not found: {self.config_path}"
            )
        with open(self.config_path, "r", encoding="utf-8") as f:
            self._config = json.load(f)
        logger.info(f"Configuration loaded successfully from: {self.config_path}")

    # --- Top-Level Directory / File Names ---

    @property
    def temp_json_directory_name(self) -> str:
        """Name of the temporary JSON output directory."""
        return self._config.get("TemporaryJSONFileDirectoryName", "")

    @property
    def temp_consolidated_json_filename(self) -> str:
        """Filename for the temporary consolidated metadata JSON file."""
        return self._config.get(
            "TemporaryConsolidatedJSONFileName",
            "_temp_consolidated_metadata.json"
        )

    @property
    def export_plot_directory_name(self) -> str:
        """Name of the exported plots directory."""
        return self._config.get("ExportPlotDirectoryName", "")

    @property
    def default_saved_json_filename(self) -> str:
        """Default filename for saving metadata JSON files."""
        return self._config.get(
            "DefaultSavedJSONFileName", "Consolidated_ATC_Metadata.json"
        )

    @property
    def minify_exported_json(self) -> bool:
        """Whether to minify exported JSON files (no indentation)."""
        return self._config.get("MinifyExportedJSON", False)

    # --- ATC Project Directory Config ---

    @property
    def _directory_config(self) -> dict:
        """Access the ATCProjectDirectoryConfig section."""
        return self._config.get("ATCProjectDirectoryConfig", {})

    @property
    def validation_files(self) -> list[str]:
        """List of files required in the ATC project root directory
        to confirm a valid ATC project."""
        return self._directory_config.get("ValidationFiles", [])

    @property
    def root_directories_to_exclude(self) -> list[str]:
        """Directories to exclude when parsing the ATC project root."""
        root_dirs = self._directory_config.get("ProjectRootDirectories", {})
        return root_dirs.get("DirectoriesToExclude", [])

    @property
    def sub_directories_to_exclude(self) -> list[str]:
        """Subdirectories to exclude when parsing within site folders
        (e.g. 'AutoFocus')."""
        sub_dirs = self._directory_config.get("ProjectSubDirectories", {})
        return sub_dirs.get("DirectoriesToExclude", [])

    @property
    def parse_project_root_files(self) -> list[dict]:
        """List of root file parsing rules (Name and Parse flag).

        Each entry is a dict with 'Name' (filename) and 'Parse'
        (bool indicating whether to parse the file).
        """
        return self._directory_config.get("ParseProjectRootFiles", [])

    @property
    def files_to_parse(self) -> list[str]:
        """Filenames that have Parse set to true in the config.

        Convenience property that filters parse_project_root_files
        to only those with Parse=True and returns just the names.
        """
        return [
            entry["Name"]
            for entry in self.parse_project_root_files
            if entry.get("Parse", False)
        ]

    # --- Consolidated Metadata Config ---

    @property
    def _consolidated_metadata_config(self) -> dict:
        """Access the ConsolidatedMetadataConfig section."""
        return self._config.get("ConsolidatedMetadataConfig", {})

    @property
    def consolidated_metadata_template(self) -> dict:
        """Full template dictionary for building consolidated metadata."""
        return self._consolidated_metadata_config

    # --- Version ---

    @property
    def version(self) -> str:
        """Configuration file version."""
        return self._config.get("_version", "unknown")