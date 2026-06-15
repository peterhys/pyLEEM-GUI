"""Qt-free metadata display, numeric lookup, and ImageJ Info helpers."""

import re
from datetime import datetime

# Raw byte fields hidden from the metadata display.
META_SKIP = {"markup_data", "extra_leem_data", "LEEMdata"}

# Per-frame header in exported ImageJ Info text.
_FRAME_HEADER = re.compile(r"^\[Frame (\d+)\]$")


def parse_metadata_entry(value):
    """Normalize a metadata entry to ``(value, unit)``."""
    if isinstance(value, tuple) and len(value) == 2:
        return value
    return value, None


def numeric_value_or_none(value):
    """``float(value)`` for a plain numeric entry, else None."""
    if isinstance(value, (bytes, bytearray, datetime, bool)):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def numeric_metadata_value(meta, key):
    """Numeric metadata value for ``key``, or None."""
    if key in META_SKIP or key not in meta:
        return None
    return numeric_value_or_none(parse_metadata_entry(meta[key])[0])


def numeric_metadata_fields(metas):
    """Numeric metadata fields as ``(key, unit)`` pairs."""
    units = {}
    for meta in metas:
        for key, raw in meta.items():
            if key in META_SKIP:
                continue
            value, unit = parse_metadata_entry(raw)
            if numeric_value_or_none(value) is None:
                continue
            name = str(key)
            if name not in units or (unit and not units[name]):
                units[name] = str(unit) if unit else ""
    return list(units.items())


def axis_label(key, unit=""):
    """Axis label with a square-bracket unit suffix."""
    return f"{key} [{unit}]" if unit else str(key)


def metadata_rows(meta):
    """Return ``(key, value, unit)`` display rows."""
    rows = []
    for key, raw in meta.items():
        if key in META_SKIP:
            continue
        value, unit = parse_metadata_entry(raw)
        if isinstance(value, bytes):
            continue
        if isinstance(value, datetime):
            value = value.isoformat()
        rows.append((str(key), str(value), str(unit) if unit else ""))
    return rows


def _info_line(key, value, unit):
    """One ``key = value [unit]`` line; the unit bracket is dropped if empty."""
    return f"{key} = {value} [{unit}]" if unit else f"{key} = {value}"


def imagej_info(frame_metadatas):
    """Build ImageJ ``Info`` text for exported TIFF metadata."""
    single = len(frame_metadatas) == 1
    blocks = []
    for n, meta in enumerate(frame_metadatas):
        body = "\n".join(_info_line(*row) for row in metadata_rows(meta))
        blocks.append(body if single else "[Frame %d]\n%s" % (n, body))
    return "\n".join(blocks)


def _coerce_value(text):
    """Coerce a metadata value string to int or float when numeric, else keep it."""
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        return text


def _split_value_unit(rest):
    """Split a metadata value string into ``(value, unit)``."""
    rest = rest.strip()
    if rest.endswith("]") and " [" in rest:
        value_text, unit = rest.rsplit(" [", 1)
        return _coerce_value(value_text.strip()), (unit[:-1].strip() or None)
    return _coerce_value(rest), None


def parse_imagej_info(info, n_frames):
    """Parse pyLEEM-GUI ImageJ ``Info`` text into per-frame metadata."""
    metas = [{} for _ in range(n_frames)]
    if not info:
        return metas
    current = 0
    for line in info.splitlines():
        line = line.strip()
        if not line:
            continue
        header = _FRAME_HEADER.match(line)
        if header:
            current = int(header.group(1))
            continue
        if " = " not in line:
            continue
        key, rest = line.split(" = ", 1)
        if 0 <= current < n_frames:
            metas[current][key.strip()] = _split_value_unit(rest)
    return metas
