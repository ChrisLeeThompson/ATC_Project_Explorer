"""
Module for combobox widgets.
"""
from PySide6.QtWidgets import QComboBox
from script_modules.app_styles import AppStyles


class StyledComboBox(QComboBox):

    def __init__(self, parent=None, combobox_text: str = ""):
        super().__init__(parent)
        self.setEditable(True)
        self.lineEdit().setReadOnly(True)
        self.lineEdit().setPlaceholderText(combobox_text)
        self.setCurrentIndex(-1)
        # Set style
        self.setStyleSheet(AppStyles.ComboBox.default())
        # Show text from the left when an item is selected
        self.currentIndexChanged.connect(self._reset_cursor_position)

    def _reset_cursor_position(self):
        """Move the cursor to the start so long text is visible
        from the left with natural clipping on the right."""
        self.lineEdit().setCursorPosition(0)


class LamellaSiteComboBox(StyledComboBox):

    def __init__(self, parent=None):
        super().__init__(parent, combobox_text="Select Lamella Site")


class ImageDirectoryComboBox(StyledComboBox):

    def __init__(self, parent=None):
        super().__init__(parent, combobox_text="Select Image Directory")
        self.setMinimumWidth(AppStyles.Dimensions.IMAGE_VIEWER_COMBOBOX_WIDTH)