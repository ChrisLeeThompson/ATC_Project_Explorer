"""
Global Site Preview GroupBox

Horizontally scrollable strip of compact site-preview cards
for the global panel.  Each card shows the same two-image
preview pair as the site panel's ``SitePreviewGroupBox``
(electron image left, polishing image right) with the site
name displayed as the groupbox title.

Layout::

    GlobalSitePreviewGroupBox (titled "Site Previews")
    ┌──────────────────────────────────────────────────────┐
    │  ◄ horizontal scroll ►                               │
    │  ┌───────────┐ ┌───────────┐ ┌───────────┐          │
    │  │ Site 01   │ │ Site 02   │ │ Site 03   │          │
    │  │ img │ img │ │ img │ img │ │ img │ img │  …       │
    │  │     │     │ │     │     │ │     │     │          │
    │  └───────────┘ └───────────┘ └───────────┘          │
    └──────────────────────────────────────────────────────┘

Clicking a card emits :attr:`site_selected` with the site
name so the main module can navigate to the corresponding
site panel.
"""
import logging
from pathlib import Path

from PySide6.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout,
    QScrollArea, QWidget, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCursor

from script_modules.app_styles import AppStyles
from script_modules.preview_image_helpers import (
    PreviewLabel,
    find_left_image,
    find_right_image,
    load_preview_pixmap,
)


logger = logging.getLogger(__name__)


# -----------------------------------------------------------------
# Site Preview Card
# -----------------------------------------------------------------

class _SitePreviewCard(QGroupBox):
    """Compact preview card for a single lamella site.

    Shows two side-by-side QPixmap thumbnails (electron and
    polishing images) inside a titled groupbox.  The groupbox
    title displays the site name.  The entire card is clickable:
    hovering shows a subtle border and pointing-hand cursor;
    clicking emits :attr:`clicked` with the site name.
    """

    clicked = Signal(str)

    # Base stylesheet (with_title) — cached once so hover
    # toggling only appends the border override.
    _BASE_STYLE = AppStyles.GroupBox.with_title()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._site_name: str = ""
        self._clickable: bool = False
        self._default_cursor = self.cursor()

        self._create_widgets()
        self._setup_layout()

        # Apply base style with transparent border so the
        # layout does not shift on hover.
        self._apply_border(False)

        self.setFixedWidth(AppStyles.Dimensions.GLOBAL_SITE_PREVIEW_CARD_FIXED_WIDTH)
        self.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Expanding,
        )

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    def populate(
        self,
        site_name: str,
        left_path: Path | None,
        right_path: Path | None,
    ) -> None:
        """Display the two preview images and site name.

        :param site_name: Display name shown as the groupbox
            title.
        :param left_path: Absolute path to the electron /
            evaluation image, or *None*.
        :param right_path: Absolute path to the polishing
            image, or *None*.
        """
        self._site_name = site_name
        self.setTitle(site_name)

        left_pixmap = (
            load_preview_pixmap(left_path, max_dim=AppStyles.Dimensions.GLOBAL_SITE_PREVIEW_CARD_THUMBNAIL_MAX_DIM)
            if left_path is not None else None
        )
        right_pixmap = (
            load_preview_pixmap(right_path, max_dim=AppStyles.Dimensions.GLOBAL_SITE_PREVIEW_CARD_THUMBNAIL_MAX_DIM)
            if right_path is not None else None
        )

        self._left_label.set_preview(
            left_pixmap,
            tooltip=left_path.name if left_path else "",
        )
        self._right_label.set_preview(
            right_pixmap,
            tooltip=right_path.name if right_path else "",
        )

        # Enable click interaction when at least one image loaded
        self._clickable = (
            left_path is not None or right_path is not None
        )

    def clear(self) -> None:
        """Reset the card to its empty state."""
        self._site_name = ""
        self._clickable = False
        self.setTitle("")
        self._left_label.clear_preview()
        self._right_label.clear_preview()

    # -----------------------------------------------------------------
    # Setup
    # -----------------------------------------------------------------

    def _create_widgets(self):
        """Create the two preview labels."""
        self._left_label = PreviewLabel(parent=self)
        self._right_label = PreviewLabel(parent=self)

    def _setup_layout(self):
        """Arrange labels side by side inside the groupbox."""
        canvas_row = QHBoxLayout()
        canvas_row.setContentsMargins(0, 0, 0, 0)
        canvas_row.setSpacing(
            AppStyles.Dimensions.LAYOUT_VSPACING
        )
        canvas_row.addWidget(self._left_label, 1)
        canvas_row.addWidget(self._right_label, 1)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(
            AppStyles.Dimensions.LAYOUT_CONTENTS_MARGIN,
            AppStyles.Dimensions.LAYOUT_CONTENTS_MARGIN,
            AppStyles.Dimensions.LAYOUT_CONTENTS_MARGIN,
            AppStyles.Dimensions.LAYOUT_CONTENTS_MARGIN,
        )
        main_layout.setSpacing(0)
        main_layout.addLayout(canvas_row, 1)

    # -----------------------------------------------------------------
    # Hover / Click
    # -----------------------------------------------------------------

    def _apply_border(self, visible: bool) -> None:
        """Toggle the hover border.

        Re-applies the base ``with_title`` stylesheet and
        appends a border override when *visible* is True.

        :param visible: Show or hide the border.
        """
        if visible:
            border_override = (
                f"QGroupBox {{"
                f"  border: 2px solid "
                f"  {AppStyles.Colors.BUTTON_HOVER};"
                f"}}"
            )
            self.setStyleSheet(
                self._BASE_STYLE + border_override
            )
        else:
            self.setStyleSheet(self._BASE_STYLE)

    def enterEvent(self, event):
        """Show hover border and pointing-hand cursor."""
        if self._clickable:
            self._apply_border(True)
            self.setCursor(
                QCursor(Qt.CursorShape.PointingHandCursor)
            )
        super().enterEvent(event)

    def leaveEvent(self, event):
        """Restore default border and cursor."""
        self._apply_border(False)
        self.setCursor(self._default_cursor)
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        """Handle clicks anywhere on the card."""
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self._clickable
        ):
            logger.info(
                f"Site preview card clicked: "
                f"'{self._site_name}'"
            )
            self.clicked.emit(self._site_name)
        super().mousePressEvent(event)


# -----------------------------------------------------------------
# Global Site Preview GroupBox
# -----------------------------------------------------------------

class GlobalSitePreviewGroupBox(QGroupBox):
    """Horizontally scrollable strip of site preview cards.

    Displays a compact preview card for each lamella site in
    the project.  Clicking a card emits :attr:`site_selected`
    with the site name.

    Signals:
        site_selected(str): Emitted when a card is clicked,
            carrying the site name.
    """

    site_selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("Site Previews")

        self._project_root: Path | None = None
        self._cards: list[_SitePreviewCard] = []

        self._setup_layout()

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    def set_project_root(self, project_root: Path | None) -> None:
        """Store the project root for resolving relative paths.

        :param project_root: Absolute path to the ATC project
            root directory, or *None* to clear.
        """
        self._project_root = project_root

    def populate(self, metadata: dict) -> None:
        """Create a preview card for every site in the project.

        Existing cards are removed and rebuilt from scratch.

        :param metadata: Consolidated metadata dictionary with
            top-level keys ``"ProjectData"`` and ``"Sites"``.
        """
        self._clear_cards()

        sites = metadata.get("Sites", [])
        for site_data in sites:
            site_name = site_data.get("SiteName", "Unknown")
            directories = site_data.get(
                "ImageDirectories", []
            )

            left_path, _ = find_left_image(
                directories, self._project_root
            )
            right_path, _ = find_right_image(
                directories, self._project_root
            )

            card = _SitePreviewCard(parent=self._content_widget)
            card.populate(site_name, left_path, right_path)
            card.clicked.connect(self.site_selected)

            # Insert before the trailing stretch
            self._card_layout.insertWidget(
                self._card_layout.count() - 1, card
            )
            self._cards.append(card)

        logger.info(
            f"GlobalSitePreviewGroupBox populated with "
            f"{len(self._cards)} cards"
        )

    def clear(self) -> None:
        """Remove all preview cards."""
        self._clear_cards()
        logger.info("GlobalSitePreviewGroupBox cleared")

    # -----------------------------------------------------------------
    # Setup
    # -----------------------------------------------------------------

    def _setup_layout(self):
        """Build the horizontal scroll area and card layout."""
        # Content widget that holds the card row
        self._content_widget = QWidget()
        self._card_layout = QHBoxLayout(self._content_widget)
        self._card_layout.setContentsMargins(0, 0, 0, 0)
        self._card_layout.setSpacing(
            AppStyles.Dimensions.LAYOUT_VSPACING
        )
        self._card_layout.addStretch(1)

        # Horizontal scroll area
        self._scroll_area = QScrollArea()
        self._scroll_area.setWidget(self._content_widget)
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self._scroll_area.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._scroll_area.setStyleSheet(
            AppStyles.ScrollArea.default()
        )

        # GroupBox layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(
            AppStyles.Dimensions.LAYOUT_CONTENTS_MARGIN,
            AppStyles.Dimensions.LAYOUT_CONTENTS_MARGIN,
            AppStyles.Dimensions.LAYOUT_CONTENTS_MARGIN,
            AppStyles.Dimensions.LAYOUT_CONTENTS_MARGIN,
        )
        main_layout.setSpacing(0)
        main_layout.addWidget(self._scroll_area)

        self.setStyleSheet(
            AppStyles.GroupBox.plot_with_title()
            + AppStyles.AppToolTips.default()
        )

    # -----------------------------------------------------------------
    # Internals
    # -----------------------------------------------------------------

    def _clear_cards(self):
        """Remove and delete all current cards."""
        for card in self._cards:
            card.clear()
            self._card_layout.removeWidget(card)
            card.deleteLater()
        self._cards.clear()