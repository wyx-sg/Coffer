// frontend/src/components/workflow/TemplateFlow.tsx
// The template as a MAP, read at three depths (FR-061).
//
// The editor used to render every field of every task inline, so a four-task
// flow was a wall of forty controls and the shape of the work — which is the
// thing a template IS — could not be seen at all. Then it showed every stage
// with its tasks unpacked inside, which is better and still answers two
// questions at once.
//
// So: STAGES and the edges between them; click one for the TASKS inside it in
// the order they run; click one of those for what that task actually does.
// Each level answers exactly one question, and the reader chooses when to ask
// the next.
//
// Which stage is open is state and not a route. It is a reading position
// inside one resource's editor, and a URL that restored it would also have to
// survive that stage being renamed or deleted by the very editor it points at.
import { useState } from "react";

import { TemplateNodeDialog } from "@/components/workflow/TemplateNodeDialog";
import { TemplateNodeFlow } from "@/components/workflow/TemplateNodeFlow";
import { TemplateStageDialog } from "@/components/workflow/TemplateStageDialog";
import { TemplateStageFlow } from "@/components/workflow/TemplateStageFlow";
import type { TemplateConfig } from "@/lib/api/workflow";
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

interface Props {
  config: TemplateConfig;
  refusal: TemplateRefusal | null;
  editor: TemplateEditor;
}

export function TemplateFlow({ config, refusal, editor }: Props) {
  // Fetched once here rather than per task: a template with six tasks would
  // otherwise ask the daemon for the same two lists twelve times.
  const skills = (useSkills().data ?? []).map((s) => s.name);
  const agents = (useAgents().data ?? []).map((a) => a.name);
  const [open, setOpen] = useState<Open>(null);
  const [inside, setInside] = useState<number | null>(null);

  const close = () => setOpen(null);
  const openDialog = (next: Exclude<Open, null>) => {
    editor.reset();
    setOpen(next);
  };

  // A stage deleted while it was open leaves nothing to be inside of, and the
  // index would otherwise point at whichever stage slid into its place.
  const stage = inside === null ? undefined : config.stages[inside];

  return (
    <div className="space-y-4">
      {stage !== undefined && inside !== null ? (
        <TemplateNodeFlow
          stage={stage}
          index={inside}
          refusal={refusal}
          editor={editor}
          onBack={() => setInside(null)}
          onEditStage={() => openDialog({ kind: "stage", stage: inside })}
          onEditNode={(node) => openDialog({ kind: "node", stage: inside, node })}
        />
      ) : (
        <TemplateStageFlow
          config={config}
          refusal={refusal}
          editor={editor}
          onOpenStage={setInside}
          onEditStage={(index) => openDialog({ kind: "stage", stage: index })}
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
