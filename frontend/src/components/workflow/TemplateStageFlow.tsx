// frontend/src/components/workflow/TemplateStageFlow.tsx
// The top level of the map: the stages, the order they run in, and the edges
// that send work back (FR-061, FR-005).
//
// Only stages. A template's shape is the relationship BETWEEN its stages, and
// a diagram that also unpacked every task inside every stage would drown that
// in exactly the detail the reader came here to skip. The tasks are one click
// in, and a task's fields one click further.
//
// The return edges are drawn rather than listed, because "testing sends work
// back to coding" is a shape and reads as one. They are laid out with CSS grid
// rather than measured: each stage owns an odd row and each forward connector
// the even row after it, so an edge from stage f back to stage t is simply a
// gutter cell spanning rows. Nothing is measured, so nothing is wrong for one
// frame after a stage is renamed, and none of it moves under a scroll.
import { ArrowUp, ChevronDown, Plus } from "lucide-react";
import { Fragment } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { TemplateFieldError } from "@/components/workflow/TemplateFieldError";
import { TemplateStageCard } from "@/components/workflow/TemplateStageCard";
import type { TemplateConfig } from "@/lib/api/workflow";
import type { TemplateEditor } from "@/lib/hooks/useTemplateEditor";
import { removeStage } from "@/lib/workflow/templateDraft";
import type { TemplateRefusal } from "@/lib/workflow/templateErrors";

/** The grid row a stage sits on. Connectors take the even rows between. */
const rowOf = (index: number) => index * 2 + 1;

interface Props {
  config: TemplateConfig;
  refusal: TemplateRefusal | null;
  editor: TemplateEditor;
  /** Drill into a stage's own diagram. */
  onOpenStage: (index: number) => void;
  /** Open a stage's fields; `null` adds one. */
  onEditStage: (index: number | null) => void;
}

export function TemplateStageFlow({ config, refusal, editor, onOpenStage, onEditStage }: Props) {
  const { t } = useTranslation();
  const stages = config.stages;
  const indexOf = (key: string) => stages.findIndex((stage) => stage.key === key);
  const nameOf = (key: string) => {
    const stage = stages.find((s) => s.key === key);
    return stage === undefined || stage.name.length === 0 ? key : stage.name;
  };

  // Backwards only. A forward edge is the array order and is never written
  // (FR-005); one that somehow arrived would draw an arrow pointing the way
  // the run already goes, which is worse than not drawing it.
  const edges = (config.edges ?? [])
    .map((edge) => ({ edge, from: indexOf(edge.from_stage), to: indexOf(edge.to_stage) }))
    .filter(({ from, to }) => from >= 0 && to >= 0 && to < from);

  return (
    <div className="space-y-4">
      <p className="max-w-prose text-sm text-muted-foreground">
        {t("workflow.templates.flowHint")}
      </p>

      <div className="grid" style={{ gridTemplateColumns: "7rem minmax(0, 1fr)" }}>
        {edges.map(({ edge, from, to }, i) => (
          <div
            key={`${edge.from_stage}-${edge.reason}-${edge.to_stage}`}
            className="relative col-start-1"
            style={{ gridRowStart: rowOf(to), gridRowEnd: rowOf(from) + 1 }}
          >
            {/* An open bracket: up the gutter, with a stub into each card. */}
            <span
              aria-hidden
              className="absolute inset-y-6 rounded-l-md border-y border-l border-dashed border-muted-foreground/50"
              style={{ left: `${0.5 + i * 0.4}rem`, right: 0 }}
            />
            <ArrowUp
              aria-hidden
              className="absolute size-3 text-muted-foreground/60"
              style={{ top: "1.25rem", left: `${i * 0.4}rem` }}
            />
            <span
              className="absolute left-0 max-w-[6.5rem] truncate text-xs text-muted-foreground"
              style={{ top: `calc(50% + ${i * 1.25}rem)` }}
              title={t("workflow.templates.edgeTitle", {
                reason: edge.reason,
                stage: nameOf(edge.to_stage),
              })}
            >
              {edge.reason}
            </span>
          </div>
        ))}

        {stages.map((stage, index) => (
          <Fragment key={stage.key}>
            <div className="col-start-2" style={{ gridRow: rowOf(index) }}>
              <TemplateStageCard
                stage={stage}
                index={index}
                canDelete={stages.length > 1}
                busy={editor.isSaving}
                refusal={refusal}
                onOpen={() => onOpenStage(index)}
                onEdit={() => onEditStage(index)}
                onDelete={() => void editor.apply((c) => removeStage(c, index)).catch(() => {})}
              />
            </div>
            {index < stages.length - 1 ? (
              <div
                className="col-start-2 flex justify-center py-1"
                style={{ gridRow: rowOf(index) + 1 }}
              >
                <ChevronDown className="size-4 text-muted-foreground" aria-hidden />
              </div>
            ) : null}
          </Fragment>
        ))}
      </div>

      <TemplateFieldError refusal={refusal} path="stages" />

      <Button type="button" variant="outline" onClick={() => onEditStage(null)}>
        <Plus className="mr-1 size-4" aria-hidden />
        {t("workflow.templates.addStage")}
      </Button>
    </div>
  );
}
