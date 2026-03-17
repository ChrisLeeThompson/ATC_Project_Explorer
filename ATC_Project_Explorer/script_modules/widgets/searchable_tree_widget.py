"""
Searchable Tree Widget

Reusable group box containing a search field, Expand All
checkbox, and a ``QTreeWidget`` that displays nested dict data.

Used by:
    - ``SiteParametersGroupBox`` for the parameters panel and
      each per-recipe panel.
    - ``ImageViewerGroupBox`` for the image metadata tree.

The widget handles:
    - Building a two-column tree from nested dicts / lists.
    - Live search filtering with recursive visibility.
    - Expand / collapse all via checkbox.
"""
from PySide6.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QWidget,
    QLineEdit, QCheckBox, QTreeWidget, QTreeWidgetItem,
    QHeaderView, QAbstractItemView,
)
from PySide6.QtCore import Qt, Slot
from script_modules.app_styles import AppStyles


class SearchableTreePanel(QGroupBox):
    """Group box with a search field, Expand All checkbox, and a
    two-column ``QTreeWidget`` that displays nested dictionary
    data.

    :param title: Group box title shown above the panel.
    :param parent: Optional parent widget.
    """

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setTitle(title)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._create_widgets()
        self._setup_layout()
        self._connect_signals()

    # -----------------------------------------------------------------
    # Setup
    # -----------------------------------------------------------------

    def _create_widgets(self):
        """Create search field, expand checkbox, and tree widget."""
        # Search field
        self.search_line_edit = QLineEdit()
        self.search_line_edit.setPlaceholderText("Search")
        self.search_line_edit.setStyleSheet(AppStyles.LineEdit.search())

        # Expand All checkbox (checked — tree starts expanded)
        self.expand_all_checkbox = QCheckBox("Expand All")
        self.expand_all_checkbox.setStyleSheet(
            AppStyles.CheckBox.default()
        )
        self.expand_all_checkbox.setChecked(True)

        # Search row container
        self._search_row = QWidget()
        search_row_layout = QHBoxLayout(self._search_row)
        search_row_layout.setContentsMargins(0, 0, 0, 0)
        search_row_layout.setSpacing(AppStyles.Dimensions.LAYOUT_VSPACING)
        search_row_layout.addWidget(self.search_line_edit, 1)
        search_row_layout.addWidget(self.expand_all_checkbox)

        # Tree widget
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["", ""])
        self.tree.setColumnCount(2)
        self.tree.setRootIsDecorated(True)
        self.tree.setItemsExpandable(True)
        self.tree.setExpandsOnDoubleClick(True)
        self.tree.setAlternatingRowColors(False)
        self.tree.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.tree.setHorizontalScrollMode(
            QAbstractItemView.ScrollMode.ScrollPerPixel
        )
        self.tree.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.tree.setStyleSheet(AppStyles.TreeWidget.metadata())

        # Header: interactive field column, auto-fit value column
        header = self.tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(
            0, QHeaderView.ResizeMode.Interactive
        )
        header.setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )

    def _setup_layout(self):
        """Stack search row above tree widget."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            AppStyles.Dimensions.LAYOUT_CONTENTS_MARGIN,
            AppStyles.Dimensions.LAYOUT_CONTENTS_MARGIN,
            AppStyles.Dimensions.LAYOUT_CONTENTS_MARGIN,
            AppStyles.Dimensions.LAYOUT_CONTENTS_MARGIN,
        )
        layout.setSpacing(AppStyles.Dimensions.LAYOUT_VSPACING)
        layout.addWidget(self._search_row)
        layout.addWidget(self.tree, 1)

    def _connect_signals(self):
        """Connect search and expand signals."""
        self.search_line_edit.textChanged.connect(
            self._on_search_text_changed
        )
        self.expand_all_checkbox.toggled.connect(
            self._on_expand_all_toggled
        )

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    def populate(self, data: dict) -> None:
        """Build the tree from a nested dictionary.

        :param data: Dictionary to display in the tree.
        """
        self.search_line_edit.clear()
        self._build_tree(data)
        self._reapply_search_filter()

    def clear_tree(self) -> None:
        """Reset the tree to empty."""
        self.search_line_edit.clear()
        self.tree.clear()

    def apply_style(self, style: str) -> None:
        """Apply a QGroupBox stylesheet to this panel.

        :param style: CSS stylesheet string.
        """
        self.setStyleSheet(style)

    def set_search_row_visible(self, visible: bool) -> None:
        """Show or hide the search row.

        Useful when the host widget manages its own visibility
        state (e.g. hiding the tree until an image is selected).

        :param visible: True to show, False to hide.
        """
        self._search_row.setVisible(visible)

    # -----------------------------------------------------------------
    # Tree Building
    # -----------------------------------------------------------------

    def _build_tree(self, data: dict):
        """Build the tree widget from a nested dictionary.

        :param data: Nested dictionary to display.
        """
        self.tree.clear()
        self.tree.setUpdatesEnabled(False)

        bold_font = self.tree.font()
        bold_font.setBold(True)

        for key, value in data.items():
            top_item = QTreeWidgetItem([str(key)])
            top_item.setFont(0, bold_font)
            self._add_children(top_item, value)
            self.tree.addTopLevelItem(top_item)

        # Respect the Expand All checkbox state
        if self.expand_all_checkbox.isChecked():
            self.tree.expandAll()
        else:
            self.tree.collapseAll()

        self.tree.resizeColumnToContents(0)
        self.tree.resizeColumnToContents(1)
        self.tree.setUpdatesEnabled(True)

        # Center the column divider
        self.tree.header().resizeSection(
            0, self.tree.viewport().width() // 2
        )

    def _add_children(
        self, parent_item: QTreeWidgetItem, value
    ):
        """Recursively add child items to a parent tree item.

        :param parent_item: The parent ``QTreeWidgetItem``.
        :param value: The value — dict, list, or leaf.
        """
        if isinstance(value, dict):
            for child_key, child_value in value.items():
                if isinstance(child_value, (dict, list)):
                    branch = QTreeWidgetItem([str(child_key)])
                    self._add_children(branch, child_value)
                    parent_item.addChild(branch)
                else:
                    leaf = QTreeWidgetItem(
                        [str(child_key), str(child_value)]
                    )
                    parent_item.addChild(leaf)
        elif isinstance(value, list):
            for i, item in enumerate(value):
                child = QTreeWidgetItem([f"[{i}]"])
                self._add_children(child, item)
                parent_item.addChild(child)
        else:
            parent_item.setText(1, str(value))

    # -----------------------------------------------------------------
    # Expand All
    # -----------------------------------------------------------------

    @Slot(bool)
    def _on_expand_all_toggled(self, checked: bool):
        """Expand or collapse all tree items.

        :param checked: True to expand, False to collapse.
        """
        if checked:
            self.tree.expandAll()
        else:
            self.tree.collapseAll()

    # -----------------------------------------------------------------
    # Search / Filter
    # -----------------------------------------------------------------

    def _reapply_search_filter(self):
        """Reapply current search text after a tree rebuild."""
        search = self.search_line_edit.text().strip().lower()
        if not search:
            return
        for i in range(self.tree.topLevelItemCount()):
            self._filter_item(self.tree.topLevelItem(i), search)

    @Slot(str)
    def _on_search_text_changed(self, text: str):
        """Filter tree items based on search text.

        :param text: Current search text.
        """
        search = text.strip().lower()

        if not search:
            self._set_all_visible(True)
            if self.expand_all_checkbox.isChecked():
                self.tree.expandAll()
            else:
                self.tree.collapseAll()
            return

        for i in range(self.tree.topLevelItemCount()):
            self._filter_item(self.tree.topLevelItem(i), search)

    def _filter_item(
        self, item: QTreeWidgetItem, search: str
    ) -> bool:
        """Recursively filter a tree item and its children.

        :param item: The tree item to evaluate.
        :param search: Lowercase search text.
        :return: True if this item or any descendant matches.
        """
        item_matches = (
            search in item.text(0).lower()
            or search in item.text(1).lower()
        )
        child_matches = False
        for i in range(item.childCount()):
            if self._filter_item(item.child(i), search):
                child_matches = True

        visible = item_matches or child_matches
        item.setHidden(not visible)
        return visible

    def _set_all_visible(self, visible: bool):
        """Set visibility on all items in the tree.

        :param visible: True to show all, False to hide all.
        """
        for i in range(self.tree.topLevelItemCount()):
            self._set_item_visible(
                self.tree.topLevelItem(i), visible
            )

    def _set_item_visible(
        self, item: QTreeWidgetItem, visible: bool
    ):
        """Recursively set visibility on an item and children."""
        item.setHidden(not visible)
        for i in range(item.childCount()):
            self._set_item_visible(item.child(i), visible)