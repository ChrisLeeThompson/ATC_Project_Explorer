"""
Image Utilities

Shared image loading and conversion functions used by the
image viewer and site position plot widgets.

``load_image`` returns NumPy arrays suitable for direct use with
``matplotlib.axes.Axes.imshow``.  The Image Viewer instead loads with
``load_image_native``, which keeps the pixel values the file stores,
and renders them through levels with ``numpy_to_qpixmap``.
"""
import logging
from pathlib import Path

import numpy as np
import matplotlib.image as mpimg
from PIL import Image
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


# Pillow modes whose pixel values load as a 2-D array as-is.
_GRAY_MODES = {"L", "I", "F", "I;16", "I;16B", "I;16L", "I;16N"}


def load_image_native(path: Path) -> np.ndarray | None:
    """Load an image with the pixel values the file stores.

    Unlike :func:`load_image`, whose ``matplotlib.image.imread``
    returns PNGs as floats normalized to 0-1, this keeps the stored
    values (0-255 for 8-bit and 0-65535 for 16-bit images), so the
    Image Viewer's histogram and levels work in pixel values.

    :param path: Absolute path to the image file.
    :return: 2-D array (``uint8``, ``uint16``, ``int32`` or
        ``float32``) for a grayscale image, a 3-D RGB ``uint8`` array
        for a color or palette image, or *None* on failure.
    """
    try:
        with Image.open(path) as img:
            if img.mode in _GRAY_MODES:
                arr = np.asarray(img)
            elif img.mode in ("1", "LA"):
                arr = np.asarray(img.convert("L"))
            else:
                arr = np.asarray(img.convert("RGB"))
    except Exception:
        logger.error(
            f"Failed to read image: {path.name}", exc_info=True
        )
        return None

    # 16-bit PNGs open as 32-bit integers ("I"), and big-endian 16-bit
    # TIFFs as ">u2"; store both as native uint16.
    if (
        arr.ndim == 2
        and arr.dtype.kind in "ui"
        and arr.dtype.itemsize >= 2
        and arr.dtype != np.uint16
        and arr.size
        and arr.min() >= 0
        and arr.max() <= np.iinfo(np.uint16).max
    ):
        arr = arr.astype(np.uint16)
    return np.ascontiguousarray(arr)


def apply_levels(
    arr: np.ndarray, black: float, white: float,
) -> np.ndarray:
    """Map pixel values to 8-bit display gray through levels.

    The black point maps to 0 and the white point to 255, linearly,
    and values beyond either point clip.  A black point above the
    white point inverts the image; equal points threshold at that
    value.  ``uint8`` and ``uint16`` arrays go through a lookup table,
    other dtypes are mapped arithmetically, with the same result.

    :param arr: 2-D array of pixel values.
    :param black: Pixel value displayed as black.
    :param white: Pixel value displayed as white.
    :return: 2-D ``uint8`` array.
    """
    if white == black:
        return np.where(arr > black, 255, 0).astype(np.uint8)

    scale = 255.0 / (white - black)
    if arr.dtype in (np.uint8, np.uint16):
        values = np.arange(
            np.iinfo(arr.dtype).max + 1, dtype=np.float32
        )
        lut = _to_gray8((values - black) * scale)
        return lut[arr]
    return _to_gray8((arr.astype(np.float32) - black) * scale)


def _to_gray8(norm: np.ndarray) -> np.ndarray:
    """Clip normalized values to 0-255 and truncate to ``uint8``."""
    return np.clip(norm, 0, 255).astype(np.uint8)


def gray8_to_qpixmap(img8: np.ndarray) -> QPixmap:
    """Convert a 2-D ``uint8`` array to a grayscale ``QPixmap``.

    :param img8: 2-D ``uint8`` array.
    :return: ``QPixmap`` holding its own copy of the pixels.
    """
    img8 = np.ascontiguousarray(img8)
    h, w = img8.shape
    qimg = QImage(img8.data, w, h, w, QImage.Format.Format_Grayscale8)
    # .copy() detaches the QImage from the temporary NumPy
    # buffer so the array can be garbage-collected safely.
    return QPixmap.fromImage(qimg.copy())


def numpy_to_qpixmap(
    arr: np.ndarray,
    levels: tuple[float, float] | None = None,
) -> QPixmap | None:
    """Convert a 2-D grayscale NumPy array to a ``QPixmap``.

    With no *levels* (auto levels), applies a per-image min-max
    stretch, matching matplotlib's default
    ``imshow(..., cmap='gray')``; a uniform image renders mid-gray
    rather than black, which would hide any overlay drawn over it.

    SEM/FIB images are always grayscale; if a 3D array is passed,
    the first channel is used and a warning is logged.

    :param arr: 2D NumPy array (grayscale).  3D arrays are
        accepted defensively but discouraged.
    :param levels: ``(black_point, white_point)`` pixel values, or
        *None* for auto levels.
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

    if levels is not None:
        img8 = apply_levels(arr, *levels)
    else:
        lo = float(arr.min())
        hi = float(arr.max())
        if hi > lo:
            img8 = apply_levels(arr, lo, hi)
        else:
            img8 = np.full(arr.shape, 127, dtype=np.uint8)
    return gray8_to_qpixmap(img8)
