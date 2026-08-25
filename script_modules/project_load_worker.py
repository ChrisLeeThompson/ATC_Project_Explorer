"""
Project Load Worker

Background worker for parsing ATC project directories and loading
JSON metadata files.  Runs I/O-bound operations on a ``QThread``
so the main UI thread remains responsive, with progress signals
for status bar and progress bar updates.

Two entry modes are supported, each with a factory class method:

- **Directory parsing** (:meth:`ProjectLoadWorker.for_directory`):
  runs the three parsers, builds consolidated metadata, saves a
  temporary JSON file, and preloads preview media.
- **JSON file loading** (:meth:`ProjectLoadWorker.for_json_file`):
  loads and validates a previously saved consolidated metadata file.
"""
import logging
from pathlib import Path
from PySide6.QtCore import QObject, Signal, Slot
from script_modules.cancellation import OperationCancelled
from script_modules.parsers.project_data_parser import ProjectDataParser
from script_modules.parsers.statistics_parser import StatisticsParser
from script_modules.parsers.atc_directory_parser import ATCDirectoryParser
from script_modules.consolidated_metadata_writer import (
    build_consolidated_metadata,
    save_consolidated_metadata,
    load_consolidated_metadata,
)
from script_modules.preview_media_loader import load_project_media


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
        """Request cancellation.  The worker polls this flag between
        processing steps and inside the parse/build/media loops."""
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
                self.error.emit("Internal error: unknown load mode")
        except Exception:
            logger.error(
                "Worker encountered an unhandled exception",
                exc_info=True,
            )
            self.error.emit("An unexpected error occurred")

    # -----------------------------------------------------------------
    # Directory Parsing Pipeline
    # -----------------------------------------------------------------

    def _run_directory_parse(self) -> None:
        """Parse an ATC project directory through the full
        pipeline: three parsers → build → save → preload media."""
        total_steps = 6
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
                f"Failed to parse ProjectData.dat for "
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
                f"Failed to parse Statistics.txt for "
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
            directory_data = directory_parser.parse(
                cancel_check=self._cancel_requested
            )
        except OperationCancelled:
            self.cancelled.emit()
            return
        except Exception:
            logger.error(
                "Failed to scan directories", exc_info=True
            )
            self.error.emit(
                f"Failed to scan directories for "
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
                cancel_check=self._cancel_requested,
            )
        except OperationCancelled:
            self.cancelled.emit()
            return
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

        # Step 6: Preload preview + atlas media off the GUI thread
        self.progress.emit(
            6, total_steps, "Loading preview media..."
        )
        if self._is_cancelled():
            return
        try:
            media = load_project_media(
                metadata,
                project_path,
                cancel_check=self._cancel_requested,
                progress=lambda done, total: self.progress.emit(
                    6,
                    total_steps,
                    f"Loading preview media... ({done}/{total})",
                ),
            )
        except OperationCancelled:
            self.cancelled.emit()
            return
        except Exception:
            # A media decode failure must not fail the whole load;
            # degrade to on-demand loading in the panels.
            logger.error(
                "Failed to preload media", exc_info=True
            )
            media = None

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
            "media": media,
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
        total_steps = 2
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

        # Tolerate a hand-edited JSON file: skip sites missing SiteName.
        site_names = [
            site.get("SiteName")
            for site in metadata.get("Sites", [])
            if site.get("SiteName")
        ]

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

        # Step 2: Preload media when the project root resolves.
        # Without a resolvable root the images can't be located, so
        # the panels degrade silently to on-demand loading.
        media = None
        if project_root is not None:
            self.progress.emit(
                2, total_steps, "Loading preview media..."
            )
            if self._is_cancelled():
                return
            try:
                media = load_project_media(
                    metadata,
                    project_root,
                    cancel_check=self._cancel_requested,
                    progress=lambda done, total: self.progress.emit(
                        2,
                        total_steps,
                        f"Loading preview media... "
                        f"({done}/{total})",
                    ),
                )
            except OperationCancelled:
                self.cancelled.emit()
                return
            except Exception:
                logger.error(
                    "Failed to preload media", exc_info=True
                )
                media = None
        else:
            self.progress.emit(
                2, total_steps, f"Loading {path.name}..."
            )

        result = {
            "metadata": metadata,
            "site_names": site_names,
            "project_root": project_root,
            "temp_output_file": None,
            "source_label": path.name,
            "media": media,
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
        signal if set.  Used at step boundaries.

        :return: True if cancellation was requested.
        """
        if self._cancelled_flag:
            logger.info("Worker cancelled by user")
            self.cancelled.emit()
            return True
        return False

    def _cancel_requested(self) -> bool:
        """Pure cancellation check for the inner parse/build loops.

        Reads the flag without emitting (unlike :meth:`_is_cancelled`);
        the single ``cancelled`` emit is done by the
        ``except OperationCancelled`` handlers.  Passed as the
        ``cancel_check`` callable (see :mod:`script_modules.cancellation`)
        so the parsers and writer poll it without depending on Qt.

        The flag is a plain ``bool`` set once from the GUI thread
        (:meth:`request_cancel`) and read many times on the worker
        thread; that set-once / read-many pattern is GIL-safe without
        additional locking.

        :return: True if cancellation was requested.
        """
        return self._cancelled_flag