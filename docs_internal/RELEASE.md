# Release Process

> How to release new versions of VenomQA.

---

## Version Scheme

We use [Semantic Versioning](https://semver.org/):

```
MAJOR.MINOR.PATCH

0.2.0  ← Current
│ │ │
│ │ └── Patch: Bug fixes, no API changes
│ └──── Minor: New features, backward compatible
└────── Major: Breaking changes
```

**Pre-1.0:** Breaking changes can happen in minor versions.

---

## Release Checklist

### 1. Pre-Release

- [ ] All tests passing: `pytest tests/ -v`
- [ ] Type checking passing: `mypy venomqa/`
- [ ] Linting passing: `ruff check venomqa/`
- [ ] Docs build: `mkdocs build`
- [ ] CHANGELOG.md updated
- [ ] Version bumped in `venomqa/__init__.py`
- [ ] Version bumped in `pyproject.toml`

### 2. Create Release

```bash
# Ensure clean working directory
git status

# Create version tag
git tag -a v0.2.1 -m "Release v0.2.1"

# Push tag
git push origin v0.2.1
```

### 3. Build & Publish

```bash
# Build distributions
python -m build

# Check distributions
twine check dist/*

# Upload to PyPI
twine upload dist/*
```

### 4. Post-Release

- [ ] Verify on PyPI: https://pypi.org/project/venomqa/
- [ ] Test install: `pip install venomqa==0.2.1`
- [ ] Create GitHub Release with notes
- [ ] Announce (Twitter, Discord, etc.)
- [ ] Update PROJECT_TRACKER.md

---

## Automated Release (GitHub Actions)

The `publish.yml` workflow handles releases automatically:

1. Push a tag starting with `v` (e.g., `v0.2.1`)
2. GitHub Actions builds and publishes to PyPI
3. Creates GitHub Release

```yaml
# .github/workflows/publish.yml triggers on:
on:
  push:
    tags:
      - 'v*'
```

---

## Version Bumping

### Patch Release (0.2.0 → 0.2.1)
Bug fixes only, no new features.

```bash
# Update version
sed -i '' 's/__version__ = "0.2.0"/__version__ = "0.2.1"/' venomqa/__init__.py
```

### Minor Release (0.2.0 → 0.3.0)
New features, backward compatible.

### Major Release (0.x.x → 1.0.0)
Breaking changes or "stable" milestone.

---

## Changelog Format

```markdown
# Changelog

## [0.2.1] - 2026-02-15

### Added
- New `venomqa demo --explain` mode

### Changed
- Improved error messages with suggestions

### Fixed
- Journey discovery now finds all .py files

### Deprecated
- Old config format (will be removed in 0.3.0)

### Removed
- Removed deprecated `--legacy` flag

### Security
- Fixed credential exposure in logs
```

---

## Hotfix Process

For urgent fixes to production:

```bash
# 1. Create hotfix branch from tag
git checkout -b hotfix/0.2.1 v0.2.0

# 2. Fix the issue
# ... make changes ...

# 3. Update version and changelog
# 4. Commit and tag
git commit -am "Hotfix: description"
git tag -a v0.2.1 -m "Hotfix release"

# 5. Push
git push origin hotfix/0.2.1
git push origin v0.2.1

# 6. Merge back to main
git checkout main
git merge hotfix/0.2.1
git push origin main
```

---

## PyPI Credentials

### Using Token (Recommended)

```bash
# Set in environment
export TWINE_USERNAME=__token__
export TWINE_PASSWORD=pypi-xxxxx

# Or use keyring
pip install keyring
keyring set https://upload.pypi.org/legacy/ __token__
```

### GitHub Actions

Secrets configured in repository:
- `PYPI_API_TOKEN`: PyPI API token

---

## Release Notes Template

```markdown
# VenomQA v0.2.1

## Highlights

- 🎉 New `venomqa demo --explain` mode for learning
- 🐛 Fixed journey discovery issues
- 📚 Improved documentation

## What's Changed

### New Features
- Added `--explain` flag to demo command (#123)

### Bug Fixes
- Fixed journey discovery to find all .py files (#124)

### Documentation
- Added theory documentation
- Improved quickstart guide

## Breaking Changes

None in this release.

## Upgrade Guide

```bash
pip install --upgrade venomqa
```

## Contributors

- @namanag97
- @contributor1

**Full Changelog**: https://github.com/namanag97/venomqa/compare/v0.2.0...v0.2.1
```

---

## Rollback Procedure

If a release has critical issues:

```bash
# 1. Yank from PyPI (hides but doesn't delete)
# Go to PyPI project page → Manage → Yank

# 2. Or delete and re-upload fixed version
# (same version number only if caught quickly)

# 3. Communicate to users
# - GitHub issue
# - Social media
# - Discord
```

---

## Release Frequency

| Type | Frequency | Notes |
|------|-----------|-------|
| Patch | As needed | Bug fixes |
| Minor | Monthly | New features |
| Major | Rare | Breaking changes |

---

## Pre-release Versions

For testing before official release:

```bash
# Alpha
0.3.0a1, 0.3.0a2

# Beta
0.3.0b1, 0.3.0b2

# Release candidate
0.3.0rc1, 0.3.0rc2

# Install pre-release
pip install venomqa==0.3.0a1
pip install --pre venomqa
```
