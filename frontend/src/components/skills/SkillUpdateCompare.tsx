// src/components/skills/SkillUpdateCompare.tsx
// Compare, for a conflicting update: one file as it is here, at the pinned commit and in the new commit, side by side.
//
// Spec skill-manager "Update a Git-imported skill from its source" — Compare
// shows the local folder, the pinned commit and the new commit side by side.
import { useTranslation } from "react-i18next";

import { Skeleton } from "@/components/ui/skeleton";
import { translateApiError } from "@/lib/api/errors";
import type { SkillUpdateCompare as CompareOut } from "@/lib/api/skills";
import { useSkillUpdateCompare } from "@/lib/hooks/useSkills";
import { cn } from "@/lib/utils";

type Side = "local" | "pinned" | "incoming";

const SIDES: readonly Side[] = ["local", "pinned", "incoming"];

interface Props {
  uid: string;
  stagingId: string;
  /** The files that can be compared: the local edits and the incoming changes. */
  paths: string[];
  selected: string | null;
  onSelect: (path: string) => void;
}

function Column({ side, version }: { side: Side; version: CompareOut[Side] | undefined }) {
  const { t } = useTranslation();
  const body = !version ? (
    <Skeleton className="h-24 w-full" />
  ) : version.binary ? (
    <p className="p-3 text-xs text-text-muted">{t("skillSources.compare.binary")}</p>
  ) : version.text === null ? (
    <p className="p-3 text-xs text-text-muted">{t("skillSources.compare.missing")}</p>
  ) : (
    <pre className="overflow-auto whitespace-pre p-3 font-mono text-xs leading-5 text-text">
      {version.text}
    </pre>
  );
  return (
    <section
      aria-label={t(`skillSources.compare.${side}`)}
      className="flex min-w-0 flex-col overflow-hidden rounded-lg border border-border bg-surface-raised"
    >
      <header className="border-b border-border-subtle bg-surface-sunken px-3 py-1.5 text-2xs font-semibold text-text-muted">
        {t(`skillSources.compare.${side}`)}
        {version?.truncated ? ` · ${t("skillSources.compare.truncated")}` : null}
      </header>
      <div className="max-h-80 min-h-0 overflow-auto">{body}</div>
    </section>
  );
}

export function SkillUpdateCompare({ uid, stagingId, paths, selected, onSelect }: Props) {
  const { t } = useTranslation();
  const path = selected ?? paths[0] ?? null;
  const compare = useSkillUpdateCompare(uid, stagingId, path);
  return (
    <div className="flex min-w-0 flex-col gap-3">
      <div
        className="flex flex-wrap gap-1.5"
        role="group"
        aria-label={t("skillSources.compare.files")}
      >
        {paths.map((p) => (
          <button
            key={p}
            type="button"
            aria-pressed={p === path}
            onClick={() => onSelect(p)}
            className={cn(
              "h-control-sm rounded-md border px-2 font-mono text-2xs",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring",
              p === path
                ? "border-accent bg-accent-soft text-accent-text"
                : "border-border bg-surface-raised text-text hover:bg-surface-hover",
            )}
          >
            {p}
          </button>
        ))}
      </div>
      {compare.error ? (
        <p role="alert" className="text-xs text-danger">
          {translateApiError(t, compare.error)}
        </p>
      ) : (
        <div className="grid grid-cols-3 gap-3">
          {SIDES.map((side) => (
            <Column key={side} side={side} version={compare.data?.[side]} />
          ))}
        </div>
      )}
    </div>
  );
}
