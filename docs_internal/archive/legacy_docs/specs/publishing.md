# Publishing VenomQA to PyPI

This guide covers the complete process for publishing VenomQA to PyPI and TestPyPI.

## Prerequisites

1. **PyPI Account**: Create accounts at:
   - [PyPI](https://pypi.org/account/register/)
   - [TestPyPI](https://test.pypi.org/account/register/)

2. **API Tokens**: Generate API tokens for secure publishing:
   - PyPI: https://pypi.org/manage/account/token/
   - TestPyPI: https://test.pypi.org/manage/account/token/

3. **Install Build Tools**:
   ```bash
   pip install build twine
   ```

## Configuration

### 1. Configure .pypirc

Copy the template and add your tokens:

```bash
cp .pypirc.template ~/.pypirc
chmod 600 ~/.pypirc
```

Edit `~/.pypirc` and replace the placeholder tokens:

```ini
[distutils]
index-servers =
    pypi
    testpypi

[pypi]
username = __token__
password = pypi-xxxx...  # Your PyPI token

[testpypi]
username = __token__
password = pypi-xxxx...  # Your TestPyPI token
```

### 2. Trusted Publishing (Recommended)

For GitHub Actions CI/CD, use trusted publishing instead of tokens:

1. Go to PyPI → Publishing → Add GitHub repository
2. Configure the workflow name (e.g., `publish.yml`)

See: https://docs.pypi.org/trusted-publishers/

## Pre-Publish Checklist

Before publishing, verify:

- [ ] Version updated in `pyproject.toml` and `venomqa/__init__.py`
- [ ] `CHANGELOG.md` updated with release notes
- [ ] All tests pass: `pytest`
- [ ] Linting passes: `ruff check .`
- [ ] Type checking passes: `mypy venomqa`
- [ ] Documentation is up to date
- [ ] Git tag created for the version

## Building the Package

### Clean Previous Builds

```bash
rm -rf dist/ build/ *.egg-info
```

### Build Source and Wheel Distributions

```bash
python -m build
```

This creates:
- `dist/venomqa-0.2.0.tar.gz` (source distribution)
- `dist/venomqa-0.2.0-py3-none-any.whl` (wheel)

### Verify the Build

```bash
# Check package metadata
twine check dist/*

# List package contents
tar -tzf dist/venomqa-0.2.0.tar.gz
unzip -l dist/venomqa-0.2.0-py3-none-any.whl
```

## Publishing to TestPyPI (Recommended First)

Always test with TestPyPI before publishing to the main PyPI:

```bash
# Upload to TestPyPI
twine upload --repository testpypi dist/*

# Test installation from TestPyPI
pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ venomqa
```

Verify the installed package works:

```bash
python -c "import venomqa; print(venomqa.__version__)"
venomqa --help
```

## Publishing to PyPI

Once verified on TestPyPI:

```bash
# Upload to PyPI
twine upload dist/*
```

The package will be available at: https://pypi.org/project/venomqa/

## Version Management

### Semantic Versioning

Follow [SemVer](https://semver.org/):
- **MAJOR**: Breaking changes
- **MINOR**: New features (backward compatible)
- **PATCH**: Bug fixes

### Updating Version

1. Update `pyproject.toml`:
   ```toml
   version = "0.3.0"
   ```

2. Update `venomqa/__init__.py`:
   ```python
   __version__ = "0.3.0"
   ```

3. Update `CHANGELOG.md` with release notes

4. Create git tag:
   ```bash
   git tag -a v0.3.0 -m "Release 0.3.0"
   git push origin v0.3.0
   ```

## GitHub Actions CI/CD

Create `.github/workflows/publish.yml` for automated publishing:

```yaml
name: Publish to PyPI

on:
  release:
    types: [published]

permissions:
  id-token: write  # For trusted publishing
  contents: read

jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install build twine

      - name: Build package
        run: python -m build

      - name: Check package
        run: twine check dist/*

      - name: Publish to PyPI
        uses: pypa/gh-action-pypi-publish@release/v1
```

## Troubleshooting

### File Already Exists Error

```
HTTPError: 400 Bad Request from https://upload.pypi.org/legacy/
File already exists
```

**Solution**: You cannot re-upload the same version. Bump the version number.

### Invalid Distribution

```
error: invalid command 'bdist_wheel'
```

**Solution**: Install wheel: `pip install wheel build`

### Missing Files in Distribution

**Solution**: Check `MANIFEST.in` and ensure files are included. For `hatchling`, files tracked by git are included by default.

### Import Errors After Install

**Solution**: Verify `__init__.py` exports are correct and all dependencies are listed in `pyproject.toml`.

## Quick Reference Commands

```bash
# Clean
rm -rf dist/ build/ *.egg-info

# Build
python -m build

# Check
twine check dist/*

# Upload to TestPyPI
twine upload --repository testpypi dist/*

# Upload to PyPI
twine upload dist/*

# Test install
pip install --index-url https://test.pypi.org/simple/ venomqa
```

## Resources

- [PyPI Publishing Guide](https://packaging.python.org/en/latest/tutorials/packaging-projects/)
- [Twine Documentation](https://twine.readthedocs.io/)
- [Trusted Publishers](https://docs.pypi.org/trusted-publishers/)
- [Semantic Versioning](https://semver.org/)
