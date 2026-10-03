// frontend/src/components/skills/SkillLibrary.tsx
// The left pane of the Skills page: the library of managed skills, laid out
// like the MCP servers list. A filter field (name + description); under it the
// Reach filter and Check copies; then the
// skills grouped In use (reaches at least one agent), Unused (off, or limited
// to nobody) and, last, Built-in (what Coffer ships), a count on each heading.
// Every filter applies to the built-in rows too. While rows are ticked the
// selection bar (SkillsBulkBar) takes the filters' place and every row shows
// its checkbox; otherwise a row shows it on hover. Built-in rows have no
// checkbox and select-all skips them. Only managed skills are here — an
// agent's own skills live on that agent's Skills tab.
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { RefreshCw } from "lucide-react";

import { ListSelectAll } from "@/components/ListSelectAll";
import { ListLoadError, ListLoadingRows, ListNoMatch } from "@/components/ListPaneStates";
import { AgentFilterPill } from "@/components/agents/tabs/AgentFilterPill";
import { ReachFilter } from "@/components/reach/ReachFilter";
import { SearchInput } from "@/components/SearchInput";
import { SkillLibraryRow } from "@/components/skills/SkillLibraryRow";
import { SkillOrphanList } from "@/components/skills/SkillOrphanList";
import { SkillsBulkBar } from "@/components/skills/SkillsBulkBar";
import { Button } from "@/components/ui/button";
import type { SkillDriftEntry, SkillOut } from "@/lib/api/skills";
import { useAgentFilter } from "@/lib/agents/agentFilter";
import { useAgents } from "@/lib/hooks/useAgents";
import { useClis } from "@/lib/hooks/useClis";
import { GROUP_ORDER, skillGroup, type SkillGroup } from "@/lib/skills/groups";
import { matchesReach, type ReachFilterValue } from "@/lib/reachFilter";

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
  const clis = useClis().data?.items ?? [];
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<ReachFilterValue>("all");
  const agentFilter = useAgentFilter();

  const groups = useMemo(() => {
    const q = query.trim().toLowerCase();
    const out: Record<SkillGroup, SkillOut[]> = { inUse: [], unused: [], builtin: [] };
    for (const s of skills) {
      if (!matchesReach(filter, s)) continue;
      if (agentFilter && !agentFilter.matches(s)) continue;
      if (q && !`${s.name} ${s.description}`.toLowerCase().includes(q)) continue;
      out[skillGroup(s)].push(s);
    }
    return out;
  }, [skills, query, filter, agentFilter]);
  const shown = GROUP_ORDER.reduce((n, g) => n + groups[g].length, 0);

  // The listed skills the filters show, never a built-in one: the bar's "of M".
  const visibleUids = [...groups.inUse, ...groups.unused].map((s) => s.uid);
  const toggle = (uid: string, on: boolean) => {
    const next = new Set(picked);
    if (on) next.add(uid);
    else next.delete(uid);
    onPickedChange(next);
  };

  const setAll = (all: boolean) => onPickedChange(all ? new Set(visibleUids) : new Set());

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex flex-col gap-2.5 px-3 pb-2.5 pt-3.5">
        {selected.length > 0 ? (
          <SkillsBulkBar
            skills={selected}
            total={visibleUids.length}
            onDone={() => onPickedChange(new Set())}
          />
        ) : (
          <>
            <SearchInput
              value={query}
              onChange={setQuery}
              placeholder={t("skills.searchPlaceholder")}
              ariaLabel={t("skills.searchPlaceholder")}
            />
            <div className="flex flex-wrap items-center gap-2">
              <AgentFilterPill filter={agentFilter} />
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
          </>
        )}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-3">
        <ListSelectAll
          count={visibleUids.filter((u) => picked.has(u)).length}
          total={visibleUids.length}
          onChange={setAll}
        />
        {error ? (
          <ListLoadError kind="skills" error={error} onRetry={() => onRetry?.()} />
        ) : isLoading ? (
          <ListLoadingRows />
        ) : shown === 0 && skills.length > 0 ? (
          <ListNoMatch
            kind="skills"
            query={query}
            onClear={() => {
              setQuery("");
              setFilter("all");
            }}
          />
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
