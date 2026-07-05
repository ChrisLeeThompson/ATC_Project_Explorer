"""
Site Preview GroupBox

Displays two side-by-side preview images that give the user an
immediate sense of the lamella's final state after preparation.

Layout::

    SitePreviewGroupBox (titled "Site Preview")
    ┌────────────────────────────────────────────┐
    │  ┌──────────────────┐ ┌──────────────────┐ │
    │  │  Electron image  │ │  Polishing image │ │
    │  │  (evaluation or  │ │  (last polishing │ │
    │  │   last electron  │ │   match image)   │ │
    │  │   match image)   │ │                  │ │
    │  └──────────────────┘ └──────────────────┘ │
    │  (hover for filename)  (hover for filename)│
    └────────────────────────────────────────────┘

Image selection logic:

- **Left image**: The last image in the
  ``LamellaEvaluationImages`` directory.  If that directory
  is empty or missing, falls back to the last image in
  ``PrecisePositioningLogImages`` whose file name contains
  ``"electron"`` (case-insensitive).

- **Right image**: The last image in
  ``PrecisePositioningLogImages`` whose file name contains
  ``"Polishing"`` but not ``"electron"`` (case-insensitive),
  corresponding to the ion beam polishing image.

Both images are displayed as lightweight QPixmap thumbnails
with no matplotlib overhead.  File names are shown as
tooltips on hover.  A centred "Image not available"
placeholder is shown when the target image cannot be found
or loaded.

Each preview image is clickable: hovering shows a subtle
border and a pointing-hand cursor; clicking emits the
:attr:`~SitePreviewGroupBox.preview_clicked` signal with
the source directory name and file name so the parent panel
can scroll to and select the image in the full image viewer.
"""
import logging
from pathlib import Path

from PySide6.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QFrame,
    QSizePolicy,
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
# Clickable Preview Frame
# -----------------------------------------------------------------

class _ClickablePreviewFrame(QFrame):
    """QFrame wrapper that adds hover border and click detection
    to a :class:`PreviewLabel`.

    When ``clickable`` is True, entering the frame shows a
    subtle border and switches to a pointing-hand cursor.
    Leaving restores the default appearance.  Clicking emits
    the :attr:`clicked` signal.
    """

    clicked = Signal()

    def __init__(self, label: PreviewLabel, parent=None):
        super().__init__(parent)
        self._label = label
        self._clickable = False
        self._default_cursor = self.cursor()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(0)
        layout.addWidget(label)

        # Reserve border space with a transparent border so
        # the layout does not shift on hover.
        self._apply_border(False)

    def set_clickable(self, clickable: bool) -> None:
        """Enable or disable the hover and click behaviour.

        :param clickable: True when a valid image is displayed.
        """
        self._clickable = clickable
        if not clickable:
            self._apply_border(False)
            self.setCursor(self._default_cursor)

    def _apply_border(self, visible: bool) -> None:
        """Toggle the hover border.

        :param visible: Show or hide the border.
        """
        color = (
            AppStyles.Colors.BUTTON_HOVER
            if visible
            else "transparent"
        )
        self.setStyleSheet(
            f"QFrame {{"
            f"  border: 2px solid {color};"
            f"  border-radius: "
            f"  {AppStyles.Dimensions.BORDER_RADIUS_SMALL};"
            f"  background-color: transparent;"
            f"}}"
        )

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
        """Emit :attr:`clicked` on left-click when clickable."""
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self._clickable
        ):
            self.clicked.emit()
        super().mousePressEvent(event)


# -----------------------------------------------------------------
# Site Preview GroupBox
# -----------------------------------------------------------------

class SitePreviewGroupBox(QGroupBox):
    """Side-by-side preview of electron and polishing images."""

    # Emitted when the user clicks a preview image.  Carries
    # the image directory name and the image file name so the
    # image viewer can navigate directly to that image.
    preview_clicked = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("Site Preview")

        # State
        self._project_root: Path | None = None

        # Track the source directory and filename for each side
        # so the signal can carry them on click.
        self._left_dir_name: str = ""
        self._left_filename: str = ""
        self._right_dir_name: str = ""
        self._right_filename: str = ""

        self._create_widgets()
        self._setup_layout()
        self._connect_click_events()

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    def set_project_root(self, project_root: Path | None) -> None:
        """Store the project root for resolving relative paths.

        :param project_root: Absolute path to the ATC project
            root directory, or *None* to clear.
        """
        self._project_root = project_root

    def populate(self, site_data: dict) -> None:
        """Find and display the two preview images for a site.

        :param site_data: A single site entry from the consolidated
            metadata ``"Sites"`` list.
        """
        directories = site_data.get("ImageDirectories", [])
        site_name = site_data.get("SiteName", "Unknown")

        left_path, left_dir = find_left_image(
            directories, self._project_root
        )
        right_path, right_dir = find_right_image(
            directories, self._project_root
        )

        # Store source info for click-to-navigate
        self._left_dir_name = left_dir
        self._left_filename = left_path.name if left_path else ""
        self._right_dir_name = right_dir
        self._right_filename = right_path.name if right_path else ""

        left_name = left_path.name if left_path else "None"
        right_name = right_path.name if right_path else "None"
        logger.info(
            f"Site preview for '{site_name}': "
            f"left='{left_name}', right='{right_name}'"
        )

        # Load and display
        left_pixmap = (
            load_preview_pixmap(left_path)
            if left_path is not None else None
        )
        right_pixmap = (
            load_preview_pixmap(right_path)
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

        # Enable click interaction when an image is loaded
        self._left_frame.set_clickable(left_path is not None)
        self._right_frame.set_clickable(right_path is not None)

    def clear(self) -> None:
        """Reset both preview panels to empty."""
        self._left_label.clear_preview()
        self._right_label.clear_preview()

        self._left_frame.set_clickable(False)
        self._right_frame.set_clickable(False)
        self._left_dir_name = ""
        self._left_filename = ""
        self._right_dir_name = ""
        self._right_filename = ""

    # -----------------------------------------------------------------
    # Setup
    # -----------------------------------------------------------------

    def _create_widgets(self):
        """Create the two preview labels and clickable frames."""
        self._left_label = PreviewLabel(parent=self)
        self._right_label = PreviewLabel(parent=self)

        # Wrap each label in a clickable frame for hover
        # border and click-to-navigate behaviour.
        self._left_frame = _ClickablePreviewFrame(
            self._left_label, parent=self
        )
        self._right_frame = _ClickablePreviewFrame(
            self._right_label, parent=self
        )

    def _setup_layout(self):
        """Arrange the two previews side by side."""
        pair_layout = QHBoxLayout()
        pair_layout.setContentsMargins(0, 0, 0, 0)
        pair_layout.setSpacing(AppStyles.Dimensions.LAYOUT_VSPACING)
        pair_layout.addWidget(self._left_frame, 1)
        pair_layout.addWidget(self._right_frame, 1)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(
            AppStyles.Dimensions.LAYOUT_CONTENTS_MARGIN,
            AppStyles.Dimensions.LAYOUT_CONTENTS_MARGIN,
            AppStyles.Dimensions.LAYOUT_CONTENTS_MARGIN,
            AppStyles.Dimensions.LAYOUT_CONTENTS_MARGIN,
        )
        main_layout.setSpacing(AppStyles.Dimensions.LAYOUT_VSPACING)
        main_layout.addLayout(pair_layout, 1)

        self.setStyleSheet(
            AppStyles.GroupBox.plot_with_title()
            + AppStyles.AppToolTips.default()
        )

    # -----------------------------------------------------------------
    # Click-to-Navigate
    # -----------------------------------------------------------------

    def _connect_click_events(self):
        """Connect frame click signals to navigation handlers."""
        self._left_frame.clicked.connect(
            self._on_left_clicked
        )
        self._right_frame.clicked.connect(
            self._on_right_clicked
        )

    def _on_left_clicked(self):
        """Handle click on the left preview frame."""
        if not self._left_dir_name or not self._left_filename:
            return
        logger.info(
            f"Preview click: '{self._left_filename}' "
            f"in '{self._left_dir_name}'"
        )
        self.preview_clicked.emit(
            self._left_dir_name, self._left_filename
        )

    def _on_right_clicked(self):
        """Handle click on the right preview frame."""
        if not self._right_dir_name or not self._right_filename:
            return
        logger.info(
            f"Preview click: '{self._right_filename}' "
            f"in '{self._right_dir_name}'"
        )
        self.preview_clicked.emit(
            self._right_dir_name, self._right_filename
        )