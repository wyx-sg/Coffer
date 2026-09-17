// frontend/src/components/workflow/SendBackDialog.tsx
// Crossing a feedback edge, from the task that found the problem (FR-025).
//
// What the developer writes here is the BRIEF of a new task in the earlier
// stage — not feedback on the node that passed, which is why the field asks
// what is wrong rather than what to redo. The node that already ran keeps its
// conversation and its result: it answered the question it was asked, and a
// different question deserves its own thread.
//
// The reason is a choice rather than free text: it names one of the edges the
// template wrote, and an edge that does not exist is refused by the daemon.
// With exactly one edge leaving the stage there is nothing to choose, so the
// picker is not rendered at all.
import { useEffect, useState } from "react";
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
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { translateApiError } from "@/lib/api/errors";
import { useSendBack } from "@/lib/hooks/useWorkflowRun";
import type { SendBackEdge } from "@/lib/api/workflow";

interface Props {
  runId: string;
  /** The run's observed version (FR-015). */
  version: number;
  /** The edges leaving the stage this task is in; never empty when open. */
  edges: SendBackEdge[];
  open: boolean;
  onClose: () => void;
  /** The new task's node key. The caller opens its conversation. */
  onSent: (nodeKey: string) => void;
}

export function SendBackDialog({ runId, version, edges, open, onClose, onSent }: Props) {
  const { t } = useTranslation();
  const send = useSendBack(runId);
  const [reason, setReason] = useState(edges[0]?.reason ?? "");
  const [note, setNote] = useState("");

  // The stage changes under this dialog when the developer moves between
  // tasks, and a reason left over from the last stage names no edge here.
  useEffect(() => {
    if (open) setReason(edges[0]?.reason ?? "");
  }, [open, edges]);

  const edge = edges.find((e) => e.reason === reason) ?? edges[0];
  if (edge === undefined) return null;

  const submit = () => {
    send.mutate(
      { version, from_stage: edge.from_stage, reason: edge.reason, note: note.trim() || null },
      {
        onSuccess: (result) => {
          setNote("");
          onClose();
          if (result.task) onSent(result.task.node_key);
        },
      },
    );
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) onClose();
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("workflow.sendBack.title", { stage: edge.to_stage_name })}</DialogTitle>
          <DialogDescription>{t("workflow.sendBack.description")}</DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {edges.length > 1 ? (
            <div className="space-y-2">
              <Label htmlFor="send-back-reason">{t("workflow.sendBack.reasonLabel")}</Label>
              <Select value={edge.reason} onValueChange={setReason}>
                <SelectTrigger id="send-back-reason">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {edges.map((option) => (
                    <SelectItem key={option.reason} value={option.reason}>
                      {t("workflow.sendBack.reasonOption", {
                        reason: option.reason,
                        stage: option.to_stage_name,
                      })}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          ) : null}
          <div className="space-y-2">
            <Label htmlFor="send-back-note">{t("workflow.sendBack.noteLabel")}</Label>
            <Textarea
              id="send-back-note"
              rows={5}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder={t("workflow.sendBack.notePlaceholder")}
            />
          </div>
          {send.error ? (
            <p className="text-sm text-destructive" role="alert">
              {translateApiError(t, send.error)}
            </p>
          ) : null}
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button disabled={send.isPending} onClick={submit}>
            {t("workflow.sendBack.submit", { stage: edge.to_stage_name })}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
