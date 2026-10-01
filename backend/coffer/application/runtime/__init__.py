"""The daemon's runtime substrate: supervised tasks, loop lag, correlation ids.

Kind-agnostic and stdlib-only, so every layer that starts background work or
writes a record can use it: ``application`` code imports it directly, and
``infrastructure`` (the channel transports, the log formatter) may too, because
infrastructure adapts to application. See ADR
``background-work-runs-supervised-and-correlated``.
"""
