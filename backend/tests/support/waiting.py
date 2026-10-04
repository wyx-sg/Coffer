"""Wait on a condition instead of sleeping and hoping (``.agents/testing.md``)."""

from __future__ import annotations

import asyncio
import inspect
from typing import Any

import pytest


async def wait_until(
    predicate: Any,
    *,
    timeout: float = 5.0,
    interval: float = 0.01,
    message: str = "condition not met within timeout",
) -> None:
    """Poll ``predicate`` (sync or async) until truthy, bounded by ``timeout``."""
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        result = predicate()
        if inspect.isawaitable(result):
            result = await result
        if result:
            return
        if asyncio.get_running_loop().time() >= deadline:
            pytest.fail(message)
        await asyncio.sleep(interval)
