# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/2.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

Establish the project and the initial release.

### Added

- Add main GUI with the image viewer, process bar, and plugin tabs.
- Add layering logic split across ProcessLayer, ImageLayer, and ViewLayer.
- Add plugin API with auto-discovery and a host that builds each tab from typed edit, render, and analysis components.
- Add Builtin (auto level, manual level, and the ROI overlay), Metadata, Line Profile, and Stack Profile plugins.
