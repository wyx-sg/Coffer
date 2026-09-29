"""The daemon-wide event stream: invalidation hints for every change.

ADR wire-contract-generated-from-the-pydantic-models, option E1. The
:class:`~coffer.application.events.broker.EventBroker` numbers each change,
keeps a bounded buffer of recent envelopes for reconnecting clients, and fans
them out to subscribers; the
:class:`~coffer.application.events.attention_watch.AttentionWatcher` turns a
change in what the attention list reports into one envelope of its own.
"""
