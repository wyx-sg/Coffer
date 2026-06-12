"""Entry point: ``python -m coffer.surfaces.callback``.

Configuration arrives via environment (set by the daemon at spawn):

- ``COFFER_CB_PORT`` — loopback port to bind (required)
- ``COFFER_CB_SECRETS`` — JSON ``{channel_name: signing_secret}`` (required)
- ``COFFER_CB_DAEMON_URL`` — daemon base URL (required)
- ``COFFER_CB_DAEMON_TOKEN`` — daemon API token (required)
"""

from __future__ import annotations

import json
import os
import sys

import uvicorn

from coffer.surfaces.callback.app import create_listener_app


def main() -> int:
    try:
        port = int(os.environ["COFFER_CB_PORT"])
        secrets = json.loads(os.environ["COFFER_CB_SECRETS"])
        daemon_url = os.environ["COFFER_CB_DAEMON_URL"]
        daemon_token = os.environ["COFFER_CB_DAEMON_TOKEN"]
    except (KeyError, ValueError) as e:
        print(f"coffer-callback: bad environment: {e!r}", file=sys.stderr)
        return 2
    if not isinstance(secrets, dict):
        print("coffer-callback: COFFER_CB_SECRETS must be a JSON object", file=sys.stderr)
        return 2
    app = create_listener_app(
        signing_secrets={str(k): str(v) for k, v in secrets.items()},
        daemon_url=daemon_url,
        daemon_token=daemon_token,
    )
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
