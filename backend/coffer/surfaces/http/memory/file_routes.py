"""``/api/v1/memory/partitions/{uid}/files`` — the partition's own directory.

**Read-only, and that is the design.** Everything under ``~/.coffer/memory/``
is derived ("Keep the memory tree derived and local"): an edit would survive
exactly until the next aggregation
pass, so offering one would be offering a lie. It does not route through
``/api/v1/fs`` either — that family browses directories and deliberately never
serves file contents — so the shape here follows ``knowledge/routes.py``'s own
``tree``/``file`` pair instead, scoped to one partition.
"""

from __future__ import annotations

import pathlib

from fastapi import APIRouter, Depends, Query

from coffer.application.resource_service import ResourceService
from coffer.infrastructure.memory import files as memory_files
from coffer.infrastructure.memory import paths as memory_paths
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_resource_service
from coffer.surfaces.http.memory.lookup import require_partition
from coffer.surfaces.http.memory.schemas import FileContentOut, FileNodeOut, FileTreeOut

router = APIRouter(
    prefix="/api/v1/memory",
    tags=["memory"],
    dependencies=[Depends(require_token)],
)


def _abs_paths(root: pathlib.Path, relpath: str) -> tuple[str, str]:
    """An entry's absolute path and that of the folder holding it.

    Both travel on every node and every read because a browser cannot resolve
    a path on the user's own disk — the open-in-editor and reveal-in-file-
    manager actions hand these back to the daemon, which can (ADR
    ``daemon-proxies-os-file-actions``).
    """
    target = root if relpath == "" else root / relpath
    return str(target), str(target.parent)


def _node_out(node: memory_files.FileNode, root: pathlib.Path) -> FileNodeOut:
    abs_path, folder_abs_path = _abs_paths(root, node.path)
    return FileNodeOut(
        name=node.name,
        path=node.path,
        abs_path=abs_path,
        folder_abs_path=folder_abs_path,
        type=node.type,
        derived=node.derived,
        size=node.size,
        truncated=node.truncated,
        children=[_node_out(child, root) for child in node.children],
    )


def _content_out(content: memory_files.FileContent, root: pathlib.Path) -> FileContentOut:
    abs_path, folder_abs_path = _abs_paths(root, content.path)
    return FileContentOut(
        path=content.path,
        abs_path=abs_path,
        folder_abs_path=folder_abs_path,
        content=content.content,
        truncated=content.truncated,
        binary=content.binary,
        size=content.size,
    )


@router.get("/partitions/{uid}/files", response_model=FileTreeOut)
async def list_partition_files(
    uid: str,
    resources: ResourceService = Depends(get_resource_service),  # noqa: B008
) -> FileTreeOut:
    """The partition's own directory, as a read-only tree."""
    partition = await require_partition(uid, resources)
    # The directory is named by the label, which is why the row is resolved
    # rather than the uid used directly: identity addresses the partition, the
    # label is where its files are.
    root = memory_paths.partition_dir(partition.name)
    return FileTreeOut(root=_node_out(memory_files.build_tree(root), root))


@router.get("/partitions/{uid}/files/content", response_model=FileContentOut)
async def read_partition_file(
    uid: str,
    #: A path INSIDE the already-identified partition — ``notes/foo.md``. A
    #: filesystem path, so it is a name and stays one: there is no identity
    #: below the partition to address a file by.
    path: str = Query(min_length=1),
    resources: ResourceService = Depends(get_resource_service),  # noqa: B008
) -> FileContentOut:
    """One file out of the partition's directory.

    ``UnsafeMemoryPath`` (400) and ``MemoryFileNotFound`` (404) both propagate
    to the app-wide handler in ``surfaces/http/errors.py``, which already maps
    every ``CofferError`` — the same way knowledge's own file read reports an
    escape or a miss, rather than each route inventing an ``HTTPException``.
    """
    partition = await require_partition(uid, resources)
    root = memory_paths.partition_dir(partition.name)
    return _content_out(memory_files.read_file(partition.name, root, path), root)
