// src/components/scheduled-tasks/TaskDialog.tsx — New task, or edit one: its name, when, and the agent and model every run opens with.
//
// A new task is given its prompt here and starts on its schedule at once; the
// prompt is then the task's PROMPT.md, edited on its Overview tab, so the edit
// dialog does not show it. Every run works in the task's own folder.
//
// Spec scheduled-tasks "Manage scheduled tasks from the Scheduled tasks page". Every
// run is a new conversation of its own; what it does with a chat or a report
// is the prompt's. Catch up runs a slot missed while the Mac slept once, late.
// The body scrolls between a fixed header and footer, so the buttons stay at
// the bottom of the dialog however tall the form is. A refused save stays in
// the dialog with the daemon's reason and the primary button becomes Retry.
import { CircleAlert } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
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
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { translateApiError } from "@/lib/api/errors";
import type { ScheduledTask } from "@/lib/api/scheduledTasks";
import { useCreateScheduledTask, useEditScheduledTask } from "@/lib/hooks/useScheduledTasks";
import { configFrom, formFrom, formValid, type TaskForm } from "@/lib/scheduledTasks/format";
import { TaskScheduleFields } from "./TaskScheduleFields";
import { TaskSessionFields } from "./TaskSessionFields";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The task being edited; omit for a new one. */
  existing?: ScheduledTask;
  /** Called with the uid once it is saved. */
  onSaved?: (uid: string) => void;
}

function Form({ onOpenChange, existing, onSaved }: Omit<Props, "open">) {
  const { t } = useTranslation();
  const editing = existing !== undefined;
  const create = useCreateScheduledTask();
  const edit = useEditScheduledTask();
  const save = editing ? edit : create;
  const [form, setForm] = useState<TaskForm>(() => formFrom(existing));
  const set = (patch: Partial<TaskForm>) => {
    setForm((f) => ({ ...f, ...patch }));
    if (save.error) save.reset();
  };
  const valid = formValid(form, !editing);

  const submit = () => {
    if (!valid || save.isPending) return;
    const config = configFrom(form);
    const done = (uid: string) => {
      onOpenChange(false);
      onSaved?.(uid);
    };
    if (editing) {
      edit.mutate(
        { uid: existing.uid, name: form.name.trim(), config },
        { onSuccess: () => done(existing.uid) },
      );
    } else {
      create.mutate(
        { name: form.name.trim(), prompt: form.prompt, config },
        { onSuccess: (task) => done(task.uid) },
      );
    }
  };

  return (
    <form
      className="flex min-h-0 flex-col gap-3.5"
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
    >
      <DialogHeader>
        <DialogTitle>
          {editing
            ? t("scheduledTasks.dialog.editTitle", { name: existing.name })
            : t("scheduledTasks.dialog.title")}
        </DialogTitle>
        <DialogDescription>
          {t(editing ? "scheduledTasks.dialog.editBody" : "scheduledTasks.dialog.body")}
        </DialogDescription>
      </DialogHeader>
      <div className="-mx-5 min-h-0 flex-1 space-y-4 overflow-y-auto px-5 py-1">
        <div className="space-y-1.5">
          <Label htmlFor="task-name" required>
            {t("scheduledTasks.dialog.name")}
          </Label>
          <Input
            id="task-name"
            value={form.name}
            autoComplete="off"
            autoFocus
            onChange={(e) => set({ name: e.target.value })}
          />
        </div>
        {editing ? null : (
          <div className="space-y-1.5">
            <Label htmlFor="task-prompt" required>
              {t("scheduledTasks.dialog.prompt")}
            </Label>
            <Textarea
              id="task-prompt"
              rows={5}
              className="font-mono text-xs"
              value={form.prompt}
              placeholder={t("scheduledTasks.dialog.promptPlaceholder")}
              onChange={(e) => set({ prompt: e.target.value })}
            />
            <p className="text-xs text-text-muted">{t("scheduledTasks.dialog.promptHint")}</p>
          </div>
        )}
        <TaskScheduleFields form={form} set={set} />
        <TaskSessionFields form={form} set={set} />
        <label className="flex items-start justify-between gap-3">
          <span className="space-y-0.5">
            <span className="block text-sm text-text">{t("scheduledTasks.dialog.catchUp")}</span>
            <span className="block text-xs text-text-muted">
              {t("scheduledTasks.dialog.catchUpHint")}
            </span>
          </span>
          <Switch checked={form.catchUp} onCheckedChange={(catchUp) => set({ catchUp })} />
        </label>
        {save.error ? (
          <Alert variant="error">
            <CircleAlert aria-hidden />
            <AlertTitle>
              {t(editing ? "scheduledTasks.dialog.editFailed" : "scheduledTasks.dialog.addFailed")}
            </AlertTitle>
            <AlertDescription>{translateApiError(t, save.error)}</AlertDescription>
          </Alert>
        ) : null}
      </div>
      <DialogFooter className="mt-0">
        <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
          {t("common.cancel")}
        </Button>
        <Button type="submit" disabled={!valid || save.isPending}>
          {save.error
            ? t("common.retry")
            : t(editing ? "common.save" : "scheduledTasks.dialog.submit")}
        </Button>
      </DialogFooter>
    </form>
  );
}

export function TaskDialog({ open, onOpenChange, existing, onSaved }: Props) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-[540px] grid-rows-[minmax(0,1fr)]">
        {open ? <Form onOpenChange={onOpenChange} existing={existing} onSaved={onSaved} /> : null}
      </DialogContent>
    </Dialog>
  );
}
