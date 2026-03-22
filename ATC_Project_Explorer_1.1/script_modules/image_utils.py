"""
Image Utilities

Shared image loading and downsampling functions used by the
image viewer and site position plot widgets.

All functions return NumPy arrays suitable for direct use with
``matplotlib.axes.Axes.imshow``.
"""
import logging
from pathlib import Path

import numpy as np
import matplotlib.image as mpimg


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
    :return: NumPy array (2D for greyscale, 3D for colour),
        or *None* on failure.
    """
    try:
        img = mpimg.imread(str(path))
    except Exception:
        logger.error(
            f"Failed to read image: {path.name}", exc_info=True
        )
        return None

    # Drop alpha channel if present (RGBA → RGB)
    if img.ndim == 3 and img.shape[2] == 4:
        img = img[:, :, :3]

    # Stride-based downsample
    if max_dim is not None and img.ndim >= 2:
        h, w = img.shape[:2]
        factor = max(1, max(h, w) // max_dim)
        if factor > 1:
            img = img[::factor, ::factor]

    return img