import os

import pytest

from pyleem_gui.image import ImageLayer

from .support import FakeReader

# Run Qt headless so GUI tests work without a display.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(autouse=True)
def _no_external_plugins(monkeypatch):
    """Keep plugin discovery hermetic."""
    monkeypatch.setattr("pyleem_gui.plugins.discovery._external_dirs", lambda: [])


@pytest.fixture
def folder(tmp_path):
    for i in range(3):
        (tmp_path / f"{i:03d}.dat").write_bytes(b"")
    return tmp_path


@pytest.fixture
def images(folder):
    layer = ImageLayer(reader_factory=FakeReader)
    layer.open_folder(folder)
    return layer
