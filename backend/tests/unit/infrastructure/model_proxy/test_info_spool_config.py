"""proxy.json, the usage spool, the proxy-port setting and the Host predicate."""

from __future__ import annotations

import json
import os
import stat
from datetime import UTC, datetime
from pathlib import Path

import pytest

from coffer.domain.usage.records import Outcome, UsageRecord, Wire
from coffer.infrastructure.daemon import config
from coffer.infrastructure.model_proxy import info as info_mod
from coffer.infrastructure.model_proxy.spool import UsageSpool, finalize_orphans, spool_dir
from coffer.infrastructure.net.loopback_authority import is_allowed_host, split_authority


def _record(n: int) -> UsageRecord:
    return UsageRecord(
        dedupe_key=f"d{n}",
        attempt_id=f"a{n}",
        started_at=datetime.now(UTC),
        wire=Wire.ANTHROPIC,
        endpoint="/v1/messages",
        outcome=Outcome.COMPLETED,
    )


def test_proxy_info_round_trip_is_private_and_owned(tmp_path: Path) -> None:
    info = info_mod.ProxyInfo(port=8001, pid=4242, started_at="t", version="v", control_token="c")
    info_mod.write_info(info, tmp_path)
    path = info_mod.info_path(tmp_path)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert info_mod.read_info(tmp_path) == info
    assert "c" not in repr(info).split("version")[1]
    assert not info_mod.remove_info_if_owned(1, tmp_path) and path.exists()
    assert info_mod.remove_info_if_owned(4242, tmp_path) and not path.exists()
    path.write_text("{}")
    assert info_mod.read_info(tmp_path) is None


def test_spool_dir_honours_the_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COFFER_PROXY_SPOOL_DIR", str(tmp_path / "s"))
    assert spool_dir() == tmp_path / "s"
    monkeypatch.delenv("COFFER_PROXY_SPOOL_DIR")
    monkeypatch.setenv("HOME", str(tmp_path))
    assert spool_dir() == tmp_path / ".coffer" / "proxy-usage"


async def test_spool_finalizes_on_count_on_age_and_on_close(tmp_path: Path) -> None:
    spool = UsageSpool(tmp_path, max_age=0.2, max_records=3, pid=77)
    await spool.start()
    for n in range(4):
        spool.append(_record(n))
    await spool.flush()
    done = sorted(tmp_path.glob("*.jsonl"))
    lines = [json.loads(line) for f in done for line in f.read_text().splitlines()]
    assert [r["dedupe_key"] for r in lines] == ["d0", "d1", "d2", "d3"]
    assert all(f.name.startswith("77-") for f in done)
    spool.append(_record(9))
    import asyncio

    await asyncio.sleep(0.5)  # age-based rename, no flush
    assert (
        not list(tmp_path.glob("*.part")) and len(list(tmp_path.glob("*.jsonl"))) == len(done) + 1
    )
    spool.append(_record(10))
    await spool.close()
    assert not list(tmp_path.glob("*.part"))
    for f in tmp_path.glob("*.jsonl"):
        assert stat.S_IMODE(f.stat().st_mode) == 0o600


def test_orphaned_parts_of_dead_writers_are_finalized(tmp_path: Path) -> None:
    dead = tmp_path / "999999-000001.jsonl.part"
    dead.write_text('{"x":1}\n')
    mine = tmp_path / f"{os.getpid()}-000001.jsonl.part"
    mine.write_text('{"x":2}\n')
    assert finalize_orphans(tmp_path, own_pid=12345) == 1
    assert (tmp_path / "999999-000001.jsonl").exists() and mine.exists()


def test_proxy_port_setting(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    assert config.read_proxy_port() is None and config.effective_proxy_port() == 8001
    config.write_fixed_port(9000)
    config.write_proxy_port(9001)
    assert config.effective_proxy_port() == 9001 and config.effective_port() == 9000
    with pytest.raises(config.InvalidPort):
        config.write_proxy_port(80)
    config.write_proxy_port(None)
    assert config.effective_proxy_port() == 8001 and config.effective_port() == 9000
    config.config_path().write_text(json.dumps({"proxy_port": "x"}))
    assert config.effective_proxy_port() == 8001


def test_loopback_authority_predicates() -> None:
    assert split_authority("[::1]:8001") == ("::1", 8001)
    assert is_allowed_host("127.0.0.1:8001", 8001)
    assert is_allowed_host("localhost:8001", 8001)
    assert not is_allowed_host("localhost:8000", 8001)
    assert not is_allowed_host("evil.example:8001", 8001)
    assert is_allowed_host("evil.example:8001", 8001, ("evil.example",))
    assert is_allowed_host(None, 8001, ("*",)) and not is_allowed_host(None, 8001)
