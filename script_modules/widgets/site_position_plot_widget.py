"""
Site Position Plot Widget (Grid Atlas)

Spatial atlas of lamella site positions on the grid, optionally
overlaid with SEM reference images from the PrecisePositioning
log directory.

When available, the **first** eucentric-tilt-match-information
image for each site is placed at its stage position using embedded
FEI XML metadata (``BinaryResult.PixelSize`` for extent,
``StageCollection`` for centre coordinates).  A lamella marker
is drawn at the ``PatternCenterPositionPx`` position when
present, otherwise at the image centre.

If the image or its metadata is unavailable the widget falls back
to stage coordinates from the project's ``ChunkSiteLocation``
and draws a simple scatter point.

Duplicate images (tiles that cover essentially the same area) are
detected by comparing stage positions: if two image centres fall
within a configurable fraction of the field of view, only the
first is rendered.

Site markers are interactive: hovering enlarges the point and
changes the cursor to a pointing hand; clicking shows a context
menu with options to navigate to the site or open it in a
detached window.  These actions are emitted as
:attr:`~SitePositionPlotWidget.site_selected` and
:attr:`~SitePositionPlotWidget.site_open_new_window` signals.

All coordinates are displayed relative to the centroid of all
sites, in µm.

The widget wraps a matplotlib ``FigureCanvasQTAgg`` inside a
styled ``QGroupBox`` and follows the standard ``populate`` /
``clear`` interface used by the panel layer.
"""
import logging
from pathlib import Path

import numpy as np
from PySide6.QtWidgets import QMenu
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCursor
from script_modules.app_styles import AppStyles
from script_modules.value_utils import (
    convert_to_metres,
    extract_numeric,
)
from script_modules.image_utils import load_image
from script_modules.preview_image_helpers import (
    find_first_eucentric_image,
)
from script_modules.parsers.image_metadata_parser import (
    extract_image_metadata,
)
from script_modules.widgets.styled_chart_widget import StyledChartWidget


logger = logging.getLogger(__name__)


# ── Constants ────────────────────────────────────────────────────
# Maximum pixel dimension (longest edge) when downsampling images
# for display.  Keeps memory and render time reasonable for large
# projects while preserving enough detail for a montage overview.
_MAX_IMAGE_DIM = 512

# Two image centres closer than this fraction of the average FOV
# are considered duplicates (same tileset tile).  Only the first
# encountered image is rendered.
_DEDUP_FOV_FRACTION = 0.4


class SitePositionPlotWidget(StyledChartWidget):
    """Grid atlas scatter plot with optional SEM image montage."""

    # Enable the matplotlib navigation toolbar (zoom, pan, home,
    # save) so users can inspect closely-spaced lamella positions.
    _toolbar_enabled = True

    # Emitted when the user chooses "Open site" from the marker
    # context menu.  Carries the site name string.
    site_selected = Signal(str)

    # Emitted when the user chooses "Open site in new window"
    # from the marker context menu.  Carries the site name string.
    site_open_new_window = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._site_points: list[dict] = []
        self._scatter = None          # PathCollection from ax.scatter
        self._hovered_index: int | None = None  # currently enlarged
        self._default_cursor = self.cursor()
        # Optional preloaded media bundle (built off-thread by
        # preview_media_loader); None => load images on demand.
        self._preloaded_media: dict | None = None
        # Override minimum height for the atlas plot
        self.setMinimumHeight(
            AppStyles.Dimensions.SITE_POSITION_PLOT_MINIMUM_HEIGHT
        )
        self._connect_events()

    # =================================================================
    # Public API
    # =================================================================

    def set_preloaded_media(self, media: dict | None) -> None:
        """Provide (or clear) the preloaded media bundle.

        When set before :meth:`populate`, the atlas consumes each
        site's ``atlas_array`` / ``atlas_meta`` from the bundle
        instead of decoding images on the GUI thread.  Sites absent
        from the bundle fall back to on-demand loading.

        :param media: Mapping ``{site_name: {...}}`` from
            ``preview_media_loader.load_project_media``, or *None*.
        """
        self._preloaded_media = media

    def populate(self, metadata: dict) -> None:
        """Build the atlas from consolidated metadata.

        :param metadata: Full consolidated metadata dictionary
            (must include ``"Sites"`` and optionally
            ``"ProjectRootPath"``).
        """
        sites = metadata.get("Sites", [])
        if not sites:
            self._clear_axes()
            return

        project_root = self._resolve_project_root(metadata)

        # ── 1. Collect per-site data ─────────────────────────────
        entries = self._collect_site_entries(sites)
        if not entries:
            # Every site was skipped (no parseable ChunkSiteLocation)
            # — without this guard the centroid division below would
            # raise ZeroDivisionError.
            logger.warning(
                "No sites with usable stage positions; "
                "site-position atlas left empty"
            )
            self._clear_axes()
            return

        # ── 2. Load images and extract metadata ──────────────────
        if project_root is not None:
            for entry in entries:
                preloaded = (
                    self._preloaded_media.get(entry["site_name"])
                    if self._preloaded_media else None
                )
                self._load_image_data(
                    entry, project_root, preloaded=preloaded
                )

        # ── Diagnostic: compare coordinate sources ───────────────
        # Log fallback (ChunkSiteLocation) vs. image metadata
        # stage positions so coordinate-system mismatches are
        # easy to spot.
        for e in entries:
            name = e["site_name"]
            fb_x = e["fallback_x_m"]
            fb_y = e["fallback_y_m"]
            im_x = e["image_stage_x_m"]
            im_y = e["image_stage_y_m"]
            if im_x is not None and im_y is not None:
                delta_x = (im_x - fb_x) * 1e6
                delta_y = (im_y - fb_y) * 1e6
                logger.debug(
                    f"[{name}] fallback=("
                    f"{fb_x*1e3:.4f}, {fb_y*1e3:.4f}) mm | "
                    f"image_stage=("
                    f"{im_x*1e3:.4f}, {im_y*1e3:.4f}) mm | "
                    f"delta=({delta_x:.1f}, {delta_y:.1f}) µm"
                )
            else:
                logger.debug(
                    f"[{name}] fallback=("
                    f"{fb_x*1e3:.4f}, {fb_y*1e3:.4f}) mm | "
                    f"image_stage=None (using fallback)"
                )

        # ── 3. Compute display positions and centroid ────────────
        # Use the same position source for both the centroid and
        # display so they share a consistent coordinate frame.
        # Previously the centroid was always from fallback, while
        # display preferred image metadata — when those used
        # different coordinate systems (e.g. StageSettings vs
        # StageCollection) images were displaced from markers.
        display_positions: list[tuple[float, float]] = []
        for e in entries:
            pos_x = (
                e["image_stage_x_m"]
                if e["image_stage_x_m"] is not None
                else e["fallback_x_m"]
            )
            pos_y = (
                e["image_stage_y_m"]
                if e["image_stage_y_m"] is not None
                else e["fallback_y_m"]
            )
            display_positions.append((pos_x, pos_y))

        mean_x_m = (
            sum(p[0] for p in display_positions) / len(entries)
        )
        mean_y_m = (
            sum(p[1] for p in display_positions) / len(entries)
        )
        logger.debug(
            f"Display centroid: "
            f"({mean_x_m*1e3:.4f}, {mean_y_m*1e3:.4f}) mm"
        )

        for e, (pos_x, pos_y) in zip(entries, display_positions):
            e["display_x_um"] = (pos_x - mean_x_m) * 1e6
            e["display_y_um"] = (pos_y - mean_y_m) * 1e6

        # ── Diagnostic: sites sharing identical coordinates ──────
        self._report_coincident_sites(entries, display_positions)

        # ── 4. Deduplicate images ────────────────────────────────
        self._deduplicate_images(entries)

        # ── 5. Plot ──────────────────────────────────────────────
        self._plot_atlas(entries)

    def clear(self) -> None:
        """Reset the chart to a blank state."""
        self._site_points.clear()
        self._scatter = None
        self._hovered_index = None
        self._clear_axes()

    # =================================================================
    # Data Collection
    # =================================================================

    def _collect_site_entries(
        self, sites: list[dict]
    ) -> list[dict]:
        """Build an entry dict for each site with fallback stage
        positions from ChunkSiteLocation.

        :param sites: The ``"Sites"`` list from consolidated
            metadata.
        :return: List of entry dicts ready for image loading.
        """
        entries: list[dict] = []
        for site in sites:
            name = site.get("SiteName", "Unknown")
            spd = site.get("SiteProjectData", {})
            coords = self._extract_chunk_xy(spd)
            if coords is None:
                logger.debug(
                    f"No ChunkSiteLocation for '{name}', skipping"
                )
                continue
            x_m, y_m = coords
            entries.append({
                "site_name": name,
                "site_data": site,
                "fallback_x_m": x_m,
                "fallback_y_m": y_m,
                # Populated by _load_image_data:
                "image_array": None,
                "image_stage_x_m": None,
                "image_stage_y_m": None,
                "pixel_size_x_m": None,
                "pixel_size_y_m": None,
                "fov_x_m": None,
                "fov_y_m": None,
                "pattern_center_x_um": None,
                "pattern_center_y_um": None,
                # Set by _deduplicate_images:
                "place_image": False,
                # Set during coordinate conversion:
                "display_x_um": 0.0,
                "display_y_um": 0.0,
            })
        return entries

    # =================================================================
    # Image Loading and Metadata Extraction
    # =================================================================

    def _load_image_data(
        self,
        entry: dict,
        project_root: Path,
        preloaded: dict | None = None,
    ) -> None:
        """Obtain a site's atlas image + metadata and apply placement.

        When *preloaded* media is supplied (built off-thread by
        ``preview_media_loader``), its ``atlas_array`` / ``atlas_meta``
        are consumed directly — no image is decoded on the GUI thread.
        Otherwise the image is found, decoded, and its metadata
        extracted on demand (the original behaviour).  Either way the
        cheap coordinate math is applied via
        :meth:`_apply_image_placement`.

        :param entry: Site entry dict from _collect_site_entries.
        :param project_root: Absolute path to the project root.
        :param preloaded: Optional per-site media dict with
            ``"atlas_array"`` and ``"atlas_meta"`` keys.
        """
        name = entry["site_name"]

        if preloaded is not None:
            image_array = preloaded.get("atlas_array")
            if image_array is None:
                return
            xml_meta = preloaded.get("atlas_meta") or {}
        else:
            image_path = find_first_eucentric_image(
                entry["site_data"].get("ImageDirectories", []),
                project_root,
            )
            if image_path is None:
                return

            # Load and downsample the image
            image_array = load_image(
                image_path, max_dim=_MAX_IMAGE_DIM
            )
            if image_array is None:
                return

            # Extract embedded metadata
            try:
                meta = extract_image_metadata(image_path)
            except Exception:
                logger.debug(
                    f"Metadata extraction failed for '{name}'",
                    exc_info=True,
                )
                return
            xml_meta = meta.get("XMLMetadata", {})

        self._apply_image_placement(
            entry, name, image_array, xml_meta
        )

    def _apply_image_placement(
        self,
        entry: dict,
        name: str,
        image_array,
        xml_meta: dict,
    ) -> None:
        """Populate *entry* placement fields from a loaded image array
        and its ``XMLMetadata`` (pure computation; no I/O).

        Extracts pixel size, field of view, stage position, and
        pattern centre.  When metadata is missing the image is still
        stored (the site falls back to its ChunkSiteLocation
        position).

        :param entry: Site entry dict to populate in place.
        :param name: Site name (for logging).
        :param image_array: Downsampled image array for the site.
        :param xml_meta: The ``XMLMetadata`` dict (possibly empty).
        """
        if not xml_meta:
            logger.debug(
                f"No XMLMetadata in image for '{name}'"
            )
            # Still use the image with fallback position
            entry["image_array"] = image_array
            return

        # Extract pixel size (required for image placement)
        pixel_size = self._extract_pixel_size(xml_meta)
        if pixel_size is None:
            logger.debug(
                f"No pixel size in image metadata for '{name}'"
            )
            entry["image_array"] = image_array
            return

        px_x, px_y = pixel_size
        # Use the ORIGINAL image dimensions from metadata for
        # FOV, not the downsampled array dimensions.  The image
        # array is downsampled for display (max_dim=512) but the
        # field of view must reflect the full acquisition size.
        orig_w, orig_h = self._extract_image_size(xml_meta)
        if orig_w is None:
            # Fall back to downsampled dimensions (incorrect but
            # better than nothing)
            img_h, img_w = image_array.shape[:2]
            orig_w = img_w
            orig_h = img_h
            logger.debug(
                f"No BinaryResult.ImageSize for '{name}', "
                f"using downsampled dimensions for FOV"
            )
        fov_x_m = px_x * orig_w
        fov_y_m = px_y * orig_h

        entry["image_array"] = image_array
        entry["pixel_size_x_m"] = px_x
        entry["pixel_size_y_m"] = px_y
        entry["fov_x_m"] = fov_x_m
        entry["fov_y_m"] = fov_y_m

        # Extract stage position from image metadata
        stage_pos = self._extract_stage_position(xml_meta)
        if stage_pos is not None:
            entry["image_stage_x_m"] = stage_pos[0]
            entry["image_stage_y_m"] = stage_pos[1]
        else:
            logger.debug(
                f"No stage position in image metadata for "
                f"'{name}', will use ChunkSiteLocation"
            )

        # Extract pattern centre (in image pixel coordinates),
        # convert to stage-relative offset in µm.
        # Pattern centre coordinates are in ORIGINAL pixel space,
        # so use orig_w / orig_h (not the downsampled dimensions).
        pattern_px = self._extract_pattern_center(xml_meta)
        if pattern_px is not None and pixel_size is not None:
            # Pattern centre offset from image centre, in µm
            cx_px, cy_px = pattern_px
            offset_x_m = (cx_px - orig_w / 2) * px_x
            offset_y_m = (cy_px - orig_h / 2) * px_y
            entry["pattern_center_x_um"] = offset_x_m * 1e6
            # Negate Y: image pixel Y increases downward,
            # plot Y increases upward
            entry["pattern_center_y_um"] = -offset_y_m * 1e6

        img_h, img_w = image_array.shape[:2]
        logger.debug(
            f"Image loaded for '{name}': "
            f"original {orig_w}x{orig_h} px, "
            f"downsampled {img_w}x{img_h} px, "
            f"FOV {fov_x_m*1e6:.1f}x{fov_y_m*1e6:.1f} µm"
        )

    # =================================================================
    # Metadata Extraction Helpers
    # =================================================================

    @staticmethod
    def _extract_pixel_size(
        xml_meta: dict,
    ) -> tuple[float, float] | None:
        """Extract pixel size (X, Y) in metres from
        ``XMLMetadata.BinaryResult.PixelSize``.

        The FEI XML schema stores pixel size with XML attributes
        (``unit``, ``unitPrefixPower``), causing the parser to
        produce a dict like
        ``{"unit": "m", "_text": "6.48...E-07"}`` rather than
        a plain numeric value.  Uses :func:`extract_numeric` to
        handle both forms.

        :param xml_meta: The ``XMLMetadata`` dictionary from
            ``extract_image_metadata``.
        :return: ``(pixel_size_x_m, pixel_size_y_m)`` or *None*.
        """
        pixel_size = (
            xml_meta.get("BinaryResult", {})
            .get("PixelSize", {})
        )
        if not isinstance(pixel_size, dict):
            return None
        x_val = extract_numeric(pixel_size.get("X"))
        y_val = extract_numeric(pixel_size.get("Y"))
        if x_val is not None and y_val is not None:
            return x_val, y_val
        return None

    @staticmethod
    def _extract_image_size(
        xml_meta: dict,
    ) -> tuple[int, int]:
        """Extract the original image dimensions from
        ``XMLMetadata.BinaryResult.ImageSize``.

        :param xml_meta: The ``XMLMetadata`` dictionary.
        :return: ``(width, height)`` or ``(None, None)`` if not
            available.
        """
        image_size = (
            xml_meta.get("BinaryResult", {})
            .get("ImageSize", {})
        )
        if not isinstance(image_size, dict):
            return None, None
        x_val = extract_numeric(image_size.get("X"))
        y_val = extract_numeric(image_size.get("Y"))
        if x_val is not None and y_val is not None:
            return int(x_val), int(y_val)
        return None, None

    @staticmethod
    def _extract_stage_position(
        xml_meta: dict,
    ) -> tuple[float, float] | None:
        """Extract stage X, Y position in metres from the image's
        XMLMetadata.

        Tries several paths to accommodate the FEI XML schema as
        processed by the scope-aware XML parser:

        1. ``CustomSectionGroup.CustomSection.StageCollection
           .Stage.{X, Y}`` — the ATC software's stage position
           (values include unit strings like ``"-4.770 mm"``).
           Preferred because it aligns with ChunkSiteLocation in
           the project data.
        2. ``StageSettings.StagePosition.{X, Y}`` — the raw
           microscope stage position in metres.  Serves as a
           reliable fallback.

        Values with unit strings are converted to metres by
        :func:`extract_numeric` + :func:`convert_to_metres`.

        :param xml_meta: The ``XMLMetadata`` dictionary.
        :return: ``(x_metres, y_metres)`` or *None*.
        """
        # Path 1: CustomSectionGroup → StageCollection → Stage
        # (scope-grouped by the XML parser)
        custom_section = (
            xml_meta
            .get("CustomSectionGroup", {})
            .get("CustomSection", {})
        )
        if isinstance(custom_section, dict):
            stage = (
                custom_section
                .get("StageCollection", {})
                .get("Stage", {})
            )
            if isinstance(stage, dict):
                x_val = extract_numeric(stage.get("X"))
                y_val = extract_numeric(stage.get("Y"))
                if x_val is not None and y_val is not None:
                    # Values are in mm (e.g. "-4.770 mm"),
                    # extract_numeric strips the unit but returns
                    # the raw number — convert mm → m
                    x_val = convert_to_metres(
                        x_val, stage.get("X")
                    )
                    y_val = convert_to_metres(
                        y_val, stage.get("Y")
                    )
                    logger.debug(
                        "Stage position from "
                        "CustomSectionGroup.StageCollection"
                    )
                    return x_val, y_val

        # Path 2: StageSettings → StagePosition (raw metres)
        stage_pos = (
            xml_meta
            .get("StageSettings", {})
            .get("StagePosition", {})
        )
        if isinstance(stage_pos, dict):
            x_val = extract_numeric(stage_pos.get("X"))
            y_val = extract_numeric(stage_pos.get("Y"))
            if x_val is not None and y_val is not None:
                logger.debug(
                    "Stage position from StageSettings"
                )
                return x_val, y_val

        logger.debug(
            "Stage position not found in XMLMetadata. "
            f"Top-level keys: {list(xml_meta.keys())}"
        )
        return None

    @staticmethod
    def _extract_pattern_center(
        xml_meta: dict,
    ) -> tuple[float, float] | None:
        """Extract the pattern centre pixel coordinates from the
        image's XMLMetadata.

        Primary path (via scope-grouped custom sections)::

            CustomSectionGroup.CustomSection
            .MatchInformationCollection.MatchInformation
            .PatternCenterPositionPx.{X, Y}

        Falls back to a direct top-level path if the custom
        section grouping is absent.

        Handles both list and dict forms of ``MatchInformation``
        (the parser may produce either depending on the number
        of entries).

        :param xml_meta: The ``XMLMetadata`` dictionary.
        :return: ``(x_pixels, y_pixels)`` or *None*.
        """
        # Path 1: CustomSectionGroup → MatchInformationCollection
        custom_section = (
            xml_meta
            .get("CustomSectionGroup", {})
            .get("CustomSection", {})
        )
        mic = None
        if isinstance(custom_section, dict):
            mic = custom_section.get(
                "MatchInformationCollection", {}
            )

        # Path 2: Direct top-level fallback
        if not mic:
            mic = xml_meta.get("MatchInformationCollection", {})

        if not isinstance(mic, dict):
            return None

        mi = mic.get("MatchInformation")
        if mi is None:
            return None

        # Normalise to a list
        if isinstance(mi, dict):
            mi = [mi]
        if not isinstance(mi, list) or not mi:
            return None

        # Use the first entry (first match attempt)
        first = mi[0] if isinstance(mi[0], dict) else {}
        pc = first.get("PatternCenterPositionPx", {})
        if not isinstance(pc, dict):
            return None

        x_val = extract_numeric(pc.get("X"))
        y_val = extract_numeric(pc.get("Y"))
        if x_val is not None and y_val is not None:
            return x_val, y_val
        return None

    @staticmethod
    def _extract_chunk_xy(
        site_project_data: dict,
    ) -> tuple[float, float] | None:
        """Extract X and Y stage positions from ChunkSiteLocation.

        Path: ``SiteProjectData.ChunkSiteLocation.StagePosition
        .StagePosition.{X, Y}``

        Parsed with the same :func:`extract_numeric` +
        :func:`convert_to_metres` recipe as the image stage path
        (:meth:`_extract_stage_position`), so unit-suffixed strings
        (``"-4.221 mm"``), scientific notation (``"-4.2E-03"``),
        bare numbers, and attributed XML nodes (``{"_text": ...}``)
        are all handled consistently.

        :param site_project_data: A single site's SiteProjectData.
        :return: ``(x_metres, y_metres)`` or *None*.
        """
        try:
            stage_pos = (
                site_project_data
                .get("ChunkSiteLocation", {})
                .get("StagePosition", {})
                .get("StagePosition", {})
            )
            if not isinstance(stage_pos, dict):
                return None
            x_raw = stage_pos.get("X")
            y_raw = stage_pos.get("Y")

            x_val = extract_numeric(x_raw)
            y_val = extract_numeric(y_raw)

            if x_val is not None and y_val is not None:
                return (
                    convert_to_metres(x_val, x_raw),
                    convert_to_metres(y_val, y_raw),
                )
        except Exception:
            logger.debug(
                "Failed to extract ChunkSiteLocation",
                exc_info=True,
            )
        return None

    @staticmethod
    def _report_coincident_sites(
        entries: list[dict],
        positions: list[tuple[float, float]],
    ) -> None:
        """Warn when multiple sites resolve to identical coordinates.

        Sites sharing an identical source position render as stacked
        markers — visually indistinguishable from a single site.
        This is genuine in ATC data when several lamella sites are
        prepared from the same chunk and no per-site image stage
        position is available to separate them.  The warning names
        the sites and the coordinate source each used so overlap
        seen in the plot can be traced to the data immediately.

        Grouping uses exact float equality deliberately: identical
        source strings parse to identical floats, so an exact match
        means the *data* is shared, while merely-close positions
        (a rendering concern) stay out of this report.

        :param entries: Site entry dicts (parallel to positions).
        :param positions: The chosen source ``(x_m, y_m)`` per
            entry, as used for display.
        """
        groups: dict[tuple[float, float], list[int]] = {}
        for i, pos in enumerate(positions):
            groups.setdefault(pos, []).append(i)

        for (x_m, y_m), idxs in groups.items():
            if len(idxs) < 2:
                continue
            parts = []
            for i in idxs:
                e = entries[i]
                has_img_x = e["image_stage_x_m"] is not None
                has_img_y = e["image_stage_y_m"] is not None
                if has_img_x and has_img_y:
                    source = "image_stage"
                elif not has_img_x and not has_img_y:
                    source = "fallback"
                else:
                    source = "mixed"
                parts.append(f"'{e['site_name']}' ({source})")
            logger.warning(
                f"{len(idxs)} sites share stage position "
                f"({x_m * 1e3:.4f}, {y_m * 1e3:.4f}) mm and "
                f"render as stacked markers: {', '.join(parts)}"
            )

    # =================================================================
    # Image Deduplication
    # =================================================================

    def _deduplicate_images(self, entries: list[dict]) -> None:
        """Mark images for placement, skipping duplicates whose
        centres overlap significantly.

        Iterates entries in order.  An image is placed unless its
        centre (in metres) is within ``_DEDUP_FOV_FRACTION`` of
        the average FOV of an already-placed image.

        Modifies entries in place (sets ``"place_image"``).

        :param entries: List of site entry dicts.
        """
        # Compute average FOV across entries that have image data
        fovs_x = [
            e["fov_x_m"] for e in entries if e["fov_x_m"] is not None
        ]
        fovs_y = [
            e["fov_y_m"] for e in entries if e["fov_y_m"] is not None
        ]
        if not fovs_x:
            return

        avg_fov_x = sum(fovs_x) / len(fovs_x)
        avg_fov_y = sum(fovs_y) / len(fovs_y)
        threshold_x = avg_fov_x * _DEDUP_FOV_FRACTION
        threshold_y = avg_fov_y * _DEDUP_FOV_FRACTION

        placed_centres: list[tuple[float, float]] = []

        for entry in entries:
            if entry["image_array"] is None:
                continue
            if entry["fov_x_m"] is None:
                # Image loaded but no pixel size: place without
                # dedup (cannot compute spatial overlap)
                entry["place_image"] = True
                continue

            # Use image stage position if available, else fallback
            cx = (
                entry["image_stage_x_m"]
                if entry["image_stage_x_m"] is not None
                else entry["fallback_x_m"]
            )
            cy = (
                entry["image_stage_y_m"]
                if entry["image_stage_y_m"] is not None
                else entry["fallback_y_m"]
            )

            is_duplicate = False
            for px, py in placed_centres:
                if (
                    abs(cx - px) < threshold_x
                    and abs(cy - py) < threshold_y
                ):
                    is_duplicate = True
                    break

            if is_duplicate:
                logger.debug(
                    f"Skipping duplicate image for "
                    f"'{entry['site_name']}'"
                )
            else:
                entry["place_image"] = True
                placed_centres.append((cx, cy))

        placed = sum(1 for e in entries if e["place_image"])
        total_images = sum(
            1 for e in entries if e["image_array"] is not None
        )
        if total_images > 0:
            logger.info(
                f"Image dedup: {placed}/{total_images} images "
                f"placed ({total_images - placed} duplicates)"
            )

    # =================================================================
    # Plotting
    # =================================================================

    def _plot_atlas(self, entries: list[dict]) -> None:
        """Render the full atlas: images, markers, and labels.

        :param entries: List of populated and deduplicated site
            entry dicts.
        """
        self.ax.clear()
        self._style_axes()
        self._site_points = entries

        any_images = any(e["place_image"] for e in entries)

        # ── Place images ─────────────────────────────────────────
        if any_images:
            for entry in entries:
                if entry["place_image"]:
                    self._place_image(entry)

        # ── Lamella markers (single scatter for interactive sizing) ─
        xs = [self._marker_position(e)[0] for e in entries]
        ys = [self._marker_position(e)[1] for e in entries]

        self._scatter = self.ax.scatter(
            xs, ys,
            s=AppStyles.Dimensions.MARKER_SIZE_DEFAULT,
            color=AppStyles.Colors.SITE_POSITION_PLOT_MARKER_COLOR,
            edgecolors=AppStyles.Colors.SITE_POSITION_PLOT_MARKER_EDGE_COLOR,
            linewidths=0.5,
            zorder=5,
        )

        # ── Site name labels ─────────────────────────────────────
        for entry in entries:
            mx, my = self._marker_position(entry)
            self.ax.annotate(
                entry["site_name"],
                xy=(mx, my),
                xytext=(6, 6),
                textcoords="offset points",
                fontsize=AppStyles.Dimensions.PLOT_LABEL_FONT_SIZE,
                color=AppStyles.Colors.TEXT_PRIMARY,
                zorder=6,
            )

        # ── Axes ─────────────────────────────────────────────────
        self.ax.set_xlabel("\nRelative X (µm)")
        self.ax.set_ylabel("Relative Y (µm)")
        self.ax.set_title(
            "Relative Site Positions\n",
            fontsize=AppStyles.Dimensions.PLOT_TITLE_FONT_SIZE,
        )

        if not any_images:
            # Pure scatter mode: equal aspect with padding
            self.ax.set_aspect("equal", adjustable="datalim")
            if len(entries) > 1:
                span = max(max(xs) - min(xs), max(ys) - min(ys))
                pad = span * 0.15 + 10
                self.ax.set_xlim(min(xs) - pad, max(xs) + pad)
                self.ax.set_ylim(min(ys) - pad, max(ys) + pad)
        else:
            self.ax.set_aspect("equal", adjustable="datalim")

        self._hovered_index = None
        self.canvas.draw_idle()

        img_count = sum(1 for e in entries if e["place_image"])
        scatter_count = len(entries) - img_count
        logger.info(
            f"Atlas rendered: {len(entries)} site(s), "
            f"{img_count} image(s) placed, "
            f"{scatter_count} scatter-only"
        )

    def _place_image(self, entry: dict) -> None:
        """Render a single SEM image on the axes using imshow.

        Grayscale (2D) arrays are rendered with ``cmap='gray'``
        for natural SEM appearance.  Colour (3D) arrays are
        rendered directly.

        :param entry: Site entry dict with image data.
        """
        img = entry["image_array"]
        cx = entry["display_x_um"]
        cy = entry["display_y_um"]
        fov_x = entry.get("fov_x_m")
        fov_y = entry.get("fov_y_m")

        if fov_x is None or fov_y is None:
            # No pixel size: render at a nominal extent around the
            # marker position (1/4 of the total coordinate range)
            fov_x_um = 50.0
            fov_y_um = 50.0
        else:
            fov_x_um = fov_x * 1e6
            fov_y_um = fov_y * 1e6

        half_x = fov_x_um / 2
        half_y = fov_y_um / 2

        # extent = [left, right, bottom, top]
        extent = [
            cx - half_x,
            cx + half_x,
            cy - half_y,
            cy + half_y,
        ]

        # Use gray colourmap for grayscale (2D) images
        cmap = "gray" if img.ndim == 2 else None

        self.ax.imshow(
            img,
            extent=extent,
            origin="upper",
            aspect="equal",
            alpha=0.75,
            zorder=2,
            interpolation="bilinear",
            cmap=cmap,
        )

    @staticmethod
    def _marker_position(entry: dict) -> tuple[float, float]:
        """Determine the lamella marker position in display µm.

        Uses the pattern centre offset when available, otherwise
        the image/fallback centre.

        :param entry: Site entry dict.
        :return: ``(x_µm, y_µm)`` in display coordinates.
        """
        x = entry["display_x_um"]
        y = entry["display_y_um"]
        if entry["pattern_center_x_um"] is not None:
            x += entry["pattern_center_x_um"]
            y += entry["pattern_center_y_um"]
        return x, y

    # =================================================================
    # Interactive Markers (hover + click)
    # =================================================================

    def _connect_events(self):
        """Connect matplotlib canvas events for hover and click."""
        self.canvas.mpl_connect(
            "motion_notify_event", self._on_mouse_move
        )
        self.canvas.mpl_connect(
            "button_press_event", self._on_mouse_click
        )

    def _on_mouse_move(self, event):
        """Enlarge the nearest marker on hover and switch to a
        pointing-hand cursor to indicate it is clickable.

        Suppressed when the toolbar is in pan or zoom mode so the
        drag interaction is not disrupted.

        :param event: Matplotlib motion_notify_event.
        """
        if self._is_toolbar_active():
            return

        if (
            self._scatter is None
            or event.inaxes != self.ax
            or not self._site_points
        ):
            self._reset_hover()
            return

        hit_index = self._find_nearest_index(
            event.xdata, event.ydata
        )

        if hit_index == self._hovered_index:
            # No change — avoid redundant redraws
            return

        if hit_index is None:
            self._reset_hover()
            return

        # Build sizes array: default for all, hover for the hit
        sizes = np.full(
            len(self._site_points), AppStyles.Dimensions.MARKER_SIZE_DEFAULT,
            dtype=float,
        )
        sizes[hit_index] = AppStyles.Dimensions.MARKER_SIZE_HOVER
        self._scatter.set_sizes(sizes)
        self._hovered_index = hit_index
        self.canvas.setCursor(
            QCursor(Qt.CursorShape.PointingHandCursor)
        )
        self.canvas.draw_idle()

    def _on_mouse_click(self, event):
        """Show a context menu when a marker is left-clicked.

        Suppressed when the toolbar is in pan or zoom mode so the
        click is consumed by the toolbar instead.

        :param event: Matplotlib button_press_event.
        """
        if self._is_toolbar_active():
            return

        if (
            self._scatter is None
            or event.inaxes != self.ax
            or not self._site_points
            or event.button != 1  # left click only
        ):
            return

        hit_index = self._find_nearest_index(
            event.xdata, event.ydata
        )
        if hit_index is None:
            return

        site_name = self._site_points[hit_index]["site_name"]
        self._show_marker_context_menu(site_name)

    def _show_marker_context_menu(self, site_name: str) -> None:
        """Display a context menu at the cursor with actions for
        the clicked site.

        :param site_name: Name of the clicked site.
        """
        menu = QMenu(self)
        menu.setStyleSheet(AppStyles.ComboBox.context_menu())

        go_to_action = menu.addAction(f"Open {site_name}")
        open_new_action = menu.addAction(
            f"Open {site_name} in new window"
        )

        chosen = menu.exec(QCursor.pos())

        if chosen == go_to_action:
            logger.info(f"Atlas menu: open '{site_name}'")
            self.site_selected.emit(site_name)
        elif chosen == open_new_action:
            logger.info(
                f"Atlas menu: open '{site_name}' in new window"
            )
            self.site_open_new_window.emit(site_name)

    def _reset_hover(self):
        """Restore all markers to default size and reset the
        cursor."""
        if self._hovered_index is not None:
            sizes = np.full(
                len(self._site_points),
                AppStyles.Dimensions.MARKER_SIZE_DEFAULT,
                dtype=float,
            )
            self._scatter.set_sizes(sizes)
            self._hovered_index = None
            self.canvas.setCursor(self._default_cursor)
            self.canvas.draw_idle()

    def _find_nearest_index(
        self, x: float, y: float, threshold: float = 0.05
    ) -> int | None:
        """Find the index of the site marker closest to the cursor.

        Coordinates are normalised to axes range so the threshold
        works consistently regardless of zoom level.

        :param x: Cursor x in data coordinates (µm).
        :param y: Cursor y in data coordinates (µm).
        :param threshold: Maximum normalised distance to match.
        :return: Index into ``_site_points``, or *None*.
        """
        xlim = self.ax.get_xlim()
        ylim = self.ax.get_ylim()
        x_range = xlim[1] - xlim[0]
        y_range = ylim[1] - ylim[0]

        if x_range == 0 or y_range == 0:
            return None

        best_dist = float("inf")
        best_index = None

        for i, entry in enumerate(self._site_points):
            mx, my = self._marker_position(entry)
            dx = (x - mx) / x_range
            dy = (y - my) / y_range
            dist = (dx ** 2 + dy ** 2) ** 0.5
            if dist < best_dist and dist < threshold:
                best_dist = dist
                best_index = i

        return best_index

    # =================================================================
    # Helpers
    # =================================================================

    @staticmethod
    def _resolve_project_root(metadata: dict) -> Path | None:
        """Resolve the project root from the consolidated metadata.

        :param metadata: Consolidated metadata dictionary.
        :return: Path object, or *None* if the directory does not
            exist on the current machine.
        """
        raw = metadata.get("ProjectRootPath")
        if raw is None:
            return None
        path = Path(raw)
        if path.is_dir():
            return path
        logger.debug(
            f"ProjectRootPath not accessible: {raw}"
        )
        return None