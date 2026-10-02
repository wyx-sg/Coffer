// src/components/change-preview/ChangeTargetList.tsx
// The targets of a write grouped by agent: in review each row shows its line counts and op chip; in progress its mark.
import { Check, File, Folder, Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";

import { AgentBadge } from "@/components/agent/AgentBadge";
import { agentTypeLabel } from "@/lib/agents/display";
import { cn } from "@/lib/utils";
import { LineCounts } from "./LineCounts";
import { OpChip } from "./OpChip";
import { groupByAgent, looksLikeFolder, type ChangeItem, type ChangeStatus } from "@/lib/changePreview/changeCounts";

interface Props {
  items: readonly ChangeItem[];
  /** `review` shows counts + op chip; `progress` shows each item's apply mark. */
  mode: "review" | "progress";
  /** Status for items that carry none (e.g. "applied" once everything landed). */
  defaultStatus?: ChangeStatus;
  selectedId?: string;
  /** Review only: rows with a diff become buttons that select (and scroll to) it. */
  onSelect?(id: string): void;
}

function StatusMark({ status }: { status: ChangeStatus }) {
  const { t } = useTranslation();
  if (status === "failed") {
    return (
      <span className="inline-flex shrink-0 items-center gap-[7px] whitespace-nowrap text-xs text-danger">
        <span aria-hidden className="size-[7px] shrink-0 rounded-full bg-danger" />
        {t("changePreview.failed.word")}
      </span>
    );
  }
  const label = t(`changePreview.status.${status}`);
  if (status === "applied") {
    return (
      <Check
        role="img"
        aria-label={label}
        className="size-3.5 shrink-0 stroke-[2.5] text-success"
      />
    );
  }
  if (status === "applying") {
    return (
      <Loader2
        role="img"
        aria-label={label}
        className="size-3.5 shrink-0 animate-spin text-text-muted motion-reduce:animate-none"
      />
    );
  }
  return (
    <span
      role="img"
      aria-label={label}
      className="m-px size-3 shrink-0 rounded-full border-[1.5px] border-dashed border-text-subtle"
    />
  );
}

function TargetRow({
  item,
  mode,
  status,
  selected,
  onSelect,
}: {
  item: ChangeItem;
  mode: Props["mode"];
  status: ChangeStatus;
  selected: boolean;
  onSelect?(id: string): void;
}) {
  const Icon = looksLikeFolder(item.path) ? Folder : File;
  const clickable = mode === "review" && !!onSelect && !!item.diff?.length;
  const body = (
    <>
      <Icon aria-hidden className="size-3.5 shrink-0 stroke-[1.75] text-text-subtle" />
      <span className="min-w-0 grow truncate text-left font-mono text-xs text-text">
        {item.path}
      </span>
      {mode === "review" ? (
        <>
          <LineCounts added={item.added} removed={item.removed} />
          <OpChip op={item.op} size="sm" />
        </>
      ) : (
        <StatusMark status={status} />
      )}
    </>
  );
  const rowClass = cn(
    "flex min-h-control-md w-full items-center gap-2 rounded-item pl-10 pr-2",
    selected && "bg-surface-selected",
  );
  return (
    <li data-change-id={item.id} data-status={mode === "progress" ? status : undefined}>
      {clickable ? (
        <button
          type="button"
          aria-pressed={selected}
          onClick={() => onSelect?.(item.id)}
          className={cn(
            rowClass,
            "transition-colors duration-fast focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-focus-ring",
            !selected && "hover:bg-surface-hover",
          )}
        >
          {body}
        </button>
      ) : (
        <div className={rowClass}>{body}</div>
      )}
      {mode === "progress" && status === "failed" && item.error ? (
        <p className="pb-1.5 pl-[62px] pr-2 text-xs leading-[1.45] text-danger">{item.error}</p>
      ) : null}
    </li>
  );
}

export function ChangeTargetList({ items, mode, defaultStatus, selectedId, onSelect }: Props) {
  const groups = groupByAgent(items);
  return (
    <div className="-mx-2 flex flex-col gap-px">
      {groups.map((group) => {
        const name = group.agentName ?? agentTypeLabel(group.agentType);
        return (
          <section key={group.key} aria-label={name} className="flex flex-col gap-px">
            <div className="flex items-center gap-2 px-2 pb-1 pt-2">
              <AgentBadge type={group.agentType} name={group.agentName} size="md" />
              <span className="text-xs font-semibold text-text">{name}</span>
              <span className="text-xs text-text-subtle">{group.items.length}</span>
            </div>
            <ul className="flex flex-col gap-px">
              {group.items.map((item) => (
                <TargetRow
                  key={item.id}
                  item={item}
                  mode={mode}
                  status={item.status ?? defaultStatus ?? "pending"}
                  selected={item.id === selectedId}
                  onSelect={onSelect}
                />
              ))}
            </ul>
          </section>
        );
      })}
    </div>
  );
}
