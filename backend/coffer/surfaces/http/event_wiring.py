"""Composition of the daemon-wide event stream (spec resource-framework
"Announce every change on one daemon-wide event stream").

Built right after the reconciler and before any kind, because its hint sink is
what the resource repository announces writes to: :func:`fan_out` hands each
``Changed`` to the reconciler (bring the next pass forward), to the broker (one
envelope), and to the attention watcher (recompute once writes settle). The
watcher also listens to every writing reconcile pass. It starts once the
attention list is wired — its baseline computed before the daemon reports
ready, so the first change after boot is announced — and the shutdown cancels
it.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from coffer.application.attention import AttentionService
from coffer.application.events.attention_watch import AttentionWatcher
from coffer.application.events.broker import DEFAULT_BUFFER_SIZE, EventBroker
from coffer.application.mcp.upstream_auth import UpstreamAuthMonitor
from coffer.application.reconcile.hints import HintSink, fan_out
from coffer.application.reconcile.reconciler import Reconciler
from coffer.application.runtime.supervisor import spawn_restarting
from coffer.domain.reconcile import Changed
from coffer.surfaces.http.event_dependencies import set_event_broker

#: How many recent envelopes a reconnecting client can resume across.
BUFFER_SIZE = DEFAULT_BUFFER_SIZE


@dataclass(frozen=True)
class EventStream:
    broker: EventBroker
    watcher: AttentionWatcher
    #: What ``HintingResourceRepo`` announces every resource write to.
    hint_sink: HintSink
    #: Listeners added once the services exist (the secret citation index).
    late_sinks: list[HintSink]


def build_event_stream(reconciler: Reconciler) -> EventStream:
    """The broker, published for the route, and the one hint sink."""
    broker = EventBroker(buffer_size=BUFFER_SIZE)
    watcher = AttentionWatcher(broker)
    reconciler.add_pass_listener(watcher.on_pass)
    set_event_broker(broker)
    late: list[HintSink] = []

    def late_sink(changed: Changed) -> None:
        for each in list(late):
            each(changed)

    sink = fan_out(reconciler.hint, broker.publish_changed, watcher.on_changed, late_sink)
    return EventStream(broker=broker, watcher=watcher, hint_sink=sink, late_sinks=late)


async def start_attention_watch(
    events: EventStream, attention: AttentionService, auth_monitor: UpstreamAuthMonitor
) -> asyncio.Task[None]:
    """Compute the attention baseline now, then watch it as a task the
    shutdown cancels."""
    # A key rejected in a real call changes the list: recompute at once.
    auth_monitor.on_change = events.watcher.nudge
    await events.watcher.prime(attention.report)
    return spawn_restarting(lambda: events.watcher.serve(attention.report), name="attention-watch")


__all__ = ["BUFFER_SIZE", "EventStream", "build_event_stream", "start_attention_watch"]
