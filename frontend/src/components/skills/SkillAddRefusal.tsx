// src/components/skills/SkillAddRefusal.tsx
// Why a source was refused, inline under its field: no SKILL.md where one is looked for, the unsafe archive entries, or git's own message.
//
// Stage refusals arrive as `SKILL_INVALID` with a `details.reason` (and, for an
// archive, `details.offenders`), or as `SKILL_SOURCE_UNREACHABLE` whose message
// is git's (spec skill-manager "Add skills from a Git repository").
import { AlertTriangle } from "lucide-react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { AgentHandoff } from "@/components/handoff/AgentHandoff";
import { errorHandoff } from "@/lib/api/errorHandoff";
import { ApiError, translateApiError } from "@/lib/api/errors";

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

interface Props {
  error: unknown;
  /** One action beside the message, e.g. "Choose another file". */
  action?: ReactNode;
}

export function SkillAddRefusal({ error, action }: Props) {
  const { t } = useTranslation();
  const details = detailsOf(error);
  const reason = typeof details.reason === "string" ? details.reason : null;
  const offenders = offendersOf(details);
  // No git on this machine: the refusal carries the install hand-off.
  const handoff = errorHandoff(error);
  const message = error instanceof ApiError ? error.envelopeMessage : translateApiError(t, error);

  let title = t("skillSources.refusal.title");
  let body: ReactNode = message;
  if (reason === "git_missing") {
    title = t("skillSources.refusal.gitMissing");
    body = t("skillSources.refusal.gitMissingBody");
  } else if (error instanceof ApiError && error.code === "SKILL_SOURCE_UNREACHABLE") {
    title = t("skillSources.refusal.unreachable");
  } else if (error instanceof ApiError && error.code === "SKILL_INVALID") {
    if (reason === "skill_md_not_found") {
      title = t("skillSources.refusal.noSkillMd");
      body = t("skillSources.refusal.noSkillMdBody");
    } else if (reason === "archive_unsafe_entries") {
      title = t("skillSources.refusal.unsafe");
      body = t("skillSources.refusal.unsafeBody");
    } else if (reason === "size_limit_exceeded" || reason === "archive_too_large") {
      title = t("skillSources.refusal.tooLarge");
    }
  } else if (!(error instanceof ApiError)) {
    body = translateApiError(t, error);
  }

  return (
    <div role="alert" className="flex items-start gap-2.5 rounded-lg bg-danger-soft px-3 py-2.5">
      <AlertTriangle aria-hidden className="mt-px size-[15px] shrink-0 text-danger" />
      <div className="flex min-w-0 flex-col gap-1">
        <span className="text-sm font-label text-text">{title}</span>
        <span className="whitespace-pre-wrap break-words text-xs leading-[1.45] text-text-muted">
          {body}
        </span>
        {offenders.length > 0 ? (
          <ul className="flex flex-col gap-0.5" aria-label={t("skillSources.refusal.entries")}>
            {offenders.map((o) => (
              <li key={`${o.entry}:${o.problem}`} className="flex min-w-0 gap-2 text-xs">
                <span className="min-w-0 truncate font-mono text-text">{o.entry}</span>
                <span className="shrink-0 text-text-muted">
                  {PROBLEMS.has(o.problem)
                    ? t(`skillSources.refusal.problem.${o.problem}`)
                    : o.problem}
                </span>
              </li>
            ))}
          </ul>
        ) : null}
        {handoff ? (
          <span className="pt-1">
            <AgentHandoff prompt={handoff} size="sm" />
          </span>
        ) : null}
      </div>
      {action ? <span className="ml-auto shrink-0">{action}</span> : null}
    </div>
  );
}
