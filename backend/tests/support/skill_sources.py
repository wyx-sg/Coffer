"""Local Git repositories and archives for the skill-source tests.

Every repository is a bare one under ``tmp_path`` reached over ``file://``
(spec skill-manager "Add skills from a Git repository" allows the ``file``
transport), so nothing here touches the network. ``Upstream`` is the
maintainer's side: a working clone that commits and pushes to the bare
repository Coffer clones from.
"""

from __future__ import annotations

import io
import pathlib
import subprocess
import zipfile
from dataclasses import dataclass

from coffer.application.skill.source_service import SkillSourceService

_IDENTITY = ("-c", "user.name=t", "-c", "user.email=t@t")


def git(*args: str, cwd: pathlib.Path) -> str:
    out = subprocess.run(
        ["git", *_IDENTITY, *args], cwd=cwd, check=True, capture_output=True, text=True
    )
    return out.stdout.strip()


def skill_md(name: str, body: str = "body", *, requires: str | None = None) -> str:
    extra = f"requires: {requires}\n" if requires else ""
    return f"---\nname: {name}\ndescription: A test skill named {name}.\n{extra}---\n\n{body}\n"


@dataclass
class Upstream:
    work: pathlib.Path
    bare: pathlib.Path

    @property
    def url(self) -> str:
        return f"file://{self.bare}"

    def write(self, rel: str, text: str) -> None:
        path = self.work / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def remove(self, rel: str) -> None:
        (self.work / rel).unlink()

    def commit(self, message: str, *, tag: str | None = None) -> str:
        """Commit everything in the working clone, push it, return the commit id."""
        git("add", "-A", cwd=self.work)
        git("commit", "-q", "--allow-empty", "-m", message, cwd=self.work)
        if tag:
            git("tag", tag, cwd=self.work)
        git("push", "-q", "--tags", str(self.bare), "main", cwd=self.work)
        return git("rev-parse", "HEAD", cwd=self.work)

    def head(self) -> str:
        return git("rev-parse", "HEAD", cwd=self.work)


def make_upstream(root: pathlib.Path, files: dict[str, str], *, tag: str | None = None) -> Upstream:
    """A bare repository at ``root/repo.git`` whose ``main`` holds ``files``."""
    root.mkdir(parents=True, exist_ok=True)
    bare = root / "repo.git"
    subprocess.run(
        ["git", "init", "-q", "--bare", "-b", "main", str(bare)], check=True, capture_output=True
    )
    work = root / "work"
    work.mkdir()
    git("init", "-q", "-b", "main", cwd=work)
    up = Upstream(work=work, bare=bare)
    for rel, text in files.items():
        up.write(rel, text)
    up.commit("initial", tag=tag)
    return up


def zip_bytes(entries: dict[str, str | bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return buf.getvalue()


def symlink_zip(link: str, target: str, extra: dict[str, str] | None = None) -> bytes:
    """An archive whose ``link`` entry is a symlink to ``target``."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in (extra or {}).items():
            zf.writestr(name, data)
        info = zipfile.ZipInfo(link)
        info.external_attr = 0o120777 << 16
        zf.writestr(info, target)
    return buf.getvalue()


def stage_dirs(service: SkillSourceService) -> list[str]:
    """The stage directories a running source service still holds on disk."""
    root = service.staging._root
    if root is None or not root.exists():
        return []
    return sorted(p.name for p in root.iterdir())


__all__ = [
    "Upstream",
    "git",
    "make_upstream",
    "skill_md",
    "stage_dirs",
    "symlink_zip",
    "zip_bytes",
]
