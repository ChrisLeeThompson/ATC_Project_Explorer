"""
Preview Image Helpers

Shared utilities for finding and loading lamella preview
images.  Used by both ``SitePreviewGroupBox`` (site panel)
and ``GlobalSitePreviewGroupBox`` (global panel).

Extracted from ``site_preview_groupbox.py`` so both modules
can share image-selection logic without duplication.

Rendering uses lightweight QPixmap/QLabel rather than
matplotlib figures to keep per-thumbnail overhead minimal.
"""
import logging
from pathlib import Path

from PySide6.QtWidgets import QLabel, QSizePolicy
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap

from script_modules.app_styles import AppStyles


logger = logging.getLogger(__name__)


# -----------------------------------------------------------------
# Image Loading
# -----------------------------------------------------------------

def load_preview_pixmap(
    path: Path,
    max_dim: int = AppStyles.Dimensions.PREVIEW_MAX_DIM_DEFAULT,
) -> QPixmap | None:
    """Load an image file and return a downsampled QPixmap.

    Attempts native Qt loading first.  Falls back to PIL for
    formats Qt cannot decode (e.g. 16-bit TIFF), and handles
    JPEG files saved with a ``.png`` extension automatically
    since Qt probes file content, not the extension.

    :param path: Absolute path to the image file.
    :param max_dim: Maximum pixel dimension for downsampling.
        Defaults to :data:`PREVIEW_MAX_DIM_DEFAULT` (512).
    :return: Scaled QPixmap, or *None* on failure.
    """
    pixmap = QPixmap(str(path))

    if pixmap.isNull():
        pixmap = _load_via_pil(path)
        if pixmap is None:
            logger.debug(
                f"Failed to read preview image: {path.name}",
                exc_info=True,
            )
            return None

    # Downsample if either dimension exceeds max_dim.
    # FastTransformation (nearest-neighbour) is used here
    # because this is purely a memory-reduction step.  The
    # final display scaling in PreviewLabel._rescale applies
    # SmoothTransformation for presentation quality, so using
    # smooth here as well would double-blur the image.
    if max(pixmap.width(), pixmap.height()) > max_dim:
        pixmap = pixmap.scaled(
            max_dim,
            max_dim,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )

    return pixmap


def _load_via_pil(path: Path) -> QPixmap | None:
    """Fallback loader using PIL for images Qt cannot decode.

    Handles 16-bit grayscale TIFFs common in electron
    microscopy by normalising to 8-bit before conversion
    to QImage.

    :param path: Absolute path to the image file.
    :return: QPixmap or *None* on failure.
    """
    try:
        from PIL import Image
        import numpy as np

        img = Image.open(path)

        # Normalise 16-bit / float grayscale to 8-bit
        if img.mode in ("I", "I;16", "F"):
            arr = np.array(img, dtype=np.float64)
            lo, hi = arr.min(), arr.max()
            if hi - lo > 0:
                arr = (arr - lo) / (hi - lo) * 255.0
            else:
                arr = np.zeros_like(arr)
            img = Image.fromarray(arr.astype(np.uint8), mode="L")

        # Convert to RGB or RGBA for QImage
        if img.mode == "L":
            img = img.convert("RGB")
        elif img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGBA")

        data = img.tobytes()
        if img.mode == "RGBA":
            fmt = QImage.Format.Format_RGBA8888
            stride = img.width * 4
        else:
            fmt = QImage.Format.Format_RGB888
            stride = img.width * 3

        qimage = QImage(data, img.width, img.height, stride, fmt)
        # .copy() ensures the QImage owns its data after
        # the PIL byte buffer goes out of scope.
        pixmap = QPixmap.fromImage(qimage.copy())
        if pixmap.isNull():
            return None
        return pixmap
    except Exception:
        logger.debug(
            f"PIL fallback failed for: {path.name}",
            exc_info=True,
        )
        return None


# -----------------------------------------------------------------
# Preview Label
# -----------------------------------------------------------------

class PreviewLabel(QLabel):
    """QLabel that displays a preview thumbnail with
    aspect-ratio-preserving scaling, or a centred placeholder
    when no image is set.

    Stores the original QPixmap internally and rescales it
    whenever the widget is resized so the image always fills
    the available space without distortion.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._original_pixmap: QPixmap | None = None
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Ignored,
        )
        self._show_placeholder()

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    def set_preview(
        self,
        pixmap: QPixmap | None,
        tooltip: str = "",
    ) -> None:
        """Display *pixmap* as the preview, or show a placeholder
        if *pixmap* is None.

        :param pixmap: Preview image, or *None*.
        :param tooltip: Tooltip text (typically the file name).
        """
        if pixmap is None or pixmap.isNull():
            self._original_pixmap = None
            self.setToolTip("")
            self._show_placeholder()
            return

        self._original_pixmap = pixmap
        self.setToolTip(tooltip)
        self.setStyleSheet(AppStyles.Label.preview_image())
        self._rescale()

    def clear_preview(self) -> None:
        """Reset the label to the placeholder state."""
        self._original_pixmap = None
        self.setToolTip("")
        self._show_placeholder()

    # -----------------------------------------------------------------
    # Overrides
    # -----------------------------------------------------------------

    def resizeEvent(self, event):
        """Rescale the stored pixmap to fit the new size."""
        super().resizeEvent(event)
        if self._original_pixmap is not None:
            self._rescale()

    # -----------------------------------------------------------------
    # Internals
    # -----------------------------------------------------------------

    def _rescale(self):
        """Scale the stored pixmap to fit the label."""
        if self._original_pixmap is None:
            return
        scaled = self._original_pixmap.scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.setPixmap(scaled)

    def _show_placeholder(self):
        """Show centred placeholder text."""
        self.setStyleSheet(AppStyles.Label.preview_placeholder())
        self.setText(AppStyles.AppText.PREVIEW_PLACEHOLDER_TEXT)


# -----------------------------------------------------------------
# Image Selection
# -----------------------------------------------------------------

def find_left_image(
    directories: list[dict],
    project_root: Path | None,
) -> tuple[Path | None, str]:
    """Find the left preview image path.

    Prefers the last image from ``LamellaEvaluationImages``.
    Falls back to the last electron match image from
    ``PrecisePositioningLogImages``.

    :param directories: Site's ImageDirectories list.
    :param project_root: Absolute path to the project root.
    :return: Tuple of (absolute image path or *None*, source
        directory name).
    """
    dir_name = "LamellaEvaluationImages"
    path = _last_image_in_directory(
        directories, dir_name, project_root
    )
    if path is not None:
        logger.debug(
            "Left preview: using LamellaEvaluationImages"
        )
        return path, dir_name

    dir_name = "PrecisePositioningLogImages"
    logger.debug(
        "Left preview: LamellaEvaluationImages unavailable, "
        "falling back to PrecisePositioningLogImages"
    )
    return _last_matching_image(
        directories, dir_name, "electron",
        project_root=project_root,
    ), dir_name


def find_right_image(
    directories: list[dict],
    project_root: Path | None,
) -> tuple[Path | None, str]:
    """Find the right preview image path.

    Returns the last polishing match image (excluding electron
    images) from ``PrecisePositioningLogImages``.

    :param directories: Site's ImageDirectories list.
    :param project_root: Absolute path to the project root.
    :return: Tuple of (absolute image path or *None*, source
        directory name).
    """
    dir_name = "PrecisePositioningLogImages"
    return _last_matching_image(
        directories, dir_name, "polishing",
        exclude="electron",
        project_root=project_root,
    ), dir_name


# -----------------------------------------------------------------
# Private Helpers
# -----------------------------------------------------------------

def _last_image_in_directory(
    directories: list[dict],
    dir_name: str,
    project_root: Path | None,
) -> Path | None:
    """Return the last image path from a named directory.

    :param directories: Site's ImageDirectories list.
    :param dir_name: Directory name to search for
        (case-insensitive).
    :param project_root: Absolute path to the project root.
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
        if project_root is None:
            logger.debug(
                "Project root not set — cannot resolve "
                f"'{dir_name}' image paths"
            )
            return None
        rel = paths[-1].replace("\\", "/")
        abs_path = project_root / Path(rel)
        if abs_path.is_file():
            return abs_path
        logger.debug(f"Preview file not found: {abs_path}")
    return None


def _last_matching_image(
    directories: list[dict],
    dir_name: str,
    keyword: str,
    exclude: str = "",
    *,
    project_root: Path | None,
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
    :param project_root: Absolute path to the project root.
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
        if matches and project_root is not None:
            rel = matches[-1].replace("\\", "/")
            abs_path = project_root / Path(rel)
            if abs_path.is_file():
                return abs_path
    return None