"""Root conftest.py — ensures the local venomqa package takes precedence over any installed version."""

from __future__ import annotations

import sys
from pathlib import Path

# Insert the project root at the front of sys.path so that
# `import venomqa` always resolves to the local source tree,
# even if an older venomqa is installed in the environment.
_src_root = str(Path(__file__).parent / "src")
if _src_root not in sys.path:
    sys.path.insert(0, _src_root)
