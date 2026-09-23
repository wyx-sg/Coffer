// frontend/src/components/workflow/TemplateFlow.tsx
// The template as its SHAPE, in two halves.
//
// The editor used to render every field of every task inline, so a four-task
// flow was a wall of forty controls and the shape of the work — which is the
// thing a template IS — could not be seen at all. Then it showed one depth at
// a time, which fixed that and cost the other half: inside a stage you could
// no longer see the flow you were editing.
//
// So both, side by side: the stages on the left in the order they run, one
// stage's tasks on the right, and a task's own fields one click further in a
// dialog. Two questions on screen, never three — a second stage's tasks are
// still behind selecting that stage.
//
// Which stage is open is state and not a route. It is a reading position
// inside one resource's editor, and a URL that restored it would also have to
// survive that stage being renamed or deleted by the very editor it points at.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { TemplateNodeDialog } from "@/components/workflow/TemplateNodeDialog";
import { TemplateNodeFlow } from "@/components/workflow/TemplateNodeFlow";
import { TemplateStageDialog } from "@/components/workflow/TemplateStageDialog";
import { TemplateStageList } from "@/components/workflow/TemplateStageList";
import type { TemplateConfig } from "@/lib/api/workflow";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { removeNode, removeStage } from "@/lib/workflow/templateDraft";
import { useAgents } from "@/lib/hooks/useAgents";
import { useSkills } from "@/lib/hooks/useSkills";
import type { TemplateEditor } from "@/lib/hooks/useTemplateEditor";
import type { TemplateRefusal } from "@/lib/workflow/templateErrors";

/** Which dialog is open, and on what. `stage: null` means a new stage; a node
 *  with `node: null` means a new task in that stage. */
type Open =
  | { kind: "stage"; stage: number | null }
  | { kind: "node"; stage: number; node: number | null }
  | null;

/** What a Delete button asked for. Held here rather than acted on where it was
 *  pressed: the editor writes every edit the moment it is made, so a
 *  delete IS the save — there is no draft to change your mind in afterwards,
 *  and the question has to come first. */
type Doomed = { kind: "stage"; stage: number } | { kind: "node"; stage: number; node: number };

interface Props {
  config: TemplateConfig;
  refusal: TemplateRefusal | null;
  editor: TemplateEditor;
}

/** What the doomed thing is called, for the question that names it. */
function doomedName(config: TemplateConfig, doomed: Doomed): string {
  const stage = config.stages[doomed.stage];
  if (stage === undefined) return "";
  if (doomed.kind === "stage") return stage.name || stage.key;
  const node = stage.nodes[doomed.node];
  return node === undefined ? "" : node.name || node.key;
}

export function TemplateFlow({ config, refusal, editor }: Props) {
  const { t } = useTranslation();
  // Fetched once here rather than per task: a template with six tasks would
  // otherwise ask the daemon for the same two lists twelve times.
  const skills = (useSkills().data ?? []).map((s) => s.name);
  const agents = (useAgents().data ?? []).map((a) => a.name);
  const [open, setOpen] = useState<Open>(null);
  const [doomed, setDoomed] = useState<Doomed | null>(null);
  const [picked, setPicked] = useState(0);

  const close = () => setOpen(null);
  const openDialog = (next: Exclude<Open, null>) => {
    editor.reset();
    setOpen(next);
  };

  // Clamped rather than remembered: a stage deleted while it was selected
  // would otherwise leave this pointing past the end, or at whichever stage
  // slid into its place.
  const selected = Math.min(picked, Math.max(config.stages.length - 1, 0));
  const stage = config.stages[selected];

  return (
    <div className="grid gap-6 md:grid-cols-[minmax(0,21rem)_minmax(0,1fr)]">
      <TemplateStageList
        config={config}
        refusal={refusal}
        selected={selected}
        onSelect={setPicked}
        onAddStage={() => openDialog({ kind: "stage", stage: null })}
        onEditStage={(index) => openDialog({ kind: "stage", stage: index })}
        onDeleteStage={(index) => setDoomed({ kind: "stage", stage: index })}
        busy={editor.isSaving}
      />

      {stage === undefined ? null : (
        <TemplateNodeFlow
          stage={stage}
          index={selected}
          refusal={refusal}
          editor={editor}
          onEditNode={(node) => openDialog({ kind: "node", stage: selected, node })}
          onDeleteNode={(node) => setDoomed({ kind: "node", stage: selected, node })}
        />
      )}

      {open?.kind === "stage" ? (
        <TemplateStageDialog
          config={config}
          index={open.stage}
          refusal={refusal}
          editor={editor}
          onClose={close}
        />
      ) : null}

      <ConfirmDialog
        open={doomed !== null}
        onOpenChange={(next) => {
          if (!next) setDoomed(null);
        }}
        title={t(
          doomed?.kind === "node"
            ? "workflow.templates.deleteNodeTitle"
            : "workflow.templates.deleteStageTitle",
        )}
        description={
          doomed === null
            ? undefined
            : doomed.kind === "node"
              ? t("workflow.templates.deleteNodeConfirm", { name: doomedName(config, doomed) })
              : t("workflow.templates.deleteStageConfirm", {
                  name: doomedName(config, doomed),
                  count: config.stages[doomed.stage]?.nodes.length ?? 0,
                })
        }
        confirmLabel={t("common.delete")}
        pending={editor.isSaving}
        error={editor.error}
        onConfirm={async () => {
          if (doomed === null) return;
          await editor.apply((c) =>
            doomed.kind === "node"
              ? removeNode(c, doomed.stage, doomed.node)
              : removeStage(c, doomed.stage),
          );
          setDoomed(null);
        }}
      />

      {open?.kind === "node" ? (
        <TemplateNodeDialog
          config={config}
          stageIndex={open.stage}
          nodeIndex={open.node}
          skills={skills}
          agents={agents}
          refusal={refusal}
          editor={editor}
          onClose={close}
        />
      ) : null}
    </div>
  );
}
