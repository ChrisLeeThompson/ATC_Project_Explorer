"""
Image Metadata Parser

Module handles extraction of metadata from images in ATC project
site directories.  Two image types are encountered:

    - **.tif** files from the FEI/ThermoFisher instrument.  These
      contain rich metadata in TIFF tags:

        - Tag 34682 (``FEI_HELIOS``): key-value microscope metadata
          (beam, stage, scan, detector settings, etc.).
        - Tag 34683 (``FEI_TITAN``): XML metadata with acquisition
          parameters, optics, stage settings, and vacuum properties.

    - **.png** files. These may contain
      FEI XML metadata embedded as raw text in the file bytes.
      The metadata uses the same XML schema as TIFF tag 34683.

      Large elements within the ``MatchInformationCollection``
      section (``<Image>`` and ``<ImageMetadata>``) are stripped
      before parsing to keep the result concise.  If no embedded
      XML is found, only basic file information (dimensions, file
      size) is returned.

Usage::

    from script_modules.parsers.image_metadata_parser import (
        extract_image_metadata,
    )

    metadata = extract_image_metadata(Path("path/to/image.tif"))

For batch XML-only extraction (e.g. pattern data parsing)::

    from script_modules.parsers.image_metadata_parser import (
        extract_xml_metadata,
    )

    xml_only = extract_xml_metadata(Path("path/to/image.png"))
"""
import logging
import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import matplotlib.image as mpimg


logger = logging.getLogger(__name__)


# -----------------------------------------------------------------
# Public API
# -----------------------------------------------------------------

def extract_image_metadata(image_path: Path) -> dict:
    """Extract metadata from an image file.

    For ``.tif`` / ``.tiff`` files, reads FEI TIFF tags 34682 and
    34683.  For all other formats, scans the raw file bytes for
    embedded FEI XML metadata.  Basic file information (dimensions,
    file size) is always included.

    :param image_path: Absolute path to the image file.
    :return: Dictionary containing the extracted metadata.  Always
        includes an ``"ImageInfo"`` section.  TIF files additionally
        include ``"MicroscopeMetadata"`` and/or ``"XMLMetadata"``
        sections.  Non-TIF files with embedded XML include
        ``"XMLMetadata"``.
    """
    result: dict[str, Any] = {}

    # Basic file info (available for all formats)
    result["ImageInfo"] = _get_basic_info(image_path)

    # Detect actual format from magic bytes and flag mismatches.
    # The FEI instrument software may write JPEG data with a
    # ``.png`` extension; this prevents embedded XML recovery.
    try:
        raw_head = image_path.read_bytes()[:8]
        actual = _detect_actual_format(raw_head)
        if actual is not None:
            result["ImageInfo"]["ActualFormat"] = actual.upper()
            if (
                actual == "jpeg"
                and image_path.suffix.lower() == ".png"
            ):
                result["ImageInfo"]["FormatNote"] = (
                    "File is JPEG despite .png extension — "
                    "embedded XML metadata is not available"
                )
    except OSError:
        pass

    suffix = image_path.suffix.lower()

    # TIF-specific metadata (TIFF tags)
    if suffix in (".tif", ".tiff"):
        tif_meta = _extract_tif_metadata(image_path)
        if tif_meta:
            result.update(tif_meta)

    # Non-TIF: scan raw bytes for embedded FEI XML metadata
    if "XMLMetadata" not in result:
        embedded = _extract_embedded_xml_metadata(image_path)
        if embedded:
            result.update(embedded)

    return result


def extract_xml_metadata(image_path: Path) -> dict | None:
    """Extract only the XML metadata from an image file.

    This is a lightweight alternative to ``extract_image_metadata``
    that skips basic file info (dimensions, file size) and format
    detection.  It only scans the raw bytes for embedded FEI XML
    metadata, making it significantly faster for batch operations
    where only the XML content is needed (e.g. pattern data
    extraction during consolidation).

    For ``.tif`` / ``.tiff`` files, reads TIFF tag 34683.
    For all other formats, scans raw bytes for embedded XML.

    :param image_path: Absolute path to the image file.
    :return: Dictionary with ``"XMLMetadata"`` key, or *None*
        if no XML metadata was found.
    """
    suffix = image_path.suffix.lower()

    if suffix in (".tif", ".tiff"):
        tif_meta = _extract_tif_metadata(image_path)
        if tif_meta and "XMLMetadata" in tif_meta:
            return {"XMLMetadata": tif_meta["XMLMetadata"]}
        return None

    embedded = _extract_embedded_xml_metadata(image_path)
    return embedded


# -----------------------------------------------------------------
# Basic File Info
# -----------------------------------------------------------------

def _get_basic_info(image_path: Path) -> dict:
    """Build a basic info dict from the file on disk.

    :param image_path: Path to the image file.
    :return: Dict with file name, size, and image dimensions.
    """
    info: dict[str, Any] = {
        "FileName": image_path.name,
        "FileExtension": image_path.suffix,
    }

    try:
        stat = image_path.stat()
        size_bytes = stat.st_size
        if size_bytes >= 1_048_576:
            info["FileSize"] = f"{size_bytes / 1_048_576:.1f} MB"
        elif size_bytes >= 1024:
            info["FileSize"] = f"{size_bytes / 1024:.1f} KB"
        else:
            info["FileSize"] = f"{size_bytes} bytes"
    except OSError:
        info["FileSize"] = "Unknown"

    # Image dimensions
    try:
        img = mpimg.imread(str(image_path))
        if img.ndim >= 2:
            h, w = img.shape[:2]
            info["Width"] = w
            info["Height"] = h
            if img.ndim == 3:
                info["Channels"] = img.shape[2]
            info["DataType"] = str(img.dtype)
    except Exception:
        try:
            from PIL import Image
            with Image.open(image_path) as pil_img:
                info["Width"] = pil_img.size[0]
                info["Height"] = pil_img.size[1]
                info["Format"] = pil_img.format or "Unknown"
        except Exception:
            logger.debug(
                f"Could not read image dimensions: "
                f"{image_path.name}",
                exc_info=True,
            )

    return info


# -----------------------------------------------------------------
# TIF Metadata Extraction
# -----------------------------------------------------------------

def _extract_tif_metadata(tif_path: Path) -> dict | None:
    """Extract FEI microscope metadata from a TIF file.

    Reads TIFF tags 34682 (``FEI_HELIOS``, key-value pairs) and
    34683 (``FEI_TITAN``, XML string).

    :param tif_path: Path to the ``.tif`` file.
    :return: Dict with ``"MicroscopeMetadata"`` and/or
        ``"XMLMetadata"`` keys, or *None* on failure.
    """
    try:
        import tifffile
    except ImportError:
        logger.debug("tifffile not installed — skipping TIF metadata")
        return None

    result: dict[str, Any] = {}

    try:
        with tifffile.TiffFile(tif_path) as tif:
            page = tif.pages[0]
            tags = page.tags

            # Tag 34682: FEI_HELIOS (key-value metadata)
            if 34682 in tags:
                data = tags[34682].value
                if isinstance(data, dict):
                    result["MicroscopeMetadata"] = (
                        _clean_metadata_keys(data)
                    )

            # Tag 34683: FEI_TITAN (XML metadata)
            if 34683 in tags:
                xml_data = tags[34683].value
                if isinstance(xml_data, str) and xml_data.strip():
                    parsed_xml = _parse_xml_metadata(xml_data)
                    if parsed_xml:
                        # Unwrap root "Metadata" key if present
                        result["XMLMetadata"] = parsed_xml.get(
                            "Metadata", parsed_xml
                        )

    except Exception:
        logger.error(
            f"Error extracting TIF metadata: {tif_path.name}",
            exc_info=True,
        )
        return None

    return result if result else None


# -----------------------------------------------------------------
# Embedded XML Metadata (PNG files)
# -----------------------------------------------------------------

def _extract_embedded_xml_metadata(
    image_path: Path,
) -> dict | None:
    """Scan raw file bytes for embedded FEI XML metadata.

    The ``MatchInformationCollection`` custom section can contain
    very large child elements that are not useful for display:

    - ``<Image>`` — a base64-encoded reference image.
    - ``<ImageMetadata>`` — a full HTML-entity-encoded copy of the
      reference image's metadata XML.

    Both are stripped before parsing so the tree stays concise
    while preserving the useful match fields (Timestamp,
    MatchSuccess, MatchQuality, PatternCenterPositionPx,
    Transformation, etc.).

    :param image_path: Path to the image file.
    :return: Dict with ``"XMLMetadata"`` key, or *None* if no
        embedded XML was found.
    """
    try:
        raw = image_path.read_bytes()
    except OSError:
        logger.debug(
            "Could not read file for embedded XML scan: "
            f"{image_path.name}",
            exc_info=True,
        )
        return None

    # Detect actual file format vs. extension.  The FEI
    # instrument software sometimes writes JPEG data with a
    # ``.png`` extension.  JPEG files cannot carry the raw
    # embedded XML that real PNG files contain, so log a
    # diagnostic and bail early.
    actual_format = _detect_actual_format(raw)
    if actual_format == "jpeg" and image_path.suffix.lower() == ".png":
        logger.debug(
            f"File is JPEG despite .png extension, no "
            f"embedded XML possible: {image_path.name}"
        )
        return None

    # Locate the outer <Metadata ...>...</Metadata> block.
    # Try several start forms to accommodate FEI XML with or
    # without namespace attributes on the root element.
    end_marker = b"</Metadata>"

    start_idx = -1
    for start_marker in (b"<Metadata ", b"<Metadata>"):
        start_idx = raw.find(start_marker)
        if start_idx != -1:
            break

    if start_idx == -1:
        logger.debug(
            f"No embedded XML metadata found in: "
            f"{image_path.name}"
        )
        return None

    end_idx = raw.find(end_marker, start_idx)
    if end_idx == -1:
        return None

    xml_bytes = raw[start_idx : end_idx + len(end_marker)]

    # Decode bytes to string.  Try strict UTF-8 first; fall back
    # to Latin-1 which correctly maps single-byte characters such
    # as µ (micro sign, 0xB5) that the FEI software may write
    # without the leading 0xC2 byte required by UTF-8.
    try:
        xml_str = xml_bytes.decode("utf-8")
    except UnicodeDecodeError:
        xml_str = xml_bytes.decode("latin-1")

    # Strip bulky elements from MatchInformationCollection
    # before parsing.  These are large and not useful for display.
    xml_str = re.sub(
        r"<Image>.*?</Image>", "", xml_str, flags=re.DOTALL
    )
    xml_str = re.sub(
        r"<ImageMetadata>.*?</ImageMetadata>",
        "",
        xml_str,
        flags=re.DOTALL,
    )

    result: dict[str, Any] = {}

    parsed = _parse_xml_metadata(xml_str)
    if parsed:
        result["XMLMetadata"] = parsed.get("Metadata", parsed)

    return result if result else None


# -----------------------------------------------------------------
# File Format Detection
# -----------------------------------------------------------------

def _detect_actual_format(raw: bytes) -> str | None:
    """Detect the actual image format from magic bytes.

    Returns ``"jpeg"``, ``"png"``, ``"tiff"``, or *None* if
    the format is not recognised.

    :param raw: Raw file bytes (only the first 8 are inspected).
    :return: Format string or *None*.
    """
    if raw[:2] == b"\xff\xd8":
        return "jpeg"
    if raw[:4] == b"\x89PNG":
        return "png"
    if raw[:2] in (b"II", b"MM"):
        return "tiff"
    return None


# -----------------------------------------------------------------
# Key-Value Metadata Helpers
# -----------------------------------------------------------------

def _clean_metadata_keys(data: Any) -> Any:
    """Recursively remove trailing ``=`` from metadata dict keys.

    ThermoFisher TIFF tag 34682 stores keys with trailing ``=``
    characters (e.g. ``"EBeam="``).  This strips them for cleaner
    display and access.

    :param data: Metadata structure (dict, list, or primitive).
    :return: Cleaned structure.
    """
    if isinstance(data, dict):
        return {
            (key.rstrip("=") if isinstance(key, str) else key):
            _clean_metadata_keys(value)
            for key, value in data.items()
        }
    elif isinstance(data, list):
        return [_clean_metadata_keys(item) for item in data]
    return data


# -----------------------------------------------------------------
# XML Metadata Helpers
# -----------------------------------------------------------------

def _parse_xml_metadata(xml_string: str) -> dict | None:
    """Parse an FEI XML metadata string into a nested dict.

    Handles the XML schema used by FEI/ThermoFisher instruments,
    whether sourced from TIFF tag 34683 or from raw bytes embedded
    in PNG files.

    :param xml_string: Raw XML string.
    :return: Parsed dict, or *None* on failure.
    """
    try:
        root = ET.fromstring(xml_string)
        result: dict = {}
        _extract_xml_element(root, result)
        return result
    except ET.ParseError:
        logger.debug(
            "XML parsing failed for TIF metadata", exc_info=True
        )
        return None
    except Exception:
        logger.error(
            "Error parsing XML metadata", exc_info=True
        )
        return None


def _extract_xml_element(
    element: ET.Element, parent_dict: dict
):
    """Recursively extract an XML element into a dictionary.

    Handles leaf nodes, nodes with attributes, and branch nodes.
    Duplicate child tags with a ``scope`` attribute are grouped
    under the scope name.

    :param element: The XML element to extract.
    :param parent_dict: The parent dict to insert into.
    """
    # Strip namespace prefix
    tag = (
        element.tag.split("}")[-1]
        if "}" in element.tag
        else element.tag
    )
    text = (
        element.text.strip()
        if element.text and element.text.strip()
        else None
    )
    attrs = dict(element.attrib)
    children = list(element)

    if not children and not attrs:
        # Leaf with text only
        if text:
            parent_dict[tag] = _convert_text_value(text)

    elif not children and attrs:
        # Leaf with attributes
        parent_dict[tag] = attrs
        if text:
            parent_dict[tag]["_text"] = text

    else:
        # Branch with children
        child_dict: dict = {}
        if attrs:
            child_dict.update(attrs)
        if text:
            child_dict["_text"] = text

        child_tags = [
            c.tag.split("}")[-1] if "}" in c.tag else c.tag
            for c in children
        ]
        duplicate_tags = {
            t for t in child_tags if child_tags.count(t) > 1
        }

        for child in children:
            child_tag = (
                child.tag.split("}")[-1]
                if "}" in child.tag
                else child.tag
            )

            if child_tag in duplicate_tags:
                if "scope" in child.attrib:
                    if child_tag not in child_dict:
                        child_dict[child_tag] = {}
                    scope = child.attrib["scope"]
                    scope_dict: dict = {}
                    for grandchild in child:
                        _extract_xml_element(
                            grandchild, scope_dict
                        )
                    if (
                        len(scope_dict) == 1
                        and scope in scope_dict
                    ):
                        child_dict[child_tag][scope] = (
                            scope_dict[scope]
                        )
                    else:
                        child_dict[child_tag][scope] = scope_dict
                else:
                    if child_tag not in child_dict:
                        child_dict[child_tag] = []
                    item_dict: dict = {}
                    _extract_xml_element(child, item_dict)
                    child_dict[child_tag].append(
                        item_dict.get(child_tag, {})
                    )
            else:
                _extract_xml_element(child, child_dict)

        parent_dict[tag] = child_dict


def _convert_text_value(text: str) -> int | float | str:
    """Convert a text string to int, float, or leave as str.

    :param text: The text value to convert.
    :return: Converted value.
    """
    try:
        if "." in text or "e" in text.lower():
            return float(text)
        return int(text)
    except ValueError:
        return text