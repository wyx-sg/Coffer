from datetime import UTC, datetime

from coffer.infrastructure.daemon.pid_lock import DaemonInfo, read, write


def test_round_trip(tmp_path):
    f = tmp_path / "daemon.json"
    info = DaemonInfo(
        version=1,
        pid=1234,
        port=8000,
        token="tok",
        started_at=datetime(2026, 5, 20, tzinfo=UTC),
        binary_path="/usr/local/bin/coffer-daemon",
    )
    write(f, info)
    assert f.stat().st_mode & 0o777 == 0o600
    assert read(f) == info
