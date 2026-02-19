# Publishing Guide

Guide for maintainers on publishing to PyPI, versioning, and changelog management.

## Overview

This document covers the release process for VenomQA maintainers.

## Versioning

VenomQA follows [Semantic Versioning](https://semver.org/):

- **MAJOR**: Breaking API changes
- **MINOR**: New features, backward compatible
- **PATCH**: Bug fixes, backward compatible

### Version Locations

Update version in these files:

1. `pyproject.toml`:
```toml
[project]
version = "0.6.4"
```

2. `src/venomqa/__init__.py`:
```python
__version__ = "0.6.4"
```

### Pre-release Versions

For testing before official release:

```bash
# Alpha
0.7.0a1

# Beta  
0.7.0b1

# Release candidate
0.7.0rc1
```

## Changelog

Maintain a `CHANGELOG.md` following [Keep a Changelog](https://keepachangelog.com/):

```markdown
# Changelog

All notable changes to this project will be documented in this file.

## [0.7.0] - 2024-01-15

### Added
- MCTS exploration strategy for bug-focused exploration
- MongoDB adapter with checkpoint/rollback support
- Elasticsearch adapter for search indices

### Changed
- Improved state hashing performance by 40%
- DFS is now the default strategy

### Fixed
- PostgreSQL savepoint cleanup on early termination
- Context checkpoint memory leak

### Deprecated
- `Agent.run()` method (use `Agent.explore()`)
- Old-style reporter interface (use callable)

## [0.6.4] - 2024-01-01
...
```

### Changelog Categories

| Category | Description |
|----------|-------------|
| Added | New features |
| Changed | Changes to existing features |
| Deprecated | Features to be removed |
| Removed | Features removed this release |
| Fixed | Bug fixes |
| Security | Security improvements |

## Release Process

### 1. Prepare Release

```bash
# Ensure you're on main
git checkout main
git pull origin main

# Run full test suite
pytest tests/ --ignore=tests/v1/test_postgres.py

# Run linting
ruff check src/ tests/
mypy src/

# Build docs
mkdocs build
```

### 2. Update Version and Changelog

```bash
# Update version in pyproject.toml and __init__.py
# Update CHANGELOG.md with release date
# Commit changes

git add pyproject.toml src/venomqa/__init__.py CHANGELOG.md
git commit -m "chore: release v0.7.0"
```

### 3. Create Tag

```bash
git tag -a v0.7.0 -m "Release v0.7.0"
git push origin main
git push origin v0.7.0
```

### 4. Build Package

```bash
# Install build tools
pip install build twine

# Clean previous builds
rm -rf dist/ build/ *.egg-info

# Build source distribution and wheel
python -m build
```

### 5. Verify Package

```bash
# Check package metadata
twine check dist/*

# Expected output:
# Checking dist/venomqa-0.7.0-py3-none-any.whl: PASSED
# Checking dist/venomqa-0.7.0.tar.gz: PASSED
```

### 6. Upload to TestPyPI (Optional)

```bash
# Upload to TestPyPI first
twine upload --repository testpypi dist/*

# Verify installation
pip install --index-url https://test.pypi.org/simple/ venomqa==0.7.0
```

### 7. Upload to PyPI

```bash
# Upload to production PyPI
twine upload dist/*
```

### 8. Verify Release

```bash
# Wait a few minutes for PyPI to index
pip install venomqa==0.7.0

# Verify version
python -c "import venomqa; print(venomqa.__version__)"
```

### 9. Create GitHub Release

1. Go to https://github.com/namanag97/venomqa/releases/new
2. Select the tag
3. Title: `v0.7.0`
4. Description: Copy from CHANGELOG.md
5. Attach built wheel and source distribution

## Automated Releases (GitHub Actions)

### Workflow Configuration

`.github/workflows/release.yml`:

```yaml
name: Release

on:
  push:
    tags:
      - 'v*'

jobs:
  build-and-publish:
    runs-on: ubuntu-latest
    permissions:
      id-token: write  # For trusted publishing
      contents: write

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install build tools
        run: |
          pip install build twine

      - name: Build package
        run: python -m build

      - name: Check package
        run: twine check dist/*

      - name: Publish to PyPI
        uses: pypa/gh-action-pypi-publish@release/v1
        # Uses trusted publishing, no token needed

      - name: Create GitHub Release
        uses: softprops/action-gh-release@v1
        with:
          files: dist/*
          body_path: RELEASE_NOTES.md
```

### Trusted Publishing Setup

1. Go to PyPI → Publishing
2. Add GitHub repository as trusted publisher
3. Configure workflow name: `release.yml`
4. No API token needed!

## Branching Strategy

```
main
  │
  ├── develop
  │     │
  │     ├── feature/mcts-strategy
  │     ├── feature/mongodb-adapter
  │     └── fix/postgres-cleanup
  │
  └── release/0.7.0
```

### Branch Types

| Branch | Purpose | Merge To |
|--------|---------|----------|
| `main` | Production releases | - |
| `develop` | Integration branch | `main` |
| `feature/*` | New features | `develop` |
| `fix/*` | Bug fixes | `develop` |
| `release/*` | Release preparation | `main`, `develop` |
| `hotfix/*` | Production hotfixes | `main`, `develop` |

## Hotfix Process

For critical production bugs:

```bash
# Create hotfix branch from main
git checkout main
git checkout -b hotfix/critical-bug

# Fix the bug
# Update version (e.g., 0.7.1)
# Update CHANGELOG.md

# Test
pytest

# Commit and tag
git commit -m "fix: critical bug in state hashing"
git tag v0.7.1

# Merge to main and develop
git checkout main
git merge hotfix/critical-bug
git checkout develop
git merge hotfix/critical-bug

# Push and release
git push origin main develop v0.7.1
```

## Deprecation Policy

### Deprecation Process

1. **Announce**: Add deprecation warning in code
2. **Document**: Update docs with migration guide
3. **Wait**: 2 minor versions (e.g., 0.7.x → 0.9.x)
4. **Remove**: Delete in next major version

### Adding Deprecation

```python
import warnings

def old_function():
    warnings.warn(
        "old_function is deprecated. Use new_function instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return new_function()
```

### Deprecation Timeline

| Version | Status |
|---------|--------|
| 0.7.0 | Deprecated with warning |
| 0.8.0 | Still works with warning |
| 0.9.0 | Still works with warning |
| 1.0.0 | Removed |

## Security Releases

For security vulnerabilities:

1. **Do not** publish details until fix is released
2. Email security@venomqa.dev with details
3. Create private fix branch
4. Coordinate release with security advisory
5. Publish to PyPI immediately after GitHub advisory

## Rollback Process

If a release has critical issues:

```bash
# Yank the bad release from PyPI
twine upload --repository pypi dist/venomqa-0.7.0.tar.gz --skip-existing

# Or use PyPI web interface to yank

# Create and release fix
# Version becomes 0.7.1
```

## Checklist

### Pre-release

- [ ] All tests pass
- [ ] Linting passes
- [ ] Type checking passes
- [ ] Docs build successfully
- [ ] Version updated in all locations
- [ ] CHANGELOG.md updated
- [ ] Release notes prepared

### Release

- [ ] Tag created
- [ ] Package built
- [ ] Package verified
- [ ] Uploaded to PyPI
- [ ] GitHub release created
- [ ] Installation verified

### Post-release

- [ ] Announcement posted (Discord, Twitter)
- [ ] Docs updated with new version
- [ ] Close resolved issues
- [ ] Update milestone

## PyPI Configuration

### API Token (Legacy)

```bash
# Create token at https://pypi.org/manage/account/token/
# Add to ~/.pypirc:

[pypi]
  username = __token__
  password = pypi-...
```

### Trusted Publishing (Recommended)

Configure in PyPI → Publishing → Add GitHub:
- Repository: namanag97/venomqa
- Workflow: release.yml
- Environment: (leave empty)

## Troubleshooting

### "File already exists"

The version was already uploaded. Bump version.

### "Invalid classifier"

Check classifier syntax in `pyproject.toml`:
```toml
classifiers = [
    "Development Status :: 4 - Beta",
    "Intended Audience :: Developers",
    ...
]
```

### "Upload failed: 400"

Check:
- Version not already exists
- Metadata is valid
- No duplicate files in dist/

### Twine SSL errors

```bash
# Upgrade certifi
pip install --upgrade certifi twine
```
