"""The optional-SDK loader: where it looks, and what it says when it finds nothing.

Real filesystem and a real import, which is what the loader is — there is no
pure half to unit-test. The SDK itself is never required: one test asserts the
real package IS importable when the operator happens to have it, and skips
otherwise; everything else runs against a written-on-the-fly fake.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

from coffer.infrastructure.channel import seatalk_sdk
from coffer.infrastructure.channel.seatalk_sdk import (
    SeaTalkSdkMissingError,
    load_sdk,
    sdk_dir,
)

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


def test_sdk_dir_honours_the_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COFFER_SEATALK_SDK_DIR", "~/elsewhere/vendor")
    assert sdk_dir() == Path.home() / "elsewhere/vendor"


def test_sdk_dir_defaults_to_the_coffer_vendor_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("COFFER_SEATALK_SDK_DIR", raising=False)
    assert sdk_dir() == Path.home() / ".coffer" / "vendor"


def test_loads_the_package_from_the_vendor_dir(tmp_path: Path) -> None:
    write_fake_sdk_package(tmp_path / "vendor", marker="from-vendor")
    module = load_sdk()
    assert module.MARKER == "from-vendor"
    assert str(tmp_path / "vendor") in sys.path


def test_loads_a_package_already_on_the_normal_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """An operator who pip-installed it into the venv needs no vendor dir."""
    from .fake_seatalk_sdk import build_fake_sdk

    handle = build_fake_sdk()
    monkeypatch.setitem(sys.modules, _PACKAGE, handle.module)
    assert load_sdk() is handle.module
    # Nothing was added to sys.path: the vendor dir does not even exist here.
    assert not (sdk_dir()).exists()


def test_missing_sdk_raises_an_actionable_error(tmp_path: Path) -> None:
    with pytest.raises(SeaTalkSdkMissingError) as excinfo:
        load_sdk()
    message = str(excinfo.value)
    # The three things the owner needs: what is missing, where to put it, and
    # where to read about it.
    assert _PACKAGE in message
    assert str(tmp_path / "vendor") in message
    assert "https://open.seatalk.io/docs/WebSocket-Event-Callback" in message
    assert "webhook" in message  # and the way to run without it at all


def test_vendor_dir_is_added_to_sys_path_only_once(tmp_path: Path) -> None:
    """The reconnect ladder calls this every few seconds; a path that grew per
    attempt would be a slow leak."""
    write_fake_sdk_package(tmp_path / "vendor")
    load_sdk()
    sys.modules.pop(_PACKAGE, None)
    load_sdk()
    assert sys.path.count(str(tmp_path / "vendor")) == 1


def test_absent_vendor_dir_is_not_added_to_sys_path(tmp_path: Path) -> None:
    with pytest.raises(SeaTalkSdkMissingError):
        load_sdk()
    assert str(tmp_path / "vendor") not in sys.path


def test_a_second_call_returns_the_already_imported_module(tmp_path: Path) -> None:
    write_fake_sdk_package(tmp_path / "vendor")
    assert load_sdk() is load_sdk()


def test_real_sdk_loads_when_the_operator_has_supplied_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Not a requirement — a bonus check for a machine that has the real SDK.

    Skipped everywhere it is absent (CI, any outside contributor), because the
    product must work without it.
    """
    monkeypatch.delenv("COFFER_SEATALK_SDK_DIR", raising=False)
    real_dir = seatalk_sdk.sdk_dir()
    if not (real_dir / _PACKAGE).is_dir():
        pytest.skip(f"no operator-supplied SeaTalk SDK in {real_dir}")
    module = load_sdk()
    assert hasattr(module, "Client")
    assert hasattr(module, "EventDispatcher")
    assert hasattr(module, "KickError")
