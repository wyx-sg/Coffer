"""Persistence for the workflow kind — the four tables and the run directory.

The shape of the work (a template) is an ordinary Resource and needs nothing
here. What this package owns is the *execution*: ``workflow_runs``,
``workflow_events``, ``workflow_node_attempts`` and ``workflow_approvals``
(``models.py`` / ``repository.py``), and the files a run's nodes write
(``paths.py`` / ``artifacts.py``).
"""
