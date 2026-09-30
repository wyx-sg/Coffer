"""Read the bundled model price list shipped with this build.

``price_list/genai-prices.json`` is pydantic/genai-prices (MIT; the licence sits
beside it), written by ``make refresh-prices`` at release time. It is read
once per process; the daily refresh (:mod:`.price_refresh`) may cache a newer
copy, and pricing reads whichever is fresher (spec provider-switching "Refresh
the bundled price list in the background"). A build that lost the file still prices the
models Coffer's own supplement knows, and logs why the rest are unpriced.
"""

from __future__ import annotations

import functools
import json
import logging
from pathlib import Path

from coffer.domain.usage.bundled_prices import BundledPrices

_logger = logging.getLogger(__name__)

DATA_FILE = Path(__file__).resolve().parent / "price_list" / "genai-prices.json"


@functools.cache
def load_bundled_prices() -> BundledPrices:
    """The bundled list, parsed once."""
    try:
        document = json.loads(DATA_FILE.read_text("utf-8"))
    except (OSError, ValueError):
        _logger.warning("usage.bundled_prices_unreadable", extra={"file": str(DATA_FILE)})
        return BundledPrices.empty()
    return BundledPrices.from_document(document)


__all__ = ["DATA_FILE", "load_bundled_prices"]
