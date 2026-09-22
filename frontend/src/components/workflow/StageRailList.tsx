// frontend/src/components/workflow/StageRailList.tsx
// The stages of a flow, in the order they run (FR-061). Used by the template
// editor and by a run.
//
// SHARED ON PURPOSE. A run is the same shape as the template it froze, with
// state on it, so the two must not drift into two different pictures of one
// thing — a developer who learns to read a template here has learned to read a
// run. Keeping that true by convention would have lasted about two changes;
// keeping it true by sharing the component is structural.
//
// One line per stage: index, name, and two slots the caller fills — a trailing
// fact (how many tasks in the editor, where the run got to in a run) and, in
// the editor, that stage's own Edit and Delete.
//
// PER ROW, not one pair over the list. A single pair acting on "the selected
// one" makes selecting a stage a precondition for editing it, and reads as
// editing whatever the other pane happens to be showing. A row that carries
// its own buttons is the same bargain the task cards make.
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";

interface StageRow {
  key: string;
  name: string;
  optional?: boolean;
  /** Whatever the trailing edge of the row should say about this stage. */
  trailing?: ReactNode;
  /** This stage's own controls, laid over the right of its row. Siblings of
   *  the row rather than children: a button cannot nest inside a button. */
  actions?: ReactNode;
}

interface Props {
  stages: StageRow[];
  selected: number;
  onSelect: (index: number) => void;
  /** Rendered under the list — "add a stage" in the editor, nothing in a run. */
  footer?: ReactNode;
}

export function StageRailList({ stages, selected, onSelect, footer }: Props) {
  const { t } = useTranslation();
  // The row keeps clear of its own buttons. Only the editor has any, so a run
  // gets the whole width for the name.
  const room = stages.some((stage) => stage.actions !== undefined) ? "pr-[10.5rem]" : "pr-2";

  return (
    <div className="space-y-3">
      <h3 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {t("workflow.templates.cols.stages")}
      </h3>

      <ol className="space-y-1">
        {stages.map((stage, index) => {
          const label = stage.name.length > 0 ? stage.name : stage.key;
          return (
            <li key={stage.key} className="relative">
              <button
                type="button"
                data-testid={`stage-${stage.key}`}
                aria-current={index === selected ? "true" : undefined}
                onClick={() => onSelect(index)}
                className={`flex h-9 w-full items-center gap-2 rounded-md pl-2 text-left text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${room} ${
                  index === selected
                    ? "bg-secondary font-medium"
                    : "text-muted-foreground hover:bg-secondary/50"
                }`}
              >
                <span className="w-3 shrink-0 text-xs tabular-nums text-muted-foreground">
                  {index + 1}
                </span>
                <span className="min-w-0 flex-1 truncate">{label}</span>
                {stage.optional ? (
                  <Badge variant="outline" className="shrink-0 px-1.5 py-0 text-[10px]">
                    {t("workflow.templates.optional")}
                  </Badge>
                ) : null}
                {stage.trailing}
              </button>
              {stage.actions === undefined ? null : (
                <div className="absolute right-1 top-1/2 flex -translate-y-1/2 items-center gap-1">
                  {stage.actions}
                </div>
              )}
            </li>
          );
        })}
      </ol>

      {footer}
    </div>
  );
}
