# Plugins

This page points to the current plugin authoring docs.

Use [Plugin API](../api.md) to write or load plugins. The current runtime uses:

| Module | Purpose |
| --- | --- |
| `pyleem_gui.plugins.spec` | Qt-free plugin declarations and registry |
| `pyleem_gui.plugins.host` | Qt host classes and generated plugin tabs |
| `pyleem_gui.plugins.discovery` | Built-in and external plugin loading |
| `pyleem_gui.plugins.builtin` | Builtin plugin entrypoint |

Plugin modules register themselves by calling `plugin()`. There is no plugin
list to edit.
