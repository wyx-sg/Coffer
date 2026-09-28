"""Run the SeaTalk SDK's blocking ``listen()`` on a thread we own and join.

Split out of ``seatalk_ws`` (the connector and its supervision loop): this is
the thread half of the sync-SDK / event-loop boundary described there.
"""

from __future__ import annotations

import asyncio
import contextlib
import threading
from collections.abc import Callable
from types import ModuleType
from typing import Any

__all__ = ["listen_on_thread", "require"]


async def listen_on_thread(
    client: Any,
    *,
    name: str,
    join_timeout: float,
    started: Callable[[threading.Thread], None],
) -> BaseException | None:
    """Run ``client.listen()`` on its own thread; return what it raised, if anything.

    The thread hands its outcome back through a future resolved with
    ``call_soon_threadsafe``, so the supervisor awaits the connection's whole
    lifetime without a thread parked on ``join``. ``started`` receives the
    thread as soon as it runs, so the connector can join it on stop.
    """
    loop = asyncio.get_running_loop()
    finished: asyncio.Future[BaseException | None] = loop.create_future()

    def _resolve(error: BaseException | None) -> None:
        if not finished.done():
            finished.set_result(error)

    def _run() -> None:
        outcome: BaseException | None = None
        try:
            client.listen()
        except BaseException as e:
            outcome = e
        finally:
            with contextlib.suppress(RuntimeError):  # loop already closed
                loop.call_soon_threadsafe(_resolve, outcome)

    thread = threading.Thread(target=_run, name=f"seatalk-ws-listen:{name}", daemon=True)
    started(thread)
    thread.start()
    try:
        return await finished
    finally:
        # ``_run`` resolves the future in its ``finally``, so the thread is on
        # its way out; joining makes that observable instead of assumed.
        await asyncio.to_thread(thread.join, join_timeout)


def require(sdk: ModuleType, attribute: str) -> Any:
    value = getattr(sdk, attribute, None)
    if value is None:
        raise RuntimeError(
            f"the SeaTalk SDK at {sdk.__file__} exposes no {attribute!r}; "
            f"this is not the seatalk_oapi_sdk package Coffer expects"
        )
    return value
