// frontend/src/components/skills/SkillLibrary.tsx
// The left pane of the Skills page: the library of managed skills. A filter
// field (name + description), the Reach filter, Check copies, then
// "Library N" over one row per skill (SkillLibraryRow). While rows are ticked
// the selection bar (SkillsBulkBar) sits under the filter and every row shows
// its checkbox; otherwise a row shows it on hover. Only managed skills are
// here — an agent's own skills live on that agent's Skills tab.
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { RefreshCw } from "lucide-react";

import { ReachFilter } from "@/components/reach/ReachFilter";
import { SearchInput } from "@/components/SearchInput";
import { SkillLibraryRow } from "@/components/skills/SkillLibraryRow";
import { SkillOrphanList } from "@/components/skills/SkillOrphanList";
import { SkillsBulkBar } from "@/components/skills/SkillsBulkBar";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import type { SkillDriftEntry, SkillOut } from "@/lib/api/skills";
import { useAgents } from "@/lib/hooks/useAgents";
import { useClis } from "@/lib/hooks/useClis";
import { matchesReach, type ReachFilterValue } from "@/lib/reachFilter";

interface Props {
  skills: SkillOut[];
  isLoading: boolean;
  /** The open skill's name, highlighted in the list. */
  selectedName: string | null;
  /** Where a row leads for a skill name — the same tab as the open one. */
  hrefFor: (name: string) => string;
  onOpenSkill: () => void;
  onCheckCopies: () => void;
  checkingCopies: boolean;
  /** The last Check copies report, for the rows' "Folder in the way" lines. */
  drift: SkillDriftEntry[] | undefined;
  /** Ticked row uids (the page owns them: the reading pane shows the selection). */
  picked: ReadonlySet<string>;
  onPickedChange: (picked: ReadonlySet<string>) => void;
  /** The ticked skills that still exist and can be deleted. */
  selected: SkillOut[];
  /** The store folder open in the reading pane (`?orphan=`), if any. */
  orphan: string | null;
}

export function SkillLibrary({
  skills,
  isLoading,
  selectedName,
  hrefFor,
  onOpenSkill,
  onCheckCopies,
  checkingCopies,
  drift,
  picked,
  onPickedChange,
  selected,
  orphan,
}: Props) {
  const { t } = useTranslation();
  const { data: agents = [] } = useAgents();
  const clis = useClis().data?.items ?? [];
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<ReachFilterValue>("all");

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return skills.filter((s) => {
      if (!matchesReach(filter, s)) return false;
      return !q || `${s.name} ${s.description}`.toLowerCase().includes(q);
    });
  }, [skills, query, filter]);

  const toggle = (uid: string, on: boolean) => {
    const next = new Set(picked);
    if (on) next.add(uid);
    else next.delete(uid);
    onPickedChange(next);
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex flex-col gap-2.5 px-3 pb-2.5 pt-3.5">
        <SearchInput
          value={query}
          onChange={setQuery}
          placeholder={t("skills.searchPlaceholder")}
          ariaLabel={t("skills.searchPlaceholder")}
        />
        <div className="flex items-center gap-2">
          <ReachFilter value={filter} onChange={setFilter} />
          <Button
            variant="ghost"
            size="sm"
            className="ml-auto"
            onClick={onCheckCopies}
            disabled={checkingCopies}
          >
            <RefreshCw aria-hidden className={checkingCopies ? "animate-spin" : undefined} />
            {t("skills.checkCopies")}
          </Button>
        </div>
        {selected.length > 0 ? (
          <SkillsBulkBar skills={selected} onDone={() => onPickedChange(new Set())} />
        ) : null}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-3">
        <h2 className="flex items-center px-2.5 pb-1 text-2xs font-semibold text-text-muted">
          {t("skills.library")}
          <span className="ml-auto font-book">{skills.length}</span>
        </h2>
        {isLoading ? (
          <div className="space-y-2 px-2.5 py-1" aria-busy="true">
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} className="h-10 w-full" />
            ))}
          </div>
        ) : visible.length === 0 && skills.length > 0 ? (
          <p className="px-2.5 py-3 text-xs text-text-muted">{t("skills.noMatches")}</p>
        ) : (
          <ul className="flex flex-col gap-0.5" aria-label={t("skills.library")}>
            {visible.map((s) => (
              <SkillLibraryRow
                key={s.uid}
                skill={s}
                agents={agents}
                clis={clis}
                drift={drift}
                selecting={selected.length > 0}
                to={hrefFor(s.name)}
                current={s.name === selectedName}
                checked={picked.has(s.uid)}
                onCheckedChange={(on) => toggle(s.uid, on)}
                onOpen={onOpenSkill}
              />
            ))}
          </ul>
        )}
        <SkillOrphanList selected={orphan} />
      </div>
    </div>
  );
}
