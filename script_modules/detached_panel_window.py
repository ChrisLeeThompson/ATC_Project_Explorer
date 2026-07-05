"""
Detached Panel Window

A standalone top-level window that displays either a GlobalPanel
or SitePanel, allowing the user to compare data from different
sites (or the global project view) side by side.

Each detached window owns its own panel instance and is fully
independent of the MainWindow panels.

Usage from MainWindow::

    window = DetachedPanelWindow.for_global(
        metadata=self._metadata,
        project_name=project_name,
        project_root=self._project_root,
        parent=self,
    )
    window.show()

    window = DetachedPanelWindow.for_site(
        site_data=site_data,
        project_name=project_name,
        project_root=self._project_root,
        parent=self,
    )
    window.show()
"""
import logging
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QApplication
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCloseEvent, QIcon
from script_modules.app_styles import AppStyles, ICON_PATH
from script_modules.groupboxes.header_groupbox import HeaderGroupBox
from script_modules.global_panel import GlobalPanel
from script_modules.site_panel import SitePanel


logger = logging.getLogger(__name__)

# Text for the top-level "Global" item, matching the main window.
GLOBAL_SITE_LABEL = AppStyles.AppText.GLOBAL_SITE_LABEL


class DetachedPanelWindow(QWidget):
    """Top-level window that wraps a single GlobalPanel or SitePanel.

    The window mirrors the left-column layout of the main UI:
    header groupbox at the top (project name + site label) with
    the appropriate panel filling the remaining space.

    :signal closed: Emitted when the window is closed, carrying
        a reference to *self* so the owner can remove it from its
        tracking list.
    """

    closed = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        # Use the Window flag so this widget is a top-level window
        # while still allowing non-modal interaction with the parent.
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowCloseButtonHint
            | Qt.WindowType.WindowMinMaxButtonsHint
        )
        # Apply the same background as the main window.
        self.setStyleSheet(
            f"QWidget#DetachedPanelWindow "
            f"{{ background-color: {AppStyles.Colors.MAIN_BG}; }}"
        )
        self.setObjectName("DetachedPanelWindow")
        # Margins matching the main window left-column padding.
        self.setContentsMargins(
            AppStyles.Dimensions.MAIN_WINDOW_MARGIN,
            AppStyles.Dimensions.MAIN_WINDOW_MARGIN,
            AppStyles.Dimensions.MAIN_WINDOW_MARGIN,
            AppStyles.Dimensions.MAIN_WINDOW_MARGIN,
        )
        # Window icon (same as MainWindow, via centralized ICON_PATH).
        if ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(ICON_PATH)))

        # Header
        self._header = HeaderGroupBox(parent=self)

        # The panel widget is set by the factory classmethods.
        self._panel: QWidget | None = None

    # -----------------------------------------------------------------
    # Factory class methods
    # -----------------------------------------------------------------

    @classmethod
    def for_global(
        cls,
        metadata: dict,
        project_name: str,
        project_root: Path | None = None,
        media: dict | None = None,
        parent=None,
    ) -> "DetachedPanelWindow":
        """Create a detached window showing the global panel.

        :param metadata: Full consolidated metadata dictionary.
        :param project_name: Project name shown in the header.
        :param project_root: Absolute path to the ATC project
            root, needed for site preview image resolution.
        :param media: Optional preloaded media bundle (``{site_name:
            {...}}``) reused from the main window so the detached
            panel does not re-decode images.  When *None*, the panel
            loads on demand.
        :param parent: Optional parent widget.
        :return: Ready-to-show DetachedPanelWindow instance.
        """
        window = cls(parent=parent)
        window.setWindowTitle(
            f"{GLOBAL_SITE_LABEL} \u2014 {AppStyles.AppText.WINDOW_TITLE}"
        )
        window._header.project_name_button.setText(project_name)
        window._header.site_name_label.setText(
            f"Site selected: {GLOBAL_SITE_LABEL}"
        )
        window._header.set_project_root(project_root)

        panel = GlobalPanel(parent=window)
        if project_root is not None:
            panel.set_project_root(project_root)
        panel.set_preloaded_media(media)
        panel.populate(metadata)

        window._panel = panel
        window._build_layout()
        window._apply_default_geometry()
        logger.info("Detached window created for global view")
        return window

    @classmethod
    def for_site(
        cls,
        site_data: dict,
        project_name: str,
        project_root: Path | None = None,
        parent=None,
    ) -> "DetachedPanelWindow":
        """Create a detached window showing a single site panel.

        :param site_data: A single site entry from the
            consolidated metadata ``"Sites"`` list.
        :param project_name: Project name shown in the header.
        :param project_root: Absolute path to the ATC project
            root, needed for image path resolution.
        :param parent: Optional parent widget.
        :return: Ready-to-show DetachedPanelWindow instance.
        """
        site_name = site_data.get("SiteName", "Unknown")
        window = cls(parent=parent)
        window.setWindowTitle(
            f"{site_name} \u2014 {AppStyles.AppText.WINDOW_TITLE}"
        )
        window._header.project_name_label.setText(project_name)
        window._header.site_name_label.setText(
            f"Site selected: {site_name}"
        )

        panel = SitePanel(parent=window)
        if project_root is not None:
            panel.set_project_root(project_root)
        panel.populate(site_data)

        window._panel = panel
        window._build_layout()
        window._apply_default_geometry()
        logger.info(
            f"Detached window created for site '{site_name}'"
        )
        return window

    # -----------------------------------------------------------------
    # Overrides
    # -----------------------------------------------------------------

    def closeEvent(self, event: QCloseEvent) -> None:
        """Emit *closed* so the owner can drop its reference."""
        self.closed.emit(self)
        super().closeEvent(event)

    # -----------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------

    def _build_layout(self) -> None:
        """Assemble the header + panel layout.

        Called once by the factory classmethod after the panel
        widget has been created and populated.
        """
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._header)
        layout.addWidget(self._panel, 1)

    def _apply_default_geometry(self) -> None:
        """Size and centre the window relative to the primary
        screen, using dimensions similar to the main window."""
        screen = QApplication.primaryScreen()
        if screen is None:
            self.resize(
                AppStyles.Dimensions.WINDOW_WIDTH,
                AppStyles.Dimensions.WINDOW_HEIGHT,
            )
            return
        available = screen.availableGeometry()
        width = int(available.width() * 0.55)
        height = int(available.height() * 0.80)
        x = available.x() + (available.width() - width) // 2
        y = available.y() + (available.height() - height) // 2
        self.setGeometry(x, y, width, height)