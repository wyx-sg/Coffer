"""The proxy token files OpenCode reads its key from (ADR
opencode-reads-its-proxy-token-from-a-file)."""

from __future__ import annotations

import asyncio
import stat

from coffer.application.provider.proxy_tokens import ProxyTokenService, token_ref
from coffer.infrastructure.model_proxy.token_files import TokenFileMirror


class _Secrets:
    def __init__(self) -> None:
        self.data: dict[str, str] = {}

    def get(self, ref: str) -> str | None:
        return self.data.get(ref)

    def set(self, ref: str, value: str) -> None:
        self.data[ref] = value

    def delete(self, ref: str) -> None:
        self.data.pop(ref, None)

    def list_refs(self) -> list[tuple[str, str, str]]:
        return [(r, "", "") for r in self.data]


def test_the_file_is_private_and_holds_exactly_the_token(tmp_path) -> None:
    mirror = TokenFileMirror(tmp_path / "proxy-tokens")
    mirror.write("opencode", "cfr_one")
    path = tmp_path / "proxy-tokens" / "opencode"
    assert path.read_text() == "cfr_one"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    mtime = path.stat().st_mtime_ns
    mirror.write("opencode", "cfr_one")
    assert path.stat().st_mtime_ns == mtime, "an unchanged token rewrites nothing"
    mirror.remove("opencode")
    mirror.remove("opencode")
    assert not path.exists()


def test_the_service_keeps_the_file_equal_to_the_stored_token(tmp_path) -> None:
    secrets = _Secrets()
    mirror = TokenFileMirror(tmp_path)
    tokens = ProxyTokenService(secrets, files=mirror, file_agents={"opencode"})

    async def run() -> None:
        first = await tokens.token_for("opencode")
        assert (tmp_path / "opencode").read_text() == first
        await tokens.token_for("claude-code")
        assert not (tmp_path / "claude-code").exists(), "only file agents get a file"
        # A file deleted by hand comes back at the next issue.
        (tmp_path / "opencode").unlink()
        assert await tokens.token_for("opencode") == first
        assert (tmp_path / "opencode").read_text() == first
        rotated = await tokens.rotate("opencode")
        assert rotated != first and (tmp_path / "opencode").read_text() == rotated
        await tokens.revoke("opencode")
        assert not (tmp_path / "opencode").exists()
        await tokens.token_for("opencode")
        await tokens.prune(["claude-code"])
        assert token_ref("opencode") not in secrets.data
        assert not (tmp_path / "opencode").exists()

    asyncio.run(run())
