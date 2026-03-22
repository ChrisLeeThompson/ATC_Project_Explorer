"""
Header GroupBox

This module handles the header group box.
The header group box is used to provide context for the user about the currently loaded project and selected site.
The header group box includes:
- QLabel to display the project name
- QLabel to display the selected site name or "Global Project Data" if no site is selected
"""
import logging
from pathlib import Path
from PySide6.QtWidgets import (
    QGroupBox, QVBoxLayout, QLabel
)
from PySide6.QtCore import Signal, Slot
from script_modules.app_styles import AppStyles


logger = logging.getLogger(__name__)


class HeaderGroupBox(QGroupBox):

    def __init__(self, parent=None):
        super().__init__(parent)
        # Create widgets
        self._create_widgets()
        # Setup layout
        self._setup_layout()
    
    def _create_widgets(self):
        self.project_name_label = QLabel("", parent=self)
        self.site_name_label = QLabel("Site selected: None", parent=self)
        self.project_name_label.setStyleSheet(AppStyles.Label.large_label())
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
        main_layout.addWidget(self.project_name_label)
        main_layout.addWidget(self.site_name_label)
        # Set layout and group box style
        self.setLayout(main_layout)
        self.setStyleSheet(AppStyles.GroupBox.default_main_background())