"""What a spawned stdio upstream is allowed to see, and what its failures say.

An upstream MCP server is third-party code the daemon starts as a child
process. Two boundaries matter, and both fail silently if they regress: the
child must not inherit the daemon's own environment (which holds the daemon
token and every secret the user's shell exported), and a failure to start must
not echo the exception text back up (argv and URLs at that point routinely
embed credentials, and the message ends up in an API response and the log).
"""

from __future__ import annotations

import pytest


async def test_a_spawned_upstream_does_not_inherit_the_daemons_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only the SDK's safe base (PATH/HOME/…), the server's own static env, and
    its materialised credentials reach the child. A daemon-side secret env var
    must be absent, so an untrusted upstream cannot read it — while the env the
    server was configured with, and the credentials resolved for it, must still
    arrive or the server cannot authenticate at all.
    """
    from coffer.domain.errors import UpstreamUnavailable
    from coffer.domain.mcp.server_config import StdioTransport
    from coffer.infrastructure.mcp import subprocess as sp

    monkeypatch.setenv("COFFER_DAEMON_SECRET", "super-secret-value")

    captured: dict[str, dict[str, str]] = {}

    class _StopCtx:
        async def __aenter__(self) -> None:
            raise RuntimeError("stop after capture")

        async def __aexit__(self, *_a: object) -> bool:
            return False

    def _fake_stdio_client(params: object, **_kwargs: object) -> _StopCtx:
        # **_kwargs absorbs `errlog`, which the adapter passes so an upstream's
        # stderr lands in its own file rather than the daemon's.
        captured["env"] = dict(getattr(params, "env", None) or {})
        return _StopCtx()

    monkeypatch.setattr(sp, "stdio_client", _fake_stdio_client)

    conn = sp.StdioUpstreamConnection(
        transport=StdioTransport(command="/bin/true", args=[], env={"MY_STATIC": "x"}),
        env_overlay={"API_KEY": "from-keychain"},
    )
    with pytest.raises(UpstreamUnavailable):
        await conn.spawn_and_initialize()

    env = captured["env"]
    assert "COFFER_DAEMON_SECRET" not in env, "daemon secret leaked into upstream env"
    assert env.get("MY_STATIC") == "x"
    assert env.get("API_KEY") == "from-keychain"
    assert "PATH" in env, "the safe base environment must still be present"


async def test_a_failed_spawn_reports_the_exception_type_and_not_its_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The raised `UpstreamUnavailable` names the exception TYPE only.

    The underlying exception text at spawn time can embed credential-bearing
    argv and URLs, and this message travels into an HTTP response body and the
    daemon log. The type is enough to diagnose; the text is a leak.
    """
    from coffer.domain.errors import UpstreamUnavailable
    from coffer.domain.mcp.server_config import StdioTransport
    from coffer.infrastructure.mcp import subprocess as sp

    secret = "token=SECRET-abc123"

    def _boom(params: object, **_kwargs: object) -> object:
        raise ValueError(f"connect failed https://host/?{secret}")

    monkeypatch.setattr(sp, "stdio_client", _boom)
    conn = sp.StdioUpstreamConnection(
        transport=StdioTransport(command="/bin/true", args=[]),
        env_overlay={},
    )
    with pytest.raises(UpstreamUnavailable) as ei:
        await conn.spawn_and_initialize()
    assert "SECRET" not in str(ei.value)
    assert "ValueError" in str(ei.value)
