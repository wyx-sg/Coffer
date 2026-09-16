"""Concrete file→Markdown converters, dispatched by ``registry.py``.

``markitdown`` is imported only inside ``markitdown_converter.py`` — nowhere
else in this package, and nowhere outside ``infrastructure.knowledge`` /
``infrastructure.chat`` (spec knowledge FR-037, enforced by the import-linter
contract in ``backend/pyproject.toml``).
"""

from __future__ import annotations
