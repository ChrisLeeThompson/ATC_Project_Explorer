"""
Select Site Groupbox

This module handles the select site groupbox.
The groupbox includes:
- A combo box to select the lamella site.
- A button to open the selected lamella site in a new window.
- The combo box has a top-level item to select the global project data.
"""
import logging
from pathlib import Path
from PySide6.QtWidgets import (
    QGroupBox, QHBoxLayout, QVBoxLayout
)
from PySide6.QtCore import Qt, Signal, Slot
from script_modules.app_styles import AppStyles
from script_modules.widgets.button_widgets import (
    OpenInNewWindowButton, PreviousButton, NextButton
)
from script_modules.widgets.combobox_widgets import LamellaSiteComboBox


logger = logging.getLogger(__name__)


class SelectSiteGroupBox(QGroupBox):

    def __init__(self, parent=None):
        super().__init__(parent)
        # Set title
        self.setTitle("Site Selection")
        # Set focus policy
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        # Create widgets
        self._create_widgets()
        # Setup layout
        self._setup_layout()
    
    def _create_widgets(self):
        # Combo box
        self.lamella_site_combobox = LamellaSiteComboBox(parent=self)
        # Button (disabled until site combobox is populated)
        self.open_in_new_window_button = OpenInNewWindowButton(parent=self)
        self.previous_button = PreviousButton(parent=self)
        self.next_button = NextButton(parent=self)
        self.open_in_new_window_button.setEnabled(False)
        self.previous_button.setEnabled(False)
        self.next_button.setEnabled(False)
    
    def _setup_layout(self):
        # Layout
        main_layout = QVBoxLayout(self)
        # Previous and next buttons in horizontal layout
        buttons_layout = QHBoxLayout()
        buttons_layout.addWidget(self.previous_button)
        buttons_layout.addWidget(self.next_button)
        # Add widgets to layout
        main_layout.addWidget(self.lamella_site_combobox)
        main_layout.addLayout(buttons_layout)
        main_layout.addWidget(self.open_in_new_window_button)
        main_layout.setContentsMargins(
            AppStyles.Dimensions.LAYOUT_CONTENTS_MARGIN,
            AppStyles.Dimensions.LAYOUT_CONTENTS_MARGIN,
            AppStyles.Dimensions.LAYOUT_CONTENTS_MARGIN,
            AppStyles.Dimensions.LAYOUT_CONTENTS_MARGIN
        )
        main_layout.setSpacing(AppStyles.Dimensions.LAYOUT_VSPACING)
        # Set layout and group box style
        self.setLayout(main_layout)
        self.setStyleSheet(AppStyles.GroupBox.with_title())