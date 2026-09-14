"""The git adapter, against a real local bare repository — no network.

Spec vault-sync ``## Backup``. These tests shell out to the real git
binary on purpose: the adapter's whole job is to be right about git's actual
behaviour, and a mocked subprocess would only assert our own assumptions.
"""

from __future__ import annotations

import pathlib
import subprocess
import tempfile

import pytest

from coffer.infrastructure.sync.git_mirror import GitMirror, GitMirrorError


@pytest.fixture
def remote(tmp_path: pathlib.Path) -> pathlib.Path:
    bare = tmp_path / "remote.git"
    subprocess.run(
        ["git", "init", "--bare", "-b", "main", str(bare)], check=True, capture_output=True
    )
    return bare


@pytest.fixture
def worktree(tmp_path: pathlib.Path) -> pathlib.Path:
    return tmp_path / "worktree"


@pytest.mark.asyncio
async def test_ensure_repo_initializes_and_sets_origin(
    worktree: pathlib.Path, remote: pathlib.Path
) -> None:
    mirror = GitMirror(worktree)
    await mirror.ensure_repo(remote_url=str(remote), branch="main")
    assert (worktree / ".git").is_dir()
    out = subprocess.run(
        ["git", "-C", str(worktree), "remote", "get-url", "origin"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert out.stdout.strip() == str(remote)


@pytest.mark.asyncio
async def test_ensure_repo_adopts_an_existing_repository(
    worktree: pathlib.Path, remote: pathlib.Path
) -> None:
    worktree.mkdir(parents=True)
    subprocess.run(["git", "init", "-b", "main", str(worktree)], check=True, capture_output=True)
    (worktree / "already-here.txt").write_text("kept")
    subprocess.run(["git", "-C", str(worktree), "add", "-A"], check=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(worktree),
            "-c",
            "user.email=t@t",
            "-c",
            "user.name=t",
            "commit",
            "-m",
            "history",
        ],
        check=True,
        capture_output=True,
    )

    mirror = GitMirror(worktree)
    await mirror.ensure_repo(remote_url=str(remote), branch="main")

    log = subprocess.run(
        ["git", "-C", str(worktree), "log", "--oneline"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "history" in log.stdout
    assert (worktree / "already-here.txt").exists()


@pytest.mark.asyncio
async def test_stage_all_reports_whether_anything_changed(
    worktree: pathlib.Path, remote: pathlib.Path
) -> None:
    mirror = GitMirror(worktree)
    await mirror.ensure_repo(remote_url=str(remote), branch="main")
    assert await mirror.stage_all() is False

    (worktree / "a.txt").write_text("one")
    assert await mirror.stage_all() is True
    await mirror.commit("first")
    assert await mirror.stage_all() is False


@pytest.mark.asyncio
async def test_commit_and_push_reach_the_remote(
    worktree: pathlib.Path, remote: pathlib.Path
) -> None:
    mirror = GitMirror(worktree)
    await mirror.ensure_repo(remote_url=str(remote), branch="main")
    (worktree / "a.txt").write_text("one")
    await mirror.stage_all()
    sha = await mirror.commit("first")
    assert sha
    await mirror.push(branch="main", token=None)

    out = subprocess.run(
        ["git", "-C", str(remote), "log", "--oneline", "main"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "first" in out.stdout


@pytest.mark.asyncio
async def test_push_failure_raises_with_a_redacted_message(
    worktree: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    missing = tmp_path / "nope.git"
    mirror = GitMirror(worktree)
    await mirror.ensure_repo(remote_url=str(missing), branch="main")
    (worktree / "a.txt").write_text("one")
    await mirror.stage_all()
    await mirror.commit("first")

    with pytest.raises(GitMirrorError) as excinfo:
        await mirror.push(branch="main", token="sup3rsecret")
    assert "sup3rsecret" not in str(excinfo.value)


@pytest.mark.asyncio
async def test_unpushed_commits_are_detected(worktree: pathlib.Path, remote: pathlib.Path) -> None:
    mirror = GitMirror(worktree)
    await mirror.ensure_repo(remote_url=str(remote), branch="main")
    (worktree / "a.txt").write_text("one")
    await mirror.stage_all()
    await mirror.commit("first")
    assert await mirror.has_unpushed(branch="main") is True
    await mirror.push(branch="main", token=None)
    assert await mirror.has_unpushed(branch="main") is False


@pytest.mark.asyncio
async def test_resolve_revision_accepts_a_date(
    worktree: pathlib.Path, remote: pathlib.Path
) -> None:
    mirror = GitMirror(worktree)
    await mirror.ensure_repo(remote_url=str(remote), branch="main")
    (worktree / "a.txt").write_text("one")
    await mirror.stage_all()
    first = await mirror.commit("first")
    (worktree / "a.txt").write_text("two")
    await mirror.stage_all()
    await mirror.commit("second")

    resolved = await mirror.resolve_revision("2999-01-01")
    assert resolved  # a far-future date resolves to the tip
    assert (await mirror.resolve_revision(first)).startswith(first[:7])


@pytest.mark.acceptance(
    spec="vault-sync",
    scenario="the push credential never reaches the repository",
)
@pytest.mark.asyncio
async def test_the_token_never_lands_in_git_config(
    worktree: pathlib.Path, remote: pathlib.Path
) -> None:
    mirror = GitMirror(worktree)
    await mirror.ensure_repo(remote_url=str(remote), branch="main")
    (worktree / "a.txt").write_text("one")
    await mirror.stage_all()
    await mirror.commit("first")
    await mirror.push(branch="main", token="sup3rsecret")
    assert "sup3rsecret" not in (worktree / ".git" / "config").read_text()


@pytest.mark.asyncio
async def test_the_askpass_helper_does_not_outlive_the_push(
    worktree: pathlib.Path, remote: pathlib.Path
) -> None:
    """The helper carrying the token is deleted even though the push succeeded."""
    tmp = pathlib.Path(tempfile.gettempdir())
    before = set(tmp.glob("coffer-askpass-*"))
    mirror = GitMirror(worktree)
    await mirror.ensure_repo(remote_url=str(remote), branch="main")
    (worktree / "a.txt").write_text("one")
    await mirror.stage_all()
    await mirror.commit("first")
    await mirror.push(branch="main", token="sup3rsecret")
    assert set(tmp.glob("coffer-askpass-*")) == before


@pytest.mark.asyncio
async def test_ensure_repo_repoints_a_changed_origin(
    worktree: pathlib.Path, remote: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    other = tmp_path / "other.git"
    subprocess.run(
        ["git", "init", "--bare", "-b", "main", str(other)], check=True, capture_output=True
    )
    mirror = GitMirror(worktree)
    await mirror.ensure_repo(remote_url=str(other), branch="main")
    await mirror.ensure_repo(remote_url=str(remote), branch="main")

    out = subprocess.run(
        ["git", "-C", str(worktree), "remote", "get-url", "origin"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert out.stdout.strip() == str(remote)


@pytest.mark.asyncio
async def test_a_date_before_any_backup_has_no_revision(
    worktree: pathlib.Path, remote: pathlib.Path
) -> None:
    mirror = GitMirror(worktree)
    await mirror.ensure_repo(remote_url=str(remote), branch="main")
    (worktree / "a.txt").write_text("one")
    await mirror.stage_all()
    await mirror.commit("first")

    with pytest.raises(GitMirrorError):
        await mirror.resolve_revision("2000-01-01")


@pytest.mark.asyncio
async def test_clone_then_read_an_earlier_revision_and_come_back(
    worktree: pathlib.Path, remote: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    """The restore path on a machine with no working tree of its own."""
    source = GitMirror(worktree)
    await source.ensure_repo(remote_url=str(remote), branch="main")
    (worktree / "a.txt").write_text("one")
    await source.stage_all()
    first = await source.commit("first")
    (worktree / "a.txt").write_text("two")
    await source.stage_all()
    await source.commit("second")
    await source.push(branch="main", token=None)

    fresh_path = tmp_path / "fresh"
    fresh = GitMirror(fresh_path)
    await fresh.clone(remote_url=str(remote), branch="main", token=None)
    assert (fresh_path / "a.txt").read_text() == "two"
    await fresh.fetch(token=None)
    assert await fresh.head() is not None

    await fresh.checkout(await fresh.resolve_revision(first))
    assert (fresh_path / "a.txt").read_text() == "one"

    await fresh.checkout_branch("main")
    assert (fresh_path / "a.txt").read_text() == "two"


# --- the converge round: merge, diff, snapshot tags ------------------------
#
# Spec vault-sync ``## The converge round``, ``## Conflicts`` and ``## Safety``.

#: Seven lines so two machines can edit opposite ends of one file and git has
#: enough context between them to merge without asking.
_LINES = "one\ntwo\nthree\nfour\nfive\nsix\nseven\n"
#: A path exercising git's C-quoting, which core.quotepath=false must switch
#: off: a knowledge note named in Chinese once came back escaped from a diff
#: and the conflict path chased a file that did not exist on disk.
_CHINESE = "知识/会议 纪要.md"


def _run(worktree: pathlib.Path, *args: str) -> str:
    """A git command run as the *other* machine would have, outside the adapter."""
    out = subprocess.run(
        ["git", "-C", str(worktree), "-c", "user.email=t@t", "-c", "user.name=t", *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return out.stdout


async def _seeded(worktree: pathlib.Path, remote: pathlib.Path, files: dict[str, str]) -> GitMirror:
    mirror = GitMirror(worktree)
    await mirror.ensure_repo(remote_url=str(remote), branch="main")
    for name, text in files.items():
        target = worktree / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    await mirror.stage_all()
    await mirror.commit("base")
    return mirror


async def _diverge(
    mirror: GitMirror, worktree: pathlib.Path, name: str, *, ours: str, theirs: str
) -> None:
    """Leave ``other`` holding ``theirs`` and the checked-out branch ``ours``."""
    _run(worktree, "checkout", "-b", "other")
    (worktree / name).write_text(theirs, encoding="utf-8")
    _run(worktree, "add", "-A")
    _run(worktree, "commit", "-m", "their edit")
    _run(worktree, "checkout", "main")
    (worktree / name).write_text(ours, encoding="utf-8")
    await mirror.stage_all()
    await mirror.commit("our edit")


@pytest.mark.asyncio
async def test_different_hunks_of_one_file_merge_without_a_conflict(
    worktree: pathlib.Path, remote: pathlib.Path
) -> None:
    mirror = await _seeded(worktree, remote, {"notes.md": _LINES})
    await _diverge(
        mirror,
        worktree,
        "notes.md",
        ours=_LINES.replace("seven", "SEVEN"),
        theirs=_LINES.replace("one", "ONE"),
    )

    assert await mirror.merge("other", message="converge") == []

    merged = (worktree / "notes.md").read_text(encoding="utf-8")
    assert "ONE" in merged and "SEVEN" in merged
    parents = _run(worktree, "rev-list", "--parents", "-n", "1", "HEAD").split()
    assert len(parents) == 3  # the commit and both sides


@pytest.mark.asyncio
async def test_an_up_to_date_merge_reports_nothing_and_commits_nothing(
    worktree: pathlib.Path, remote: pathlib.Path
) -> None:
    mirror = await _seeded(worktree, remote, {"notes.md": _LINES})
    _run(worktree, "branch", "other")
    before = await mirror.head()

    assert await mirror.merge("other", message="converge") == []
    assert await mirror.head() == before


@pytest.mark.asyncio
async def test_a_conflict_is_reported_and_the_merge_is_left_in_progress(
    worktree: pathlib.Path, remote: pathlib.Path
) -> None:
    mirror = await _seeded(worktree, remote, {"notes.md": _LINES})
    await _diverge(
        mirror,
        worktree,
        "notes.md",
        ours=_LINES.replace("four", "OURS"),
        theirs=_LINES.replace("four", "THEIRS"),
    )

    assert await mirror.merge("other", message="converge") == ["notes.md"]
    # In progress, not aborted and not committed: a resolver may still run.
    assert (worktree / ".git" / "MERGE_HEAD").exists()


@pytest.mark.asyncio
async def test_abort_merge_restores_the_pre_merge_commit(
    worktree: pathlib.Path, remote: pathlib.Path
) -> None:
    mirror = await _seeded(worktree, remote, {"notes.md": _LINES})
    await _diverge(
        mirror,
        worktree,
        "notes.md",
        ours=_LINES.replace("four", "OURS"),
        theirs=_LINES.replace("four", "THEIRS"),
    )
    before = await mirror.head()
    assert await mirror.merge("other", message="converge") == ["notes.md"]

    await mirror.abort_merge()

    assert await mirror.head() == before
    assert not (worktree / ".git" / "MERGE_HEAD").exists()
    assert "OURS" in (worktree / "notes.md").read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_commit_merge_concludes_a_resolved_merge(
    worktree: pathlib.Path, remote: pathlib.Path
) -> None:
    mirror = await _seeded(worktree, remote, {"notes.md": _LINES})
    await _diverge(
        mirror,
        worktree,
        "notes.md",
        ours=_LINES.replace("four", "OURS"),
        theirs=_LINES.replace("four", "THEIRS"),
    )
    await mirror.merge("other", message="converge")

    (worktree / "notes.md").write_text(_LINES.replace("four", "BOTH"), encoding="utf-8")
    assert await mirror.commit_merge("resolved")

    assert not (worktree / ".git" / "MERGE_HEAD").exists()
    assert "BOTH" in (worktree / "notes.md").read_text(encoding="utf-8")
    parents = _run(worktree, "rev-list", "--parents", "-n", "1", "HEAD").split()
    assert len(parents) == 3


@pytest.mark.asyncio
async def test_take_side_resolves_each_path_through_the_index(
    worktree: pathlib.Path, remote: pathlib.Path
) -> None:
    """Two conflicts, one resolved each way, and the index left merge-ready."""
    mirror = await _seeded(worktree, remote, {"a.md": _LINES, "b.md": _LINES})
    _run(worktree, "checkout", "-b", "other")
    for name in ("a.md", "b.md"):
        (worktree / name).write_text(_LINES.replace("four", "THEIRS"), encoding="utf-8")
    _run(worktree, "add", "-A")
    _run(worktree, "commit", "-m", "their edit")
    _run(worktree, "checkout", "main")
    for name in ("a.md", "b.md"):
        (worktree / name).write_text(_LINES.replace("four", "OURS"), encoding="utf-8")
    await mirror.stage_all()
    await mirror.commit("our edit")
    assert sorted(await mirror.merge("other", message="converge")) == ["a.md", "b.md"]

    await mirror.take_side("a.md", "ours")
    await mirror.take_side("b.md", "theirs")

    assert "OURS" in (worktree / "a.md").read_text(encoding="utf-8")
    assert "THEIRS" in (worktree / "b.md").read_text(encoding="utf-8")
    assert _run(worktree, "diff", "--name-only", "--diff-filter=U").strip() == ""
    assert await mirror.commit_merge("resolved")


@pytest.mark.asyncio
async def test_take_side_refuses_anything_but_ours_or_theirs(
    worktree: pathlib.Path, remote: pathlib.Path
) -> None:
    mirror = await _seeded(worktree, remote, {"notes.md": _LINES})
    with pytest.raises(GitMirrorError):
        await mirror.take_side("notes.md", "mine")


@pytest.mark.asyncio
async def test_both_sides_of_a_conflict_are_readable_as_merge_stages(
    worktree: pathlib.Path, remote: pathlib.Path
) -> None:
    """The arbitration reads the two versions without parsing conflict markers."""
    mirror = await _seeded(worktree, remote, {"notes.md": _LINES})
    ours = _LINES.replace("four", "OURS")
    theirs = _LINES.replace("four", "THEIRS")
    await _diverge(mirror, worktree, "notes.md", ours=ours, theirs=theirs)
    await mirror.merge("other", message="converge")

    assert await mirror.read_file(":2", "notes.md") == ours.encode()
    assert await mirror.read_file(":3", "notes.md") == theirs.encode()


@pytest.mark.asyncio
async def test_read_file_returns_raw_bytes_or_none(
    worktree: pathlib.Path, remote: pathlib.Path
) -> None:
    """Credential ciphertext must survive the trip; a decode would corrupt it."""
    blob = b"\x00\x01\xfe\xff gAAAA"
    mirror = await _seeded(worktree, remote, {"notes.md": _LINES})
    (worktree / "credentials").mkdir()
    (worktree / "credentials" / "a.enc").write_bytes(blob)
    await mirror.stage_all()
    await mirror.commit("ciphertext")
    head = await mirror.head()
    assert head

    assert await mirror.read_file(head, "credentials/a.enc") == blob
    assert await mirror.read_file(head, "credentials/gone.enc") is None


@pytest.mark.asyncio
async def test_read_worktree_sees_what_a_resolver_wrote(
    worktree: pathlib.Path, remote: pathlib.Path
) -> None:
    mirror = await _seeded(worktree, remote, {"notes.md": _LINES})
    (worktree / "notes.md").write_text("resolved by hand\n", encoding="utf-8")

    assert await mirror.read_worktree("notes.md") == b"resolved by hand\n"
    assert await mirror.read_worktree("never-existed.md") is None


@pytest.mark.acceptance(
    spec="vault-sync",
    scenario="a new machine takes the union and deletes nothing",
)
@pytest.mark.asyncio
async def test_diff_against_the_empty_tree_is_additions_only(
    worktree: pathlib.Path, remote: pathlib.Path
) -> None:
    mirror = await _seeded(worktree, remote, {"knowledge/a.md": "a", "knowledge/b.md": "b"})
    head = await mirror.head()
    assert head

    changes = await mirror.diff_paths(GitMirror.EMPTY_TREE, head)

    assert sorted(changes) == [("A", "knowledge/a.md"), ("A", "knowledge/b.md")]


@pytest.mark.asyncio
async def test_diff_paths_reports_a_deletion_and_a_modification(
    worktree: pathlib.Path, remote: pathlib.Path
) -> None:
    mirror = await _seeded(worktree, remote, {"knowledge/a.md": "a", "knowledge/b.md": "b"})
    first = await mirror.head()
    assert first
    (worktree / "knowledge" / "a.md").unlink()
    (worktree / "knowledge" / "b.md").write_text("edited", encoding="utf-8")
    await mirror.stage_all()
    await mirror.commit("second")
    second = await mirror.head()
    assert second

    changes = await mirror.diff_paths(first, second)

    assert sorted(changes) == [("D", "knowledge/a.md"), ("M", "knowledge/b.md")]


@pytest.mark.asyncio
async def test_a_non_ascii_path_is_never_c_quoted(
    worktree: pathlib.Path, remote: pathlib.Path
) -> None:
    """Regression: a note named in Chinese came back escaped and matched no file."""
    mirror = await _seeded(worktree, remote, {_CHINESE: _LINES})
    first = await mirror.head()
    assert first
    await _diverge(
        mirror,
        worktree,
        _CHINESE,
        ours=_LINES.replace("four", "OURS"),
        theirs=_LINES.replace("four", "THEIRS"),
    )
    second = await mirror.head()
    assert second

    assert await mirror.diff_paths(first, second) == [("M", _CHINESE)]
    assert await mirror.merge("other", message="converge") == [_CHINESE]
    assert (worktree / _CHINESE).exists()


@pytest.mark.asyncio
async def test_file_count_reads_the_commit_not_the_working_tree(
    worktree: pathlib.Path, remote: pathlib.Path
) -> None:
    mirror = await _seeded(
        worktree,
        remote,
        {"knowledge/a.md": "a", "knowledge/b.md": "b", "skills/s.md": "s"},
    )
    head = await mirror.head()
    assert head

    assert await mirror.file_count(head, "knowledge/") == 2
    assert await mirror.file_count(head, "skills/") == 1
    assert await mirror.file_count(head, "resources/") == 0
    assert await mirror.file_count(head, "") == 3

    # Deleting on disk must not move the denominator until it is committed.
    (worktree / "knowledge" / "a.md").unlink()
    assert await mirror.file_count(head, "knowledge/") == 2
    await mirror.stage_all()
    await mirror.commit("drop one")
    later = await mirror.head()
    assert later
    assert await mirror.file_count(later, "knowledge/") == 1


@pytest.mark.asyncio
async def test_snapshot_tags_are_created_listed_and_deleted(
    worktree: pathlib.Path, remote: pathlib.Path
) -> None:
    mirror = await _seeded(worktree, remote, {"notes.md": _LINES})
    head = await mirror.head()
    assert head
    await mirror.tag("coffer-sync/2026-09-13-1", head)
    await mirror.tag("coffer-sync/2026-09-13-2", head)
    await mirror.tag("release/v1", head)

    listed = await mirror.tags("coffer-sync/")
    assert sorted(listed) == ["coffer-sync/2026-09-13-1", "coffer-sync/2026-09-13-2"]

    await mirror.delete_tag("coffer-sync/2026-09-13-1")
    assert await mirror.tags("coffer-sync/") == ["coffer-sync/2026-09-13-2"]
    assert await mirror.tags("release/") == ["release/v1"]


@pytest.mark.asyncio
async def test_reset_hard_returns_the_tree_to_a_revision(
    worktree: pathlib.Path, remote: pathlib.Path
) -> None:
    """The round's repair step: a tree a crash left elsewhere goes back."""
    mirror = await _seeded(worktree, remote, {"notes.md": _LINES})
    pointer = await mirror.head()
    assert pointer
    (worktree / "notes.md").write_text("drifted\n", encoding="utf-8")
    await mirror.stage_all()
    await mirror.commit("drift")

    await mirror.reset_hard(pointer)

    assert await mirror.head() == pointer
    assert (worktree / "notes.md").read_text(encoding="utf-8") == _LINES
