// src/components/skills/SkillFoundList.tsx
// What a staged source holds: one card for a single skill, or a row per skill to choose from, with the ones that can't be added and why.
//
// A taken name is chosen as a Replace (spec skill-manager "Add skills from an
// archive", "a taken name offers replace"); a built-in name and an invalid
// folder cannot be chosen at all.
import { AlertTriangle, Check, X } from "lucide-react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { Checkbox } from "@/components/ui/checkbox";
import type { SkillStaging, StagedSkill } from "@/lib/api/skills";
import { cn, formatBytes } from "@/lib/utils";
import { isChoosable } from "./skillSourceHelpers";

interface Props {
  stage: SkillStaging;
  selected: Set<string>;
  onToggle: (name: string) => void;
}

function Meta({ skill }: { skill: StagedSkill }) {
  const { t } = useTranslation();
  return (
    <span className="shrink-0 text-xs text-text-muted">
      {t("skillSources.found.meta", {
        count: skill.file_count,
        size: formatBytes(skill.size_bytes),
      })}
    </span>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[90px_minmax(0,1fr)] items-baseline gap-4 border-t border-border-subtle py-[7px]">
      <span className="text-xs text-text-muted">{label}</span>
      <span className="min-w-0 break-words text-sm text-text">{children}</span>
    </div>
  );
}

function SingleSkill({ skill }: { skill: StagedSkill }) {
  const { t } = useTranslation();
  const ok = skill.valid && !skill.protected;
  const heading = !skill.valid
    ? t("skillSources.found.invalid")
    : skill.folder === "."
      ? t("skillSources.found.top")
      : t("skillSources.found.inFolder", { folder: skill.folder });
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col gap-1.5 overflow-hidden rounded-lg border border-border bg-surface-raised px-3 pb-1 pt-2.5">
        <div className="flex items-center gap-2">
          {ok ? (
            <Check aria-hidden className="size-[15px] shrink-0 text-success" />
          ) : (
            <X aria-hidden className="size-[15px] shrink-0 text-danger" />
          )}
          <span className="min-w-0 text-sm text-text">{heading}</span>
          <span className="ml-auto">
            <Meta skill={skill} />
          </span>
        </div>
        <div className="flex flex-col">
          {skill.name ? (
            <Field label={t("skillSources.found.name")}>
              <span className="font-mono text-xs">{skill.name}</span>
            </Field>
          ) : null}
          {skill.valid ? (
            <Field label={t("skillSources.found.description")}>
              {skill.description || (
                <span className="text-text-muted">{t("skillSources.found.noDescription")}</span>
              )}
            </Field>
          ) : (
            <Field label={t("skillSources.found.why")}>{skill.message ?? skill.reason}</Field>
          )}
          {skill.protected ? (
            <Field label={t("skillSources.found.why")}>{t("skillSources.found.protected")}</Field>
          ) : null}
        </div>
      </div>
      {skill.valid && skill.taken && !skill.protected && skill.name ? (
        <div
          role="status"
          className="flex items-start gap-2.5 rounded-lg bg-warning-soft px-3 py-2.5"
        >
          <AlertTriangle aria-hidden className="mt-px size-[15px] shrink-0 text-warning" />
          <div className="flex min-w-0 flex-col gap-1">
            <span className="text-sm font-label text-text">
              {t("skillSources.found.takenTitle", { name: skill.name })}
            </span>
            <span className="text-xs leading-[1.45] text-text-muted">
              {t("skillSources.found.takenBody", { name: skill.name })}
            </span>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function SkillRow({
  skill,
  checked,
  onToggle,
}: {
  skill: StagedSkill;
  checked: boolean;
  onToggle: (name: string) => void;
}) {
  const { t } = useTranslation();
  const choosable = isChoosable(skill);
  const label = skill.name ?? skill.folder;
  const note = !skill.valid
    ? (skill.message ?? skill.reason)
    : skill.protected
      ? t("skillSources.found.protected")
      : skill.taken
        ? t("skillSources.found.taken")
        : null;
  return (
    <li
      className={cn(
        "flex items-start gap-2.5 border-t border-border-subtle px-3 py-2 first:border-t-0",
        !choosable && "bg-surface-sunken",
      )}
    >
      {choosable ? (
        <Checkbox
          className="mt-0.5"
          checked={checked}
          onChange={() => onToggle(skill.name)}
          aria-label={
            skill.taken
              ? t("skillSources.found.replaceNamed", { name: skill.name })
              : t("skillSources.found.chooseNamed", { name: skill.name })
          }
        />
      ) : (
        <X aria-hidden className="mt-0.5 size-[15px] shrink-0 text-danger" />
      )}
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <div className="flex min-w-0 items-center gap-2">
          <span className="min-w-0 truncate font-mono text-xs font-medium text-text">{label}</span>
          {skill.valid && skill.taken && !skill.protected ? (
            <span className="shrink-0 rounded-sm bg-warning-soft px-1.5 text-2xs font-label text-warning-foreground">
              {t("skillSources.found.replace")}
            </span>
          ) : null}
          <span className="ml-auto">
            <Meta skill={skill} />
          </span>
        </div>
        {skill.valid && skill.description ? (
          <span className="text-xs text-text-muted">{skill.description}</span>
        ) : null}
        {note ? (
          <span className={cn("text-xs", choosable ? "text-text-muted" : "text-danger")}>
            {note}
          </span>
        ) : null}
      </div>
    </li>
  );
}

export function SkillFoundList({ stage, selected, onToggle }: Props) {
  const { t } = useTranslation();
  if (stage.skills.length === 1) return <SingleSkill skill={stage.skills[0]} />;
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-xs text-text-muted">
        {t("skillSources.found.several", { count: stage.skills.length })}
      </span>
      <ul
        aria-label={t("skillSources.found.listLabel")}
        className="max-h-72 overflow-y-auto rounded-lg border border-border bg-surface-raised"
      >
        {stage.skills.map((skill) => (
          <SkillRow
            key={skill.folder}
            skill={skill}
            checked={!!skill.name && selected.has(skill.name)}
            onToggle={onToggle}
          />
        ))}
      </ul>
    </div>
  );
}
