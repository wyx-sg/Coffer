// src/components/custom-tools/GroupList.tsx — the list pane: a filter, then the groups sectioned by health
// (needs attention first, then healthy, then off).
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { ListLoadError, ListLoadingRows, ListNoMatch } from "@/components/ListPaneStates";
import { ReachFilter } from "@/components/reach/ReachFilter";
import { SearchInput } from "@/components/SearchInput";
import type { CustomToolGroup } from "@/lib/api/customTools";
import { sectionGroups } from "@/lib/customTools/groups";
import type { ReachFilterValue } from "@/lib/reachFilter";
import { GroupRow } from "./GroupRow";

interface Props {
  groups: CustomToolGroup[];
  loading: boolean;
  /** The list read failed: the pane shows the error block under the filter. */
  error?: unknown;
  onRetry?: () => void;
  selected: string | undefined;
  onOpen: (name: string) => void;
}

export function GroupList({ groups, loading, error, onRetry, selected, onOpen }: Props) {
  const { t } = useTranslation();
  const [filter, setFilter] = useState("");
  const [reach, setReach] = useState<ReachFilterValue>("all");
  const sections = sectionGroups(groups, filter, reach);

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3 p-3">
      <SearchInput
        value={filter}
        onChange={setFilter}
        placeholder={t("customTools.list.filter")}
        ariaLabel={t("customTools.list.filter")}
      />
      <ReachFilter value={reach} onChange={setReach} />
      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto">
        {error ? (
          <ListLoadError kind="customTools" error={error} onRetry={() => onRetry?.()} />
        ) : loading ? (
          <ListLoadingRows />
        ) : sections.length === 0 ? (
          <ListNoMatch
            kind="customTools"
            query={filter}
            onClear={() => {
              setFilter("");
              setReach("all");
            }}
          />
        ) : (
          sections.map(({ section, groups: inSection }) => (
            <section key={section} aria-label={t(`customTools.list.section.${section}`)}>
              <h2
                aria-hidden
                className="mb-1 flex items-center justify-between px-2.5 text-xs font-semibold text-text-muted"
              >
                {t(`customTools.list.section.${section}`)}
                <span className="font-normal tabular-nums">{inSection.length}</span>
              </h2>
              <ul>
                {inSection.map((group) => (
                  <GroupRow
                    key={group.uid}
                    group={group}
                    selected={group.name === selected}
                    onOpen={() => onOpen(group.name)}
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
