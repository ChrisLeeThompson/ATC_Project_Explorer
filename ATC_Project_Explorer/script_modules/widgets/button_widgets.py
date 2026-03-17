"""
Module for styled button widgets.
"""
from PySide6.QtWidgets import QPushButton
from script_modules.app_styles import AppStyles


class StyledButton(QPushButton):

    def __init__(self, parent=None, button_text: str = ""):
        super().__init__(parent)
        self.setText(button_text)
        self.setStyleSheet(AppStyles.Button.default())


class LoadATCDataButton(StyledButton):

    def __init__(self, parent=None):
        super().__init__(parent, "Load ATC Project")


class LoadJSONFileButton(StyledButton):

    def __init__(self, parent=None):
        super().__init__(parent, "Load Metadata File")


class DeleteJSONFileButton(StyledButton):

    def __init__(self, parent=None):
        super().__init__(parent, "Delete Metadata File")


class SaveJSONFileButton(StyledButton):

    def __init__(self, parent=None):
        super().__init__(parent, "Save Metadata File")


class CancelButton(StyledButton):

    def __init__(self, parent=None):
        super().__init__(parent, "Cancel")
        self.setFixedWidth(AppStyles.Dimensions.BUTTON_WIDTH)


class OpenInNewWindowButton(StyledButton):

    def __init__(self, parent=None):
        super().__init__(parent, "Open In New Window")


class PreviousButton(StyledButton):

    def __init__(self, parent=None):
        super().__init__(parent, "Previous")


class NextButton(StyledButton):

    def __init__(self, parent=None):
        super().__init__(parent, "Next")