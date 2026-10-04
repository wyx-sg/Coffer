// src/components/skills/SkillAddRefusal.tsx
// Why a source was refused. A folder or an archive is refused in red text under its own field (canvas 4.3.33, 4.3.51, 4.3.52); only the two Git
// refusals that depend on this machine — git missing, a clone that failed — are a problem block with the hand-off beside it (4.3.38, 4.3.53).
//
// Stage refusals arrive as `SKILL_INVALID` with a `details.reason` (and, for an
// archive, `details.offenders`; for a folder whose only skill is one level down,
// `details.candidate_folder` / `candidate_path`), or as `SKILL_SOURCE_UNREACHABLE`
// whose message is git's (spec skill-manager "Add skills from a Git repository").
import { AlertTriangle, CircleAlert } from "lucide-react";
import { useTranslation } from "react-i18next";

import { AgentHandoff } from "@/components/handoff/AgentHandoff";
import { errorHandoff } from "@/lib/api/errorHandoff";
import { ApiError, translateApiError } from "@/lib/api/errors";
import { gitSays, repoName } from "./skillSourceHelpers";

interface Offender {
  entry: string;
  problem: string;
}

const PROBLEMS = new Set(["absolute_path", "parent_segment", "symlink", "size_limit", "corrupt"]);

function detailsOf(error: unknown): Record<string, unknown> {
  if (error instanceof ApiError && error.details && typeof error.details === "object") {
    return error.details as Record<string, unknown>;
  }
  return {};
}

function offendersOf(details: Record<string, unknown>): Offender[] {
  const raw = details.offenders;
  if (!Array.isArray(raw)) return [];
  return raw.flatMap((o) =>
    o && typeof o === "object" && typeof (o as Offender).entry === "string"
      ? [{ entry: (o as Offender).entry, problem: String((o as Offender).problem ?? "") }]
      : [],
  );
}

function Line({ children }: { children: React.ReactNode }) {
  return (
    <p role="alert" className="flex items-start gap-1.5 text-xs leading-[1.45] text-danger">
      <CircleAlert aria-hidden className="mt-px size-[13px] shrink-0" />
      <span className="min-w-0 break-words">{children}</span>
    </p>
  );
}

interface FieldProps {
  error: unknown;
  /** What was looked in, for "No SKILL.md in {{file}}": the archive's name, the folder's last segment, the repository. */
  subject: string;
  /** "Use that folder": restage the folder one level down. */
  onUseFolder?: (path: string) => void;
}

/** The refusal of a folder, an archive or a repository without a skill, as red text under its field. */
export function SkillAddRefusal({ error, subject, onUseFolder }: FieldProps) {
  const { t } = useTranslation();
  const details = detailsOf(error);
  const reason = typeof details.reason === "string" ? details.reason : null;
  const offenders = offendersOf(details);
  const candidate = typeof details.candidate_folder === "string" ? details.candidate_folder : null;
  const candidatePath = typeof details.candidate_path === "string" ? details.candidate_path : null;
  const invalid = error instanceof ApiError && error.code === "SKILL_INVALID";

  if (invalid && candidate && candidatePath) {
    return (
      <>
        <Line>
          {t("skillSources.refusal.noSkillMdTop")}{" "}
          <span className="font-mono text-text">{candidate}/</span>
          {onUseFolder ? (
            <>
              {" — "}
              <button
                type="button"
                className="font-label text-accent-text hover:underline"
                onClick={() => onUseFolder(candidatePath)}
              >
                {t("skillSources.refusal.useFolder")}
              </button>
            </>
          ) : null}
        </Line>
        {reason !== "skill_md_not_found" ? (
          <Line>{(error as ApiError).envelopeMessage}</Line>
        ) : null}
      </>
    );
  }
  if (invalid && reason === "skill_md_not_found") {
    return <Line>{t("skillSources.refusal.noSkillMdIn", { file: subject })}</Line>;
  }
  if (invalid && reason === "archive_unsafe_entries") {
    return (
      <>
        <Line>{t("skillSources.refusal.unsafeBody")}</Line>
        <ul aria-label={t("skillSources.refusal.entries")} className="flex flex-col pl-[18px]">
          {offenders.map((o) => (
            <li
              key={`${o.entry}:${o.problem}`}
              className="flex min-w-0 gap-3 border-t border-border-subtle py-[5px] text-xs"
            >
              <span className="min-w-0 truncate font-mono text-text">{o.entry}</span>
              <span className="ml-auto shrink-0 whitespace-nowrap text-text-muted">
                {PROBLEMS.has(o.problem)
                  ? t(`skillSources.refusal.problem.${o.problem}`)
                  : o.problem}
              </span>
            </li>
          ))}
        </ul>
      </>
    );
  }
  if (invalid && (reason === "size_limit_exceeded" || reason === "archive_too_large")) {
    return <Line>{t("skillSources.refusal.tooLarge")}</Line>;
  }
  return (
    <Line>{error instanceof ApiError ? error.envelopeMessage : translateApiError(t, error)}</Line>
  );
}

/** Git missing or a clone that failed: a problem block, the hand-off to its right, then "?". */
export function SkillGitProblem({ error, url }: { error: unknown; url: string }) {
  const { t } = useTranslation();
  const details = detailsOf(error);
  const handoff = errorHandoff(error);
  const message = error instanceof ApiError ? error.envelopeMessage : translateApiError(t, error);
  const missing = details.reason === "git_missing";
  return (
    <div role="alert" className="flex items-start gap-2.5 rounded-lg bg-danger-soft px-3 py-2.5">
      <AlertTriangle aria-hidden className="mt-px size-[15px] shrink-0 text-danger" />
      <div className="flex min-w-0 flex-col gap-[3px]">
        <span className="text-sm font-label text-text">
          {missing
            ? t("skillSources.refusal.gitMissing")
            : t("skillSources.refusal.cloneFailed", { repo: repoName(url) })}
        </span>
        <span className="whitespace-pre-wrap break-words text-xs leading-[1.45] text-text-muted">
          {missing ? (
            t("skillSources.refusal.gitMissingBody")
          ) : (
            <>
              {t("skillSources.refusal.gitSaid")}{" "}
              <span className="font-mono text-text">{gitSays(message)}</span>
              {". "}
              {t(
                handoff
                  ? "skillSources.refusal.cloneHintHandoff"
                  : "skillSources.refusal.cloneHint",
              )}
            </>
          )}
        </span>
      </div>
      {handoff ? (
        <span className="ml-auto shrink-0">
          <AgentHandoff prompt={handoff} size="sm" />
        </span>
      ) : null}
    </div>
  );
}
