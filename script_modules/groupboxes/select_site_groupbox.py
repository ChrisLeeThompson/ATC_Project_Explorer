"""
Select Site GroupBox

Group box with the lamella-site combo box (topped by a Global
Project Data item), Previous/Next navigation buttons, and an
Open in New Window button.
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
        self.setTitle("Site Selection")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._create_widgets()
        self._setup_layout()

    def _create_widgets(self):
        self.lamella_site_combobox = LamellaSiteComboBox(parent=self)
        self.open_in_new_window_button = OpenInNewWindowButton(parent=self)
        self.previous_button = PreviousButton(parent=self)
        self.next_button = NextButton(parent=self)
        self.open_in_new_window_button.setEnabled(False)
        self.previous_button.setEnabled(False)
        self.next_button.setEnabled(False)

    def _setup_layout(self):
        main_layout = QVBoxLayout(self)
        buttons_layout = QHBoxLayout()
        buttons_layout.addWidget(self.previous_button)
        buttons_layout.addWidget(self.next_button)
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
        self.setLayout(main_layout)
        self.setStyleSheet(AppStyles.GroupBox.with_title())