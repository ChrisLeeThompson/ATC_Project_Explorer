"""
Module for combobox widgets.

Includes:
- CurrentItemDelegate: Popup delegate marking the combo's current item.
- StyledComboBox: Base styled combo box with placeholder text.
- LamellaSiteComboBox, ImageDirectoryComboBox: Single-select combo boxes.
"""
from PySide6.QtWidgets import QComboBox, QStyledItemDelegate
from PySide6.QtGui import QColor
from PySide6.QtCore import Qt
from script_modules.app_styles import AppStyles


class CurrentItemDelegate(QStyledItemDelegate):
    """
    Draws an accent bar down the current item's row in the popup.

    The popup's row highlight follows the mouse and the arrow keys, so
    it shows which row would be committed — not which one the combo is
    set to. This bar keeps the current setting locatable while the user
    browses a long list, and stays distinct from the highlight (which
    the stylesheet paints as a full-width accent row).

    The bar is painted over the finished row: the stylesheet's ::item
    rules would otherwise cover a background painted underneath. It is
    inset so it sits between the row separators rather than across them,
    and follows the layout direction (leading edge of the text).
    """

    def __init__(self, combo: QComboBox):
        super().__init__(combo)
        self._combo = combo
        self._inset = AppStyles.Dimensions.COMBOBOX_CURRENT_ITEM_BAR_INSET
        self._bar_width = AppStyles.Dimensions.COMBOBOX_CURRENT_ITEM_BAR_WIDTH
        self._bar_color = QColor(AppStyles.Colors.COMBO_CURRENT_ITEM_BG)

    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        if index.row() != self._combo.currentIndex():
            return
        rect = option.rect
        height = rect.height() - 2 * self._inset
        if height <= 0:
            return
        if option.direction == Qt.LayoutDirection.RightToLeft:
            left = rect.right() - self._inset - self._bar_width + 1
        else:
            left = rect.left() + self._inset
        painter.fillRect(
            left,
            rect.top() + self._inset,
            self._bar_width,
            height,
            self._bar_color,
        )


class StyledComboBox(QComboBox):
    """
    Base single-select combo box with placeholder text.

    Opening the popup highlights the current item; while the user
    browses, an accent bar keeps marking it (see CurrentItemDelegate).
    """

    def __init__(self, parent=None, combobox_text: str = ""):
        super().__init__(parent)
        self.setEditable(True)
        self.lineEdit().setReadOnly(True)
        self.lineEdit().setPlaceholderText(combobox_text)
        self.setCurrentIndex(-1)
        # The delegate must be installed after setEditable(): Qt's
        # updateDelegate() runs on style changes and only swaps its own
        # QComboBoxDelegate/QComboMenuDelegate, which this is not.
        self.setItemDelegate(CurrentItemDelegate(self))
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