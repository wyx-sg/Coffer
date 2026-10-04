"""How long Coffer waits for its own model on one call.

The one call Coffer makes on its own behalf is a speech-to-text request, and it
is bounded, because an unbounded one holds a connection until the daemon is
restarted when an endpoint wedges, and nothing in the UI says so. The bound is
a fixed constant, not a setting.
"""

from __future__ import annotations

#: Seconds one model call may take before the caller gives up.
DEFAULT_MODEL_TIMEOUT_S = 60.0

__all__ = ["DEFAULT_MODEL_TIMEOUT_S"]
