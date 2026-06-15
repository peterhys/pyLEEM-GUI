"""Tests for the Qt-free metadata formatting."""

from datetime import datetime

from pyleem_gui.metadata import (
    META_SKIP,
    axis_label,
    imagej_info,
    metadata_rows,
    numeric_metadata_fields,
    numeric_metadata_value,
    parse_imagej_info,
    parse_metadata_entry,
)


def test_metadata_rows_value_unit_and_bare_value():
    rows = metadata_rows(
        {
            "ImageWidth": (1024, None),  # (value, unit) with no unit
            "Pressure": (1.2e-9, "mbar"),  # (value, unit)
            "filetype": "UViewdat",  # bare value, not a tuple
        }
    )
    assert rows == [
        ("ImageWidth", "1024", ""),
        ("Pressure", "1.2e-09", "mbar"),
        ("filetype", "UViewdat", ""),
    ]


def test_metadata_rows_skips_blobs_and_bytes():
    rows = metadata_rows(
        {
            "ImageWidth": (8, None),
            "markup_data": ("deadbeef", None),  # in META_SKIP
            "extra_leem_data": (b"\x00\x01", None),  # in META_SKIP
            "LEEMdata": (b"raw", None),  # in META_SKIP
            "blob": (b"rawbytes", None),  # bytes value -> skipped
        }
    )
    assert rows == [("ImageWidth", "8", "")]
    assert {"markup_data", "extra_leem_data", "LEEMdata"} <= META_SKIP


def test_metadata_rows_formats_datetime_isoformat():
    rows = metadata_rows({"TimeStamp": (datetime(2024, 1, 2, 3, 4, 5), None)})
    assert rows == [("TimeStamp", "2024-01-02T03:04:05", "")]


def test_parse_metadata_entry_normalizes_bare_values():
    assert parse_metadata_entry((3.2, "eV")) == (3.2, "eV")
    assert parse_metadata_entry("UViewdat") == ("UViewdat", None)


def test_numeric_metadata_value_filters_non_numeric_values():
    meta = {
        "Energy": (12.5, "eV"),
        "TimeStamp": (datetime(2024, 1, 2), None),
        "Enabled": (True, None),
        "blob": (b"raw", None),
        "Name": ("abc", None),
        "markup_data": (1, None),
    }
    assert numeric_metadata_value(meta, "Energy") == 12.5
    assert numeric_metadata_value(meta, "TimeStamp") is None
    assert numeric_metadata_value(meta, "Enabled") is None
    assert numeric_metadata_value(meta, "blob") is None
    assert numeric_metadata_value(meta, "Name") is None
    assert numeric_metadata_value(meta, "markup_data") is None


def test_numeric_metadata_fields_preserves_units_and_order():
    fields = numeric_metadata_fields(
        [
            {"Energy": (12.5, "eV"), "Name": ("abc", None)},
            {"Pressure": (1.2e-9, "mbar"), "Energy": (12.6, "eV")},
        ]
    )
    assert fields == [("Energy", "eV"), ("Pressure", "mbar")]


def test_axis_label_uses_square_brackets_for_units():
    assert axis_label("Energy", "eV") == "Energy [eV]"
    assert axis_label("Frame") == "Frame"


# ImageJ Info text
def test_imagej_info_single_frame_has_no_headers():
    info = imagej_info([{"ImageWidth": (1024, None), "Pressure": (1.2e-9, "mbar")}])
    assert info == "ImageWidth = 1024\nPressure = 1.2e-09 [mbar]"


def test_imagej_info_multi_frame_uses_frame_sections():
    info = imagej_info([{"ImageWidth": (4, None)}, {"ImageWidth": (8, None)}])
    assert info == "[Frame 0]\nImageWidth = 4\n[Frame 1]\nImageWidth = 8"


def test_imagej_info_skips_blob_keys():
    info = imagej_info([{"ImageWidth": (4, None), "markup_data": (b"x", None)}])
    assert info == "ImageWidth = 4"


def test_parse_single_frame_info():
    info = "Energy = 5.0 [eV]\nStart Voltage = 10\nLabel = scan one"
    assert parse_imagej_info(info, 1) == [
        {
            "Energy": (5.0, "eV"),
            "Start Voltage": (10, None),
            "Label": ("scan one", None),
        }
    ]


def test_parse_multiframe_info():
    info = "[Frame 0]\nEnergy = 1 [eV]\n[Frame 1]\nEnergy = 2 [eV]"
    assert parse_imagej_info(info, 2) == [{"Energy": (1, "eV")}, {"Energy": (2, "eV")}]


def test_parse_info_roundtrips_export():
    # imagej_info -> parse_imagej_info preserves units and numeric values so the
    # correlation plot still sees numeric metadata.
    src = [
        {"Energy": (1.5, "eV"), "Temperature": (300, "K")},
        {"Energy": (2.5, "eV"), "Temperature": (310, "K")},
    ]
    assert parse_imagej_info(imagej_info(src), 2) == src


def test_parse_empty_or_missing_info():
    assert parse_imagej_info(None, 3) == [{}, {}, {}]
    assert parse_imagej_info("", 2) == [{}, {}]
    # A line without " = " is ignored; the rest still parses.
    assert parse_imagej_info("plain text\nEnergy = 1 [eV]", 1) == [
        {"Energy": (1, "eV")}
    ]


def test_parse_dates_stay_strings():
    metas = parse_imagej_info("TimeStamp = 2024-01-01T00:00:00", 1)
    assert metas == [{"TimeStamp": ("2024-01-01T00:00:00", None)}]


def test_parse_whitespace_unit_is_none():
    assert parse_imagej_info("Pressure = 5 [ ]", 1) == [{"Pressure": (5, None)}]
