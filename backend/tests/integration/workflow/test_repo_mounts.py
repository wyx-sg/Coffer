"""A run's own checkout of a local repository, against real git (FR-057, FR-058).

Real ``git``, not a fake: what this layer promises is that the developer's
checkout is untouched, and only git can be asked whether that is true.
"""

from __future__ import annotations

import asyncio
import pathlib
import shutil

import pytest

from coffer.domain.workflow.run import REPO_MOUNT_LINK, REPO_MOUNT_WORKTREE
from coffer.infrastructure.workflow import artifacts, paths, repos

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not on PATH")

RUN_ID = "0123456789abcdef0123456789abcdef"


async def git(cwd: pathlib.Path, *args: str) -> str:
    proc = await asyncio.create_subprocess_exec(
        "git",
        "-C",
        str(cwd),
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate()
    assert proc.returncode == 0, err.decode()
    return out.decode()


@pytest.fixture(autouse=True)
def _run_tree(isolated_workflow_root: pathlib.Path) -> None:
    artifacts.ensure_run_dirs(RUN_ID)


@pytest.fixture
async def source(tmp_path: pathlib.Path) -> pathlib.Path:
    """A real git repository with one commit and one uncommitted edit."""
    repo = tmp_path / "account"
    repo.mkdir()
    await git(repo, "init", "-b", "main")
    await git(repo, "config", "user.email", "dev@example.invalid")
    await git(repo, "config", "user.name", "Dev")
    (repo / "README.md").write_text("committed\n", encoding="utf-8")
    await git(repo, "add", "README.md")
    await git(repo, "commit", "-m", "first")
    # The thing a run must never be able to touch.
    (repo / "scratch.txt").write_text("uncommitted work\n", encoding="utf-8")
    return repo


@pytest.mark.acceptance(
    spec="workflow", scenario="a mounted repository gives the run its own checkout"
)
async def test_a_git_repository_becomes_the_runs_own_worktree(source: pathlib.Path) -> None:
    mounted = await repos.mount_repo(RUN_ID, str(source))

    assert mounted.mount == REPO_MOUNT_WORKTREE
    assert mounted.isolated
    checkout = pathlib.Path(mounted.path)
    assert checkout.is_dir()
    assert checkout.parent == paths.workspace_dir(RUN_ID)
    assert (checkout / "README.md").read_text(encoding="utf-8") == "committed\n"
    # Its own branch, named for the run.
    branch = (await git(checkout, "rev-parse", "--abbrev-ref", "HEAD")).strip()
    assert branch == f"{repos.BRANCH_PREFIX}{RUN_ID[:12]}"


@pytest.mark.acceptance(
    spec="workflow", scenario="a mounted repository gives the run its own checkout"
)
async def test_the_developers_checkout_is_not_what_the_run_works_in(
    source: pathlib.Path,
) -> None:
    mounted = await repos.mount_repo(RUN_ID, str(source))
    checkout = pathlib.Path(mounted.path)

    # A separate directory, not a link back into the developer's tree, and the
    # file they had not committed is not in it.
    assert not checkout.is_symlink()
    assert checkout.resolve() != source.resolve()
    assert not (checkout / "scratch.txt").exists()
    # And theirs is where it was, on the branch it was on.
    assert (source / "scratch.txt").read_text(encoding="utf-8") == "uncommitted work\n"
    assert (await git(source, "rev-parse", "--abbrev-ref", "HEAD")).strip() == "main"


@pytest.mark.acceptance(
    spec="workflow", scenario="a mounted repository gives the run its own checkout"
)
async def test_unmounting_removes_the_worktree_and_leaves_the_source_as_it_was(
    source: pathlib.Path,
) -> None:
    before_branches = await git(source, "branch", "--list")
    before_status = await git(source, "status", "--porcelain")
    mounted = await repos.mount_repo(RUN_ID, str(source))
    checkout = pathlib.Path(mounted.path)
    (checkout / "new.txt").write_text("the run's work\n", encoding="utf-8")

    await repos.unmount_repo(RUN_ID, source=mounted.source, path=mounted.path, mount=mounted.mount)

    assert not checkout.exists()
    # Pruned, so git does not keep offering a worktree that is not there.
    listing = await git(source, "worktree", "list", "--porcelain")
    assert str(checkout) not in listing
    # FR-058: branches and working tree exactly as they were.
    assert await git(source, "branch", "--list") == before_branches
    assert await git(source, "status", "--porcelain") == before_status
    assert (source / "scratch.txt").read_text(encoding="utf-8") == "uncommitted work\n"
    assert (source / "README.md").read_text(encoding="utf-8") == "committed\n"


async def test_a_directory_that_is_not_a_repository_is_linked_in_and_says_so(
    tmp_path: pathlib.Path,
) -> None:
    plain = tmp_path / "notes"
    plain.mkdir()
    (plain / "a.md").write_text("hello\n", encoding="utf-8")

    mounted = await repos.mount_repo(RUN_ID, str(plain))

    assert mounted.mount == REPO_MOUNT_LINK
    assert not mounted.isolated
    link = pathlib.Path(mounted.path)
    assert link.is_symlink()
    assert (link / "a.md").read_text(encoding="utf-8") == "hello\n"


async def test_unmounting_a_link_removes_the_link_and_not_the_directory(
    tmp_path: pathlib.Path,
) -> None:
    plain = tmp_path / "notes"
    plain.mkdir()
    (plain / "a.md").write_text("hello\n", encoding="utf-8")
    mounted = await repos.mount_repo(RUN_ID, str(plain))

    await repos.unmount_repo(RUN_ID, source=mounted.source, path=mounted.path, mount=mounted.mount)

    assert not pathlib.Path(mounted.path).exists()
    assert (plain / "a.md").read_text(encoding="utf-8") == "hello\n"


async def test_two_repositories_with_one_basename_get_their_own_directories(
    tmp_path: pathlib.Path,
) -> None:
    first = tmp_path / "a" / "account"
    second = tmp_path / "b" / "account"
    for path in (first, second):
        path.mkdir(parents=True)

    one = await repos.mount_repo(RUN_ID, str(first))
    two = await repos.mount_repo(RUN_ID, str(second), taken=frozenset({one.name}))

    assert (one.name, two.name) == ("account", "account-2")
    assert pathlib.Path(two.path).exists()


@pytest.mark.parametrize(
    ("bad", "reason"),
    [
        ("", "no path given"),
        ("relative/path", "a repository input is an absolute path"),
        ("/nonexistent/definitely-not-here", "no such directory"),
    ],
)
async def test_a_repository_that_cannot_be_mounted_says_why_and_leaves_nothing(
    bad: str, reason: str
) -> None:
    with pytest.raises(repos.RepoMountError) as caught:
        await repos.mount_repo(RUN_ID, bad)

    assert caught.value.reason == reason
    assert list(paths.workspace_dir(RUN_ID).iterdir()) == []


async def test_a_file_is_not_a_repository(tmp_path: pathlib.Path) -> None:
    target = tmp_path / "a-file.txt"
    target.write_text("x", encoding="utf-8")

    with pytest.raises(repos.RepoMountError) as caught:
        await repos.mount_repo(RUN_ID, str(target))

    assert caught.value.reason == "not a directory"


async def test_mounting_the_same_name_twice_is_refused_rather_than_overwritten(
    source: pathlib.Path,
) -> None:
    await repos.mount_repo(RUN_ID, str(source))

    with pytest.raises(repos.RepoMountError) as caught:
        await repos.mount_repo(RUN_ID, str(source))

    assert "already in this run's working directory" in caught.value.reason


async def test_unmounting_a_checkout_whose_source_is_gone_still_clears_the_workspace(
    source: pathlib.Path,
) -> None:
    mounted = await repos.mount_repo(RUN_ID, str(source))
    shutil.rmtree(source)

    await repos.unmount_repo(RUN_ID, source=mounted.source, path=mounted.path, mount=mounted.mount)

    assert not pathlib.Path(mounted.path).exists()
