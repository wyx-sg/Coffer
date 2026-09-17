"""``WorkflowInputsService`` — what a run reads (FR-032, FR-050, FR-051).

A delivery starts from things that already exist: a PRD, a ticket, a design
doc, a file someone sent. The developer mounts them on the run and every node
that opens afterwards is told they are there.

Three properties this service exists to keep:

* **At any point in the run's life** (FR-050), not only at creation, and
  outside the version cycle — mounting a document advances nothing, so it does
  not bump the version every open client is holding. What it does change is
  what the NEXT node opens with, which is exactly the requirement.
* **Listed, never inlined** (FR-032). Nothing here reads a file's contents. A
  collection can be larger than the whole context budget, and a node is an
  agent with a filesystem: it is told the path and opens it.
* **Removing gives back what the run took.** An uploaded file's bytes and a
  mounted repository's checkout are the run's own, so unmounting one removes
  it. A collection and a link were never the run's, so unmounting one only
  unmounts it — and the repository a checkout came from is never touched
  either way (FR-058).
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Any, Protocol

from coffer.application.workflow.commands import RunCommands, utcnow
from coffer.application.workflow.context_composer import parse_inputs
from coffer.application.workflow.ports import (
    ArtifactStorePort,
    AttemptRepoPort,
    EventRepoPort,
    MachineIdPort,
    RunRepoPort,
)
from coffer.domain.workflow.errors import WorkflowError
from coffer.domain.workflow.run import RunInput, RunInputKind

__all__ = [
    "InputNotFound",
    "InputStorePort",
    "MountedRepoValue",
    "RepoMountPort",
    "WorkflowInputsService",
]

_logger = logging.getLogger(__name__)


class InputNotFound(WorkflowError):  # noqa: N818
    """Asked to unmount something this run does not have mounted."""

    code = "WORKFLOW_INPUT_NOT_FOUND"

    def __init__(self, run_id: str, ref: str) -> None:
        super().__init__(f"run {run_id} has no input {ref!r}")
        self.run_id = run_id
        self.ref = ref


class InputStorePort(Protocol):
    """An uploaded file's bytes, under the run's own directory (FR-051).

    Declared beside its only caller rather than in ``ports``: it is not a seam
    to another kind, it is this layer's own file storage, and
    ``infrastructure.workflow.inputs`` satisfies it structurally.

    ``write_input`` returns ``(ref, size)`` — the ref is the name relative to
    the run's input directory, chosen by the store because making a hostile
    filename safe is a question about paths and belongs where the path guard
    is. ``taken`` are the refs already mounted, so a second ``prd.pdf`` becomes
    a second file rather than overwriting the first.
    """

    def write_input(
        self,
        run_id: str,
        filename: str,
        content: bytes,
        *,
        taken: frozenset[str] = frozenset(),
    ) -> tuple[str, int, str]:
        """``(ref, size, absolute_path)``.

        The absolute path is the third value and not a convenience: an upload
        lands in the run's ``inputs/`` while a node runs in its ``workspace/``,
        so a path relative to the working directory would climb out of it with
        ``..`` — which some agents refuse outright. The node is told where the
        file actually is (FR-051)."""
        ...

    def delete_input(self, run_id: str, ref: str) -> None: ...


class MountedRepoValue(Protocol):
    """What mounting a repository produced, as the service records it.

    Read-only properties, not attributes: the concrete value is a FROZEN
    dataclass, which a Protocol declaring mutable attributes would not be
    satisfied by.
    """

    @property
    def path(self) -> str:
        """The checkout's absolute path inside the run's working directory."""
        ...

    @property
    def mount(self) -> str:
        """``worktree`` or ``link`` — what the run actually got (FR-057)."""
        ...


class RepoMountPort(Protocol):
    """Giving a run its own checkout of a local repository (FR-057, FR-058).

    Beside its only caller for the same reason ``InputStorePort`` is: it is
    this layer's own file and git work, satisfied structurally by
    ``infrastructure.workflow.repos``. It is async because it runs git.

    ``unmount`` takes the three things the input ROW carries, not the value the
    mount returned — the row is what survives a daemon restart, and an unmount
    that needed more would only work in the session that mounted.
    """

    async def mount(
        self, run_id: str, source: str, *, taken: frozenset[str] = frozenset()
    ) -> MountedRepoValue: ...

    async def unmount(self, run_id: str, *, source: str, path: str, mount: str) -> None: ...


class WorkflowInputsService:
    """Add, upload, remove and list a run's mounted inputs."""

    def __init__(
        self,
        *,
        runs: RunRepoPort,
        events: EventRepoPort,
        attempts: AttemptRepoPort,
        artifacts: ArtifactStorePort,
        uploads: InputStorePort,
        repos: RepoMountPort,
        machine: MachineIdPort,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self._runs = runs
        self._artifacts = artifacts
        self._uploads = uploads
        self._repos = repos
        self._clock = clock
        self._cmd = RunCommands(
            runs=runs, events=events, attempts=attempts, machine=machine, clock=clock
        )

    # -- reads ------------------------------------------------------------

    async def list_inputs(self, run_id: str) -> tuple[RunInput, ...]:
        """What the run reads, as value objects."""
        run = await self._cmd.require_run(run_id)
        return parse_inputs(run.inputs)

    def inputs_dir(self, run_id: str) -> str:
        """Where an uploaded input sits, as the node's context quotes it."""
        return f"{self._artifacts.run_dir(run_id).rstrip('/')}/inputs"

    # -- writes -----------------------------------------------------------

    async def add_input(
        self,
        run_id: str,
        *,
        kind: RunInputKind,
        ref: str,
        label: str | None = None,
    ) -> tuple[RunInput, ...]:
        """Mount a collection, an external reference, or a local repository.

        An uploaded FILE does not come through here — it carries a body rather
        than a reference, and its ref is the store's to choose.

        A REPO is checked out before the row moves, and a checkout that could
        not be made refuses the whole add (FR-057): an input pointing at a
        directory that is not there is a node told to work somewhere that does
        not exist, which reads as a broken run rather than a failed mount.
        """
        run = await self._require_mutable(run_id, "input.add")
        current = parse_inputs(run.inputs)
        # Mounting the same thing twice is the developer saying it once; the
        # label they typed the second time is the one they meant.
        kept = tuple(item for item in current if not (item.kind is kind and item.ref == ref))
        if kind is RunInputKind.REPO:
            added = await self._mount_repo(run_id, ref, label, kept)
        else:
            added = RunInput(kind=kind, ref=ref, label=label)
        return await self._write(run_id, (*kept, added))

    async def _mount_repo(
        self,
        run_id: str,
        ref: str,
        label: str | None,
        kept: Sequence[RunInput],
    ) -> RunInput:
        self._artifacts.ensure_run_dirs(run_id)
        taken = frozenset(
            _checkout_name(item) for item in kept if item.kind is RunInputKind.REPO and item.path
        )
        mounted = await self._repos.mount(run_id, ref, taken=taken)
        return RunInput(
            kind=RunInputKind.REPO,
            ref=ref,
            label=label,
            path=mounted.path,
            mount=mounted.mount,
        )

    async def upload_input(
        self,
        run_id: str,
        *,
        filename: str,
        content: bytes,
        label: str | None = None,
    ) -> tuple[RunInput, ...]:
        """Store an uploaded file under the run's directory and mount it.

        The bytes land before the row moves. A file with no input pointing at
        it is a stray the developer can delete; an input pointing at a file
        that was never written is a node told to read something that is not
        there, and it will say the run is broken rather than that the upload
        failed.
        """
        run = await self._require_mutable(run_id, "input.upload")
        current = parse_inputs(run.inputs)
        self._artifacts.ensure_run_dirs(run_id)
        taken = frozenset(item.ref for item in current if item.kind is RunInputKind.FILE)
        ref, size, path = self._uploads.write_input(run_id, filename, content, taken=taken)
        uploaded = RunInput(kind=RunInputKind.FILE, ref=ref, label=label, size=size, path=path)
        return await self._write(run_id, (*current, uploaded))

    async def remove_input(self, run_id: str, ref: str) -> tuple[RunInput, ...]:
        """Unmount ``ref``; an uploaded file's bytes go with it (FR-050)."""
        run = await self._require_mutable(run_id, "input.remove")
        current = parse_inputs(run.inputs)
        going = [item for item in current if item.ref == ref]
        if not going:
            raise InputNotFound(run_id, ref)
        kept = tuple(item for item in current if item.ref != ref)
        remaining = await self._write(run_id, kept)
        for item in going:
            await self._reclaim(run_id, item)
        return remaining

    async def _reclaim(self, run_id: str, item: RunInput) -> None:
        """Give back whatever the run was given for ``item``, if anything.

        The row is already gone, which is what the developer asked for, so a
        failure here is logged rather than raised: a file or a directory left
        behind is a stray, and refusing the unmount over one would leave the
        developer with an input they cannot remove.
        """
        try:
            if item.kind is RunInputKind.FILE:
                self._uploads.delete_input(run_id, item.ref)
            elif item.kind is RunInputKind.REPO and item.path and item.mount:
                # FR-058: this removes the run's checkout. The repository it
                # came from keeps its working tree and its own branches.
                await self._repos.unmount(run_id, source=item.ref, path=item.path, mount=item.mount)
            # A collection and a link were never the run's to delete.
        except (OSError, RuntimeError):
            _logger.warning(
                "workflow.input.reclaim_failed",
                extra={"run_id": run_id, "ref": item.ref, "kind": item.kind.value},
                exc_info=True,
            )

    # -- internals --------------------------------------------------------

    async def _require_mutable(self, run_id: str, attempted: str) -> Any:
        """The run, if this machine may change what it reads.

        ``version=None``: there is no optimistic lock on the inputs (see
        ``RunRepoPort.set_inputs``), but the machine check (FR-012) and the
        terminal-run check (FR-013) both still apply — a run this machine does
        not advance is read-only here, and an aborted run reads nothing more.
        """
        run = await self._cmd.require_run(run_id)
        self._cmd.guard(run, attempted, None)
        return run

    async def _write(self, run_id: str, inputs: Sequence[RunInput]) -> tuple[RunInput, ...]:
        updated = await self._runs.set_inputs(
            run_id, [_input_dict(item) for item in inputs], now=self._clock()
        )
        if updated is None:  # pragma: no cover - guarded by require_run above
            return tuple(inputs)
        return parse_inputs(updated.inputs)


def _checkout_name(item: RunInput) -> str:
    """The directory name a mounted repository occupies in the workspace."""
    return (item.path or "").rsplit("/", 1)[-1]


def _input_dict(item: RunInput) -> dict[str, Any]:
    """A mounted input as the ``inputs`` JSON column holds it (FR-032)."""
    return {
        "kind": item.kind.value,
        "ref": item.ref,
        "label": item.label,
        "size": item.size,
        "path": item.path,
        "mount": item.mount,
    }
