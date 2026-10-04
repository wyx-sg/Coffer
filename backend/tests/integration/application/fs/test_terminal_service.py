"""Opening an agent session in a terminal: validation, the command, the prompt file.

Spec daemon "Open an agent session in a terminal" and "List the terminals
installed on this host". The platform is a fake; the launcher spawn is recorded.
"""

from __future__ import annotations

import pathlib
import stat
import subprocess
from types import SimpleNamespace
from typing import Any

import pytest

from coffer.application.fs import terminal_service
from coffer.application.fs.terminal_service import TerminalDetectService, TerminalService
from coffer.domain.fs_terminal_errors import FsTerminalFailed, FsTerminalInvalid
from tests.unit.application.fs._fake_platform import FakePlatform


class _Spawns:
    def __init__(self) -> None:
        self.argvs: list[list[str]] = []
        self.fail: OSError | None = None

    def __call__(self, argv: list[str], **_: Any) -> None:
        if self.fail is not None:
            raise self.fail
        self.argvs.append(argv)


@pytest.fixture
def spawns(monkeypatch: pytest.MonkeyPatch) -> _Spawns:
    spawns = _Spawns()
    monkeypatch.setattr(
        terminal_service,
        "subprocess",
        SimpleNamespace(Popen=spawns, DEVNULL=subprocess.DEVNULL),
    )
    return spawns


@pytest.fixture
def workspace(tmp_path: pathlib.Path) -> pathlib.Path:
    return tmp_path / "workspace"


@pytest.fixture
def platform() -> FakePlatform:
    return FakePlatform()


@pytest.fixture
def svc(platform: FakePlatform, tmp_path: pathlib.Path, workspace: pathlib.Path) -> TerminalService:
    def default_workspace() -> str:
        workspace.mkdir(exist_ok=True)
        return str(workspace)

    return TerminalService(
        platform, default_workspace=default_workspace, handoff_dir=lambda: tmp_path / "handoff"
    )


def _open(svc: TerminalService, **kw: Any) -> None:
    body: dict[str, Any] = {
        "terminal": None,
        "agent": "claude_code",
        "cwd": None,
        "resume": None,
        "prompt": None,
    }
    body.update(kw)
    svc.open_session(**body)


@pytest.mark.acceptance(
    spec="daemon", scenario="a resume opens the agent's resume command in the session's directory"
)
def test_a_resume_runs_the_agents_resume_command_in_the_directory(
    svc: TerminalService, platform: FakePlatform, spawns: _Spawns, tmp_path: pathlib.Path
) -> None:
    work = tmp_path / "api"
    work.mkdir()

    _open(svc, cwd=str(work), resume="abc-123")
    _open(svc, agent="codex", cwd=str(work), resume="abc-123")

    assert platform.terminal_launches == [
        (None, f"cd '{work}' && claude --resume abc-123", str(work)),
        (None, f"cd '{work}' && codex resume abc-123", str(work)),
    ]
    assert len(spawns.argvs) == 2


def test_a_directory_with_a_quote_is_quoted_whole(
    svc: TerminalService, platform: FakePlatform, spawns: _Spawns, tmp_path: pathlib.Path
) -> None:
    work = tmp_path / "it's mine"
    work.mkdir()

    _open(svc, cwd=str(work), resume="abc")

    [(_, command, _)] = platform.terminal_launches
    assert command == f"cd '{tmp_path}/it'\"'\"'s mine' && claude --resume abc"


@pytest.mark.acceptance(spec="daemon", scenario="a prompt never appears on a command line")
def test_a_prompt_goes_through_a_private_file_the_command_removes(
    svc: TerminalService, platform: FakePlatform, spawns: _Spawns, tmp_path: pathlib.Path
) -> None:
    _open(svc, prompt="rotate the key sk-test")

    [(_, command, _)] = platform.terminal_launches
    [file] = list((tmp_path / "handoff").iterdir())
    assert "sk-test" not in command and "sk-test" not in " ".join(spawns.argvs[0])
    assert command.endswith(f"claude \"$(cat '{file}'; rm -f '{file}')\"")
    assert file.read_text() == "rotate the key sk-test"
    assert stat.S_IMODE(file.stat().st_mode) == 0o600
    assert stat.S_IMODE(file.parent.stat().st_mode) == 0o700


def test_a_prompt_that_looks_like_an_option_is_not_read_as_one(
    svc: TerminalService, spawns: _Spawns, tmp_path: pathlib.Path
) -> None:
    _open(svc, agent="codex", prompt="--help me")

    [file] = list((tmp_path / "handoff").iterdir())
    assert file.read_text() == "\n--help me"


def test_a_failed_spawn_removes_the_prompt_file(
    svc: TerminalService, spawns: _Spawns, tmp_path: pathlib.Path
) -> None:
    spawns.fail = FileNotFoundError("no such launcher")

    with pytest.raises(FsTerminalFailed):
        _open(svc, prompt="hello")

    assert list((tmp_path / "handoff").iterdir()) == []


@pytest.mark.acceptance(
    spec="daemon", scenario="an unsafe session id is refused before anything starts"
)
@pytest.mark.parametrize(
    "body",
    [
        {"resume": "abc;touch /tmp/x"},
        {"resume": "$(id)"},
        {"resume": ""},
        {"resume": "a" * 129},
        {"agent": "gemini", "resume": "abc"},
        {"cwd": "relative/dir", "resume": "abc"},
        {"resume": "abc", "prompt": "hi"},
        {},
        {"prompt": "   "},
    ],
)
def test_invalid_requests_are_refused_before_anything_starts(
    svc: TerminalService, platform: FakePlatform, spawns: _Spawns, body: dict[str, Any]
) -> None:
    with pytest.raises(FsTerminalInvalid):
        _open(svc, **body)

    assert platform.terminal_launches == [] and spawns.argvs == []


@pytest.mark.acceptance(spec="daemon", scenario="a custom template runs as an argument vector")
def test_a_template_is_split_then_substituted_per_argument(
    svc: TerminalService, platform: FakePlatform, spawns: _Spawns, tmp_path: pathlib.Path
) -> None:
    work = tmp_path / "my dir"
    work.mkdir()

    _open(svc, terminal="mycli --dir {cwd} -- {command}", cwd=str(work), resume="abc")

    assert spawns.argvs == [
        ["mycli", "--dir", str(work), "--", f"cd '{work}' && claude --resume abc"]
    ]
    assert platform.terminal_launches == []


def test_a_template_may_embed_the_placeholders_inside_an_argument(
    svc: TerminalService, spawns: _Spawns, tmp_path: pathlib.Path
) -> None:
    _open(svc, terminal='t "--cwd={cwd}" -c {command}', cwd=str(tmp_path), resume="abc")

    assert spawns.argvs[0][:2] == ["t", f"--cwd={tmp_path}"]


@pytest.mark.parametrize("template", ["mycli --dir {cwd}", "'{cwd} {command}"])
def test_a_template_without_command_or_that_does_not_parse_is_invalid(
    svc: TerminalService, spawns: _Spawns, tmp_path: pathlib.Path, template: str
) -> None:
    with pytest.raises(FsTerminalInvalid):
        _open(svc, terminal=template, cwd=str(tmp_path), resume="abc")

    assert spawns.argvs == []


def test_a_named_launcher_is_handed_to_the_platform(
    svc: TerminalService, platform: FakePlatform, spawns: _Spawns, tmp_path: pathlib.Path
) -> None:
    _open(svc, terminal=" Warp ", cwd=str(tmp_path), resume="abc")

    assert platform.terminal_launches[0][0] == "Warp"
    assert spawns.argvs == [["fake-terminal", "Warp", f"cd '{tmp_path}' && claude --resume abc"]]


@pytest.mark.acceptance(
    spec="daemon", scenario="a missing directory opens in the default workspace"
)
def test_a_missing_or_absent_directory_opens_in_the_default_workspace(
    svc: TerminalService, platform: FakePlatform, spawns: _Spawns, workspace: pathlib.Path
) -> None:
    _open(svc, cwd="/no/such/dir", resume="abc")
    _open(svc, cwd=None, resume="abc")

    assert [c for _, _, c in platform.terminal_launches] == [str(workspace)] * 2
    assert workspace.is_dir()


def test_a_launcher_the_platform_cannot_provide_fails_with_its_reason(
    svc: TerminalService, platform: FakePlatform, spawns: _Spawns, monkeypatch: pytest.MonkeyPatch
) -> None:
    def none_found(*_: Any, **__: Any) -> Any:
        raise FsTerminalFailed("no terminal found")

    monkeypatch.setattr(platform, "terminal_launch", none_found)

    with pytest.raises(FsTerminalFailed, match="no terminal found"):
        _open(svc, resume="abc")


def test_a_launcher_that_cannot_be_spawned_is_a_launch_failure(
    svc: TerminalService, spawns: _Spawns
) -> None:
    spawns.fail = FileNotFoundError("osascript")

    with pytest.raises(FsTerminalFailed, match="osascript"):
        _open(svc, resume="abc")


@pytest.mark.acceptance(
    spec="daemon", scenario="the daemon lists the terminals installed on this host"
)
def test_detection_lists_what_the_platform_reports_in_display_order() -> None:
    platform = FakePlatform(terminals={"iTerm": "iTerm", "Terminal": "Terminal", "Orca": "orca"})

    options = TerminalDetectService(platform).list_terminals()

    assert [(o.label, o.value) for o in options] == [
        ("Terminal", "Terminal"),
        ("iTerm", "iTerm"),
        ("Orca", "orca"),
    ]
    assert TerminalDetectService(FakePlatform()).list_terminals() == []
