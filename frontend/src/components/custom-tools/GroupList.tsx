// src/components/custom-tools/GroupList.tsx — the list pane: a filter (and the `?agent=` pill), then the groups
// sectioned by health (needs attention first, then healthy, then off). While groups are ticked the selection bar
// takes the filter's place; which are ticked belongs to the page.
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { AgentFilterPill } from "@/components/agents/tabs/AgentFilterPill";
import { ListLoadError, ListLoadingRows, ListNoMatch } from "@/components/ListPaneStates";
import { ListSelectAll } from "@/components/ListSelectAll";
import { SearchInput } from "@/components/SearchInput";
import type { CustomToolGroup } from "@/lib/api/customTools";
import { useAgentFilter } from "@/lib/agents/agentFilter";
import { reachOf, sectionGroups } from "@/lib/customTools/groups";
import { CustomToolsBulkBar } from "./CustomToolsBulkBar";
import { GroupRow } from "./GroupRow";

interface Props {
  groups: CustomToolGroup[];
  loading: boolean;
  /** The list read failed: the pane shows the error block under the filter. */
  error?: unknown;
  onRetry?: () => void;
  selected: string | undefined;
  onOpen: (name: string) => void;
  /** The ticked groups' uids, and the page's setter for them. */
  picked: ReadonlySet<string>;
  onPickedChange: (picked: ReadonlySet<string>) => void;
  /** Names removed by the bulk Delete. */
  onDeleted: (names: string[]) => void;
}

export function GroupList({
  groups,
  loading,
  error,
  onRetry,
  selected,
  onOpen,
  picked,
  onPickedChange,
  onDeleted,
}: Props) {
  const { t } = useTranslation();
  const [filter, setFilter] = useState("");
  const agentFilter = useAgentFilter();
  const sections = useMemo(
    () =>
      sectionGroups(groups, filter)
        .map((s) => ({
          ...s,
          groups: s.groups.filter(
            (g) => !agentFilter || agentFilter.matches({ enabled: g.enabled, scope: reachOf(g) }),
          ),
        }))
        .filter((s) => s.groups.length > 0),
    [groups, filter, agentFilter],
  );
  const visible = sections.flatMap((s) => s.groups);
  const ticked = groups.filter((g) => picked.has(g.uid));
  const toggle = (uid: string, on: boolean) => {
    const next = new Set(picked);
    if (on) next.add(uid);
    else next.delete(uid);
    onPickedChange(next);
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3 p-3">
      {ticked.length > 0 ? (
        <CustomToolsBulkBar
          groups={ticked}
          total={visible.length}
          onDone={() => onPickedChange(new Set())}
          onDeleted={onDeleted}
        />
      ) : (
        <>
          <SearchInput
            value={filter}
            onChange={setFilter}
            placeholder={t("customTools.list.filter")}
            ariaLabel={t("customTools.list.filter")}
          />
          {agentFilter ? (
            <div className="flex items-center gap-2">
              <AgentFilterPill filter={agentFilter} />
            </div>
          ) : null}
        </>
      )}
      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto">
        <ListSelectAll
          count={visible.filter((g) => picked.has(g.uid)).length}
          total={visible.length}
          onChange={(all) => onPickedChange(all ? new Set(visible.map((g) => g.uid)) : new Set())}
        />
        {error ? (
          <ListLoadError kind="customTools" error={error} onRetry={() => onRetry?.()} />
        ) : loading ? (
          <ListLoadingRows />
        ) : sections.length === 0 ? (
          <ListNoMatch kind="customTools" query={filter} onClear={() => setFilter("")} />
        ) : (
          sections.map(({ section, groups: inSection }) => (
            <section key={section} aria-label={t(`customTools.list.section.${section}`)}>
              <h2
                aria-hidden
                className="mb-1 flex items-center justify-between px-2.5 text-xs font-semibold text-text-muted"
              >
                {t(`customTools.list.section.${section}`)}
              </h2>
              <ul>
                {inSection.map((group) => (
                  <GroupRow
                    key={group.uid}
                    group={group}
                    selected={group.name === selected}
                    onOpen={() => onOpen(group.name)}
                    selecting={ticked.length > 0}
                    checked={picked.has(group.uid)}
                    onCheckedChange={(on) => toggle(group.uid, on)}
                  />
                ))}
              </ul>
            </section>
          ))
        )}
      </div>
    </div>
  );
}
