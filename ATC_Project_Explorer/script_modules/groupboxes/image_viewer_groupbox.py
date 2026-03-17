"""
Image Viewer GroupBox

Two-column layout for browsing site images from an ATC project.

Layout::

    ImageViewerGroupBox (titled "Image Viewer")
    ├── Left column (fixed width):
    │   ├── ImageDirectoryComboBox (select image directory)
    │   └── Searchable metadata tree (ImageInfo, MicroscopeMetadata,
    │       XMLMetadata for TIF files; ImageInfo only for PNG)
    └── Right column (expanding):
        ├── Image name + [Show Graphics] + counter row
        ├── NavigationToolbar2QT (zoom, pan, save)
        ├── FigureCanvasQTAgg (image display + optional overlay)
        └── Button row: [Previous ←──────── ] [──────────→ Next]

The group box is populated with a site's ``ImageDirectories``
data and requires the project root path to resolve relative image
paths to absolute paths on disk.

The group box starts in a placeholder state and is populated when
the user selects a site in the combo box.
"""
import logging
from pathlib import Path

from matplotlib.backends.backend_qtagg import (
    FigureCanvasQTAgg,
    NavigationToolbar2QT,
)
from matplotlib.figure import Figure

from PySide6.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QWidget,
    QLabel, QSizePolicy, QCheckBox,
)
from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor
from script_modules.app_styles import AppStyles
from script_modules.image_utils import load_image
from script_modules.widgets.combobox_widgets import ImageDirectoryComboBox
from script_modules.widgets.button_widgets import PreviousButton, NextButton
from script_modules.widgets.searchable_tree_widget import SearchableTreePanel
from script_modules.parsers.image_metadata_parser import (
    extract_image_metadata,
)


logger = logging.getLogger(__name__)


# Placeholder text
_PLACEHOLDER_LABEL = "No images available"

# Thumbnail parameters
_THUMBNAIL_MAX_DIM = 1024

# -----------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------


def _style_axes_dark(ax):
    """Apply a dark theme to matplotlib axes for image display."""
    ax.set_facecolor(AppStyles.Colors.MAIN_BG)
    ax.set_axis_off()


def _recolor_toolbar_icons(toolbar, color_hex: str = None):
    """Repaint toolbar action icons to a consistent color.

    Ensures button icons render identically on both light
    and dark OS themes by replacing all opaque pixels with
    the target color.

    :param toolbar: ``NavigationToolbar2QT`` instance.
    :param color_hex: Hex color string.  Defaults to
        ``AppStyles.Colors.TEXT_PRIMARY``.
    """
    if color_hex is None:
        color_hex = AppStyles.Colors.TEXT_PRIMARY
    color = QColor(color_hex)
    for action in toolbar.actions():
        icon = action.icon()
        if icon.isNull():
            continue
        sizes = icon.availableSizes()
        if not sizes:
            continue
        pixmap = icon.pixmap(sizes[0])
        painter = QPainter(pixmap)
        painter.setCompositionMode(
            QPainter.CompositionMode.CompositionMode_SourceIn
        )
        painter.fillRect(pixmap.rect(), color)
        painter.end()
        action.setIcon(QIcon(pixmap))


# -----------------------------------------------------------------
# Image Viewer GroupBox
# -----------------------------------------------------------------

class ImageViewerGroupBox(QGroupBox):
    """Two-column image viewer with directory selection and
    Previous/Next navigation."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("Image Viewer")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # State
        self._project_root: Path | None = None
        self._image_directories: list[dict] = []
        self._current_image_paths: list[Path] = []
        self._current_index: int = -1
        self._overlay_data: dict | None = None
        self._downsample_factor: int = 1

        self._create_widgets()
        self._setup_layout()
        self._connect_signals()

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    def set_project_root(self, project_root: Path | None) -> None:
        """Set the project root path for resolving relative image
        paths.

        :param project_root: Absolute path to the ATC project
            root directory, or *None* to clear.
        """
        self._project_root = project_root

    def populate(self, site_data: dict) -> None:
        """Populate the directory combo box from a site's image
        directories.

        :param site_data: A single site entry from the consolidated
            metadata ``"Sites"`` list.
        """
        self._image_directories = site_data.get(
            "ImageDirectories", []
        )
        self._current_image_paths.clear()
        self._current_index = -1

        # Populate combo box
        self._directory_combobox.blockSignals(True)
        self._directory_combobox.clear()
        for directory in self._image_directories:
            name = directory.get("DirectoryName", "Unknown")
            count = len(directory.get("RelativeImagePaths", []))
            self._directory_combobox.addItem(
                f"{name} ({count})"
            )
        self._directory_combobox.setCurrentIndex(-1)
        self._directory_combobox.blockSignals(False)

        # Update placeholder
        if not self._image_directories:
            self._info_label.setText(_PLACEHOLDER_LABEL)
            self._info_label.setVisible(True)
        else:
            self._info_label.setVisible(False)

        # Clear display
        self._clear_canvas()
        self._update_nav_button_states()

        site_name = site_data.get("SiteName", "Unknown")
        logger.info(
            f"Image viewer populated for '{site_name}': "
            f"{len(self._image_directories)} directory/directories"
        )

    def clear(self) -> None:
        """Reset the viewer to its empty state."""
        self._image_directories.clear()
        self._current_image_paths.clear()
        self._current_index = -1
        self._directory_combobox.blockSignals(True)
        self._directory_combobox.clear()
        self._directory_combobox.blockSignals(False)
        self._info_label.setText(_PLACEHOLDER_LABEL)
        self._info_label.setVisible(True)
        self._image_name_label.setText("")
        self._image_counter_label.setText("")
        self._clear_canvas()
        self._clear_metadata()
        self._update_nav_button_states()

    def select_image(
        self, directory_name: str, filename: str
    ) -> None:
        """Programmatically select a directory and navigate to a
        specific image.

        Used by the site preview click-to-navigate feature to
        jump directly to a preview image in the full viewer.

        :param directory_name: The ``DirectoryName`` value to
            match (e.g. ``"LamellaEvaluationImages"``).
        :param filename: The image file name to navigate to
            within that directory.
        """
        # Find the directory index
        dir_index = -1
        for i, directory in enumerate(self._image_directories):
            if directory.get("DirectoryName", "") == directory_name:
                dir_index = i
                break

        if dir_index < 0:
            logger.warning(
                f"select_image: directory '{directory_name}' "
                f"not found"
            )
            return

        # Select the directory (triggers path resolution)
        self._directory_combobox.setCurrentIndex(dir_index)
        self._on_directory_selected(dir_index)

        # Find the image by filename
        for i, path in enumerate(self._current_image_paths):
            if path.name == filename:
                self._current_index = i
                self._display_current_image()
                self._update_nav_button_states()
                logger.info(
                    f"select_image: navigated to '{filename}' "
                    f"in '{directory_name}'"
                )
                return

        logger.warning(
            f"select_image: '{filename}' not found in "
            f"'{directory_name}'"
        )

    # -----------------------------------------------------------------
    # Setup
    # -----------------------------------------------------------------

    def _create_widgets(self):
        """Create all child widgets."""
        # -- Left column widgets --
        self._directory_combobox = ImageDirectoryComboBox(parent=self)

        # Metadata panel (searchable tree, hidden until image selected)
        self._meta_panel = SearchableTreePanel("", parent=self)
        self._meta_panel.apply_style(
            AppStyles.GroupBox.embedded_untitled()
        )
        self._meta_panel.setVisible(False)

        # -- Right column widgets --
        # Info label (shown when no images)
        self._info_label = QLabel(_PLACEHOLDER_LABEL, parent=self)
        self._info_label.setStyleSheet(AppStyles.Label.default())
        self._info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Image name label
        self._image_name_label = QLabel("", parent=self)
        self._image_name_label.setStyleSheet(AppStyles.Label.default())
        self._image_name_label.setWordWrap(True)

        # Image counter label (e.g. "3 / 15")
        self._image_counter_label = QLabel("", parent=self)
        self._image_counter_label.setStyleSheet(AppStyles.Label.default())
        self._image_counter_label.setAlignment(
            Qt.AlignmentFlag.AlignRight
            | Qt.AlignmentFlag.AlignVCenter
        )

        # Show Graphics checkbox (enabled when overlay data is found)
        self._show_graphics_checkbox = QCheckBox(
            "Show Graphics", parent=self
        )
        self._show_graphics_checkbox.setStyleSheet(
            AppStyles.CheckBox.default()
        )
        self._show_graphics_checkbox.setChecked(False)
        self._show_graphics_checkbox.setEnabled(False)
        self._show_graphics_checkbox.setFocusPolicy(
            Qt.FocusPolicy.NoFocus
        )

        # Matplotlib canvas for image display
        self._figure = Figure(
            facecolor=AppStyles.Colors.MAIN_BG,
            constrained_layout=True,
        )
        self._canvas = FigureCanvasQTAgg(self._figure)
        self._canvas.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self._canvas.setMinimumHeight(
            AppStyles.Dimensions.IMAGE_VIEWER_CANVAS_MINIMUM_HEIGHT
        )
        self._ax = self._figure.add_subplot(111)
        _style_axes_dark(self._ax)
        self._figure.patch.set_antialiased(False)
        self._canvas.setStyleSheet(
            f"background-color: {AppStyles.Colors.MAIN_BG};"
        )

        # Matplotlib navigation toolbar (zoom, pan, save)
        self._toolbar = NavigationToolbar2QT(
            self._canvas, parent=self
        )
        self._toolbar.setStyleSheet(
            f"""
            QToolBar {{
                background-color: {AppStyles.Colors.GROUPBOX_BG};
                border: none;
                spacing: 4px;
                padding: 2px;
                color: {AppStyles.Colors.TEXT_PRIMARY};
            }}
            QLabel {{
                color: {AppStyles.Colors.TEXT_PRIMARY};
            }}
            QToolButton {{
                background-color: {AppStyles.Colors.BUTTON_BG};
                border: 1px solid {AppStyles.Colors.INPUT_BORDER};
                border-radius: {AppStyles.Dimensions.BORDER_RADIUS_SMALL};
                padding: 4px;
                color: {AppStyles.Colors.TEXT_PRIMARY};
            }}
            QToolButton:hover {{
                background-color: {AppStyles.Colors.BUTTON_HOVER};
            }}
            QToolButton:checked {{
                background-color: {AppStyles.Colors.BUTTON_PRESSED};
                border: 1px solid {AppStyles.Colors.BUTTON_HOVER};
            }}
            """
        )
        _recolor_toolbar_icons(self._toolbar)

        # Navigation buttons (NoFocus prevents scroll-on-click)
        self._prev_button = PreviousButton(parent=self)
        self._prev_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._next_button = NextButton(parent=self)
        self._next_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def _setup_layout(self):
        """Arrange widgets in a two-column layout."""
        # -- Left column --
        left_column = QVBoxLayout()
        left_column.setContentsMargins(0, 0, 0, 0)
        left_column.setSpacing(AppStyles.Dimensions.LAYOUT_VSPACING)
        left_column.addWidget(self._directory_combobox)
        left_column.addWidget(self._meta_panel, 1)

        left_container = QWidget()
        left_container.setLayout(left_column)
        left_container.setMinimumWidth(
            AppStyles.Dimensions.IMAGE_VIEWER_COMBOBOX_WIDTH
        )

        # -- Right column --
        # Name row: image name (left) + show graphics + counter (right)
        name_row = QHBoxLayout()
        name_row.setContentsMargins(0, 0, 0, 0)
        name_row.setSpacing(AppStyles.Dimensions.LAYOUT_VSPACING)
        name_row.addWidget(self._image_name_label, 1)
        name_row.addWidget(self._show_graphics_checkbox)
        name_row.addWidget(self._image_counter_label)

        # Button row: both buttons stretch to fill
        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.setSpacing(AppStyles.Dimensions.LAYOUT_VSPACING)
        button_row.addWidget(self._prev_button, 1)
        button_row.addWidget(self._next_button, 1)

        right_column = QVBoxLayout()
        right_column.setContentsMargins(0, 0, 0, 0)
        right_column.setSpacing(AppStyles.Dimensions.LAYOUT_VSPACING)
        right_column.addLayout(name_row)
        right_column.addWidget(self._toolbar)
        right_column.addWidget(self._info_label)
        right_column.addWidget(self._canvas, 1)
        right_column.addLayout(button_row)

        right_container = QWidget()
        right_container.setLayout(right_column)

        # -- Main layout --
        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(AppStyles.Dimensions.LAYOUT_VSPACING)
        content_layout.addWidget(left_container)
        content_layout.addWidget(right_container, 1)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(
            AppStyles.Dimensions.LAYOUT_CONTENTS_MARGIN,
            AppStyles.Dimensions.LAYOUT_CONTENTS_MARGIN,
            AppStyles.Dimensions.LAYOUT_CONTENTS_MARGIN,
            AppStyles.Dimensions.LAYOUT_CONTENTS_MARGIN,
        )
        main_layout.setSpacing(AppStyles.Dimensions.LAYOUT_VSPACING)
        main_layout.addLayout(content_layout, 1)
        self.setStyleSheet(AppStyles.GroupBox.with_title_bold())

        # Reserve the populated height so the groupbox does not
        # visibly jump when an image directory is first selected.
        self.setMinimumHeight(
            AppStyles.Dimensions.IMAGE_VIEWER_GROUPBOX_MINIMUM_HEIGHT
        )

    def _connect_signals(self):
        """Connect widget signals."""
        self._directory_combobox.activated.connect(
            self._on_directory_selected
        )
        self._prev_button.clicked.connect(self._on_previous)
        self._next_button.clicked.connect(self._on_next)
        self._show_graphics_checkbox.toggled.connect(
            self._on_show_graphics_toggled
        )

    # -----------------------------------------------------------------
    # Directory Selection
    # -----------------------------------------------------------------

    @Slot(int)
    def _on_directory_selected(self, index: int):
        """Handle directory combo box selection.

        Builds the list of absolute image paths for the selected
        directory and displays the first image.

        :param index: Selected combo box index.
        """
        if index < 0 or index >= len(self._image_directories):
            return

        directory = self._image_directories[index]
        relative_paths = directory.get("RelativeImagePaths", [])

        # Resolve to absolute paths
        self._current_image_paths.clear()
        if self._project_root is not None:
            for rel_path in relative_paths:
                # Handle both forward and backslash separators
                abs_path = self._project_root / Path(
                    rel_path.replace("\\", "/")
                )
                self._current_image_paths.append(abs_path)

        if self._current_image_paths:
            self._current_index = 0
            self._display_current_image()
            self._info_label.setVisible(False)
        else:
            self._current_index = -1
            self._clear_canvas()
            if self._project_root is None:
                self._info_label.setText(
                    "No project directory available"
                )
            else:
                self._info_label.setText("No images in directory")
            self._info_label.setVisible(True)

        self._update_nav_button_states()

        dir_name = directory.get("DirectoryName", "Unknown")
        logger.info(
            f"Directory selected: '{dir_name}' "
            f"({len(self._current_image_paths)} images)"
        )

    # -----------------------------------------------------------------
    # Previous / Next Navigation
    # -----------------------------------------------------------------

    @Slot()
    def _on_previous(self):
        """Navigate to the previous image, wrapping to the end."""
        if not self._current_image_paths:
            return
        if self._current_index <= 0:
            self._current_index = len(self._current_image_paths) - 1
        else:
            self._current_index -= 1
        self._display_current_image()

    @Slot()
    def _on_next(self):
        """Navigate to the next image, wrapping to the beginning."""
        if not self._current_image_paths:
            return
        if self._current_index >= len(self._current_image_paths) - 1:
            self._current_index = 0
        else:
            self._current_index += 1
        self._display_current_image()

    def _update_nav_button_states(self):
        """Enable Previous and Next when images are available."""
        has_images = len(self._current_image_paths) > 0
        self._prev_button.setEnabled(has_images)
        self._next_button.setEnabled(has_images)

    # -----------------------------------------------------------------
    # Image Display
    # -----------------------------------------------------------------

    def _display_current_image(self):
        """Load and render the current image on the canvas."""
        if (
            self._current_index < 0
            or self._current_index >= len(self._current_image_paths)
        ):
            self._clear_canvas()
            self._clear_metadata()
            return

        image_path = self._current_image_paths[self._current_index]

        # Update labels
        self._image_name_label.setText(image_path.name)
        self._image_counter_label.setText(
            f"{self._current_index + 1} / "
            f"{len(self._current_image_paths)}"
        )

        # Update metadata tree and extract overlay data
        self._populate_metadata(image_path)

        # Clear and prepare axes
        self._ax.clear()
        _style_axes_dark(self._ax)

        if not image_path.is_file():
            self._ax.text(
                0.5, 0.5,
                "Image file not found",
                ha="center", va="center",
                color=AppStyles.Colors.TEXT_DISABLED,
                fontsize=10,
                transform=self._ax.transAxes,
            )
            self._canvas.draw_idle()
            return

        img = load_image(image_path, max_dim=_THUMBNAIL_MAX_DIM)
        if img is None:
            self._ax.text(
                0.5, 0.5,
                "Failed to load image",
                ha="center", va="center",
                color=AppStyles.Colors.TEXT_DISABLED,
                fontsize=10,
                transform=self._ax.transAxes,
            )
            self._canvas.draw_idle()
            return

        # Track the downsample factor for overlay coordinate
        # scaling.  _load_image uses stride-based downsampling.
        if img.ndim >= 2:
            h, w = img.shape[:2]
            orig_w = (
                self._overlay_data.get("image_width", w)
                if self._overlay_data
                else w
            )
            self._downsample_factor = max(1, orig_w // w)
        else:
            self._downsample_factor = 1

        cmap = "gray" if img.ndim == 2 else None
        self._ax.imshow(img, cmap=cmap, aspect="equal")

        if self._show_graphics_checkbox.isChecked():
            self._draw_overlay()

        self._canvas.draw_idle()

        logger.debug(
            f"Image displayed: {image_path.name} "
            f"({img.shape})"
        )

    def _clear_canvas(self):
        """Clear the image canvas."""
        self._ax.clear()
        _style_axes_dark(self._ax)
        self._canvas.draw_idle()
        self._image_name_label.setText("")
        self._image_counter_label.setText("")

    # -----------------------------------------------------------------
    # Graphics Overlay
    # -----------------------------------------------------------------

    @staticmethod
    def _extract_overlay_data(metadata: dict) -> dict | None:
        """Extract crosshair data from metadata.

        Returns a dict with the fields needed by ``_draw_overlay``,
        or *None* if the minimum required data is not present.

        Required:

        - ``PatternCenterPositionPx`` X/Y from
          ``MatchInformationCollection``

        Optional:

        - ``ImageSize`` from ``BinaryResult`` (for downsample
          scaling)

        :param metadata: Full metadata dict from
            ``extract_image_metadata``.
        :return: Overlay dict or *None*.
        """
        xml = metadata.get("XMLMetadata")
        if not xml:
            return None

        # -- PatternCenterPositionPx (required) ----------------------
        custom_sections = (
            xml
            .get("CustomSectionGroup", {})
            .get("CustomSection", {})
        )
        if not isinstance(custom_sections, dict):
            return None

        match_col = custom_sections.get(
            "MatchInformationCollection", {}
        )
        match_info = match_col.get("MatchInformation", {})
        # Multiple match attempts produce a list; use the first
        # entry to match the atlas widget's behavior.
        if isinstance(match_info, list):
            match_info = match_info[0] if match_info else {}
        if not isinstance(match_info, dict):
            return None
        pattern_center = match_info.get(
            "PatternCenterPositionPx", {}
        )
        center_x = pattern_center.get("X")
        center_y = pattern_center.get("Y")

        if center_x is None or center_y is None:
            return None

        try:
            center_x = float(center_x)
            center_y = float(center_y)
        except (TypeError, ValueError):
            return None

        result: dict = {
            "center_px": (center_x, center_y),
        }

        # -- Image dimensions from BinaryResult ----------------------
        binary_result = xml.get("BinaryResult", {})
        image_size = binary_result.get("ImageSize", {})
        img_w = image_size.get("X")
        img_h = image_size.get("Y")
        if img_w is not None and img_h is not None:
            try:
                result["image_width"] = int(img_w)
                result["image_height"] = int(img_h)
            except (TypeError, ValueError):
                pass

        return result

    def _draw_overlay(self):
        """Draw a crosshair at the pattern match center.

        Uses ``self._overlay_data`` and ``self._downsample_factor``
        which must be set before calling.
        """
        if not self._overlay_data:
            return

        factor = self._downsample_factor
        cx, cy = self._overlay_data["center_px"]

        # Scale to displayed coordinates
        cx_d = cx / factor
        cy_d = cy / factor

        # Crosshair
        self._ax.axhline(
            y=cy_d, color=AppStyles.Colors.IMAGE_VIEWER_CROSSHAIR_COLOR,
            linewidth=0.5, linestyle="--", alpha=0.7,
        )
        self._ax.axvline(
            x=cx_d, color=AppStyles.Colors.IMAGE_VIEWER_CROSSHAIR_COLOR,
            linewidth=0.5, linestyle="--", alpha=0.7,
        )
        self._ax.plot(
            cx_d, cy_d, marker="+", color=AppStyles.Colors.IMAGE_VIEWER_CROSSHAIR_COLOR,
            markersize=12, markeredgewidth=1.5, alpha=0.9,
        )

    @Slot(bool)
    def _on_show_graphics_toggled(self, _checked: bool):
        """Redraw the current image with or without the overlay."""
        self._display_current_image()

    # -----------------------------------------------------------------
    # Metadata Tree
    # -----------------------------------------------------------------

    def _populate_metadata(self, image_path: Path):
        """Extract and display metadata for the current image.

        Also extracts overlay data for the graphics checkbox.

        :param image_path: Absolute path to the image file.
        """
        if not image_path.is_file():
            self._clear_metadata()
            return

        try:
            metadata = extract_image_metadata(image_path)
        except Exception:
            logger.error(
                f"Failed to extract metadata: {image_path.name}",
                exc_info=True,
            )
            self._clear_metadata()
            return

        self._meta_panel.setVisible(True)
        self._meta_panel.populate(metadata)

        # Extract overlay data and update checkbox state
        self._overlay_data = self._extract_overlay_data(metadata)
        self._show_graphics_checkbox.setEnabled(
            self._overlay_data is not None
        )

    def _clear_metadata(self):
        """Reset the metadata tree to empty."""
        self._meta_panel.clear_tree()
        self._meta_panel.setVisible(False)
        self._overlay_data = None
        self._show_graphics_checkbox.setEnabled(False)