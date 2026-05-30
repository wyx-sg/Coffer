from datetime import UTC, datetime

from coffer.infrastructure.daemon.pid_lock import DaemonInfo, read, write


def _info(port: int = 8000) -> DaemonInfo:
    return DaemonInfo(
        version=1,
        pid=1234,
        port=port,
        token="tok",
        started_at=datetime(2026, 5, 20, tzinfo=UTC),
        binary_path="/usr/local/bin/coffer-daemon",
    )


def test_round_trip(tmp_path):
    f = tmp_path / "daemon.json"
    info = _info()
    write(f, info)
    assert f.stat().st_mode & 0o777 == 0o600
    assert read(f) == info


def test_write_tolerates_preexisting_stale_tmp(tmp_path):
    """A leftover ``daemon.json.tmp`` from a crashed run must not break write.

    The old fixed-name + O_EXCL staging file crashed (FileExistsError) when a
    stale tmp existed AND when two daemons raced. write() now uses a unique
    mkstemp name, so a pre-existing tmp is irrelevant and never collides.
    """
    f = tmp_path / "daemon.json"
    (tmp_path / "daemon.json.tmp").write_text("stale junk")  # simulate a crash

    write(f, _info(port=8001))

    assert read(f).port == 8001
    assert f.stat().st_mode & 0o777 == 0o600


def test_write_leaves_no_stray_tmp_files(tmp_path):
    """After a successful write, only daemon.json remains — the unique staging
    file is atomically renamed away, not left behind."""
    f = tmp_path / "daemon.json"
    write(f, _info())
    leftovers = [p.name for p in tmp_path.iterdir() if p.name != "daemon.json"]
    assert leftovers == [], f"unexpected staging files left behind: {leftovers}"
