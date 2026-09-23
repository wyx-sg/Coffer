// frontend/src/components/workflow/AdhocTaskDialog.tsx
// Unplanned work joins the run rather than happening beside it: the
// developer picks the stage it belongs to, writes the instructions themselves,
// and the task opens with the same shared context and leaves its artifacts in
// the same place as any template node.
//
// The optional working directory is how a task that touches a SECOND
// repository is expressed — the run itself has one working directory, and this
// is the documented way past that rather than a second run.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { translateApiError } from "@/lib/api/errors";
import { useAddAdhocTask } from "@/lib/hooks/useWorkflowRun";

interface Props {
  runId: string;
  /** The run's observed version (spec workflow "Refuse a command carrying a stale version"). */
  version: number;
  /** The stage the task joins; null closes the dialog. */
  stageKey: string | null;
  onClose: () => void;
  /**
   * The new task's node key, once it exists. The caller opens its conversation:
   * an unplanned task is a conversation like any other, and landing in it is
   * the only way to say what it should do next.
   */
  onAdded: (nodeKey: string) => void;
}

export function AdhocTaskDialog({ runId, version, stageKey, onClose, onAdded }: Props) {
  const { t } = useTranslation();
  const add = useAddAdhocTask(runId);
  const [name, setName] = useState("");
  const [instructions, setInstructions] = useState("");
  const [workdir, setWorkdir] = useState("");

  const reset = () => {
    setName("");
    setInstructions("");
    setWorkdir("");
  };

  const submit = () => {
    if (stageKey === null) return;
    add.mutate(
      {
        version,
        stage_key: stageKey,
        name: name.trim(),
        instructions: instructions.trim(),
        workdir: workdir.trim() || null,
      },
      {
        onSuccess: (attempt) => {
          reset();
          onClose();
          onAdded(attempt.node_key);
        },
      },
    );
  };

  const incomplete = name.trim().length === 0 || instructions.trim().length === 0;

  return (
    <Dialog
      open={stageKey !== null}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("workflow.adhoc.title")}</DialogTitle>
          <DialogDescription>{t("workflow.adhoc.description")}</DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="adhoc-name">{t("workflow.adhoc.nameLabel")}</Label>
            <Input id="adhoc-name" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="space-y-2">
            <Label htmlFor="adhoc-instructions">{t("workflow.adhoc.instructionsLabel")}</Label>
            <Textarea
              id="adhoc-instructions"
              rows={5}
              value={instructions}
              onChange={(e) => setInstructions(e.target.value)}
              placeholder={t("workflow.adhoc.instructionsPlaceholder")}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="adhoc-workdir">{t("workflow.adhoc.workdirLabel")}</Label>
            <Input
              id="adhoc-workdir"
              value={workdir}
              onChange={(e) => setWorkdir(e.target.value)}
              placeholder={t("workflow.adhoc.workdirPlaceholder")}
            />
          </div>
          {add.error ? (
            <p className="text-sm text-destructive" role="alert">
              {translateApiError(t, add.error)}
            </p>
          ) : null}
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button disabled={incomplete || add.isPending} onClick={submit}>
            {t("workflow.adhoc.submit")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
