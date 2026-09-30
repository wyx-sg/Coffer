"""The suite's Hypothesis profiles (``.agents/testing.md`` "Property-Based Tests").

- ``ci`` (the default): a bounded number of examples, derandomized so every
  run explores the same cases, no deadline (a per-example wall-clock limit
  fails on a loaded machine, not on a regression), and no example
  database, so a run writes nothing into the checkout.
- ``thorough``: many more random examples with the database on, for a local
  hunt after a change to the code under test:
  ``HYPOTHESIS_PROFILE=thorough make verify-unit``.

Registered from the root ``conftest.py``; a no-op while ``hypothesis`` is not
installed (the property tests skip themselves then).
"""

from __future__ import annotations

import os

PROFILE_ENV = "HYPOTHESIS_PROFILE"


def register() -> None:
    try:
        from hypothesis import HealthCheck, settings
    except ImportError:
        return
    settings.register_profile(
        "ci",
        max_examples=100,
        derandomize=True,
        deadline=None,
        database=None,
        print_blob=True,
        suppress_health_check=[HealthCheck.too_slow],
    )
    settings.register_profile(
        "thorough",
        max_examples=2000,
        deadline=None,
        print_blob=True,
        suppress_health_check=[HealthCheck.too_slow],
    )
    settings.load_profile(os.environ.get(PROFILE_ENV, "ci"))


__all__ = ["PROFILE_ENV", "register"]
