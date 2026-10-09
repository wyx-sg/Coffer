"""What every installed-build suite shares, whatever surface it drives.

- ``target``: the arguments (``--daemon-json``, ``--shim``, ``--coffer``,
  ``--out``, ``--allow-sync-remote``) and the target daemon, fingerprinted and
  recorded without its token.
- ``journal``: ``qa-`` names only, reserved up front, deleted in ``finally``.
- ``sync_guard``: no write to a target that pushes its vault to a remote.
- ``recorder``: PASS / FAIL / BLOCKED / N/A cases into ``cases.json`` and
  ``summary.md``, token and canaries redacted.
- ``processes``: owned processes and the no-surviving-fixture check.
- ``run``: the lifecycle a suite plugs into (``run.main``).
"""
