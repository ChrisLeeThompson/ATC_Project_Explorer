"""
Preview Media Loader

Off-GUI-thread loader for the media the global panel needs after a
project loads: the two preview thumbnails per site plus the
representative atlas image and its metadata.

Running this on the worker thread means the decode cost — up to three
image decodes per site, which is the multi-second freeze on large
projects over network storage — happens under the progress bar
instead of locking the UI after the bar completes.  Everything it
produces is a thread-safe payload:

  - Preview thumbnails are decoded to ``QImage`` (which, unlike
    ``QPixmap``, may be built off the GUI thread); the panels convert
    them to ``QPixmap`` on arrival.
  - The atlas image is a NumPy array and its metadata a plain dict.

The result is a mapping ``{site_name: {...}}`` returned in the
worker's result dict and forwarded to the panels via
``set_preloaded_media``.  When a site — or the whole bundle — is
absent, the panels fall back to their existing on-demand loading, so
this is a pure optimisation layered on top of the synchronous path.
"""
import logging
from pathlib import Path

from script_modules.app_styles import AppStyles
from script_modules.cancellation import OperationCancelled
from script_modules.image_utils import load_image
from script_modules.parsers.image_metadata_parser import (
    extract_image_metadata,
)
from script_modules.preview_image_helpers import (
    find_first_eucentric_image,
    find_left_image,
    find_right_image,
    load_preview_qimage,
)


logger = logging.getLogger(__name__)


# Downsample cap for the atlas image.  Must match
# ``SitePositionPlotWidget._MAX_IMAGE_DIM`` so preloaded and on-demand
# atlas arrays are the same size.
_ATLAS_MAX_DIM = 512


def load_project_media(
    metadata: dict,
    project_root: Path,
    cancel_check=None,
    progress=None,
) -> dict:
    """Decode all preview and atlas media for a project off-thread.

    :param metadata: Consolidated metadata dict (with ``"Sites"``).
    :param project_root: Absolute path to the project root, used to
        resolve relative image paths.
    :param cancel_check: Optional ``Callable[[], bool]`` polled once
        per site (before its images are decoded); when it returns
        True, loading stops by raising :class:`OperationCancelled`,
        bounding cancellation latency to roughly one site's decode.
    :param progress: Optional ``Callable[[int, int], None]`` invoked
        as ``(done, total)`` after each site, for progress reporting.
    :return: Mapping ``{site_name: {"left_qimage", "left_tooltip",
        "right_qimage", "right_tooltip", "atlas_array",
        "atlas_meta"}}``.  Sites without a name are skipped.
    :raises OperationCancelled: If ``cancel_check`` returns True.
    """
    result: dict[str, dict] = {}
    sites = metadata.get("Sites", [])
    total = len(sites)

    thumb_max = (
        AppStyles.Dimensions.GLOBAL_SITE_PREVIEW_CARD_THUMBNAIL_MAX_DIM
    )

    for i, site_data in enumerate(sites):
        if cancel_check is not None and cancel_check():
            raise OperationCancelled()

        site_name = site_data.get("SiteName", "")
        if not site_name:
            continue

        directories = site_data.get("ImageDirectories", [])

        # Preview thumbnails (electron + polishing)
        left_path, _ = find_left_image(directories, project_root)
        right_path, _ = find_right_image(directories, project_root)
        left_qimage = (
            load_preview_qimage(left_path, max_dim=thumb_max)
            if left_path is not None else None
        )
        right_qimage = (
            load_preview_qimage(right_path, max_dim=thumb_max)
            if right_path is not None else None
        )

        # Atlas image array + XMLMetadata
        atlas_array, atlas_meta = _load_atlas_data(
            directories, project_root
        )

        result[site_name] = {
            "left_qimage": left_qimage,
            "left_tooltip": left_path.name if left_path else "",
            "right_qimage": right_qimage,
            "right_tooltip": right_path.name if right_path else "",
            "atlas_array": atlas_array,
            "atlas_meta": atlas_meta,
        }

        if progress is not None:
            progress(i + 1, total)

    logger.info(f"Preloaded media for {len(result)} site(s)")
    return result


def _load_atlas_data(directories, project_root):
    """Load the atlas image array + XMLMetadata for one site.

    Mirrors the I/O the atlas would otherwise perform on the GUI
    thread.  Returns ``(None, None)`` when no usable image is
    available (so the atlas falls back to a marker-only position), or
    ``(array, xml_meta)`` where ``xml_meta`` may be an empty dict when
    the image carries no embedded FEI XML.

    :param directories: Site's ImageDirectories list.
    :param project_root: Absolute path to the project root.
    :return: ``(np.ndarray | None, dict | None)``.
    """
    image_path = find_first_eucentric_image(directories, project_root)
    if image_path is None:
        return None, None
    image_array = load_image(image_path, max_dim=_ATLAS_MAX_DIM)
    if image_array is None:
        return None, None
    try:
        meta = extract_image_metadata(image_path)
    except Exception:
        logger.debug(
            f"Atlas metadata extraction failed for: "
            f"{image_path.name}",
            exc_info=True,
        )
        # Image decoded but metadata unreadable — matches the atlas's
        # on-demand behaviour of skipping the image in this case.
        return None, None
    return image_array, meta.get("XMLMetadata", {})