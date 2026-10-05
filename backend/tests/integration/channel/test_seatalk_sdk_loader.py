"""Where the optional SDK is looked for, how the bridge imports it, and what a
channel says when it is not there.

Real filesystem and a real import — inside the bridge's own ``import_sdk`` /
``open_session``, which is the only code allowed to import the SDK. The SDK
itself is never required: everything runs against a written-on-the-fly fake.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

from coffer.infrastructure.channel.seatalk_bridge.protocol import BridgeConfig, Emitter
from coffer.infrastructure.channel.seatalk_bridge.session import import_sdk, open_session
from coffer.infrastructure.channel.seatalk_sdk import missing_message, sdk_dir

from .fake_seatalk_sdk import write_fake_sdk_package

_PACKAGE = "seatalk_oapi_sdk"


@pytest.fixture(autouse=True)
def _clean_sdk_state(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Any:
    """Isolate every test from the real vendor dir and from each other.

    Without the ``sys.path``/``sys.modules`` restore, one test's fake package
    would stay importable for the next one — and a stale entry would make the
    "missing" case pass for the wrong reason.
    """
    original_path = list(sys.path)
    previous = sys.modules.pop(_PACKAGE, None)
    monkeypatch.setenv("COFFER_SEATALK_SDK_DIR", str(tmp_path / "vendor"))
    yield
    sys.path[:] = original_path
    sys.modules.pop(_PACKAGE, None)
    if previous is not None:
        sys.modules[_PACKAGE] = previous


def _emitter(lines: list[dict[str, Any]], secret: str = "s3cret") -> Emitter:
    return Emitter(lambda line: lines.append(json.loads(line)), secret=secret)


def test_sdk_dir_honours_the_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COFFER_SEATALK_SDK_DIR", "~/elsewhere/vendor")
    assert sdk_dir() == Path.home() / "elsewhere/vendor"


def test_sdk_dir_defaults_to_the_coffer_vendor_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("COFFER_SEATALK_SDK_DIR", raising=False)
    assert sdk_dir() == Path.home() / ".coffer" / "vendor"


def test_the_missing_message_says_what_where_and_where_to_read(tmp_path: Path) -> None:
    message = missing_message(tmp_path / "vendor")
    # The three things the owner needs: what is missing, where it was looked
    # for, and where to read about it.
    assert _PACKAGE in message
    assert str(tmp_path / "vendor") in message
    assert "https://open.seatalk.io/docs/WebSocket-Event-Callback" in message
    # There is no other inbound transport to fall back on, so the message must
    # not point at one; it says what still works instead.
    assert "webhook" not in message
    assert "outbound sends are unaffected" in message


def test_the_bridge_imports_the_package_from_the_vendor_dir(tmp_path: Path) -> None:
    write_fake_sdk_package(tmp_path / "vendor", marker="from-vendor")
    module = import_sdk(str(tmp_path / "vendor"))
    assert module.MARKER == "from-vendor"


def test_the_vendor_dir_is_appended_so_it_cannot_shadow_anything(tmp_path: Path) -> None:
    """A file dropped into the vendor directory named like a stdlib or bundled
    module must lose to the real one, so the directory goes LAST."""
    write_fake_sdk_package(tmp_path / "vendor")
    import_sdk(str(tmp_path / "vendor"))
    assert sys.path[-1] == str(tmp_path / "vendor")


def test_the_vendor_dir_is_added_only_once(tmp_path: Path) -> None:
    write_fake_sdk_package(tmp_path / "vendor")
    import_sdk(str(tmp_path / "vendor"))
    sys.modules.pop(_PACKAGE, None)
    import_sdk(str(tmp_path / "vendor"))
    assert sys.path.count(str(tmp_path / "vendor")) == 1


def test_an_absent_vendor_dir_is_not_added_to_sys_path(tmp_path: Path) -> None:
    with pytest.raises(ModuleNotFoundError):
        import_sdk(str(tmp_path / "vendor"))
    assert str(tmp_path / "vendor") not in sys.path


def test_a_missing_package_is_reported_as_sdk_missing(tmp_path: Path) -> None:
    lines: list[dict[str, Any]] = []
    config = BridgeConfig("app-1", "s3cret", str(tmp_path / "vendor"))
    session = open_session(lambda: import_sdk(config.sdk_dir), config, _emitter(lines))
    assert session is None
    assert lines == [
        {
            "type": "sdk_missing",
            "dir": str(tmp_path / "vendor"),
            "detail": f"ModuleNotFoundError: No module named '{_PACKAGE}'",
        }
    ]


def test_a_package_missing_its_own_dependency_is_a_failure_not_sdk_missing(
    tmp_path: Path,
) -> None:
    """The SDK is there but cannot import what IT needs: saying "not installed"
    would send the owner to re-download something they already have."""
    package = tmp_path / "vendor" / _PACKAGE
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("import a_dependency_nobody_has\n")
    lines: list[dict[str, Any]] = []
    config = BridgeConfig("app-1", "s3cret", str(tmp_path / "vendor"))
    assert open_session(lambda: import_sdk(config.sdk_dir), config, _emitter(lines)) is None
    assert lines[0]["type"] == "ended"
    assert lines[0]["outcome"] == "failed"
    assert lines[0]["error_class"] == "ModuleNotFoundError"
    assert "a_dependency_nobody_has" in lines[0]["error"]


def test_a_loaded_package_is_announced_with_its_version(tmp_path: Path) -> None:
    write_fake_sdk_package(tmp_path / "vendor")
    lines: list[dict[str, Any]] = []
    config = BridgeConfig("app-1", "s3cret", str(tmp_path / "vendor"))
    assert open_session(lambda: import_sdk(config.sdk_dir), config, _emitter(lines)) is not None
    assert lines == [{"type": "loaded", "version": "0.1.0-scripted"}]


def test_the_emitter_scrubs_the_secret_from_every_string() -> None:
    lines: list[dict[str, Any]] = []
    _emitter(lines).emit("ended", outcome="failed", error_class="X", error="bad key s3cret here")
    assert lines[0]["error"] == "bad key [redacted] here"


def test_the_config_never_shows_its_secret() -> None:
    assert "s3cret" not in repr(BridgeConfig("app-1", "s3cret", "/v"))
