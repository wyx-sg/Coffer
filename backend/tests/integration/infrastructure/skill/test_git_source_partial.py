"""A partial clone's checkout fetches the skill's files in one request.

Spec skill-manager "Add skills from a Git repository". The upstream is a bare
repository over ``file://`` that serves the ``blob:none`` filter, so the clone
really is partial: every file under the subpath is missing until fetched.
Each fetch from a promisor remote writes one ``.promisor`` pack, so their
number counts the fetches.
"""

from __future__ import annotations

import asyncio
import logging
import os
import pathlib
import stat

import pytest

from coffer.domain.skill_source_errors import SkillSourceUnreachable
from coffer.infrastructure.skill.git_source import GitSource, missing_object
from tests.support.skill_sources import Upstream, git, make_upstream, skill_md

_FILES = 12


def _upstream(tmp: pathlib.Path) -> Upstream:
    files = {"README.md": "repo\n", "skills/review/SKILL.md": skill_md("review")}
    files |= {f"skills/review/ref/{i}.md": f"file {i}\n" for i in range(_FILES)}
    files |= {"other/big.txt": "elsewhere\n"}
    up = make_upstream(tmp / "upstream", files)
    git("config", "uploadpack.allowFilter", "true", cwd=up.bare)
    git("config", "uploadpack.allowAnySHA1InWant", "true", cwd=up.bare)
    return up


def _promisor_packs(repo: pathlib.Path) -> int:
    return len(list((repo / ".git" / "objects" / "pack").glob("*.promisor")))


@pytest.mark.acceptance(
    spec="skill-manager", scenario="a partial clone fetches the skill's files in one request"
)
async def test_a_subpath_checkout_fetches_its_missing_files_in_one_request(
    tmp_path: pathlib.Path,
) -> None:
    up = _upstream(tmp_path)
    src = GitSource(timeout_s=60)
    repo = tmp_path / "repo"
    await src.clone(up.url, repo)
    commit = await src.resolve(repo, "main", url=up.url)
    assert len(await src.missing(repo, commit, "skills/review")) == _FILES + 1
    assert _promisor_packs(repo) == 1

    folder = await src.checkout(repo, commit, "skills/review", tmp_path / "tree", url=up.url)

    assert sorted(p.name for p in (folder / "ref").iterdir()) == sorted(
        f"{i}.md" for i in range(_FILES)
    )
    assert _promisor_packs(repo) == 2  # the clone, then one fetch for all thirteen files
    assert await src.missing(repo, commit, "skills/review") == []
    # Files outside the subpath stay on the server.
    assert await src.missing(repo, commit, "other") != []
    assert not (tmp_path / "repo-full").exists()


@pytest.mark.acceptance(
    spec="skill-manager", scenario="a partial clone fetches the skill's files in one request"
)
async def test_a_missing_object_falls_back_once_to_a_clone_without_the_filter(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    up = _upstream(tmp_path)
    src = GitSource(timeout_s=60)
    repo = tmp_path / "repo"
    await src.clone(up.url, repo)
    commit = await src.resolve(repo, "main", url=up.url)

    async def broken(*_a: object, **_k: object) -> int:
        raise SkillSourceUnreachable(
            "git fetch failed: fatal: You are attempting to fetch "
            f"{commit}, which is in the commit graph file but not in the object database. "
            "fatal: could not fetch c8faff05a14725142338bdff8fe9bd2901bcb443 from promisor remote"
        )

    monkeypatch.setattr(src, "prefetch", broken)
    caplog.set_level(logging.WARNING)

    folder = await src.checkout(repo, commit, "skills/review", tmp_path / "tree", url=up.url)

    assert (folder / "SKILL.md").is_file()
    assert len(list((folder / "ref").iterdir())) == _FILES
    full = tmp_path / "repo-full"
    assert full.is_dir() and _promisor_packs(full) == 0
    assert any(r.msg == "skill.git.partial_clone_fallback" for r in caplog.records)


async def test_a_subpath_the_commit_lacks_is_reported_without_a_fallback(
    tmp_path: pathlib.Path,
) -> None:
    up = _upstream(tmp_path)
    src = GitSource(timeout_s=60)
    repo = tmp_path / "repo"
    await src.clone(up.url, repo)
    commit = await src.resolve(repo, "main", url=up.url)

    with pytest.raises(SkillSourceUnreachable) as info:
        await src.checkout(repo, commit, "skills/absent", tmp_path / "tree", url=up.url)

    assert info.value.git_message.startswith("git checkout failed:")
    assert "skills/absent" in info.value.git_message
    assert not (tmp_path / "repo-full").exists()


def test_only_a_missing_object_counts_as_one() -> None:
    assert missing_object("fatal: could not fetch c8faff05a147 from promisor remote")
    assert missing_object("fatal: missing blob object 'abcdef1234'")
    assert not missing_object("error: pathspec 'skills/absent' did not match any file(s)")
    assert not missing_object("fatal: repository 'x' not found")


async def test_a_cancelled_call_kills_its_git_process(tmp_path: pathlib.Path) -> None:
    """The operation's overall deadline cancels a git call; the process goes with it."""
    pid_file = tmp_path / "pid"
    fake = tmp_path / "git"
    fake.write_text(f'#!/bin/sh\necho $$ > "{pid_file}"\nexec sleep 30\n')
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    src = GitSource(git=str(fake), timeout_s=60)

    with pytest.raises(TimeoutError):
        async with asyncio.timeout(0.5):
            await src.clone("https://example.invalid/r.git", tmp_path / "repo")

    pid = int(pid_file.read_text())
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)
