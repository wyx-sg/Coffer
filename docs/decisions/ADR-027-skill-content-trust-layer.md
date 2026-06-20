# ADR-027 — Skill Content Trust Layer (Heuristic Scan, Warn-Don't-Block)

> 中文版: [ADR-027-skill-content-trust-layer.zh.md](./ADR-027-skill-content-trust-layer.zh.md)

- **Status:** Accepted
- **Date:** 2026-06-19
- **Deciders:** Yuxing Wu
- **Spec:** [005-skill-manager](../../specs/005-skill-manager/spec.md) (FR-028, FR-029)

> **Amended (2026-06-20, simplification 4.3).** Skill Git-fetch was removed; the scan-on-ingest layer now covers local import + adopt + in-place edits only.

## Context

The competitive-landscape research ([`docs/research/agent-skills.md`](../research/agent-skills.md))
identified the **trust layer as the #1 highest-leverage gap**: the whole skill
ecosystem ships with no built-in sandboxing or signing, and the real threat is
the _bundled scripts_ a skill carries (OWASP "Agentic Skills Top 10", Snyk's
ToxicSkills, a malicious file that passed every one of Anthropic's scanners).
Coffer hardened _fetching_ (SSRF guard, shallow clone, size cap, neutralized
repo hooks — fetch since removed by simplification 4.3) but never looked at the _content_. For a tool that markets itself as
a vault, content trust is on-mission.

A hard constraint shapes what is even possible: **Coffer delivers skills but
never runs them.** The host agent (Claude Code, Codex, …) executes a skill's
scripts and is the only thing that can honor a skill's `allowed-tools`. Coffer
therefore cannot enforce runtime behavior. Its leverage is at **ingest and
enable time**: make risk legible, and gate the act of granting a skill to an
agent.

## Decision

Add a **level-L2 content trust layer**: heuristic scanning plus a
warn-don't-block acknowledgment gate.

1. **Heuristic scan.** A pure domain scanner (`domain/skill/content_scan.py`)
   walks a skill's text files and applies a small, versioned rule set
   (remote-exec pipes, network egress, secret/credential access, dangerous
   deletes, privilege escalation, obfuscated blobs), producing severity-tagged
   findings and an overall verdict. It is heuristic and non-authoritative: a
   finding is a prompt to review, and a clean report is not a guarantee. The
   ruleset carries a version so a stored verdict can be known stale.
2. **Scan on every content entry.** Import, adopt, and in-place file edits all re-scan; the verdict, findings count,
   ruleset version, and scan time are cached on the skill config (no migration —
   `config_json` is opaque). Every scan is audited.
3. **Warn, don't block ingest.** A risky skill always enters the master store.
   Over-blocking is the wrong default — false positives are common and a clean
   scan is not proof of safety, so blocking ingest would train users to bypass
   the tool while providing false assurance.
4. **Gate enabling, not ingest.** When the verdict is `high`/`critical`,
   enabling the skill for an agent is refused (`409`) until the user explicitly
   acknowledges the risk (audited). The follow/auto-bind reconcilers skip such a
   skill rather than delivering it. Acknowledgment is content-scoped: it resets
   whenever the skill's content changes. Adoption is exempt — it consolidates a
   skill already present in the agent's workspace, so blocking it would remove a
   skill the agent had and refuse to restore it.

## Alternatives considered

- **L1 — inventory + provenance only.** Surface scripts/hashes/declared
  `allowed-tools`/source, no risk judgment. Rejected as the target: it leaves
  the user to eyeball every script. L1 is retained as the foundation L2 builds on.
- **L3 — policy enforcement that blocks ingest/enable on critical findings.**
  Rejected for now: with documented scanner-evasion and false positives, hard
  blocking would reject legitimate skills and give false assurance. L3 remains a
  future opt-in policy on top of this layer.
- **Enforce `allowed-tools` at runtime.** Impossible by construction — Coffer
  does not execute skills. We parse and retain `allowed-tools` (ADR-aligned with
  FR-027) for legibility and future mismatch findings only.

## Consequences

- Users get a per-skill risk signal and an auditable acknowledgment trail; a
  flagged skill is not silently delivered to every following agent.
- The scan is best-effort and heuristic; it will both miss (false negatives) and
  over-flag (false positives). The verdict is advisory, never a safety claim.
- Future work (roadmap items): content-scan findings surfaced in discovery,
  `allowed-tools`-vs-behavior mismatch findings, and an optional L3 policy.
