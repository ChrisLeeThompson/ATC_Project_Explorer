"""
Project Load Worker

Background worker for parsing ATC project directories and loading
JSON metadata files.  Runs I/O-bound operations on a ``QThread``
so the main UI thread remains responsive, with progress signals
for status bar and progress bar updates.

Two entry modes are supported:

- **Directory parsing**: runs ProjectDataParser, StatisticsParser,
  ATCDirectoryParser, builds consolidated metadata, and saves a
  temporary JSON file.
- **JSON file loading**: loads and validates a previously saved
  consolidated metadata JSON file.

Usage from MainWindow::

    worker = ProjectLoadWorker.for_directory(
        project_path=Path("..."),
        sub_directories_to_exclude=[...],
        temp_output_file=Path("..."),
        minify=False,
    )

    # — or —

    worker = ProjectLoadWorker.for_json_file(
        file_path=Path("..."),
    )

    thread = QThread()
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.finished.connect(...)
    worker.progress.connect(...)
    worker.error.connect(...)
    thread.start()
"""
import logging
from pathlib import Path
from PySide6.QtCore import QObject, Signal, Slot
from script_modules.parsers.project_data_parser import ProjectDataParser
from script_modules.parsers.statistics_parser import StatisticsParser
from script_modules.parsers.atc_directory_parser import ATCDirectoryParser
from script_modules.consolidated_metadata_writer import (
    build_consolidated_metadata,
    save_consolidated_metadata,
    load_consolidated_metadata,
)


logger = logging.getLogger(__name__)


class ProjectLoadWorker(QObject):
    """Background worker for project I/O operations.

    :signal progress: ``(current_step, total_steps, description)``
        emitted before each processing step begins.
    :signal finished: ``(result_dict)`` emitted on successful
        completion.  The dict contains:

        - ``"metadata"`` — consolidated metadata dict.
        - ``"site_names"`` — list of site name strings.
        - ``"project_root"`` — ``Path`` or ``None``.
        - ``"temp_output_file"`` — ``Path`` or ``None``
          (directory mode only).
        - ``"source_label"`` — display-friendly name for the
          status bar (e.g. project dir name or JSON filename).

    :signal error: ``(error_message)`` emitted on failure.
    :signal cancelled: emitted if the worker was cancelled between
        steps.
    """

    progress = Signal(int, int, str)
    finished = Signal(dict)
    error = Signal(str)
    cancelled = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mode: str = ""
        self._cancelled_flag: bool = False

        # Directory mode parameters
        self._project_path: Path | None = None
        self._sub_dirs_to_exclude: list[str] = []
        self._temp_output_file: Path | None = None
        self._minify: bool = False

        # JSON mode parameters
        self._json_file_path: Path | None = None

    # -----------------------------------------------------------------
    # Factory class methods
    # -----------------------------------------------------------------

    @classmethod
    def for_directory(
        cls,
        project_path: Path,
        sub_directories_to_exclude: list[str],
        temp_output_file: Path,
        minify: bool = False,
    ) -> "ProjectLoadWorker":
        """Create a worker configured for ATC directory parsing.

        :param project_path: Absolute path to the ATC project root.
        :param sub_directories_to_exclude: Directories to skip
            during the directory scan.
        :param temp_output_file: Path for the temporary
            consolidated JSON output file.
        :param minify: Whether to write compact JSON.
        :return: Configured worker instance.
        """
        worker = cls()
        worker._mode = "directory"
        worker._project_path = project_path
        worker._sub_dirs_to_exclude = sub_directories_to_exclude
        worker._temp_output_file = temp_output_file
        worker._minify = minify
        return worker

    @classmethod
    def for_json_file(
        cls,
        file_path: Path,
    ) -> "ProjectLoadWorker":
        """Create a worker configured for JSON file loading.

        :param file_path: Absolute path to the JSON metadata file.
        :return: Configured worker instance.
        """
        worker = cls()
        worker._mode = "json"
        worker._json_file_path = file_path
        return worker

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    def request_cancel(self) -> None:
        """Request cancellation.  The worker checks this flag
        between processing steps."""
        self._cancelled_flag = True

    # -----------------------------------------------------------------
    # Main entry point (runs on worker thread)
    # -----------------------------------------------------------------

    @Slot()
    def run(self) -> None:
        """Execute the configured loading operation.

        Called automatically when the owning ``QThread`` starts.
        """
        try:
            if self._mode == "directory":
                self._run_directory_parse()
            elif self._mode == "json":
                self._run_json_load()
            else:
                self.error.emit(f"Unknown worker mode: {self._mode}")
        except Exception:
            logger.error(
                "Worker encountered an unhandled exception",
                exc_info=True,
            )
            self.error.emit("An unexpected error occurred.")

    # -----------------------------------------------------------------
    # Directory Parsing Pipeline
    # -----------------------------------------------------------------

    def _run_directory_parse(self) -> None:
        """Parse an ATC project directory through the full
        pipeline: three parsers → build → save."""
        total_steps = 5
        project_path = self._project_path

        # Step 1: Parse ProjectData.dat
        self.progress.emit(1, total_steps, "Parsing ProjectData.dat...")
        if self._is_cancelled():
            return
        try:
            project_parser = ProjectDataParser(
                project_path / "ProjectData.dat"
            )
            project_data = project_parser.parse()
        except Exception:
            logger.error(
                "Failed to parse ProjectData.dat", exc_info=True
            )
            self.error.emit(
                f"Failed to parse ProjectData.dat in "
                f"{project_path.name}"
            )
            return

        # Step 2: Parse Statistics.txt
        self.progress.emit(2, total_steps, "Parsing Statistics.txt...")
        if self._is_cancelled():
            return
        try:
            statistics_parser = StatisticsParser(
                project_path / "Statistics.txt"
            )
            statistics_data = statistics_parser.parse()
        except Exception:
            logger.error(
                "Failed to parse Statistics.txt", exc_info=True
            )
            self.error.emit(
                f"Failed to parse Statistics.txt in "
                f"{project_path.name}"
            )
            return

        # Step 3: Directory scan (often the slowest step)
        self.progress.emit(
            3, total_steps, "Scanning image directories..."
        )
        if self._is_cancelled():
            return
        try:
            directory_parser = ATCDirectoryParser(
                project_root=project_path,
                directories_to_exclude=self._sub_dirs_to_exclude,
            )
            directory_data = directory_parser.parse()
        except Exception:
            logger.error(
                "Failed to scan directories", exc_info=True
            )
            self.error.emit(
                f"Failed to scan directories in "
                f"{project_path.name}"
            )
            return

        # Step 4: Build consolidated metadata
        self.progress.emit(
            4, total_steps, "Building consolidated metadata..."
        )
        if self._is_cancelled():
            return
        try:
            metadata = build_consolidated_metadata(
                project_data=project_data,
                statistics_data=statistics_data,
                directory_data=directory_data,
                project_root_path=project_path,
            )
        except Exception:
            logger.error(
                "Failed to build consolidated metadata",
                exc_info=True,
            )
            self.error.emit(
                f"Failed to build metadata for "
                f"{project_path.name}"
            )
            return

        # Step 5: Save temporary JSON
        self.progress.emit(
            5, total_steps, "Saving temporary metadata file..."
        )
        if self._is_cancelled():
            return
        try:
            save_consolidated_metadata(
                metadata,
                self._temp_output_file,
                minify=self._minify,
            )
        except Exception:
            logger.error(
                "Failed to save temp metadata", exc_info=True
            )
            self.error.emit(
                f"Failed to save metadata for "
                f"{project_path.name}"
            )
            return

        # Build result
        site_names = [
            site["SiteName"]
            for site in metadata.get("Sites", [])
        ]
        result = {
            "metadata": metadata,
            "site_names": site_names,
            "project_root": project_path,
            "temp_output_file": self._temp_output_file,
            "source_label": project_path.name,
        }
        logger.info(
            f"Worker: parsed '{project_path.name}' — "
            f"{len(site_names)} site(s)"
        )
        self.finished.emit(result)

    # -----------------------------------------------------------------
    # JSON File Loading
    # -----------------------------------------------------------------

    def _run_json_load(self) -> None:
        """Load and validate a consolidated metadata JSON file."""
        total_steps = 1
        path = self._json_file_path

        self.progress.emit(
            1, total_steps, f"Loading {path.name}..."
        )
        if self._is_cancelled():
            return

        try:
            metadata = load_consolidated_metadata(path)
        except Exception:
            logger.error(
                f"Failed to load JSON file: {path.name}",
                exc_info=True,
            )
            self.error.emit(f"Failed to load {path.name}")
            return

        if metadata is None:
            self.error.emit(
                f"Invalid metadata file: {path.name}"
            )
            return

        site_names = [
            site["SiteName"]
            for site in metadata.get("Sites", [])
        ]

        # Resolve project root from saved metadata
        project_root = None
        stored_root = metadata.get("ProjectRootPath", "")
        if stored_root:
            candidate = Path(stored_root)
            if candidate.is_dir():
                project_root = candidate
                logger.info(
                    f"Project root restored from JSON: "
                    f"{candidate}"
                )
            else:
                logger.info(
                    f"Stored project root not found on disk: "
                    f"{stored_root}"
                )

        result = {
            "metadata": metadata,
            "site_names": site_names,
            "project_root": project_root,
            "temp_output_file": None,
            "source_label": path.name,
        }
        logger.info(
            f"Worker: loaded '{path.name}' — "
            f"{len(site_names)} site(s)"
        )
        self.finished.emit(result)

    # -----------------------------------------------------------------
    # Internal Helpers
    # -----------------------------------------------------------------

    def _is_cancelled(self) -> bool:
        """Check the cancellation flag and emit the cancelled
        signal if set.

        :return: True if cancellation was requested.
        """
        if self._cancelled_flag:
            logger.info("Worker cancelled by user")
            self.cancelled.emit()
            return True
        return False