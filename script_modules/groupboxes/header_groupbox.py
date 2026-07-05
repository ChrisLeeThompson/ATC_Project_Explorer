"""
Header GroupBox

This module handles the header group box.
The header group box is used to provide context for the user about the currently loaded project and selected site.
The header group box includes:
- QPushButton (flat, link-styled) that displays the project name and, when clicked, opens the project directory in the OS file manager
- QLabel to display the selected site name or "Global Project Data" if no site is selected
"""
import logging
from pathlib import Path
from PySide6.QtWidgets import (
    QGroupBox, QVBoxLayout, QLabel, QPushButton
)
from PySide6.QtCore import Signal, Slot, QUrl, Qt
from PySide6.QtGui import QDesktopServices
from script_modules.app_styles import AppStyles


logger = logging.getLogger(__name__)


class HeaderGroupBox(QGroupBox):

    def __init__(self, parent=None):
        super().__init__(parent)
        # Absolute path to the loaded project's root directory, used to
        # open it when the project-name button is clicked.  None until a
        # project with a resolvable root is loaded.
        self._project_root: Path | None = None
        # Create widgets
        self._create_widgets()
        # Setup layout
        self._setup_layout()
        # Open the project directory when the project name is clicked
        self.project_name_button.clicked.connect(
            self._on_project_name_clicked
        )

    def _create_widgets(self):
        # The project name is a flat, link-styled button: it looks like
        # a title but opens the project directory when clicked.  A
        # pointing-hand cursor on hover signals that it is clickable.
        self.project_name_button = QPushButton("", parent=self)
        self.project_name_button.setCursor(
            Qt.CursorShape.PointingHandCursor
        )
        self.project_name_button.setToolTip(
            AppStyles.AppText.PROJECT_NAME_BUTTON
        )
        self.project_name_button.setStyleSheet(
            AppStyles.Button.link_title()
        )
        self.site_name_label = QLabel("Site selected: None", parent=self)
        self.site_name_label.setStyleSheet(AppStyles.Label.large_label())

    def _setup_layout(self):
        # Layout
        main_layout = QVBoxLayout(self)
        # Add widgets to layout
        main_layout.setContentsMargins(
            AppStyles.Dimensions.LAYOUT_CONTENTS_MARGIN,
            AppStyles.Dimensions.LAYOUT_CONTENTS_MARGIN,
            AppStyles.Dimensions.LAYOUT_CONTENTS_MARGIN,
            AppStyles.Dimensions.LAYOUT_CONTENTS_MARGIN
        )
        main_layout.setSpacing(AppStyles.Dimensions.LAYOUT_VSPACING)
        main_layout.addWidget(self.project_name_button)
        main_layout.addWidget(self.site_name_label)
        # Set layout and group box style
        self.setLayout(main_layout)
        self.setStyleSheet(AppStyles.GroupBox.default_main_background())

    def set_project_root(self, project_root: Path | None) -> None:
        """Store the project root opened when the project-name button
        is clicked.

        :param project_root: Absolute path to the loaded project's root
            directory, or *None* (e.g. a consolidated JSON loaded
            without a resolvable root), which makes the button a no-op.
        """
        self._project_root = project_root

    @Slot()
    def _on_project_name_clicked(self):
        """Open the loaded project's root directory in the OS file
        manager.

        Does nothing when no root is set, or when the stored directory
        does not exist here (e.g. a consolidated JSON saved on another
        machine whose ``ProjectRootPath`` is unavailable); the reason
        is logged rather than surfaced, since the button primarily
        serves as the project-name display.
        """
        root = self._project_root
        if root is None or not Path(root).is_dir():
            logger.info(
                "Project directory unavailable, cannot open: "
                f"{root if root is not None else 'unknown'}"
            )
            return
        logger.info(f"Opening project directory: {root}")
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(root))):
            logger.warning(
                f"QDesktopServices could not open: {root}"
            )