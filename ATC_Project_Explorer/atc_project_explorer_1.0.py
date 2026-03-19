"""
ATC Project Explorer 1.0
.
This application is designed to help users explore Thermo Scientific AutoTEM Cryo (ATC) project metadata.
AutoScript 4.13 was used to develop the application, and no additional dependencies are required beyond what is included with AutoScript 4.13.
.
The code was written with assistance from Claude AI.
.
If you have any questions or suggestions for improvements, please contact me (Chris Thompson on GitHub: ChrisLeeThompson).
.
Thank you,
Chris Thompson
.
March 17, 2026
.
.
MIT License
.
Copyright 2026 Christopher Thompson
.
Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the “Software”),
to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense,
and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:
.
The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
.
THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
"""
import logging
import sys
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QMainWindow, QApplication, 
    QHBoxLayout, QVBoxLayout, QStackedWidget
)
from PySide6.QtCore import Qt, Slot, QThread
from PySide6.QtGui import QFont, QIcon, QCloseEvent
from script_modules.app_styles import AppStyles, ICON_PATH
from script_modules.config_manager import ConfigManager
from script_modules.consolidated_metadata_writer import (
    save_consolidated_metadata,
)
from script_modules.widgets.label_widgets import StartupLabel
from script_modules.groupboxes.dir_file_drop_groupbox import DirFileDropGroupBox
from script_modules.groupboxes.header_groupbox import HeaderGroupBox
from script_modules.groupboxes.select_site_groupbox import SelectSiteGroupBox
from script_modules.groupboxes.load_data_groupbox import LoadDataGroupBox
from script_modules.widgets.status_bar_widget import StatusBarWidget
from script_modules.global_panel import GlobalPanel
from script_modules.site_panel import SitePanel
from script_modules.detached_panel_window import DetachedPanelWindow
from script_modules.project_load_worker import ProjectLoadWorker


logger = logging.getLogger(__name__)


# Text for the top-level "Global" item in the site combo box.
GLOBAL_SITE_LABEL = AppStyles.AppText.GLOBAL_SITE_LABEL


class MainWindow(QMainWindow):

    def __init__(self, config_manager: ConfigManager):
        super().__init__()
        self.config_manager = config_manager
        # Consolidated metadata (populated by either parsing or JSON load)
        self._metadata: dict | None = None
        self._site_names: list[str] = []
        self._site_data_map: dict[str, dict] = {}
        self._project_root: Path | None = None
        # Tracking list for detached panel windows
        self._detached_windows: list[DetachedPanelWindow] = []
        # Background worker state
        self._worker: ProjectLoadWorker | None = None
        self._worker_thread: QThread | None = None
        # Set window title and size
        self.setWindowTitle(AppStyles.AppText.WINDOW_TITLE)
        screen_size = QApplication.primaryScreen().availableGeometry()
        if int(screen_size.width()) <= 1536:  # laptop, for example
            self.setGeometry(50, 50, int(screen_size.width() * 0.8), int(screen_size.height() * 0.85))
        else:
            self.setGeometry(50, 50, AppStyles.Dimensions.WINDOW_WIDTH, AppStyles.Dimensions.WINDOW_HEIGHT)
        # Set window icon
        self.setWindowIcon(QIcon(str(ICON_PATH)))
        # Set main window style
        self.setStyleSheet(AppStyles.Window.window())
        # Set main window margins
        self.setContentsMargins(
            AppStyles.Dimensions.MAIN_WINDOW_MARGIN,
            AppStyles.Dimensions.MAIN_WINDOW_MARGIN,
            AppStyles.Dimensions.MAIN_WINDOW_MARGIN,
            AppStyles.Dimensions.MAIN_WINDOW_MARGIN
        )
        # Create components
        self._create_components()
        # Setup layout
        self._setup_layout()
        # Connect signals
        self._connect_signals()
    
    # -----------------------------------------------------------------
    # Setup
    # -----------------------------------------------------------------

    def _create_components(self):
        # Left column components
        self.startup_label = StartupLabel(parent=self)
        self.header_groupbox = HeaderGroupBox(parent=self)
        self.header_groupbox.setVisible(False)
        self.global_panel = GlobalPanel(parent=self)
        self.site_panel = SitePanel(parent=self)
        self.panel_stack = QStackedWidget(parent=self)
        self.panel_stack.addWidget(self.global_panel)  # index 0
        self.panel_stack.addWidget(self.site_panel)   # index 1
        self.panel_stack.setVisible(False)
        # Right column components
        self.dir_file_drop_groupbox = DirFileDropGroupBox(
            validation_files=self.config_manager.validation_files,
            parent=self
        )
        self.select_site_groupbox = SelectSiteGroupBox(parent=self)
        self.load_data_groupbox = LoadDataGroupBox(
            validation_files=self.config_manager.validation_files,
            default_save_filename=self.config_manager.default_saved_json_filename,
            parent=self
        )
        # Status bar
        self.status_bar = StatusBarWidget()
    
    def _setup_layout(self):
        """Setup the main layout."""
        # Create central widget for QMainWindow
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main horizontal layout for two columns (left, right)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Left column container
        self.left_column_container = QWidget()
        self.left_column_layout = QVBoxLayout(self.left_column_container)
        self.left_column_layout.setContentsMargins(20, 20, 20, 20)
        self.left_column_layout.setSpacing(0)
        # Startup state: centered label with stretch above and below
        self.left_column_layout.addStretch(1)
        self.left_column_layout.addWidget(
            self.startup_label, alignment=Qt.AlignmentFlag.AlignCenter
        )
        self.left_column_layout.addStretch(3)
        
        # Right column container
        self.right_column_container = QWidget()
        right_column_layout = QVBoxLayout(self.right_column_container)
        right_column_layout.setContentsMargins(0, 0, 0, 0)
        right_column_layout.setSpacing(0)
        right_column_layout.addWidget(self.dir_file_drop_groupbox)
        right_column_layout.addWidget(self.select_site_groupbox)
        right_column_layout.addWidget(self.load_data_groupbox)
        right_column_layout.addStretch()

        # Status bar
        self.status_bar.setContentsMargins(0, 0, 0, 0)
        self.setStatusBar(self.status_bar)
        
        # Populate main layout
        main_layout.addWidget(self.left_column_container, 4)
        main_layout.addWidget(self.right_column_container, 1)
        main_layout.setContentsMargins(0, AppStyles.Dimensions.MAIN_WINDOW_MARGIN, 0, 0)

    def _connect_signals(self):
        """Connect widget signals to MainWindow handlers."""
        # Drop widget signals
        drop_widget = self.dir_file_drop_groupbox.dir_file_drop_widget
        drop_widget.directory_path_signal.connect(self._on_directory_dropped)
        drop_widget.json_file_path_signal.connect(self._on_json_file_dropped)
        drop_widget.validation_failed_signal.connect(self._on_validation_failed)
        # Load data groupbox signals (button-based dialogs)
        ldg = self.load_data_groupbox
        ldg.directory_selected.connect(self._on_directory_dropped)
        ldg.json_file_selected.connect(self._on_json_file_dropped)
        ldg.save_requested.connect(self._on_save_metadata)
        ldg.delete_requested.connect(self._on_delete_temp_file)
        ldg.validation_failed.connect(self._on_validation_failed)
        # Site combo box selection (activated = user interaction only)
        self.select_site_groupbox.lamella_site_combobox.activated.connect(
            self._on_site_selected
        )
        # Previous and next site buttons
        self.select_site_groupbox.previous_button.clicked.connect(
            self._on_previous_site
        )
        self.select_site_groupbox.next_button.clicked.connect(
            self._on_next_site
        )
        # Open in New Window button
        self.select_site_groupbox.open_in_new_window_button.clicked.connect(
            self._on_open_in_new_window
        )
        # Site position atlas: marker context menu actions
        self.global_panel.site_selected.connect(
            self._on_atlas_site_selected
        )
        self.global_panel.site_open_new_window.connect(
            self._on_atlas_open_new_window
        )
        # Cancel button in status bar
        self.status_bar.cancel_button_clicked_signal.connect(
            self._on_cancel_worker
        )

    # -----------------------------------------------------------------
    # Window Close
    # -----------------------------------------------------------------

    def closeEvent(self, event: QCloseEvent) -> None:
        """Ensure the background worker thread is stopped and all
        detached windows are closed before the main window exits.
        """
        # Stop the worker thread if it is running
        if self._worker is not None:
            self._worker.request_cancel()
        if self._worker_thread is not None:
            self._worker_thread.quit()
            self._worker_thread.wait()

        # Close all detached panel windows
        for window in list(self._detached_windows):
            window.close()

        super().closeEvent(event)

    # -----------------------------------------------------------------
    # Drop / Load Handlers
    # -----------------------------------------------------------------

    @Slot(str)
    def _on_directory_dropped(self, directory_path: str):
        """Handle a validated ATC project directory from drop or dialog."""
        logger.info(f"ATC project directory received: {directory_path}")
        self._load_project_directory(directory_path)

    @Slot(str)
    def _on_json_file_dropped(self, file_path: str):
        """Handle a JSON metadata file from drop or dialog."""
        logger.info(f"JSON file received: {file_path}")
        self._load_json_file(file_path)

    @Slot(str)
    def _on_validation_failed(self, message: str):
        """Handle validation failure from the drop widget or load dialog."""
        logger.warning(f"Validation failed: {message}")
        self.status_bar.set_status_bar_message_timed(message, 5000)

    # -----------------------------------------------------------------
    # Project Directory Loading
    # -----------------------------------------------------------------

    def _load_project_directory(self, directory_path: str):
        """Start background parsing of an ATC project directory.

        Creates a :class:`ProjectLoadWorker` configured for
        directory parsing, moves it to a ``QThread``, and connects
        its signals.  The UI is disabled during the operation and
        re-enabled in the worker callbacks.

        :param directory_path: Absolute path to the ATC project root.
        """
        project_path = Path(directory_path)

        # Build temp output path from config
        temp_output_dir = (
            project_path
            / self.config_manager.temp_json_directory_name
        )
        temp_output_file = (
            temp_output_dir
            / self.config_manager.temp_consolidated_json_filename
        )

        worker = ProjectLoadWorker.for_directory(
            project_path=project_path,
            sub_directories_to_exclude=(
                self.config_manager.sub_directories_to_exclude
            ),
            temp_output_file=temp_output_file,
            minify=self.config_manager.minify_exported_json,
        )
        self._start_worker(worker)

    # -----------------------------------------------------------------
    # JSON File Loading
    # -----------------------------------------------------------------

    def _load_json_file(self, file_path: str):
        """Start background loading of a consolidated metadata JSON
        file.

        Creates a :class:`ProjectLoadWorker` configured for JSON
        loading, moves it to a ``QThread``, and connects its
        signals.

        :param file_path: Absolute path to the JSON file.
        """
        worker = ProjectLoadWorker.for_json_file(
            file_path=Path(file_path),
        )
        self._start_worker(worker)

    # -----------------------------------------------------------------
    # Worker Lifecycle
    # -----------------------------------------------------------------

    def _start_worker(self, worker: ProjectLoadWorker) -> None:
        """Set up and start a background worker on a QThread.

        Disables input controls, shows progress feedback, and
        connects worker signals to MainWindow handlers.

        :param worker: Configured ProjectLoadWorker instance.
        """
        # Prevent overlapping operations
        if self._worker_thread is not None:
            logger.warning("Worker already running, ignoring request")
            return

        # UI feedback: Catbug to color, progress bar, cancel button
        self.dir_file_drop_groupbox.dir_file_drop_widget.set_image_color()
        self._set_loading_ui_enabled(False)
        self.status_bar.set_progress_bar_range(0, 0)
        self.status_bar.set_progress_bar_visible(True)
        self.status_bar.set_cancel_button_visible(True)
        self.status_bar.set_status_bar_message("Starting...")

        # Create thread and move worker to it
        thread = QThread()
        worker.moveToThread(thread)

        # Connect worker signals
        worker.progress.connect(self._on_worker_progress)
        worker.finished.connect(self._on_worker_finished)
        worker.error.connect(self._on_worker_error)
        worker.cancelled.connect(self._on_worker_cancelled)

        # Clean up thread when worker is done
        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)
        worker.cancelled.connect(thread.quit)
        thread.finished.connect(self._cleanup_worker)

        # Start
        thread.started.connect(worker.run)
        self._worker = worker
        self._worker_thread = thread
        thread.start()

    @Slot(int, int, str)
    def _on_worker_progress(
        self, step: int, total: int, description: str
    ) -> None:
        """Update the progress bar and status message.

        :param step: Current step number (1-based).
        :param total: Total number of steps.
        :param description: Human-readable description of the step.
        """
        self.status_bar.set_progress_bar_range(0, total)
        self.status_bar.set_progress_bar_value(step)
        self.status_bar.set_status_bar_message(description)

    @Slot(dict)
    def _on_worker_finished(self, result: dict) -> None:
        """Handle successful completion of the background worker.

        Stores the metadata, populates the UI, and restores
        controls.

        :param result: Result dictionary from the worker.
        """
        self._metadata = result["metadata"]
        self._site_names = result["site_names"]
        self._project_root = result["project_root"]

        # Build O(1) lookup map for site data by name
        self._site_data_map = {
            site["SiteName"]: site
            for site in self._metadata.get("Sites", [])
            if "SiteName" in site
        }

        # Populate the UI
        self._on_data_loaded()

        # Track the temp file for the delete button (directory mode)
        temp_file = result.get("temp_output_file")
        if temp_file is not None:
            self.load_data_groupbox.set_temp_file_path(temp_file)

        source_label = result.get("source_label", "project")
        self.status_bar.set_status_bar_message_timed(
            f"Loaded: {source_label}", 5000
        )

    @Slot(str)
    def _on_worker_error(self, message: str) -> None:
        """Handle worker failure.

        :param message: Error description for the status bar.
        """
        self.status_bar.set_status_bar_message_timed(message, 10000)
        logger.error(f"Worker error: {message}")

    @Slot()
    def _on_worker_cancelled(self) -> None:
        """Handle worker cancellation."""
        self.status_bar.set_status_bar_message_timed(
            "Operation cancelled.", 5000
        )
        logger.info("Worker cancelled")

    @Slot()
    def _on_cancel_worker(self) -> None:
        """Request cancellation of the running worker."""
        if self._worker is not None:
            self._worker.request_cancel()

    def _cleanup_worker(self) -> None:
        """Clean up worker and thread references after the thread
        has finished.  Restores the UI to its interactive state."""
        if self._worker_thread is not None:
            self._worker_thread.deleteLater()
        if self._worker is not None:
            self._worker.deleteLater()
        self._worker = None
        self._worker_thread = None

        # Restore UI
        self.dir_file_drop_groupbox.dir_file_drop_widget.set_image_grayscale()
        self.status_bar.set_progress_bar_visible(False)
        self.status_bar.set_cancel_button_visible(False)
        self._set_loading_ui_enabled(True)

    def _set_loading_ui_enabled(self, enabled: bool) -> None:
        """Enable or disable input controls during background
        loading.

        :param enabled: True to enable, False to disable.
        """
        self.dir_file_drop_groupbox.dir_file_drop_widget.set_accepts_drops(
            enabled
        )
        self.load_data_groupbox.load_project_dir_button.setEnabled(enabled)
        self.load_data_groupbox.load_json_file_button.setEnabled(enabled)

    # -----------------------------------------------------------------
    # UI Population
    # -----------------------------------------------------------------

    def _on_data_loaded(self):
        """Populate the UI after data has been parsed or loaded.

        Transitions from the startup state to the active state:
        - Removes the startup label
        - Shows the header groupbox with the project name
        - Populates the global panel with metadata
        - Populates the site combo box
        - Selects 'Global' by default
        """
        # Transition left column from startup to active
        self._show_active_layout()

        # Populate the header
        project_name = self._get_project_name()
        self.header_groupbox.project_name_label.setText(
            f"{project_name}"
        )
        self.header_groupbox.site_name_label.setText(
            f"Site selected: {GLOBAL_SITE_LABEL}"
        )

        # Populate the global panel and show it
        self.global_panel.populate(self._metadata)
        self.panel_stack.setCurrentIndex(0)

        # Set the project root for image browsing
        self.site_panel.set_project_root(self._project_root)

        # Populate the site combo box
        self._populate_site_combobox()

        # Enable save button
        self.load_data_groupbox.set_save_enabled(True)

    def _show_active_layout(self):
        """Transition the left column from startup label to active
        content with the header groupbox at the top and the panel
        stack filling the remaining space."""
        # Hide and remove startup label (and its stretches)
        self.startup_label.setVisible(False)
        # Clear the left column layout
        while self.left_column_layout.count():
            item = self.left_column_layout.takeAt(0)
            # Don't delete the widgets, just remove from layout
            if item.widget():
                item.widget().setVisible(False)

        # Rebuild left column: header at top, panel stack fills rest
        self.left_column_layout.setContentsMargins(0, 0, 0, 0)
        self.left_column_layout.setSpacing(0)
        self.left_column_layout.addWidget(self.header_groupbox)
        self.left_column_layout.addWidget(self.panel_stack, 1)
        self.header_groupbox.setVisible(True)
        self.panel_stack.setVisible(True)

    def _populate_site_combobox(self):
        """Populate the site combo box with 'Global' + site names."""
        combobox = self.select_site_groupbox.lamella_site_combobox
        combobox.clear()
        combobox.addItem(GLOBAL_SITE_LABEL)
        combobox.addItems(self._site_names)
        # Select "Global" by default
        combobox.setCurrentIndex(0)
        # Enable the "Open In New Window" button now that data is loaded
        self.select_site_groupbox.open_in_new_window_button.setEnabled(True)
        self._update_site_nav_buttons()
        logger.info(
            f"Site combobox populated: {GLOBAL_SITE_LABEL} + "
            f"{len(self._site_names)} site(s)"
        )

    # -----------------------------------------------------------------
    # Site Selection Handler
    # -----------------------------------------------------------------

    @Slot(int)
    def _on_site_selected(self, index: int):
        """Handle site combo box selection change.

        Switches between the GlobalPanel (index 0) and SitePanel
        (index 1+) via the QStackedWidget, and populates the
        active panel with the appropriate data.

        :param index: Selected combo box index.
        """
        combobox = self.select_site_groupbox.lamella_site_combobox
        selected_text = combobox.currentText()

        if index == 0:
            # Global selection
            self.header_groupbox.site_name_label.setText(
                f"Site selected: {GLOBAL_SITE_LABEL}"
            )
            self.panel_stack.setCurrentIndex(0)
            logger.info(f"Site selected: {GLOBAL_SITE_LABEL}")
        else:
            # Individual site selection
            self.header_groupbox.site_name_label.setText(
                f"Site selected: {selected_text}"
            )
            site_data = self._get_site_data(selected_text)
            if site_data is not None:
                self.site_panel.populate(site_data)
            self.panel_stack.setCurrentIndex(1)
            logger.info(f"Site selected: {selected_text}")

        self._update_site_nav_buttons()
    
    @Slot()
    def _on_previous_site(self) -> None:
        """Select the previous site in the combo box, if available."""
        combobox = self.select_site_groupbox.lamella_site_combobox
        current_index = combobox.currentIndex()
        if current_index > 0:
            combobox.setCurrentIndex(current_index - 1)
            self._on_site_selected(current_index - 1)
    
    @Slot()
    def _on_next_site(self) -> None:
        """Select the next site in the combo box, if available."""
        combobox = self.select_site_groupbox.lamella_site_combobox
        current_index = combobox.currentIndex()
        if current_index < combobox.count() - 1:
            combobox.setCurrentIndex(current_index + 1)
            self._on_site_selected(current_index + 1)
    
    @Slot(str)
    def _on_atlas_site_selected(self, site_name: str) -> None:
        """Handle 'Open site' from the atlas context menu.

        Selects the site in the combo box and triggers the normal
        site-selection flow.

        :param site_name: Name of the clicked site.
        """
        combobox = self.select_site_groupbox.lamella_site_combobox
        index = combobox.findText(site_name)
        if index < 0:
            logger.warning(
                f"Atlas: site '{site_name}' not found in combo box"
            )
            return
        combobox.setCurrentIndex(index)
        self._on_site_selected(index)

    @Slot(str)
    def _on_atlas_open_new_window(self, site_name: str) -> None:
        """Handle 'Open site in new window' from the atlas context
        menu.

        Creates a detached window for the selected site, reusing
        the existing DetachedPanelWindow machinery.

        :param site_name: Name of the clicked site.
        """
        if self._metadata is None:
            return

        site_data = self._get_site_data(site_name)
        if site_data is None:
            logger.warning(
                f"Atlas: site data not found for '{site_name}'"
            )
            return

        project_name = self._get_project_name()
        window = DetachedPanelWindow.for_site(
            site_data=site_data,
            project_name=project_name,
            project_root=self._project_root,
            parent=self,
        )
        window.closed.connect(self._on_detached_window_closed)
        self._detached_windows.append(window)
        window.show()
        logger.info(
            f"Atlas: opened detached window for '{site_name}' "
            f"(total open: {len(self._detached_windows)})"
        )
    
    @Slot()
    def _on_open_in_new_window(self) -> None:
        """Open the currently selected site (or Global) in a new
        detached window for side-by-side comparison."""
        if self._metadata is None:
            logger.warning(
                "Open in new window requested but no metadata loaded"
            )
            return
 
        project_name = self._get_project_name()
        combobox = self.select_site_groupbox.lamella_site_combobox
        index = combobox.currentIndex()
 
        if index == 0:
            # Global view
            window = DetachedPanelWindow.for_global(
                metadata=self._metadata,
                project_name=project_name,
                parent=self,
            )
        else:
            # Individual site
            site_name = combobox.currentText()
            site_data = self._get_site_data(site_name)
            if site_data is None:
                logger.warning(
                    "Cannot open detached window: "
                    f"site data not found for '{site_name}'"
                )
                return
            window = DetachedPanelWindow.for_site(
                site_data=site_data,
                project_name=project_name,
                project_root=self._project_root,
                parent=self,
            )
 
        # Track the window and clean up when it closes
        window.closed.connect(self._on_detached_window_closed)
        self._detached_windows.append(window)
        window.show()
        logger.info(
            f"Detached window opened "
            f"(total open: {len(self._detached_windows)})"
        )
 
    @Slot(object)
    def _on_detached_window_closed(self, window: DetachedPanelWindow) -> None:
        """Remove a closed detached window from the tracking list."""
        try:
            self._detached_windows.remove(window)
        except ValueError:
            pass
        logger.info(
            f"Detached window closed "
            f"(remaining: {len(self._detached_windows)})"
        )

    # -----------------------------------------------------------------
    # Save / Delete Handlers
    # -----------------------------------------------------------------

    @Slot(str)
    def _on_save_metadata(self, destination_path: str):
        """Save the current consolidated metadata to a user-chosen
        location.

        :param destination_path: Absolute path chosen by the user
            via the save dialog.
        """
        if self._metadata is None:
            self.status_bar.set_status_bar_message_timed(
                "No metadata to save.", 5000
            )
            return

        try:
            output = save_consolidated_metadata(
                self._metadata,
                destination_path,
                minify=self.config_manager.minify_exported_json,
            )
            self.status_bar.set_status_bar_message_timed(
                f"Saved: {output.name}", 5000
            )
        except Exception:
            logger.error(
                f"Failed to save metadata: {destination_path}",
                exc_info=True
            )
            self.status_bar.set_status_bar_message_timed(
                "Failed to save metadata file.", 10000
            )

    @Slot()
    def _on_delete_temp_file(self):
        """Delete the temporary consolidated metadata JSON file."""
        temp_path = self.load_data_groupbox.temp_file_path
        if temp_path is None or not temp_path.exists():
            return

        try:
            # Delete the temp file
            temp_path.unlink()
            logger.info(f"Deleted temp file: {temp_path}")

            # Remove the temp directory if it is now empty
            temp_dir = temp_path.parent
            if temp_dir.exists() and not any(temp_dir.iterdir()):
                temp_dir.rmdir()
                logger.info(f"Removed empty temp directory: {temp_dir}")

            self.status_bar.set_status_bar_message_timed(
                f"Deleted: {temp_path.name}", 5000
            )
        except Exception:
            logger.error(
                f"Failed to delete temp file: {temp_path}",
                exc_info=True
            )
            self.status_bar.set_status_bar_message_timed(
                "Failed to delete temp file.", 10000
            )
        finally:
            self.load_data_groupbox.refresh_delete_button_state()

    # -----------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------

    def _update_site_nav_buttons(self) -> None:
        """Enable or disable the previous/next site buttons based
        on the current combo box index."""
        combobox = self.select_site_groupbox.lamella_site_combobox
        index = combobox.currentIndex()
        count = combobox.count()
        self.select_site_groupbox.previous_button.setEnabled(index > 0)
        self.select_site_groupbox.next_button.setEnabled(index < count - 1)

    def _get_project_name(self) -> str:
        """Extract the project name from the consolidated metadata.

        :return: Project name string, or 'Unknown' if not found.
        """
        if self._metadata is None:
            return "Unknown"
        project_data = self._metadata.get("ProjectData", {})
        project = project_data.get("Project", {})
        if isinstance(project, dict):
            return project.get("Name", "Unknown")
        return "Unknown"

    def _get_site_data(self, site_name: str) -> dict | None:
        """Look up a single site's data dict by name.

        Uses the pre-built ``_site_data_map`` for O(1) lookup.

        :param site_name: The site name to look up.
        :return: The site data dictionary, or *None* if not found.
        """
        if self._metadata is None:
            return None
        site_data = self._site_data_map.get(site_name)
        if site_data is None:
            logger.warning(f"Site data not found for: {site_name}")
        return site_data

    
def setup_logging():
    """Configure logging for the application."""
    logging.basicConfig(
        format="%(asctime)s:\t%(levelname)s:\t%(name)s\t%(funcName)s:\t%(message)s", 
        level=logging.INFO,
        force=True
    )
    logging.getLogger("matplotlib.font_manager").setLevel(logging.WARNING)
    logging.getLogger("matplotlib").setLevel(logging.INFO)


def main():
    """Main function to run the application."""

    setup_logging()

    # Load configuration
    config_path = Path(__file__).parent / "config_files" / "ATCProjectExplorerConfig.json"
    config_manager = ConfigManager(config_path)

    app=QApplication(sys.argv)
    font = app.font()
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    app.setFont(font)
    window = MainWindow(config_manager)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()