"""``coffer run`` — hand standalone secrets to one child process, and only it.

Spec secret "Resolve standalone secrets into one child with coffer run";
ADR standalone-secrets-are-named-references-injected-into-one-child.

    coffer run --secret db-password -- psql -h db.internal
    coffer run --secret PGPASSWORD=coffer://secret/<id> -- psql -h db.internal
    coffer run --secret PGPASSWORD=db-password --env-file app.env -- ./migrate

Every ``--secret NAME`` (as ``$NAME`` upper-cased, ``-``/``.`` → ``_``) or
``--secret ENV=NAME``, every ``coffer://secret/<name>`` value in ``--env-file``
and every such value already in this environment is resolved through the
daemon — which audits each one as ``secret_resolved`` — and set **only in the
child's environment**. The shell that ran this, and its other children, never
hold the value. The child's stdout and stderr pass through a filter that
replaces each exact value with ``***``.

Only secrets a person granted to local programs in the desktop app resolve;
any other is refused, nothing starts and the request waits in the app. The
grant is the line that matters: whoever runs ``coffer run`` — an agent too —
owns the child and can read its environment or run ``coffer run --secret X --
env``, so masking only keeps a value out of transcripts, files and git by
accident. A secret an agent should only *use* stays without the grant and
reaches its service through Coffer (an MCP server or custom tool).
"""

from __future__ import annotations

import os
import pathlib
import signal
import subprocess
import sys
import threading
from typing import IO, Any

import typer

from coffer.domain.secret_masking import MIN_MASKED_LENGTH, StreamMasker
from coffer.domain.secrets import default_env_var, is_valid_secret_name, parse_secret_uri
from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli._options import ExitCode

#: Exit status when the command itself could not be started.
_NOT_STARTED = 127


def _parse_spec(spec: str) -> tuple[str, str]:
    """``NAME`` → (default var, NAME); ``ENV=NAME`` → (ENV, NAME).

    The name may be written as its URI, ``coffer://secret/<id>``, the form a
    skill cites a secret in.
    """
    var, _, name = spec.partition("=") if "=" in spec else ("", "", spec)
    name = name.strip()
    name = parse_secret_uri(name) or name
    if not is_valid_secret_name(name):
        typer.echo(f"invalid secret name: {name!r}", err=True)
        raise typer.Exit(int(ExitCode.INVALID_INPUT))
    return (var.strip() or default_env_var(name)), name


def _read_env_file(path: pathlib.Path) -> tuple[dict[str, str], dict[str, str]]:
    """(plain variables, {variable: secret name}) from a KEY=VALUE file.

    A file that cannot be read, or is not UTF-8 text, exits 6 before anything
    is resolved or started."""
    try:
        text = path.read_bytes().decode("utf-8")
    except OSError as e:
        typer.echo(f"coffer run: cannot read --env-file {path}: {e.strerror or e}", err=True)
        raise typer.Exit(int(ExitCode.INVALID_INPUT)) from None
    except UnicodeDecodeError as e:
        typer.echo(f"coffer run: --env-file {path} is not UTF-8 text (byte {e.start})", err=True)
        raise typer.Exit(int(ExitCode.INVALID_INPUT)) from None
    plain: dict[str, str] = {}
    cited: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.removeprefix("export ").partition("=")
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        name = parse_secret_uri(value)
        if name is not None:
            cited[key] = name
        else:
            plain[key] = value
    return plain, cited


def _pump(source: IO[bytes], sink: IO[bytes], masker: StreamMasker) -> None:
    for chunk in iter(lambda: source.read1(65536), b""):  # type: ignore[attr-defined]
        out = masker.feed(chunk)
        if out:
            sink.write(out)
            sink.flush()
    tail = masker.flush()
    if tail:
        sink.write(tail)
        sink.flush()


def run(
    ctx: typer.Context,
    secret: list[str] = typer.Option(
        [],
        "--secret",
        help="NAME, ENV=NAME or ENV=coffer://secret/<id> of a standalone secret (repeatable)",
    ),
    env_file: pathlib.Path | None = typer.Option(
        None,
        "--env-file",
        readable=False,
        help="KEY=VALUE file; coffer://secret/<name> values are resolved",
    ),
    no_masking: bool = typer.Option(
        False, "--no-masking", help="Pass the child's output through unfiltered"
    ),
) -> None:
    """Run a command with secrets set only in its environment.

    Only a secret granted to local programs in the Coffer app resolves; any
    other is refused and the request waits there. Each resolution is audited.
    Output is masked: exact secret values print as ***. Masking guards against
    accidents — a value landing in a transcript, a file or git — and does not
    hide a granted secret from an agent that runs the command.

    \f
    Spec secret "Resolve standalone secrets into one child with coffer run".
    """
    command = list(ctx.args)
    if not command:
        typer.echo(
            "usage: coffer run [--secret NAME|ENV=NAME|ENV=coffer://secret/ID]… -- COMMAND [ARGS]…",
            err=True,
        )
        raise typer.Exit(int(ExitCode.INVALID_USAGE))
    verbose = (ctx.obj or {}).get("verbose", False)

    wanted: dict[str, str] = {}  # variable -> secret name
    child_env = dict(os.environ)
    # References already in this environment are resolved too (the pattern
    # `op run` uses), so a wrapper script can export them once.
    for key, value in os.environ.items():
        name = parse_secret_uri(value)
        if name is not None:
            wanted[key] = name
    if env_file is not None:
        plain, cited = _read_env_file(env_file)
        child_env.update(plain)
        wanted.update(cited)
    for spec in secret:
        var, name = _parse_spec(spec)
        wanted[var] = name

    values: dict[str, str] = {}
    if wanted:
        c, _info = _cli_client.client_or_exit()
        with c:
            r = c.post(
                "/secrets/resolve",
                json={
                    "names": sorted(set(wanted.values())),
                    "argv0": command[0],
                    "cwd": os.getcwd(),
                },
            )
            _cli_client.check(r, verbose=verbose)
            values = r.json()["values"]
    for var, name in wanted.items():
        child_env[var] = values[name]

    masked = [] if no_masking else list(values.values())
    short = [n for n in set(wanted.values()) if len(values[n]) < MIN_MASKED_LENGTH]
    if short and not no_masking:
        typer.echo(
            f"coffer run: not masking {', '.join(sorted(short))} "
            f"(shorter than {MIN_MASKED_LENGTH} characters)",
            err=True,
        )
    raise typer.Exit(_spawn(command, child_env, masked))


def _spawn(command: list[str], env: dict[str, str], masked: list[str]) -> int:
    piped = StreamMasker(masked).active
    popen_kwargs: dict[str, Any] = {"env": env}
    if piped:
        popen_kwargs |= {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE}
    try:
        child = subprocess.Popen(command, **popen_kwargs)
    except OSError as e:
        typer.echo(f"coffer run: cannot start {command[0]!r}: {e.strerror or e}", err=True)
        return _NOT_STARTED

    def forward(signum: int, _frame: Any) -> None:
        child.send_signal(signum)

    previous = {s: signal.signal(s, forward) for s in (signal.SIGINT, signal.SIGTERM)}
    try:
        pumps: list[threading.Thread] = []
        if piped:
            assert child.stdout is not None and child.stderr is not None
            for source, sink in (
                (child.stdout, sys.stdout.buffer),
                (child.stderr, sys.stderr.buffer),
            ):
                # One masker per stream: each holds back its own tail.
                t = threading.Thread(target=_pump, args=(source, sink, StreamMasker(masked)))
                t.start()
                pumps.append(t)
        code = child.wait()
        for t in pumps:
            t.join()
    finally:
        for s, handler in previous.items():
            signal.signal(s, handler)
    return 128 - code if code < 0 else code
