"""
Value Utilities

Generic, dependency-free helpers for parsing and formatting the
scalar values that appear throughout ATC/FEI metadata: numeric
value+unit strings, durations, and physical-length unit
conversions.

Unit conversion is driven by a single canonical table,
:data:`UNIT_TO_METRES`, so there is exactly one place where the
recognized length units (and their micro-sign spellings) are
defined.  The three public converters differ in their output unit
and fallback policy:

    - :func:`to_metres`         — value+unit string -> metres, or
                                  *None* on an unrecognized unit
                                  (case-sensitive lookup).
    - :func:`to_micrometres`    — value+unit string -> µm; unitless
                                  or unrecognized units are assumed
                                  to already be µm; 0.0 on failure.
    - :func:`convert_to_metres` — already-extracted numeric + its raw
                                  source -> metres; an unrecognized or
                                  absent unit is assumed to be metres.
"""
import logging
import re


logger = logging.getLogger(__name__)


# =====================================================================
# Canonical unit table
# =====================================================================

# Single source of truth for length-unit -> metres factors.  Both
# micro-sign codepoints are included so the Latin-1 micro sign
# (U+00B5) and the Greek small letter mu (U+03BC) resolve correctly.
UNIT_TO_METRES: dict[str, float] = {
    "nm": 1e-9,
    "µm": 1e-6,        # Latin-1 micro sign (0xB5)
    "\u00b5m": 1e-6,   # duplicate of the literal above; keeps the codepoint explicit
    "\u03bcm": 1e-6,   # Greek lowercase mu
    "um": 1e-6,        # ASCII fallback
    "mm": 1e-3,
    "m": 1.0,
}


# =====================================================================
# Numeric value+unit parsing
# =====================================================================

# Regex for splitting a "value unit" string with scientific-notation
# support (e.g. "-192.585 nm", "7.8125E-08 m").
_VALUE_UNIT_RE = re.compile(
    r"([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\s*(.*)"
)


def parse_numeric_value(raw: str) -> tuple[float, str] | None:
    """Extract the leading numeric value and its trailing unit
    from a string (e.g. ``"150 nm"``, ``"12 °"``).

    Does *not* accept scientific notation — use
    :func:`parse_unit_value` or :func:`extract_numeric` for values
    that may be written like ``"6.48E-07"``.

    :param raw: Raw string value from the metadata.
    :return: ``(value, unit)`` tuple, or *None* if no number
        is found.  The unit string is empty when no unit is
        present.
    """
    if not raw:
        return None
    match = re.match(
        r"([+-]?\d+(?:\.\d+)?)\s*(.*)", raw.strip()
    )
    if match:
        value = float(match.group(1))
        unit = match.group(2).strip()
        return value, unit
    return None


def parse_unit_value(raw) -> tuple[float, str] | None:
    """Parse a value+unit string into ``(numeric_value, unit_str)``.

    Handles strings like ``"-192.58 nm"``, ``"17 µm"``,
    ``"-180 °"``, and scientific notation.  Also handles bare
    numeric values (int/float) and dicts with a ``"_text"`` key
    (from XML attribute nodes).

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


def extract_numeric(value) -> float | None:
    """Coerce a value to float, handling various types produced
    by the XML parser.

    - ``int`` / ``float``: returned directly.
    - ``str``: a direct ``float()`` conversion is attempted first
      (handles scientific notation like ``6.48E-07``).  If that
      fails, :func:`parse_numeric_value` is used to extract the
      leading number from values with unit suffixes (e.g.
      ``"-4.221 mm"``).
    - ``dict`` with ``"_text"`` key: the ``_text`` value is
      extracted and processed recursively.

    :param value: Value from parsed metadata.
    :return: Float, or *None* if conversion fails.
    """
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict):
        # XML parser may wrap text in a dict with "_text" key
        text = value.get("_text")
        if text is not None:
            return extract_numeric(text)
        return None
    if isinstance(value, str):
        # Try direct float first — handles scientific notation
        # (e.g. "6.4830436688441935E-07") which the regex in
        # parse_numeric_value would split incorrectly.
        try:
            return float(value)
        except (ValueError, TypeError):
            pass
        # Fall back to parse_numeric_value for unit strings
        # (e.g. "-4.770 mm", "271.493 °")
        result = parse_numeric_value(value)
        if result is not None:
            return result[0]
    return None


# =====================================================================
# Duration parsing / formatting
# =====================================================================

# .NET ``TimeSpan`` form with a leading day count: ``d.hh:mm:ss``.
# Anchored and requiring the literal '.', so it can never match a
# plain ``HH:MM:SS`` string.
_DURATION_DAYS_RE = re.compile(
    r"^(\d+)\.(\d{1,2}):(\d{1,2}):(\d{1,2})$"
)


def parse_duration_to_seconds(duration_str: str) -> int | None:
    """Parse a duration string to total seconds.

    Accepts the plain ``HH:MM:SS`` form and the .NET ``TimeSpan``
    ``d.hh:mm:ss`` form with a leading day count (e.g.
    ``"1.01:40:59"``), which FEI software emits for activities that
    span more than a day — most notably overnight ``Delay``
    activities.  Hours in the plain form may exceed 24 (e.g.
    ``"25:00:00"``).

    Zero-length durations (``"00:00:00"``) return *None* by design, so
    they are excluded from duration means and totals rather than
    counted as real zero-time activities.

    :param duration_str: Duration string (e.g. ``"01:40:59"`` or
        ``"1.01:40:59"``).
    :return: Total seconds, or *None* if the string is empty, all
        zeros, or cannot be parsed.
    """
    if not duration_str:
        return None

    text = duration_str.strip()

    # Day form first; plain HH:MM:SS falls through to the split below.
    day_match = _DURATION_DAYS_RE.match(text)
    if day_match:
        days, hours, minutes, seconds = (
            int(g) for g in day_match.groups()
        )
        total = (
            days * 86400 + hours * 3600 + minutes * 60 + seconds
        )
        return total if total > 0 else None

    try:
        parts = text.split(":")
        if len(parts) == 3:
            hours = int(parts[0])
            minutes = int(parts[1])
            seconds = int(parts[2])
            total = hours * 3600 + minutes * 60 + seconds
            return total if total > 0 else None
    except (ValueError, IndexError):
        logger.debug(f"Could not parse duration: '{duration_str}'")
    return None


def format_seconds(total_seconds: int) -> str:
    """Format total seconds as an ``HH:MM:SS`` string.

    :param total_seconds: Non-negative integer seconds.
    :return: Formatted duration string.
    """
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


# =====================================================================
# Length-unit conversion
# =====================================================================

def to_metres(raw) -> float | None:
    """Parse a value+unit string and convert to metres.

    Unit lookup is case-sensitive (FEI metadata always uses the
    canonical lowercase spellings).

    :param raw: Value string (e.g. ``"-6.18 µm"``), or a bare
        numeric / ``{"_text": ...}`` dict.
    :return: Value in metres, or *None* if the unit is not
        recognized or the string cannot be parsed.
    """
    parsed = parse_unit_value(raw)
    if parsed is None:
        return None
    value, unit = parsed
    factor = UNIT_TO_METRES.get(unit)
    if factor is None:
        return None
    return value * factor


def to_micrometres(raw) -> float:
    """Parse a value string to µm.

    Handles ``"17 µm"``, ``"398 nm"``, ``"1.5 μm"``, ``"0 m"``,
    etc.  Unitless or unrecognized units are assumed to already be
    µm.  Returns 0.0 on failure.

    :param raw: Value string (stringified if not already a str).
    :return: Value in µm.
    """
    result = parse_numeric_value(str(raw))
    if result is None:
        return 0.0
    value, unit = result
    factor = UNIT_TO_METRES.get(unit.lower().strip())
    if factor is None:
        # Unitless or unrecognized — assume the value is already µm.
        return value
    # metres-per-unit -> µm-per-unit
    return value * factor * 1e6


def convert_to_metres(numeric_value: float, raw_value) -> float:
    """Convert an already-extracted numeric value to metres based
    on the unit string detected in its raw source value.

    Used for stage positions from the StageCollection custom
    section, where values are stored as strings with unit suffixes
    (e.g. ``"-4.770 mm"``).  An unrecognized or absent unit is
    assumed to be metres.

    :param numeric_value: The already-extracted numeric value.
    :param raw_value: The original raw value (str, dict, or
        numeric) from which to detect the unit.
    :return: Value in metres.
    """
    unit_str = _extract_unit_string(raw_value)
    if unit_str is None:
        # No unit detected — assume metres
        return numeric_value
    factor = UNIT_TO_METRES.get(unit_str.lower().strip())
    if factor is None:
        # Unknown unit — return as-is and log
        logger.debug(f"Unknown unit '{unit_str}', assuming metres")
        return numeric_value
    return numeric_value * factor


def _extract_unit_string(raw_value) -> str | None:
    """Extract the unit suffix from a raw metadata value.

    :param raw_value: String, dict with ``"_text"``, or numeric.
    :return: Unit string (e.g. ``"mm"``), or *None*.
    """
    if isinstance(raw_value, dict):
        text = raw_value.get("_text")
        if text is not None:
            return _extract_unit_string(text)
        # Check for explicit "unit" attribute from XML
        unit = raw_value.get("unit")
        if unit is not None:
            return str(unit)
        return None
    if isinstance(raw_value, str):
        result = parse_numeric_value(raw_value)
        if result is not None:
            _, unit = result
            return unit if unit else None
    return None