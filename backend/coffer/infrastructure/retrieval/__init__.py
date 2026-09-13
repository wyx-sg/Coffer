"""Substrate shared by every ranked-retrieval consumer.

The disposable sidecar lived under ``infrastructure/knowledge/`` while
knowledge was its only consumer. Memory's ``recall`` is the second, and a
module two kinds depend on should not be filed under one of them.
"""
