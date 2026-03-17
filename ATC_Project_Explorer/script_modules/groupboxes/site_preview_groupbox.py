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

Both images are displayed as simple thumbnails with no
matplotlib toolbar.  File names are shown as tooltips on
hover.  A centred "Image not available" placeholder is
shown when the target image cannot be found or loaded.

Each preview image is clickable: hovering shows a subtle
border and a pointing-hand cursor; clicking emits the
:attr:`~SitePreviewGroupBox.preview_clicked` signal with
the source directory name and file name so the parent panel
can scroll to and select the image in the full image viewer.
"""
import logging
from pathlib import Path

import numpy as np
import matplotlib.image as mpimg
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from PySide6.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QFrame,
    QSizePolicy,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCursor
from script_modules.app_styles import AppStyles


logger = logging.getLogger(__name__)


# Preview thumbnail max dimension (pixels)
_PREVIEW_MAX_DIM = 512

# Placeholder text
_PLACEHOLDER = "Image not available"


# -----------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------

def _load_preview(path: Path) -> np.ndarray | None:
    """Load an image for preview display.

    Handles JPEG files saved with a ``.png`` extension by
    falling back to PIL when matplotlib's reader fails.

    :param path: Absolute path to the image file.
    :return: Numpy array downsampled to ``_PREVIEW_MAX_DIM``,
        or *None* on failure.
    """
    try:
        img = mpimg.imread(str(path))
    except Exception:
        try:
            from PIL import Image
            img = np.array(Image.open(path))
        except Exception:
            logger.debug(
                f"Failed to read preview image: {path.name}",
                exc_info=True,
            )
            return None

    if img.ndim >= 2:
        h, w = img.shape[:2]
        factor = max(1, max(h, w) // _PREVIEW_MAX_DIM)
        if factor > 1:
            img = img[::factor, ::factor]

    return img


def _style_preview_axes(ax):
    """Apply dark theme to a preview axes."""
    ax.set_facecolor(AppStyles.Colors.MAIN_BG)
    ax.set_axis_off()


# -----------------------------------------------------------------
# Clickable Preview Frame
# -----------------------------------------------------------------

class _ClickablePreviewFrame(QFrame):
    """QFrame wrapper that adds hover border and click detection
    to a preview canvas.

    When ``clickable`` is True, entering the frame shows a
    subtle border and switches to a pointing-hand cursor.
    Leaving restores the default appearance.
    """

    def __init__(self, canvas: FigureCanvasQTAgg, parent=None):
        super().__init__(parent)
        self._canvas = canvas
        self._clickable = False
        self._default_cursor = self.cursor()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(0)
        layout.addWidget(canvas)

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

        left_path, left_dir = self._find_left_image(directories)
        right_path, right_dir = self._find_right_image(directories)

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

        self._show_image(
            self._left_ax, self._left_canvas, left_path,
        )
        self._show_image(
            self._right_ax, self._right_canvas, right_path,
        )

        # Enable click interaction when an image is loaded
        self._left_frame.set_clickable(left_path is not None)
        self._right_frame.set_clickable(right_path is not None)

        self._left_canvas.draw_idle()
        self._right_canvas.draw_idle()

    def clear(self) -> None:
        """Reset both preview panels to empty."""
        for ax, canvas in [
            (self._left_ax, self._left_canvas),
            (self._right_ax, self._right_canvas),
        ]:
            ax.clear()
            _style_preview_axes(ax)
            canvas.setToolTip("")

        self._left_frame.set_clickable(False)
        self._right_frame.set_clickable(False)
        self._left_dir_name = ""
        self._left_filename = ""
        self._right_dir_name = ""
        self._right_filename = ""

        self._left_canvas.draw_idle()
        self._right_canvas.draw_idle()

    # -----------------------------------------------------------------
    # Setup
    # -----------------------------------------------------------------

    def _create_widgets(self):
        """Create the two preview canvases."""
        _canvas_style = f"""
            background-color: {AppStyles.Colors.MAIN_BG};
        """

        # Left preview (electron)
        self._left_figure = Figure(
            facecolor=AppStyles.Colors.MAIN_BG,
            constrained_layout=True,
        )
        self._left_canvas = FigureCanvasQTAgg(self._left_figure)
        self._left_canvas.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Ignored,
        )
        self._left_ax = self._left_figure.add_subplot(111)
        _style_preview_axes(self._left_ax)
        self._left_canvas.setStyleSheet(_canvas_style)

        # Right preview (polishing)
        self._right_figure = Figure(
            facecolor=AppStyles.Colors.MAIN_BG,
            constrained_layout=True,
        )
        self._right_canvas = FigureCanvasQTAgg(self._right_figure)
        self._right_canvas.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Ignored,
        )
        self._right_ax = self._right_figure.add_subplot(111)
        _style_preview_axes(self._right_ax)
        self._right_canvas.setStyleSheet(_canvas_style)

        # Wrap each canvas in a clickable frame for hover
        # border and click-to-navigate behaviour.
        self._left_frame = _ClickablePreviewFrame(
            self._left_canvas, parent=self
        )
        self._right_frame = _ClickablePreviewFrame(
            self._right_canvas, parent=self
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
        """Connect matplotlib click events on both canvases."""
        self._left_canvas.mpl_connect(
            "button_press_event", self._on_left_clicked
        )
        self._right_canvas.mpl_connect(
            "button_press_event", self._on_right_clicked
        )

    def _on_left_clicked(self, event):
        """Handle click on the left preview canvas.

        :param event: Matplotlib button_press_event.
        """
        if (
            event.button != 1
            or not self._left_dir_name
            or not self._left_filename
        ):
            return
        logger.info(
            f"Preview click: '{self._left_filename}' "
            f"in '{self._left_dir_name}'"
        )
        self.preview_clicked.emit(
            self._left_dir_name, self._left_filename
        )

    def _on_right_clicked(self, event):
        """Handle click on the right preview canvas.

        :param event: Matplotlib button_press_event.
        """
        if (
            event.button != 1
            or not self._right_dir_name
            or not self._right_filename
        ):
            return
        logger.info(
            f"Preview click: '{self._right_filename}' "
            f"in '{self._right_dir_name}'"
        )
        self.preview_clicked.emit(
            self._right_dir_name, self._right_filename
        )

    # -----------------------------------------------------------------
    # Image Selection
    # -----------------------------------------------------------------

    def _find_left_image(
        self, directories: list[dict]
    ) -> tuple[Path | None, str]:
        """Find the left preview image path.

        Prefers the last image from ``LamellaEvaluationImages``.
        Falls back to the last electron match image from
        ``PrecisePositioningLogImages``.

        :param directories: Site's ImageDirectories list.
        :return: Tuple of (absolute image path or *None*, source
            directory name).
        """
        # Try LamellaEvaluationImages first
        dir_name = "LamellaEvaluationImages"
        path = self._last_image_in_directory(
            directories, dir_name
        )
        if path is not None:
            logger.debug(
                f"Left preview: using LamellaEvaluationImages"
            )
            return path, dir_name

        # Fallback: last electron image from positioning log
        dir_name = "PrecisePositioningLogImages"
        logger.debug(
            "Left preview: LamellaEvaluationImages unavailable, "
            "falling back to PrecisePositioningLogImages"
        )
        return self._last_matching_image(
            directories,
            dir_name,
            "electron",
        ), dir_name

    def _find_right_image(
        self, directories: list[dict]
    ) -> tuple[Path | None, str]:
        """Find the right preview image path.

        Returns the last polishing match image (excluding electron
        images) from ``PrecisePositioningLogImages``.

        :param directories: Site's ImageDirectories list.
        :return: Tuple of (absolute image path or *None*, source
            directory name).
        """
        dir_name = "PrecisePositioningLogImages"
        return self._last_matching_image(
            directories,
            dir_name,
            "polishing",
            exclude="electron",
        ), dir_name

    def _last_image_in_directory(
        self,
        directories: list[dict],
        dir_name: str,
    ) -> Path | None:
        """Return the last image path from a named directory.

        :param directories: Site's ImageDirectories list.
        :param dir_name: Directory name to search for
            (case-insensitive).
        :return: Absolute path, or *None* if not found.
        """
        for directory in directories:
            name = directory.get("DirectoryName", "")
            if name.lower() != dir_name.lower():
                continue
            paths = directory.get("RelativeImagePaths", [])
            if not paths:
                logger.debug(
                    f"No images in directory '{dir_name}'"
                )
                return None
            if self._project_root is None:
                logger.debug(
                    "Project root not set — cannot resolve "
                    f"'{dir_name}' image paths"
                )
                return None
            rel = paths[-1].replace("\\", "/")
            abs_path = self._project_root / Path(rel)
            if abs_path.is_file():
                return abs_path
            logger.debug(
                f"Preview file not found: {abs_path}"
            )
        return None

    def _last_matching_image(
        self,
        directories: list[dict],
        dir_name: str,
        keyword: str,
        exclude: str = "",
    ) -> Path | None:
        """Return the last image whose name contains *keyword*
        from the named directory.

        :param directories: Site's ImageDirectories list.
        :param dir_name: Directory name to search for
            (case-insensitive).
        :param keyword: Substring to match in file names
            (case-insensitive).
        :param exclude: Substring to reject from file names
            (case-insensitive).  Empty string disables exclusion.
        :return: Absolute path, or *None* if not found.
        """
        for directory in directories:
            name = directory.get("DirectoryName", "")
            if name.lower() != dir_name.lower():
                continue
            paths = directory.get("RelativeImagePaths", [])
            keyword_lower = keyword.lower()
            exclude_lower = exclude.lower()
            matches = [
                p for p in paths
                if keyword_lower in Path(p).name.lower()
                and (
                    not exclude_lower
                    or exclude_lower not in Path(p).name.lower()
                )
            ]
            if matches and self._project_root is not None:
                rel = matches[-1].replace("\\", "/")
                abs_path = self._project_root / Path(rel)
                if abs_path.is_file():
                    return abs_path
        return None

    # -----------------------------------------------------------------
    # Display
    # -----------------------------------------------------------------

    def _show_image(
        self,
        ax,
        canvas: FigureCanvasQTAgg,
        image_path: Path | None,
    ):
        """Load and display a preview image, or show a placeholder.

        The file name is placed in the canvas tooltip so the user
        can hover to identify the image without consuming layout
        space.

        :param ax: Matplotlib axes to render into.
        :param canvas: The canvas widget (for tooltip).
        :param image_path: Absolute path, or *None*.
        """
        ax.clear()
        _style_preview_axes(ax)

        if image_path is None:
            ax.text(
                0.5, 0.5, _PLACEHOLDER,
                ha="center", va="center",
                color=AppStyles.Colors.TEXT_DISABLED,
                fontsize=10,
                transform=ax.transAxes,
            )
            canvas.setToolTip("")
            return

        img = _load_preview(image_path)
        if img is None:
            ax.text(
                0.5, 0.5, _PLACEHOLDER,
                ha="center", va="center",
                color=AppStyles.Colors.TEXT_DISABLED,
                fontsize=10,
                transform=ax.transAxes,
            )
            canvas.setToolTip("")
            return

        cmap = "gray" if img.ndim == 2 else None
        ax.imshow(img, cmap=cmap, aspect="equal")
        canvas.setToolTip(image_path.name)