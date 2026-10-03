// frontend/src/components/skills/SkillLibrary.tsx
// The left pane of the Skills page: the library of managed skills, laid out
// like the MCP servers list (canvas 4.3 SkillsList). A filter field (name +
// description) with Check copies beside it on the same row; then the skills
// grouped Needs attention (a problem — lib/skills/attention.ts), In use
// (reaches at least one agent), Off (switched off, or limited to nobody) and,
// last, Built-in (what Coffer ships), a count on each heading; then the
// folders no skill claims (SkillOrphanList). The filter applies to the
// built-in rows too. While rows are ticked the selection bar (SkillsBulkBar)
// takes the filter's place and every row shows its checkbox; otherwise a row
// shows it on hover. Built-in rows have no checkbox and select-all skips
// them. Only managed skills are here — an agent's own skills live on that
// agent's Skills tab.
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { RefreshCw } from "lucide-react";

import { ListLoadError, ListLoadingRows, ListNoMatch } from "@/components/ListPaneStates";
import { SearchInput } from "@/components/SearchInput";
import { SkillLibraryRow } from "@/components/skills/SkillLibraryRow";
import { SkillOrphanList } from "@/components/skills/SkillOrphanList";
import { SkillsBulkBar } from "@/components/skills/SkillsBulkBar";
import { Button } from "@/components/ui/button";
import type { Cli } from "@/lib/api/clis";
import type { SkillDriftEntry, SkillOut } from "@/lib/api/skills";
import { useAgents } from "@/lib/hooks/useAgents";
import { useClis } from "@/lib/hooks/useClis";
import { skillProblems } from "@/lib/skills/attention";
import { GROUP_ORDER, skillGroup, type SkillGroup } from "@/lib/skills/groups";

const NO_CLIS: readonly Cli[] = [];

interface Props {
  skills: SkillOut[];
  isLoading: boolean;
  /** The list read failed: the pane shows the error block under the filter. */
  error?: unknown;
  onRetry?: () => void;
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
  error,
  onRetry,
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
  const clis = useClis().data?.items ?? NO_CLIS;
  const [query, setQuery] = useState("");

  const groups = useMemo(() => {
    const q = query.trim().toLowerCase();
    const out: Record<SkillGroup, SkillOut[]> = { attention: [], inUse: [], off: [], builtin: [] };
    for (const s of skills) {
      if (q && !`${s.name} ${s.description}`.toLowerCase().includes(q)) continue;
      out[skillGroup(s, skillProblems(s, clis, drift).length > 0)].push(s);
    }
    return out;
  }, [skills, query, clis, drift]);
  const shown = GROUP_ORDER.reduce((n, g) => n + groups[g].length, 0);

  // What select-all covers: the listed skills the filters show, never a built-in one.
  const visibleUids = [...groups.attention, ...groups.inUse, ...groups.off].map((s) => s.uid);
  const allVisiblePicked = visibleUids.length > 0 && visibleUids.every((u) => picked.has(u));
  const toggleAll = (on: boolean) => {
    const next = new Set(picked);
    for (const u of visibleUids) {
      if (on) next.add(u);
      else next.delete(u);
    }
    onPickedChange(next);
  };

  const toggle = (uid: string, on: boolean) => {
    const next = new Set(picked);
    if (on) next.add(uid);
    else next.delete(uid);
    onPickedChange(next);
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex flex-col gap-2.5 px-3 pb-2.5 pt-3.5">
        {selected.length > 0 ? (
          <SkillsBulkBar
            skills={selected}
            allChecked={allVisiblePicked}
            onToggleAll={toggleAll}
            onDone={() => onPickedChange(new Set())}
          />
        ) : (
          <>
            <div className="flex items-center gap-1">
              <SearchInput
                className="min-w-0 flex-1"
                value={query}
                onChange={setQuery}
                placeholder={t("skills.searchPlaceholder")}
                ariaLabel={t("skills.searchPlaceholder")}
              />
              <Button
                variant="ghost"
                size="sm"
                className="shrink-0"
                title={t("skills.checkCopiesHint")}
                onClick={onCheckCopies}
                disabled={checkingCopies}
              >
                <RefreshCw aria-hidden className={checkingCopies ? "animate-spin" : undefined} />
                {checkingCopies ? t("skills.checkingCopies") : t("skills.checkCopies")}
              </Button>
            </div>
          </>
        )}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-3">
        {error ? (
          <ListLoadError kind="skills" error={error} onRetry={() => onRetry?.()} />
        ) : isLoading ? (
          <ListLoadingRows />
        ) : shown === 0 && skills.length > 0 ? (
          <ListNoMatch kind="skills" query={query} onClear={() => setQuery("")} />
        ) : (
          <div data-testid="skill-library">
            {GROUP_ORDER.map((group) => {
              const rows = groups[group];
              if (rows.length === 0) return null;
              return (
                <section key={group} className="mb-3" aria-label={t(`skills.group.${group}`)}>
                  <h2 className="flex items-center px-2.5 pb-1 text-2xs font-semibold text-text-muted">
                    {t(`skills.group.${group}`)}
                    <span className="ml-auto font-book">{rows.length}</span>
                  </h2>
                  <ul className="flex flex-col gap-0.5">
                    {rows.map((s) => (
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
                </section>
              );
            })}
          </div>
        )}
        <SkillOrphanList selected={orphan} />
      </div>
    </div>
  );
}
