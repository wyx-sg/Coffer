"""Shared test support: the real-home guard and the isolated-HOME builders.

Nothing in here is a test. Tiers import from it (``tests.support.homes``,
``tests.support.channel``); the root ``conftest.py`` installs the guard from
``tests.support.real_home_guard`` before any ``coffer`` module is imported.
"""
