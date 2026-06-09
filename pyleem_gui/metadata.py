"""Metadata formatting.

Extra formatting for metadata. This is used to show better metdata data in
the GUI. We also incorprate metadata into the TIFF export.
"""

from datetime import datetime

# Binary blobs / raw byte fields to hide from the metadata display.
META_SKIP = {"markup_data", "extra_leem_data", "LEEMdata"}


def _parse_entry(value):
    """Normalize a metadata entry to ``(value, unit)``.

    Entries are either a ``(value, unit)`` tuple or a bare value.
    """
    if isinstance(value, tuple) and len(value) == 2:
        return value
    return value, None


def metadata_rows(meta):
    """Return ``(key, value, unit)`` display rows for a metadata dict.

    Skips the binary blobs in :data:`META_SKIP` and any bytes-valued entry;
    datetimes are rendered with ``isoformat()``. Units default to an empty string.
    """
    rows = []
    for key, raw in meta.items():
        if key in META_SKIP:
            continue
        value, unit = _parse_entry(raw)
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
    """Build the ImageJ ``Info`` text for an exported TIFF.

    ``frame_metadatas`` is the list of per-frame metadata dicts in export order. A
    single frame yields plain ``key = value [unit]`` lines; multiple frames are
    grouped into ``[Frame N]`` sections. This is the format the bundled ImageJ
    overlay plugins (see ``pyleem-plugin-test``) parse to draw each slice's
    metadata, so the skip-list here matches theirs.
    """
    single = len(frame_metadatas) == 1
    blocks = []
    for n, meta in enumerate(frame_metadatas):
        body = "\n".join(_info_line(*row) for row in metadata_rows(meta))
        blocks.append(body if single else "[Frame %d]\n%s" % (n, body))
    return "\n".join(blocks)
