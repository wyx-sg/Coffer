"""Pure validator for an on-disk AgentSkills folder.

Given a directory path, returns either `ValidationOk` (with parsed
frontmatter and total size) or `ValidationError` (with a reason and details).
No I/O happens outside the small set documented here:

- reads `SKILL.md` text content
- walks the folder to compute total size and to scan for path-escape symlinks

This is borderline for the "domain is pure" contract (Contract 3) since it
does read the filesystem. Coffer's convention treats filesystem reads of
*paths the user supplies* as application-layer; this validator lives in
domain because it implements the AgentSkills spec, which is conceptual, not
infrastructural. The contract is currently satisfied because the validator
does not import any infrastructure / surfaces module — it only uses stdlib.

Domain exception: the validator must touch the filesystem to inspect a
skill folder (size walk, symlink-escape scan, ``SKILL.md`` hash) and there
is no value in extracting a pure-then-impure split — the cost of walking
the tree dominates. The schema-only check on the parsed frontmatter is
already pure (see ``SkillFrontmatter``). Future ADR if we ever revisit:
move FS I/O to ``coffer.application.skill.validator_io`` and have this
module accept a pre-walked ``FolderManifest`` instead. Not worth doing now.
"""

from __future__ import annotations

import hashlib
import os
import pathlib
from dataclasses import dataclass

import yaml
from pydantic import ValidationError

from coffer.domain.skill.frontmatter import SkillFrontmatter


@dataclass(frozen=True)
class ValidationOk:
    frontmatter: SkillFrontmatter
    total_size_bytes: int
    skill_md_sha256: str


@dataclass(frozen=True)
class ValidationFailure:
    reason: str
    details: dict[str, object]


def validate_skill_folder(
    folder: pathlib.Path,
    *,
    size_limit_bytes: int = 50 * 1024 * 1024,
) -> ValidationOk | ValidationFailure:
    """Verify a folder conforms to the AgentSkills minimum spec.

    Checks:
    - folder exists and is a directory
    - SKILL.md present at the folder root
    - SKILL.md has a parseable YAML frontmatter delimited by `---` lines
    - frontmatter conforms to `SkillFrontmatter` (non-empty name/description)
    - no symlink inside the folder resolves outside the folder
    - total folder size ≤ `size_limit_bytes`

    Returns `ValidationOk` (with parsed frontmatter, total bytes, and the
    sha256 of SKILL.md's bytes) or `ValidationFailure` with a reason code.
    """
    if not folder.exists():
        return ValidationFailure("folder_missing", {"path": str(folder)})
    if not folder.is_dir():
        return ValidationFailure("not_a_directory", {"path": str(folder)})

    skill_md = folder / "SKILL.md"
    if not skill_md.is_file():
        return ValidationFailure("skill_md_missing", {"path": str(skill_md)})

    raw_bytes = skill_md.read_bytes()
    sha = hashlib.sha256(raw_bytes).hexdigest()
    raw_text = raw_bytes.decode("utf-8", errors="replace")

    frontmatter_data = _parse_frontmatter(raw_text)
    if frontmatter_data is None:
        return ValidationFailure(
            "skill_md_frontmatter_missing",
            {"path": str(skill_md)},
        )

    try:
        fm = SkillFrontmatter.model_validate(frontmatter_data)
    except ValidationError as e:
        return ValidationFailure(
            "skill_md_frontmatter_invalid",
            {"errors": e.errors()},
        )

    # Walk: detect path-escape symlinks and accumulate size. `os.walk` with
    # followlinks=False does not recurse into symlinked directories, so a
    # cyclic symlink inside a malicious folder cannot send the walk into an
    # infinite loop. Symlinked entries still surface in dirnames/filenames
    # and are inspected individually.
    folder_resolved = folder.resolve()
    total = 0
    bad_links: list[str] = []
    for root, dirnames, filenames in os.walk(folder, followlinks=False):
        root_path = pathlib.Path(root)
        for nm in (*dirnames, *filenames):
            entry = root_path / nm
            try:
                if entry.is_symlink():
                    target = entry.resolve(strict=False)
                    # Resolved target must remain inside the folder.
                    if not _is_relative_to(target, folder_resolved):
                        bad_links.append(str(entry.relative_to(folder)))
                        continue
                if entry.is_file():
                    total += entry.stat().st_size
            except OSError:
                # Broken link or unreadable entry — treat as a bad link.
                bad_links.append(str(entry.relative_to(folder)))

    if bad_links:
        return ValidationFailure(
            "path_escape_symlinks",
            {"offenders": bad_links},
        )

    if total > size_limit_bytes:
        return ValidationFailure(
            "size_limit_exceeded",
            {"total_bytes": total, "limit_bytes": size_limit_bytes},
        )

    return ValidationOk(frontmatter=fm, total_size_bytes=total, skill_md_sha256=sha)


def _parse_frontmatter(text: str) -> dict[str, object] | None:
    """Extract the `---`-delimited YAML frontmatter at the top of SKILL.md.

    Returns `None` if no frontmatter block is found or the YAML is invalid.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return None
    body = "\n".join(lines[1:end])
    try:
        data = yaml.safe_load(body)
    except yaml.YAMLError:
        return None
    if not isinstance(data, dict):
        return None
    return data


def _is_relative_to(child: pathlib.Path, parent: pathlib.Path) -> bool:
    """Path.is_relative_to was added in 3.9; we use 3.12, so direct call works."""
    try:
        child.relative_to(parent)
    except ValueError:
        return False
    return True
