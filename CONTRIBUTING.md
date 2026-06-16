# Contributing

Thank you for your interest in contributing to pyLEEM-GUI.
This document provides guidelines for contributing to the project.

## Getting Started

1. Fork the repository on GitHub.
2. Create a new branch for your changes:

```bash
git checkout -b feature/your-feature-name
```

## Development Setup

Install this package with its development extras:

```bash
pip install -e ".[test,docs]"
```

To run the application locally:

```bash
pyleem-gui
```

## Running Tests

Run the full test suite with tox:

```bash
tox
```

Run only the tests directly with pytest:

```bash
pytest
```

Build the documentation locally:

```bash
cd docs
make html
```

## Code Style Guidelines

### Python Style

- Follow PEP 8 style guidelines.
- Use Black formatting before submission.
- Keep code modular, readable, and focused on the change.
- Prefer clear names over comments; add comments only for intent or non-obvious
  constraints.

### Documentation Style

- Keep documentation concise.
- Add docstrings for public classes, methods, and functions.
- Keep docstrings short and use one-sentence docstrings by default.

## Contribute

### Bug Reports

If you find a bug:

1. Check if it is already reported in
   [Issues](https://github.com/peterhys/pyLEEM-GUI/issues).
2. If not, create a new issue with:
   - A clear description of the bug.
   - Steps to reproduce.
   - Expected and actual behavior.
   - Python, pyLEEM-GUI, and pyLEEM versions.
   - Operating system details.
   - A minimal code example if possible.

### Feature Requests

For new features:

1. Open an issue first to discuss the feature.
2. Explain the use case and benefits.
3. Wait for maintainer feedback before implementing.

### Pull Requests

Before submitting:

- [ ] Code follows project style guidelines.
- [ ] All tests pass with `tox`.
- [ ] New tests are added for new functionality or bug fixes.
- [ ] Documentation is updated where needed.
- [ ] The pull request focuses on a single feature or bug fix.

To submit a pull request:

1. Push your branch to your fork.
2. Open a pull request against the `develop` branch.
3. Fill out the pull request template.
4. Link any related issues.
5. Wait for review.

During review:

- Maintainers will review your code.
- Address any requested changes.
- Once approved, your pull request will be merged.

## Branching Strategy

- `main` - Stable releases only.
- `develop` - Development branch; submit pull requests here.
- `feature/*` - New features.
- `fix/*` - Bug fixes.
- `docs/*` - Documentation updates.

## Questions

- Open a [Discussion](https://github.com/peterhys/pyLEEM-GUI/discussions).
- Check existing [Issues](https://github.com/peterhys/pyLEEM-GUI/issues).

## Code of Conduct

This project adheres to a Code of Conduct.
By participating, you are expected to uphold this code.
Please report unacceptable behavior to the maintainer.

## License

By contributing to pyLEEM-GUI, you agree that your contributions will be
licensed under the BSD 3-Clause License.
Additional Brookhaven National Laboratory, U.S. Department of Energy, and U.S.
Government rights notices are provided in [NOTICE](NOTICE).

Thank you for contributing to pyLEEM-GUI. Your contributions help make
scientific software better for everyone.
