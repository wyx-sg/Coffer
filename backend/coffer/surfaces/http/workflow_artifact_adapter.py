"""``ArtifactStorePort`` over the run directory (spec workflow FR-041, FR-053).

Split from ``workflow_adapters`` to keep that module under its line ceiling.
The seam is the one the rest of that file already draws: every other adapter
there wraps a SERVICE this daemon composed, while this one wraps the
filesystem — the infrastructure exposes functions rather than a class, because
path handling has no state worth holding, so the object the engine's port wants
is assembled here rather than existing anywhere else.
"""

from __future__ import annotations

import pathlib
import shutil
from collections.abc import Sequence

from coffer.infrastructure.workflow import artifacts as wf_artifacts
from coffer.infrastructure.workflow import files as wf_files
from coffer.infrastructure.workflow import paths as wf_paths


class FileArtifactStore:
    """``ArtifactStorePort`` over the run directory's module-level functions.

    The infrastructure exposes functions rather than a class — path handling has
    no state worth holding — so the object the engine's port wants is assembled
    here. ``delete_run_dir`` is the one operation with no function behind it,
    because deleting a tree is the only thing in this file that is destructive
    and it belongs beside the guard that decides what a run directory is.
    """

    def run_dir(self, run_id: str) -> str:
        return str(wf_paths.run_dir(run_id))

    def workspace_dir(self, run_id: str) -> str:
        """The run's own working directory — what every node's conversation
        runs in, and what a mounted repository is checked out into (FR-053)."""
        return str(wf_paths.workspace_dir(run_id))

    def ensure_run_dirs(self, run_id: str) -> None:
        wf_artifacts.ensure_run_dirs(run_id)

    def list_artifacts(self, run_id: str) -> Sequence[wf_artifacts.ArtifactEntry]:
        return wf_artifacts.list_artifacts(run_id)

    def write_catalogue(self, run_id: str, markdown: str) -> None:
        path = wf_paths.catalog_path(run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(markdown, encoding="utf-8")

    def read_catalogue(self, run_id: str) -> str:
        try:
            return wf_paths.catalog_path(run_id).read_text(encoding="utf-8")
        except OSError:
            # Absent is not an error: the catalogue is generated, and a run that
            # has produced nothing has nothing to describe.
            return ""

    def collect_run_files(
        self, run_id: str, destination: str, *, references: str | None = None
    ) -> int:
        return wf_artifacts.collect_run_files(
            run_id, pathlib.Path(destination), references=references
        )

    def read_file(self, run_id: str, rel_path: str) -> wf_files.RunFile | None:
        return wf_files.read_file(run_id, rel_path)

    def read_bytes(self, run_id: str, rel_path: str) -> tuple[bytes, str] | None:
        return wf_files.read_bytes(run_id, rel_path)

    def delete_run_dir(self, run_id: str) -> None:
        shutil.rmtree(wf_paths.run_dir(run_id), ignore_errors=True)
