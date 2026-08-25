"""
Image Utilities

Shared image loading and conversion functions used by the
image viewer and site position plot widgets.

``load_image`` returns NumPy arrays suitable for direct use with
``matplotlib.axes.Axes.imshow``.  ``numpy_to_qpixmap`` converts
a grayscale NumPy array to a Qt ``QPixmap`` for the QPainter-based
image viewer.
"""
import logging
from pathlib import Path

import numpy as np
import matplotlib.image as mpimg
from PySide6.QtGui import QImage, QPixmap


logger = logging.getLogger(__name__)


def load_image(
    path: Path,
    max_dim: int | None = None,
) -> np.ndarray | None:
    """Load an image and optionally downsample for display.

    Uses ``matplotlib.image.imread`` which handles PNG, JPEG,
    TIFF, and other common formats via PIL delegation.  RGBA
    images are reduced to RGB by dropping the alpha channel.

    Downsampling is stride-based (no interpolation) for speed.

    :param path: Absolute path to the image file.
    :param max_dim: If provided, downsample so neither axis
        exceeds this value.  Pass ``None`` to load at full
        resolution.
    :return: NumPy array (2D for grayscale, 3D for color),
        or *None* on failure.
    """
    try:
        img = mpimg.imread(str(path))
    except Exception:
        logger.error(
            f"Failed to read image: {path.name}", exc_info=True
        )
        return None

    if img.ndim == 3 and img.shape[2] == 4:
        img = img[:, :, :3]

    if max_dim is not None and img.ndim >= 2:
        h, w = img.shape[:2]
        factor = max(1, max(h, w) // max_dim)
        if factor > 1:
            img = img[::factor, ::factor]

    return img


def numpy_to_qpixmap(arr: np.ndarray) -> QPixmap | None:
    """Convert a 2D grayscale NumPy array to a ``QPixmap``.

    Applies a per-image min-max stretch to ``uint8`` to match
    matplotlib's default ``imshow(..., cmap='gray')`` behavior
    across ``uint8`` / ``uint16`` / ``float32`` inputs.

    SEM/FIB images are always grayscale; if a 3D array is passed,
    the first channel is used and a warning is logged.

    :param arr: 2D NumPy array (grayscale).  3D arrays are
        accepted defensively but discouraged.
    :return: ``QPixmap``, or *None* if the array is unusable.
    """
    if arr.ndim == 3:
        logger.warning(
            f"Unexpected 3D array in numpy_to_qpixmap "
            f"(shape={arr.shape}); using first channel"
        )
        arr = arr[..., 0]
    if arr.ndim != 2 or arr.size == 0:
        return None

    lo = float(arr.min())
    hi = float(arr.max())
    if hi > lo:
        norm = (arr.astype(np.float32) - lo) * (255.0 / (hi - lo))
    else:
        # Uniform image — render as mid-gray rather than black
        # (which would hide any overlay drawn over the top).
        norm = np.full(arr.shape, 127.5, dtype=np.float32)
    img8 = np.ascontiguousarray(
        norm.clip(0, 255).astype(np.uint8)
    )

    h, w = img8.shape
    qimg = QImage(
        img8.data, w, h, w, QImage.Format.Format_Grayscale8
    )
    # .copy() detaches the QImage from the temporary NumPy
    # buffer so the array can be garbage-collected safely.
    return QPixmap.fromImage(qimg.copy())