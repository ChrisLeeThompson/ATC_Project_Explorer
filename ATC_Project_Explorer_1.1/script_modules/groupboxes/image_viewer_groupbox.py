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

Graphics Overlay
~~~~~~~~~~~~~~~~

When **Show Graphics** is checked the viewer draws:

1. A **crosshair** at the ``PatternCenterPositionPx`` from the
   ``MatchInformationCollection`` metadata.
2. **Pattern rectangle outlines** from ``PatterningInformation``
   when pixel size data is available.  The coordinate origin
   depends on the activity type:

   - *Stress Relief Cuts*: rectangles are positioned relative
     to the match centre (``PatternCenterPositionPx``).
   - *All other activities* (Rough Milling, polishing, etc.):
     rectangles are positioned relative to the image centre.

   The ``<Center><X>`` metadata value points to the pattern's
   anchor point; it is adjusted to the geometric centre using
   the ``AnchorPoint`` field before drawing.  The Y axis is
   negated (physical positive-up → image positive-down).
"""
import logging
import re
from pathlib import Path

from matplotlib.backends.backend_qtagg import (
    FigureCanvasQTAgg,
    NavigationToolbar2QT,
)
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle as MplRectangle

from PySide6.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QSplitter, QWidget,
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
# Pattern Overlay Helpers
# -----------------------------------------------------------------

# Unit-string-to-metres conversion factors
_UNIT_TO_METRES: dict[str, float] = {
    "nm": 1e-9,
    "µm": 1e-6,       # Latin-1 micro sign (0xB5)
    "\u00b5m": 1e-6,   # explicit micro sign codepoint
    "\u03bcm": 1e-6,   # Greek lowercase mu
    "um": 1e-6,        # ASCII fallback
    "mm": 1e-3,
    "m": 1.0,
}

# Regex for splitting "value unit" strings (e.g. "-192.585 nm")
_VALUE_UNIT_RE = re.compile(
    r"([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\s*(.*)"
)


def _parse_unit_value(raw) -> tuple[float, str] | None:
    """Parse a value+unit string into ``(numeric_value, unit_str)``.

    Handles strings like ``"-192.58 nm"``, ``"17 µm"``,
    ``"-180 °"``.  Also handles bare numeric values (int/float)
    and dicts with a ``"_text"`` key (from XML attribute nodes).

    :param raw: String, int, float, or dict with ``"_text"`` key.
    :return: ``(value, unit)`` tuple or *None*.
    """
    if isinstance(raw, (int, float)):
        return float(raw), ""
    if isinstance(raw, dict):
        raw = raw.get("_text", "")
    if not isinstance(raw, str) or not raw.strip():
        return None
    match = _VALUE_UNIT_RE.match(raw.strip())
    if match:
        return float(match.group(1)), match.group(2).strip()
    return None


def _to_metres(raw) -> float | None:
    """Parse a value+unit string and convert to metres.

    :param raw: Value string (e.g. ``"-6.18 µm"``).
    :return: Value in metres, or *None* if the unit is not
        recognised or the string cannot be parsed.
    """
    parsed = _parse_unit_value(raw)
    if parsed is None:
        return None
    value, unit = parsed
    factor = _UNIT_TO_METRES.get(unit)
    if factor is None:
        return None
    return value * factor


def _extract_pixel_size_val(val) -> float | None:
    """Extract a numeric value from a ``PixelSize`` child element.

    The XML parser produces either a plain float or a dict like
    ``{"unit": "m", "_text": "7.8125E-08"}`` when the element
    has XML attributes.

    :param val: PixelSize X or Y value from parsed metadata.
    :return: Value in metres, or *None*.
    """
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, dict):
        text = val.get("_text")
        if text is not None:
            try:
                return float(text)
            except (TypeError, ValueError):
                return None
    if isinstance(val, str):
        try:
            return float(val)
        except ValueError:
            return None
    return None


def _adjust_anchor_x(
    anchor_x_m: float, anchor_point: str, width_m: float,
) -> float:
    """Adjust pattern X from anchor point to geometric centre.

    The metadata ``<Center><X>`` value points to the anchor
    point of the pattern.  This converts to the geometric
    centre X coordinate for drawing.

    :param anchor_x_m: X coordinate at the anchor (metres).
    :param anchor_point: ``AnchorPoint`` string from metadata
        (e.g. ``"BottomCenter"``, ``"TopRight"``).
    :param width_m: Pattern width (metres).
    :return: Geometric centre X in metres.
    """
    ap = anchor_point.lower()
    if "right" in ap:
        return anchor_x_m - width_m / 2
    elif "left" in ap:
        return anchor_x_m + width_m / 2
    # Centre-aligned anchors (BottomCenter, TopCenter, etc.)
    return anchor_x_m


def _parse_pattern_rectangles(
    raw_rects: list[dict],
) -> list[dict]:
    """Parse ``PatternDrawingRectangle`` entries into
    overlay-ready dicts with values in metres and degrees.

    Each output dict contains:

    - ``center_x_m``, ``center_y_m`` — anchor position (metres)
    - ``width_m``, ``height_m`` — rectangle size (metres)
    - ``rotation_deg`` — rotation angle (degrees)
    - ``anchor_point`` — anchor string for X adjustment

    :param raw_rects: List of raw rectangle dicts from the
        parsed XML metadata.
    :return: List of parsed rectangle dicts.  Entries that
        cannot be parsed are silently skipped.
    """
    result: list[dict] = []
    for raw in raw_rects:
        if not isinstance(raw, dict):
            continue

        center = raw.get("Center", {})
        center_x_m = _to_metres(center.get("X"))
        center_y_m = _to_metres(center.get("Y"))
        if center_x_m is None or center_y_m is None:
            continue

        size = raw.get("Size", {})
        width_m = _to_metres(size.get("Width"))
        height_m = _to_metres(size.get("Height"))
        if width_m is None or height_m is None:
            continue

        rotation_parsed = _parse_unit_value(
            raw.get("Rotation", "0")
        )
        rotation_deg = (
            rotation_parsed[0] if rotation_parsed else 0.0
        )

        anchor_point = raw.get("AnchorPoint", "")

        result.append({
            "center_x_m": center_x_m,
            "center_y_m": center_y_m,
            "width_m": abs(width_m),
            "height_m": abs(height_m),
            "rotation_deg": rotation_deg,
            "anchor_point": anchor_point,
        })

    return result


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
        self._preserved_view: tuple | None = None

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
        self._preserved_view = None
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
        self._splitter = QSplitter(Qt.Orientation.Horizontal, parent=self)
        self._splitter.setHandleWidth(
            AppStyles.Dimensions.SPLITTER_HANDLE_WIDTH
        )
        self._splitter.setStyleSheet(AppStyles.Splitter.horizontal())
        self._splitter.addWidget(left_container)
        self._splitter.addWidget(right_container)
        self._splitter.setStretchFactor(0, 0)  # left: don't absorb resize
        self._splitter.setStretchFactor(1, 1)  # right: absorbs resize

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(
            AppStyles.Dimensions.LAYOUT_CONTENTS_MARGIN,
            AppStyles.Dimensions.LAYOUT_CONTENTS_MARGIN,
            AppStyles.Dimensions.LAYOUT_CONTENTS_MARGIN,
            AppStyles.Dimensions.LAYOUT_CONTENTS_MARGIN,
        )
        main_layout.setSpacing(AppStyles.Dimensions.LAYOUT_VSPACING)
        main_layout.addWidget(self._splitter, 1)
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

        # Reset zoom/pan when switching directories
        self._preserved_view = None

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
        self._save_view()
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
        self._save_view()
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
    # View Preservation
    # -----------------------------------------------------------------

    def _save_view(self):
        """Capture the current zoom/pan state so it can be restored
        after the next image is drawn.

        Only saves when the axes contain an image (i.e. the user
        has zoomed or panned an actual image, not an empty canvas).
        """
        if not self._ax.images:
            return
        self._preserved_view = (
            self._ax.get_xlim(),
            self._ax.get_ylim(),
        )

    def _restore_view(self):
        """Reapply a previously saved zoom/pan state, then clear it.

        Called at the end of ``_display_current_image`` so that
        Previous/Next navigation preserves the user's zoom level
        and position across images in the same directory.
        """
        if self._preserved_view is None:
            return
        xlim, ylim = self._preserved_view
        self._ax.set_xlim(xlim)
        self._ax.set_ylim(ylim)
        self._preserved_view = None

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

        # Restore zoom/pan state if preserved by Previous/Next
        self._restore_view()

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
        """Extract overlay data from image metadata.

        Returns a dict with the fields needed by ``_draw_overlay``,
        or *None* if the minimum required data is not present.

        Required:

        - ``PatternCenterPositionPx`` X/Y from
          ``MatchInformationCollection``

        Optional:

        - ``ImageSize`` from ``BinaryResult`` (for downsample
          scaling and pattern origin)
        - ``PixelSize`` from ``BinaryResult`` (for converting
          physical pattern coordinates to pixels)
        - ``PatterningInformation`` rectangles from
          ``CustomSectionGroup``
        - ``ActivityName`` from ``ProgressInformation`` (to
          determine the pattern coordinate origin)

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

        # -- PixelSize from BinaryResult -----------------------------
        pixel_size = binary_result.get("PixelSize", {})
        if isinstance(pixel_size, dict):
            px_x = _extract_pixel_size_val(pixel_size.get("X"))
            px_y = _extract_pixel_size_val(pixel_size.get("Y"))
            if px_x is not None and px_y is not None:
                result["pixel_size_x_m"] = px_x
                result["pixel_size_y_m"] = px_y

        # -- ActivityName from ProgressInformation -------------------
        progress_info = custom_sections.get(
            "ProgressInformation", {}
        )
        activity_name = progress_info.get("ActivityName", "")
        if isinstance(activity_name, str):
            result["activity_name"] = activity_name

        # -- PatterningInformation rectangles ------------------------
        patterning_info = custom_sections.get(
            "PatterningInformation", {}
        )
        if isinstance(patterning_info, dict):
            raw_rects = patterning_info.get(
                "PatternDrawingRectangle"
            )
            if raw_rects is not None:
                # Normalise to list (single rect is a dict,
                # multiple rects produce a list)
                if isinstance(raw_rects, dict):
                    raw_rects = [raw_rects]
                if isinstance(raw_rects, list):
                    parsed = _parse_pattern_rectangles(raw_rects)
                    if parsed:
                        result["pattern_rectangles"] = parsed

        return result

    def _draw_overlay(self):
        """Draw overlay graphics on the image.

        Renders the crosshair at the pattern match centre and,
        when patterning data and pixel size are available, draws
        milling pattern rectangle outlines.

        Uses ``self._overlay_data`` and ``self._downsample_factor``
        which must be set before calling.
        """
        if not self._overlay_data:
            return

        factor = self._downsample_factor
        cx, cy = self._overlay_data["center_px"]
        color = AppStyles.Colors.IMAGE_VIEWER_CROSSHAIR_COLOR

        # Scale to displayed coordinates
        cx_d = cx / factor
        cy_d = cy / factor

        # Crosshair
        self._ax.axhline(
            y=cy_d, color=color,
            linewidth=0.5, linestyle="--", alpha=0.7,
        )
        self._ax.axvline(
            x=cx_d, color=color,
            linewidth=0.5, linestyle="--", alpha=0.7,
        )
        self._ax.plot(
            cx_d, cy_d, marker="+", color=color,
            markersize=12, markeredgewidth=1.5, alpha=0.9,
        )

        # Pattern rectangles
        self._draw_pattern_rectangles()

    def _draw_pattern_rectangles(self):
        """Draw patterning rectangle outlines on the image.

        Requires ``pixel_size_x_m`` and ``pixel_size_y_m`` in
        the overlay data to convert physical coordinates to
        pixels.  The coordinate origin depends on the activity:

        - **Stress Relief Cuts**: origin =
          ``PatternCenterPositionPx`` (match position).
        - **All other activities**: origin = image centre
          (``ImageSize / 2``).

        The ``PatterningInformation`` coordinates are already
        expressed in the image coordinate system for X, but the
        Y axis uses the physical convention (positive = up) and
        must be negated to match image pixels (positive = down).

        The ``<Center><X>`` value from the metadata points to
        the pattern's anchor point rather than the geometric
        centre.  The X coordinate is adjusted based on the
        ``AnchorPoint`` field before drawing.  The Y coordinate
        is always the geometric centre of the pattern.

        Uses ``self._overlay_data`` and
        ``self._downsample_factor``.
        """
        overlay = self._overlay_data
        if not overlay:
            return

        rects = overlay.get("pattern_rectangles")
        if not rects:
            return

        px_x = overlay.get("pixel_size_x_m")
        px_y = overlay.get("pixel_size_y_m")
        if px_x is None or px_y is None:
            return

        factor = self._downsample_factor
        color = AppStyles.Colors.IMAGE_VIEWER_CROSSHAIR_COLOR

        # Determine coordinate origin based on activity type
        activity = overlay.get("activity_name", "")
        is_stress_relief = "stress relief" in activity.lower()

        if is_stress_relief:
            # Stress relief: origin = match centre
            origin_x, origin_y = overlay["center_px"]
        else:
            # Regular milling / polishing: origin = image centre
            img_w = overlay.get("image_width")
            img_h = overlay.get("image_height")
            if img_w is None or img_h is None:
                return
            origin_x = img_w / 2
            origin_y = img_h / 2

        for rect in rects:
            # Adjust X from anchor point to geometric centre
            cx_m = _adjust_anchor_x(
                rect["center_x_m"],
                rect["anchor_point"],
                rect["width_m"],
            )
            cy_m = rect["center_y_m"]

            # Convert physical position to pixel coordinates.
            # X: positive = right in both coordinate systems.
            # Y: negated because the Site coordinate system is
            #    positive-up while image pixels are positive-down.
            cx_px = origin_x + (cx_m / px_x)
            cy_px = origin_y - (cy_m / px_y)

            # Convert physical dimensions to pixels
            w_px = rect["width_m"] / px_x
            h_px = rect["height_m"] / px_y

            # Scale to displayed coordinates
            cx_d = cx_px / factor
            cy_d = cy_px / factor
            w_d = w_px / factor
            h_d = h_px / factor

            # matplotlib Rectangle takes the lower-left corner
            x0 = cx_d - w_d / 2
            y0 = cy_d - h_d / 2

            patch = MplRectangle(
                (x0, y0), w_d, h_d,
                edgecolor=color,
                facecolor="none",
                linewidth=1.0,
                linestyle="-",
                alpha=0.7,
            )
            self._ax.add_patch(patch)

    @Slot(bool)
    def _on_show_graphics_toggled(self, _checked: bool):
        """Redraw the current image with or without the overlay."""
        self._save_view()
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