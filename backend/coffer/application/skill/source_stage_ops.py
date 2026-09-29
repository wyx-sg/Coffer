"""Stage a folder, an archive or a Git checkout, then confirm or cancel it.

Spec skill-manager "Import a skill from a local path", "Add skills from an
archive" and "Add skills from a Git repository". Staging reads and validates;
it never touches the master store, the database or an agent. Confirming
registers the chosen skills through the one import path every source shares
(``lifecycle_ops.register_from_validated``), so a staged skill is validated,
named, replaced and delivered exactly as a folder import is.
"""

from __future__ import annotations

import os
import pathlib
from typing import IO, TYPE_CHECKING

from coffer.application.skill.builtin_seed import is_builtin
from coffer.application.skill.lifecycle_ops import register_from_validated
from coffer.application.skill.staging import ImportStage, StagedSkill, remove_dir
from coffer.domain.audit import AuditEventType
from coffer.domain.errors import ResourceAlreadyExists, ResourceProtected, SkillValidationError
from coffer.domain.resource import Resource
from coffer.domain.skill.content_hash import folder_content_hash
from coffer.domain.skill.discovery import NO_SKILL_MD, find_skill_folders, looked_in
from coffer.domain.skill.git_url import parse_git_location
from coffer.domain.skill.source import (
    ArchiveImportSource,
    GitImportSource,
    ImportedSource,
    LocalImportSource,
)
from coffer.domain.skill.validator import ValidationFailure, validate_skill_folder
from coffer.domain.skill_source_errors import SkillSourceRejected

if TYPE_CHECKING:
    from coffer.application.skill.source_service import SkillSourceService


def _tree_size(folder: pathlib.Path) -> tuple[int, int]:
    """(file count, bytes) of the regular files under ``folder``, links not followed."""
    count = total = 0
    for root, dirnames, filenames in os.walk(folder, followlinks=False):
        dirnames[:] = [d for d in dirnames if d != ".git"]
        for name in filenames:
            entry = pathlib.Path(root) / name
            if entry.is_symlink():
                continue
            count += 1
            total += entry.stat().st_size
    return count, total


async def _taken(svc: SkillSourceService) -> tuple[set[str], set[str]]:
    """Names already used by a skill (or its master folder), and those of them
    that belong to a skill Coffer generates."""
    rows = await svc.skills._rs.list(kind="skill")
    taken = {r.name for r in rows}
    protected = {r.name for r in rows if is_builtin(r.config)}
    return taken, protected


async def _found(svc: SkillSourceService, root: pathlib.Path, label: str) -> list[StagedSkill]:
    discovery = find_skill_folders(root)
    if not discovery.folders:
        raise SkillSourceRejected(
            NO_SKILL_MD,
            f"no SKILL.md in {label}: it must be at the top or one folder down",
            looked_in(label),
        )
    taken, protected = await _taken(svc)
    out: list[StagedSkill] = []
    for rel in discovery.folders:
        path = root if rel == "." else root / rel
        count, size = _tree_size(path)
        result = validate_skill_folder(path, size_limit_bytes=svc.size_limit)
        if isinstance(result, ValidationFailure):
            err = SkillValidationError(result.reason, result.details)
            out.append(
                StagedSkill(rel, path, None, None, count, size, False, result.reason, str(err))
            )
            continue
        name = result.frontmatter.name
        out.append(
            StagedSkill(
                folder=rel,
                path=path,
                name=name,
                description=result.frontmatter.description,
                file_count=count,
                size_bytes=size,
                valid=True,
                taken=name in taken or svc.skills._store.exists(name),
                protected=name in protected,
            )
        )
    return out


async def stage_folder(svc: SkillSourceService, path: str) -> ImportStage:
    """Look at a folder on this machine; nothing is copied until confirm."""
    folder = pathlib.Path(path.strip().strip("\"'")).expanduser().resolve()
    if not folder.is_dir():
        raise SkillValidationError("folder_missing", {"path": str(folder)})
    skills = await _found(svc, folder, folder.name)

    def source(s: StagedSkill) -> ImportedSource:
        return LocalImportSource(original_path=str(s.path))

    stage = ImportStage(
        id=svc.staging.new_id(), kind="folder", label=str(folder), skills=skills, source_for=source
    )
    svc.staging.put(stage)
    return stage


async def stage_archive(svc: SkillSourceService, stream: IO[bytes], filename: str) -> ImportStage:
    """Save an uploaded archive into staging, refuse it or unpack it, and look."""
    name = pathlib.PurePath(filename.replace("\\", "/")).name or "archive.zip"
    stage_id, stage_dir = svc.staging.new_dir()
    try:
        archive = stage_dir / "upload.zip"
        svc.archives.save_upload(stream, archive, cap_bytes=svc.size_limit)
        tree = stage_dir / "tree"
        svc.archives.extract(archive, tree, cap_bytes=svc.size_limit)
        archive.unlink()
        skills = await _found(svc, tree, name)
    except BaseException:
        remove_dir(stage_dir)
        raise

    def source(s: StagedSkill) -> ImportedSource:
        return ArchiveImportSource(archive_name=name, folder="" if s.folder == "." else s.folder)

    stage = ImportStage(
        id=stage_id, kind="archive", label=name, skills=skills, source_for=source, dir=stage_dir
    )
    svc.staging.put(stage)
    return stage


async def stage_git(
    svc: SkillSourceService, url: str, ref: str | None, path: str | None
) -> ImportStage:
    """Clone into staging, pin the ref to one commit, check out the subpath, look."""
    try:
        loc = parse_git_location(url, ref, path)
    except ValueError as exc:
        raise SkillValidationError("git_location_invalid", {"path": str(exc)}) from exc
    stage_id, stage_dir = svc.staging.new_dir()
    try:
        repo = stage_dir / "repo"
        await svc.git.clone(loc.url, repo)
        commit = await svc.git.resolve(repo, loc.ref, url=loc.url)
        folder = await svc.git.checkout(repo, commit, loc.subpath, stage_dir / "tree", url=loc.url)
        _count, size = _tree_size(folder)
        if size > svc.size_limit:
            raise SkillSourceRejected(
                "size_limit_exceeded",
                f"{loc.subpath or 'the repository'} is larger than the "
                f"{svc.size_limit // (1024 * 1024)} MB skill cap at {commit[:7]}",
                {"total_bytes": size, "limit_bytes": svc.size_limit},
            )
        label = f"{loc.url}{'/' + loc.subpath if loc.subpath else ''}"
        skills = await _found(svc, folder, loc.subpath or "the repository")
    except BaseException:
        remove_dir(stage_dir)
        raise

    def source(s: StagedSkill) -> ImportedSource:
        sub = loc.subpath if s.folder == "." else "/".join(p for p in (loc.subpath, s.folder) if p)
        return GitImportSource(
            url=loc.url,
            ref=loc.ref,
            subpath=sub,
            commit=commit,
            content_hash=folder_content_hash(s.path),
        )

    stage = ImportStage(
        id=stage_id,
        kind="git",
        label=label,
        skills=skills,
        source_for=source,
        dir=stage_dir,
        ref=loc.ref,
        subpath=loc.subpath,
        commit=commit,
    )
    svc.staging.put(stage)
    return stage


async def confirm(
    svc: SkillSourceService,
    stage_id: str,
    *,
    names: list[str],
    replace: list[str],
    actor: str,
) -> list[Resource]:
    """Register the chosen skills of an import stage, then remove the stage.

    Every choice is checked before the first write: a name the stage did not
    find valid, a taken name not listed in ``replace`` (409) and a name Coffer
    generates (409) each refuse the whole confirm and keep the stage, so the
    dialog can offer Replace and try again.
    """
    stage = svc.staging.get(stage_id)
    if not isinstance(stage, ImportStage):
        raise SkillValidationError("not_an_import_stage", {"path": stage_id})
    by_name = {s.name: s for s in stage.skills if s.valid and s.name}
    if not names:
        raise SkillValidationError("no_skill_chosen", {})
    chosen: list[StagedSkill] = []
    for name in dict.fromkeys(names):
        staged = by_name.get(name)
        if staged is None:
            raise SkillValidationError("skill_not_in_stage", {"path": name})
        chosen.append(staged)
    taken, protected = await _taken(svc)
    for s in chosen:
        assert s.name is not None
        if s.name in protected:
            raise ResourceProtected(
                f"skill {s.name}",
                "the name belongs to a skill Coffer generates and rewrites at every start; "
                "add it under a different name",
            )
        exists = s.name in taken or svc.skills._store.exists(s.name)
        if exists and s.name not in replace:
            raise ResourceAlreadyExists("skill", s.name)
    added: list[Resource] = []
    try:
        for s in chosen:
            assert s.name is not None
            result = validate_skill_folder(s.path, size_limit_bytes=svc.size_limit)
            if isinstance(result, ValidationFailure):
                raise SkillValidationError(result.reason, result.details)
            if result.frontmatter.name != s.name:
                raise SkillValidationError("skill_changed_since_staged", {"path": str(s.path)})
            added.append(
                await register_from_validated(
                    service=svc.skills,
                    src=s.path,
                    validation=result,
                    source_meta=stage.source_for(s),
                    event=AuditEventType.SKILL_IMPORTED,
                    actor=actor,
                    overwrite=s.name in replace,
                    audit_details={"source": stage.kind},
                )
            )
    finally:
        svc.staging.discard(stage.id)
    return added


__all__ = ["confirm", "stage_archive", "stage_folder", "stage_git"]
