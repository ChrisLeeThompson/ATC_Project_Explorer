"""
Module for styled label widgets.
"""
from PySide6.QtWidgets import QLabel
from script_modules.app_styles import AppStyles


class StyledLabel(QLabel):

    def __init__(self, parent=None, label_text: str = ""):
        super().__init__(parent)
        self.setText(label_text)
        self.setStyleSheet(AppStyles.Label.default())


class StartupLabel(StyledLabel):

    def __init__(self, parent=None):
        super().__init__(parent, label_text="")
        label_text = "Drop an ATC project directory or previously generated JSON metadata file\n" + \
                     "onto Catbug to explore ATC metadata.\n\n" + \
                     "Alternatively, use the Load ATC Project button or the Load Metadata File button to begin."
        self.setText(label_text)
        self.setStyleSheet(AppStyles.Label.large_label())