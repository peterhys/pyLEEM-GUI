"""Plugin package facade for discovery, specs, and Qt host classes."""

from .discovery import discover_plugins, load_plugins
from .host import (
    AnalysisHandler,
    AutoTab,
    ComponentHandler,
    PluginContext,
    TabPlugin,
)
from .spec import (
    PLUGINS,
    Bool,
    Choice,
    Component,
    ComponentHandlerMark,
    Float,
    Int,
    Plugin,
    format_plugin_id,
    plugin,
)
