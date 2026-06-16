"""Plugin discovery and external plugin loading."""

import importlib
import importlib.util
import logging
import os
import pkgutil
import sys
from pathlib import Path

from .spec import PLUGINS

log = logging.getLogger(__name__)

# Builtin and Metadata anchor the tab bar ahead of ordered plugins.
PINNED_TITLES = ("Builtin", "Metadata")


def discover_plugins(external_dirs=None):
    """Import built-in and external plugins and return ordered specs."""
    _import_builtin_plugins()
    dirs = _external_dirs() if external_dirs is None else external_dirs
    for directory in dirs:
        _import_dir(Path(directory))
    return _ordered(PLUGINS)


def load_plugins(paths):
    """Import plugin files or directories and return ordered specs."""
    for path in paths:
        path = Path(path)
        if path.is_dir():
            _import_dir(path)
        elif path.is_file():
            _import_file(path)
    return _ordered(PLUGINS)


def _ordered(plugins):
    def key(plugin):
        if plugin.title in PINNED_TITLES:
            return (0, PINNED_TITLES.index(plugin.title), plugin.order, plugin.title)
        return (1, 0, plugin.order, plugin.title)

    return sorted(plugins, key=key)


def _import_builtin_plugins():
    """Import every submodule of this package; only plugin modules register."""
    import pyleem_gui.plugins as package

    for info in pkgutil.iter_modules(package.__path__):
        importlib.import_module(f"{package.__name__}.{info.name}")


def _external_dirs():
    """User plugin folders: ``~/.pyleem/plugins`` and ``PYLEEM_PLUGIN_PATH``."""
    dirs = [Path.home() / ".pyleem" / "plugins"]
    dirs += [
        Path(p) for p in os.environ.get("PYLEEM_PLUGIN_PATH", "").split(os.pathsep) if p
    ]
    return dirs


def _import_dir(directory):
    if directory.is_dir():
        for file in sorted(directory.glob("*.py")):
            _import_file(file)


def _import_file(file):
    """Load one untrusted plugin module, logging failures."""
    name = f"pyleem_plugin_{file.stem}"
    if name in sys.modules:
        return
    try:
        spec = importlib.util.spec_from_file_location(name, file)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    except Exception:  # noqa: BLE001 - broken drop-ins must not crash the app
        sys.modules.pop(name, None)
        log.warning("Could not load plugin %s", file, exc_info=True)
