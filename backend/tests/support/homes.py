"""Isolated-HOME builders: one machine, two machines and a remote, agent dirs.

Every Coffer path derives from ``$HOME``, so "a machine" in a test is a home
directory. These builders make one on disk and hand back an object that knows
its own layout; they never touch the real home (the guard in
``real_home_guard.py`` would fail the test if they did).

* :func:`make_home` / :class:`IsolatedHome` — one machine. ``activate`` points
  this process at it; ``env`` is the environment for a subprocess (daemon,
  shim, CLI) that should run *as* that machine.
* :func:`two_machine_homes` / :class:`TwoMachineHomes` — two homes and one real
  bare git repository they both reach, for sync scenarios driven through real
  processes. (The in-process vault harness in ``integration/sync/harness.py``
  composes the round from explicit roots and uses :func:`bare_remote` from
  here.)
* :func:`fake_agent_dir` / :class:`FakeAgentDir` — an agent's config tree
  (``~/.claude``, ``~/.codex``) laid out from the agent's own descriptor, so a
  file lands exactly where Coffer's code will look for it.

The fixtures that wrap these for everyday use are in ``fixtures.py``.
"""

from __future__ import annotations

import contextlib
import os
import pathlib
import subprocess
from collections.abc import Iterator, Mapping
from dataclasses import dataclass

import pytest

from coffer.domain.agent.descriptor import AGENT_DESCRIPTORS, AgentDescriptor
from coffer.domain.agent.types import AgentType
from tests.support.real_home_guard import write_home_skeleton

#: The pins the root conftest (or a test) may set that are not derived from
#: ``HOME``. A machine built here derives everything from its own ``HOME``, the
#: way an installed Coffer does, so these are removed wherever a home is applied.
ROOT_PINS: tuple[str, ...] = (
    "COFFER_LOG_DIR",
    "COFFER_DB_URL",
)

DEFAULT_BRANCH = "main"


@dataclass(frozen=True)
class IsolatedHome:
    """One machine's home directory."""

    root: pathlib.Path

    @property
    def coffer_dir(self) -> pathlib.Path:
        return self.root / ".coffer"

    @property
    def db_path(self) -> pathlib.Path:
        return self.coffer_dir / "coffer.db"

    @property
    def knowledge_root(self) -> pathlib.Path:
        return self.coffer_dir / "vault" / "knowledge"

    def activate(self, monkeypatch: pytest.MonkeyPatch) -> IsolatedHome:
        """Make this the home of the current process for the rest of the test."""
        monkeypatch.setenv("HOME", str(self.root))
        for name in ROOT_PINS:
            monkeypatch.delenv(name, raising=False)
        return self

    def env(self, extra: Mapping[str, str] | None = None) -> dict[str, str]:
        """The environment a subprocess needs to run as this machine: the
        current (already scrubbed) environment, this ``HOME``, no root pins."""
        env = {k: v for k, v in os.environ.items() if k not in ROOT_PINS}
        env["HOME"] = str(self.root)
        env.update(extra or {})
        return env


def make_home(path: pathlib.Path) -> IsolatedHome:
    """A fresh home at ``path`` with an empty ``.coffer`` and a git identity."""
    home = IsolatedHome(write_home_skeleton(path))
    home.coffer_dir.mkdir(exist_ok=True)
    return home


def bare_remote(path: pathlib.Path, *, branch: str = DEFAULT_BRANCH) -> str:
    """A real bare repository to converge through, with an identity of its own
    so a machine with no global git config can still be committed against."""
    subprocess.run(
        ["git", "init", "--bare", "-b", branch, str(path)], check=True, capture_output=True
    )
    for key, value in (("user.email", "harness@localhost"), ("user.name", "Harness")):
        subprocess.run(
            ["git", "-C", str(path), "config", key, value], check=True, capture_output=True
        )
    return str(path)


@dataclass(frozen=True)
class TwoMachineHomes:
    """Two machines that share nothing but one bare git remote."""

    a: IsolatedHome
    b: IsolatedHome
    remote_url: str
    branch: str = DEFAULT_BRANCH

    def remote_log(self) -> list[str]:
        """Subjects of the remote's commits on :attr:`branch`, newest first."""
        proc = subprocess.run(
            ["git", "--git-dir", self.remote_url, "log", "--format=%s", self.branch],
            capture_output=True,
            text=True,
        )
        return proc.stdout.splitlines() if proc.returncode == 0 else []


def two_machine_homes(base: pathlib.Path, *, branch: str = DEFAULT_BRANCH) -> TwoMachineHomes:
    """``base/machine-a``, ``base/machine-b`` and ``base/remote.git``."""
    return TwoMachineHomes(
        a=make_home(base / "machine-a"),
        b=make_home(base / "machine-b"),
        remote_url=bare_remote(base / "remote.git", branch=branch),
        branch=branch,
    )


@dataclass(frozen=True)
class FakeAgentDir:
    """An agent's config directory under an isolated home."""

    home: IsolatedHome
    descriptor: AgentDescriptor
    config_dir: pathlib.Path

    @property
    def agent_type(self) -> AgentType:
        return self.descriptor.type

    @property
    def is_default(self) -> bool:
        return self.config_dir == self.home.root / self.descriptor.config_subpath

    @property
    def skills_dir(self) -> pathlib.Path:
        return self.config_dir / self.descriptor.skill_subpath

    def path(self, key: str) -> pathlib.Path:
        """Where the agent keeps the allowlisted file ``key`` (``settings``,
        ``config``, ``global``…), resolved by the descriptor itself."""
        with _home_as(self.home.root):
            specs = {spec.key: spec for spec in self.descriptor.config_files(self.config_dir)}
        if key not in specs:
            raise KeyError(f"{self.agent_type.value} has no config file {key!r}: {sorted(specs)}")
        return specs[key].path

    def write(self, key: str, content: str) -> pathlib.Path:
        target = self.path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return target

    def add_skill(self, name: str, body: str = "# skill\n") -> pathlib.Path:
        """An unmanaged skill folder the agent owns (not a Coffer delivery)."""
        folder = self.skills_dir / name
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "SKILL.md").write_text(body, encoding="utf-8")
        return folder

    def home_env(self) -> dict[str, str]:
        """What a spawned agent needs to find a non-default dir (e.g.
        ``CLAUDE_CONFIG_DIR``); empty for the default one."""
        if self.is_default or not self.descriptor.home_env_var:
            return {}
        return {self.descriptor.home_env_var: str(self.config_dir)}


def fake_agent_dir(
    home: IsolatedHome,
    agent_type: AgentType,
    *,
    config_dir: pathlib.Path | None = None,
    files: Mapping[str, str] | None = None,
) -> FakeAgentDir:
    """Lay out ``agent_type``'s config tree in ``home``: the default dir
    (``~/.claude``) unless ``config_dir`` names a custom one, an empty skills
    dir, and ``files`` — allowlist key -> content — written where the
    descriptor says the agent reads them."""
    descriptor = AGENT_DESCRIPTORS[agent_type]
    agent = FakeAgentDir(
        home=home,
        descriptor=descriptor,
        config_dir=config_dir or home.root / descriptor.config_subpath,
    )
    agent.skills_dir.mkdir(parents=True, exist_ok=True)
    for key, content in (files or {}).items():
        agent.write(key, content)
    return agent


@contextlib.contextmanager
def _home_as(root: pathlib.Path) -> Iterator[None]:
    """The descriptor resolves some paths against the live ``$HOME`` (Claude's
    ``.claude.json`` sits beside the default dir); resolve them against the
    home being built even when it is not the active one."""
    previous = os.environ.get("HOME")
    os.environ["HOME"] = str(root)
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = previous
