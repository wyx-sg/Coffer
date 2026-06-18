"""`SkillConfig` — Pydantic schema stored on `Resource.config` for kind=skill."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from coffer.domain.skill.source import SkillSource


class SkillConfig(BaseModel):
    """Resource.config payload when kind == 'skill'."""

    model_config = ConfigDict(extra="forbid")

    source: SkillSource
    # Capped at 64 to match the master store folder-name limit and the
    # SKILL.md frontmatter ``name`` cap (see ``frontmatter._NAME_RE``).
    skill_md_name: str = Field(min_length=1, max_length=64)
    # Capped at 1024 to match the SKILL.md frontmatter ``description`` cap
    # (see ``frontmatter._DESCRIPTION_MAX``).
    skill_md_description: str = Field(min_length=1, max_length=1024)
    version_hash: str = Field(min_length=1, max_length=128)
    last_synced_from_source_at: datetime | None = None

    # Trust layer L2 (FR-028/FR-029). The content scan runs on ingest/update and
    # its result is cached here. All optional with defaults so pre-trust-layer
    # rows (and the opaque config_json) still validate without a migration.
    scan_verdict: str | None = None  # Severity value: low|medium|high|critical
    scan_findings_count: int = 0
    scan_ruleset_version: str | None = None
    last_scanned_at: datetime | None = None
    # Set True only by an explicit acknowledge action; reset on any content
    # change so a prior acknowledgment never carries over to new content.
    risk_acknowledged: bool = False

    # Update detection (FR-030/FR-031). Set by an on-demand check; cleared when
    # an update is applied. `pinned` suppresses the "update available" signal.
    # All optional with defaults — no migration (config_json is opaque).
    update_available: bool = False
    available_version_hash: str | None = None
    last_update_check_at: datetime | None = None
    pinned: bool = False
