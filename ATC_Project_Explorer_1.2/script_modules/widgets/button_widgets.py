"""
Module for styled button widgets.
"""
from PySide6.QtWidgets import QPushButton
from PySide6.QtGui import QIcon
from PySide6.QtCore import Qt, QSize
from script_modules.app_styles import AppStyles, ASSETS_DIR


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
        super().__init__(parent, "Delete Temp Metadata File")
        self.setToolTip(AppStyles.AppText.DELETE_TEMP_METADATA_BUTTON)


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


class ResetViewButton(QPushButton):

    def __init__(self, parent=None):
        super().__init__(parent)
        icon_path = str(ASSETS_DIR / "reset_view_light-gray.svg")
        self.setIcon(QIcon(icon_path))
        self.setIconSize(QSize(24, 24))
        self.setFixedSize(32, 32)
        self.setToolTip("Reset view")
        self.setStyleSheet(AppStyles.Button.reset_view() + AppStyles.AppToolTips.default())
        # self.setCursor(Qt.CursorShape.PointingHandCursor)


class PatternToggleButton(QPushButton):
    """Checkable button for pattern activity selection.

    Uses the standard button style with the checked state
    highlighted in the hover colour for visual distinction.
    """

    def __init__(self, parent=None, button_text: str = ""):
        super().__init__(parent)
        self.setText(button_text)
        self.setCheckable(True)
        self.setStyleSheet(AppStyles.Button.toggle())