// src/components/secret/SecretsByOwner.tsx — the secrets grouped by owner: each owner a collapsible group with its kind icon and count.
//
// A secret nothing uses is gathered under "Not used by anything". Few owners open at first, many
// stay closed; the first batch of owners renders and "Show more owners" adds the rest, so a
// thousand secrets stay light.
import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { useTranslation } from "react-i18next";

import { cn } from "@/lib/utils";
import type { SecretListState } from "@/lib/secrets/listState";
import { Button } from "@/components/ui/button";
import { OWNER_ICONS } from "./ownerIcons";
import { SecretsTable } from "./SecretsTable";
import type { SecretRowAction } from "./SecretRowMenu";
import { groupByOwner, type SecretItem } from "./secretListView";
import { useOwnerLabel } from "./useOwnerLabel";

/** Owners shown at first, and each "Show more owners" adds. */
const GROUP_BATCH = 20;
/** Up to this many owners start open. */
const OPEN_BELOW = 8;

interface Props {
  items: SecretItem[];
  state: SecretListState;
  selected: ReadonlySet<string>;
  onToggle: (ref: string, on: boolean) => void;
  onAction: (action: SecretRowAction, row: SecretItem["row"]) => void;
  emptyMessage: string;
}

export function SecretsByOwner({
  items,
  state,
  selected,
  onToggle,
  onAction,
  emptyMessage,
}: Props) {
  const { t } = useTranslation();
  const { kindLabel } = useOwnerLabel();
  const groups = groupByOwner(items);
  const [limit, setLimit] = useState(GROUP_BATCH);
  const [toggled, setToggled] = useState<Record<string, boolean>>({});
  if (groups.length === 0) {
    return <p className="py-6 text-center text-sm text-text-muted">{emptyMessage}</p>;
  }
  const isOpen = (key: string) => toggled[key] ?? groups.length <= OPEN_BELOW;
  return (
    <div className="space-y-3">
      {groups.slice(0, limit).map((group) => {
        const Icon = OWNER_ICONS[group.owner.kind];
        const open = isOpen(group.key);
        const title =
          group.key === "none"
            ? t("secrets.groups.unused")
            : (group.owner.name ?? kindLabel(group.owner.kind));
        const Chevron = open ? ChevronDown : ChevronRight;
        return (
          <section key={group.key} aria-label={title} className="space-y-1.5">
            <button
              type="button"
              aria-expanded={open}
              onClick={() => setToggled((prev) => ({ ...prev, [group.key]: !open }))}
              className={cn(
                "flex min-h-control-md w-full items-center gap-2 rounded-md px-1 text-left",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring",
              )}
            >
              <Chevron className="size-3.5 text-text-subtle" aria-hidden />
              <Icon className="size-3.5 text-text-muted" aria-hidden />
              <span className="truncate text-sm font-semibold text-text">{title}</span>
              {group.key === "none" ? null : (
                <span className="text-xs text-text-muted">{kindLabel(group.owner.kind)}</span>
              )}
              <span className="text-xs text-text-muted">{group.items.length}</span>
            </button>
            {open ? (
              <SecretsTable
                items={group.items}
                state={state}
                selected={selected}
                onToggle={onToggle}
                emptyMessage={emptyMessage}
                grouped
                onAction={onAction}
              />
            ) : null}
          </section>
        );
      })}
      {groups.length > limit ? (
        <Button variant="outline" size="sm" onClick={() => setLimit((l) => l + GROUP_BATCH)}>
          {t("secrets.byOwner.more", { count: groups.length - limit })}
        </Button>
      ) : null}
    </div>
  );
}
