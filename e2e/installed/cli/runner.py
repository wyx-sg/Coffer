"""The installed-build CLI smoke: what only the frozen ``coffer`` binary can get wrong.

Every behaviour of the command line is tested from source in the integration
tier (``backend/tests/integration/surfaces/cli``). This suite repeats none of
it. It checks what the source cannot show: that the PyInstaller binary carries
every module the commands import at run time (each group's help renders, shell
completion finds its shell), that it is the build its version says, and that
its input errors come out as the source's do rather than as a frozen
traceback.

It needs no daemon and touches nothing of the person's: each case runs a copy
of the binary (so no sibling ``coffer-daemon`` is in reach) with ``HOME`` set
to an empty directory under ``--out`` and a ``PATH`` of ``/usr/bin:/bin``, and
only commands that end before they would reach a daemon. After every case the
suite checks that no daemon was started under that home, and stops at the
first that was.

Case ids are the OpenSpec scenario (``<spec>/<title>``) when a case verifies
one, otherwise a short stable local id.
"""

from __future__ import annotations

import argparse
import ast
import json
import platform
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from e2e.installed._common.commands import Ran, isolated_env, run, run_pty
from e2e.installed._common.recorder import CaseRecorder
from e2e.installed._common.redact import Redactor
from e2e.installed._common.target import (
    REPO_ROOT,
    RefusedError,
    add_common_arguments,
    checked_out_dir,
    fingerprint,
)

GROUPS_SOURCE = REPO_ROOT / "backend" / "coffer" / "surfaces" / "cli" / "groups.py"
#: Root commands that are not groups.
ROOT_COMMANDS = ("run",)
#: The shells completion supports, and one it does not.
SHELLS = {"zsh": "#compdef coffer", "bash": "_coffer_completion"}
UNSUPPORTED_SHELL = "/bin/sh"
INVALID_UTF8 = b"\xff\xfe{\x00}\x00"


class DaemonReachedError(Exception):
    """A smoke case started a daemon under the isolated home: stop at once."""


def group_paths() -> list[str]:
    """Every command group the source declares (``GROUP_HELP``'s keys), read
    from the file rather than imported: the suite compares the installed build
    with this checkout, whatever ``coffer`` the runner's interpreter imports."""
    tree = ast.parse(GROUPS_SOURCE.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "GROUP_HELP"
            and isinstance(node.value, ast.Dict)
        ):
            return [
                k.value
                for k in node.value.keys
                if isinstance(k, ast.Constant) and isinstance(k.value, str)
            ]
    raise RefusedError(f"no GROUP_HELP in {GROUPS_SOURCE}")


@dataclass
class Smoke:
    coffer: Path
    home: Path
    work: Path
    rec: CaseRecorder

    def env(self) -> dict[str, str]:
        return isolated_env(self.home)

    def cli(self, *args: str, stdin: bytes | None = None) -> Ran:
        ran = run([str(self.coffer), *args], env=self.env(), stdin=stdin, cwd=self.work)
        self.assert_no_daemon()
        return ran

    def assert_no_daemon(self) -> None:
        coffer_home = self.home / ".coffer"
        traces = [p for p in ("daemon.json", "logs/daemon.log") if (coffer_home / p).exists()]
        if traces:
            raise DaemonReachedError(", ".join(traces))


def _json_error(ran: Ran, code: str, exit_code: int) -> bool:
    """One error envelope on stderr with ``code`` and ``exit_code``; stdout empty."""
    try:
        envelope = json.loads(ran.stderr)
    except ValueError:
        return False
    return (
        ran.exit == exit_code
        and ran.stdout == ""
        and isinstance(envelope, dict)
        and envelope.get("exit_code") == exit_code
        and (envelope.get("error") or {}).get("code") == code
    )


def case_version(s: Smoke) -> str | None:
    ran = s.cli("--version")
    version = ran.stdout.strip()
    s.rec.record(
        "cli.version",
        "the binary prints its version and exits",
        expected="exit 0, one line naming the version",
        actual=ran.record(),
        ok=ran.exit == 0 and bool(version) and "\n" not in version and not ran.crashed,
    )
    return version or None


def case_root_help(s: Smoke, groups: list[str]) -> None:
    ran = s.cli("--help")
    top = sorted({g for g in groups if " " not in g} | set(ROOT_COMMANDS))
    missing = [g for g in top if f" {g} " not in ran.stdout]
    s.rec.record(
        "resource-framework/management commands are visible in help",
        "the root help lists every command group the source declares",
        expected=f"exit 0 and each of {len(top)} groups listed",
        actual={**ran.record(), "stdout": "(elided)", "missing": missing},
        ok=ran.exit == 0 and not missing and not ran.crashed,
    )


def case_group_help(s: Smoke, groups: list[str]) -> None:
    broken: list[dict[str, object]] = []
    for path in groups:
        ran = s.cli(*path.split(" "), "--help")
        if ran.exit != 0 or ran.crashed:
            broken.append({"group": path, "exit": ran.exit, "stderr": ran.stderr[-600:]})
    s.rec.record(
        "cli.group-help",
        "every command group's help renders from the frozen binary",
        expected=f"exit 0 and no traceback for all {len(groups)} groups "
        "(a module PyInstaller left out fails here)",
        actual={"groups": len(groups), "broken": broken},
        ok=not broken,
    )


def case_completion(s: Smoke) -> None:
    for name, first in SHELLS.items():
        shell = f"/bin/{name}"
        ran = run_pty([str(s.coffer), "--show-completion"], shell=shell, env=s.env())
        s.assert_no_daemon()
        s.rec.record(
            f"cli.completion.{name}",
            f"--show-completion prints the {name} script in a terminal",
            expected=f"exit 0, output containing {first!r}",
            actual=ran.record(),
            ok=ran.exit == 0 and first in ran.stdout and not ran.crashed,
        )
    ran = run_pty([str(s.coffer), "--show-completion"], shell=UNSUPPORTED_SHELL, env=s.env())
    s.assert_no_daemon()
    s.rec.record(
        "cli.completion.unsupported",
        "an unsupported shell gets a one-line refusal, not a traceback",
        expected="non-zero exit, a 'not supported' line, no traceback",
        actual=ran.record(),
        ok=ran.exit != 0 and "not supported" in ran.stdout and not ran.crashed,
    )


def case_bad_input(s: Smoke) -> None:
    bad = s.work / "qa-cli-invalid-utf8.json"
    bad.write_bytes(INVALID_UTF8)
    create = ["custom-tool", "group", "create", "qa-cli-smoke", "--base-url", "http://127.0.0.1:1"]
    ran = s.cli(*create, "--data", f"@{bad}", "--json")
    s.rec.record(
        "resource-framework/every failure path keeps the JSON error contract",
        "a --data file that is not UTF-8 is one JSON error, exit 6, before any request",
        expected="exit 6, stderr one envelope with CLI_INVALID_INPUT, stdout empty",
        actual=ran.record(),
        ok=_json_error(ran, "CLI_INVALID_INPUT", 6) and not ran.crashed,
    )
    ran = s.cli(*create, "--data", "{nope", "--json")
    s.rec.record(
        "cli.input.invalid-json",
        "--data that is not JSON is one JSON error, exit 6",
        expected="exit 6, stderr one envelope with CLI_INVALID_INPUT, stdout empty",
        actual=ran.record(),
        ok=_json_error(ran, "CLI_INVALID_INPUT", 6) and not ran.crashed,
    )
    marker = s.work / "qa-cli-child-ran"
    missing = s.work / "qa-cli-no-such.env"
    ran = s.cli("run", "--env-file", str(missing), "--", "/usr/bin/touch", str(marker))
    s.rec.record(
        "cli.input.env-file",
        "coffer run with an --env-file it cannot read exits 6 and starts nothing",
        expected="exit 6, a message naming --env-file, no child, no traceback",
        actual={**ran.record(), "child_ran": marker.exists()},
        ok=ran.exit == 6 and "--env-file" in ran.stderr and not marker.exists() and not ran.crashed,
    )


def case_offline(s: Smoke) -> None:
    ran = s.cli("path", "logs", "--json")
    try:
        paths = json.loads(ran.stdout)
    except ValueError:
        paths = {}
    s.rec.record(
        "cli.offline.path-logs",
        "path logs answers with no daemon, under the home it runs in",
        expected="exit 0, JSON whose paths sit under the isolated home",
        actual=ran.record(),
        ok=ran.exit == 0
        and bool(paths)
        and all(str(v).startswith(str(s.home)) for v in paths.values()),
    )


CASES: list[Callable[[Smoke], None]] = [case_completion, case_bad_input, case_offline]


def _copy(binary: Path, out: Path) -> Path:
    """The binary, copied where no ``coffer-daemon`` sits beside it."""
    target = out / "bin" / binary.name
    target.parent.mkdir()
    shutil.copy2(binary, target)
    return target


def smoke(args: argparse.Namespace) -> int:
    out = checked_out_dir(args.out)
    installed = Path(args.coffer).expanduser().resolve()
    if not installed.is_file():
        raise RefusedError(f"no coffer binary at {installed} (pass --coffer)")
    on_path = shutil.which("coffer-daemon", path=isolated_env(out)["PATH"])
    if on_path:
        raise RefusedError(f"a coffer-daemon is on the isolated PATH ({on_path})")
    home, work = out / "home", out / "work"
    home.mkdir()
    work.mkdir()
    rec = CaseRecorder(out, Redactor(), "cli")
    s = Smoke(_copy(installed, out), home, work, rec)
    header: dict[str, object] = {
        "coffer": json.dumps(fingerprint(installed)),
        "out": str(out),
    }
    try:
        rec.area = "build"
        version = case_version(s)
        header["version"] = version or "(none)"
        groups = group_paths()
        rec.area = "help"
        case_root_help(s, groups)
        case_group_help(s, groups)
        for case in CASES:
            rec.area = case.__name__.removeprefix("case_")
            case(s)
    except DaemonReachedError as exc:
        rec.area = "isolation"
        rec.record(
            "cli.no-daemon",
            "no smoke case reaches for a daemon",
            expected="nothing under the isolated home's .coffer",
            actual={"found": str(exc)},
            ok=False,
        )
    else:
        rec.area = "isolation"
        rec.record(
            "cli.no-daemon",
            "no smoke case reaches for a daemon",
            expected="nothing under the isolated home's .coffer",
            actual={"home": str(home)},
            ok=True,
        )
    (out / "target.json").write_text(
        json.dumps(
            {
                "coffer": fingerprint(installed),
                "version": header["version"],
                "runner": {
                    "python": sys.version,
                    "platform": platform.platform(),
                    "started_at": datetime.now(UTC).isoformat(),
                    "source": _source_commit(),
                },
            },
            indent=2,
        )
    )
    rec.write(header)
    print(f"RESULT {json.dumps(rec.counts())} → {out / 'summary.md'}", flush=True)
    return rec.exit_code()


def _source_commit() -> str | None:
    done = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    return done.stdout.strip() or None


def entry(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Smoke the installed frozen coffer binary (no daemon, nothing of yours touched)"
    )
    add_common_arguments(parser)
    args = parser.parse_args(argv)
    try:
        return smoke(args)
    except RefusedError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2


__all__ = ["entry", "group_paths", "smoke"]
