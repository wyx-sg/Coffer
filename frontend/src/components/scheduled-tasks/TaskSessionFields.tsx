// src/components/scheduled-tasks/TaskSessionFields.tsx — for a task that opens a fresh conversation: the agent, model and directory it opens with.
//
// Each is optional: left empty, the chat's channel decides, as it does for a
// message.
import { useTranslation } from "react-i18next";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { TaskForm } from "@/lib/scheduledTasks/format";

const CHANNEL_DEFAULT = "__channel__";
const AGENTS = [
  { key: "claude_code", label: "Claude Code" },
  { key: "codex", label: "Codex" },
] as const;

interface Props {
  form: TaskForm;
  set: (patch: Partial<TaskForm>) => void;
}

export function TaskSessionFields({ form, set }: Props) {
  const { t } = useTranslation();
  return (
    <div className="grid grid-cols-[140px_minmax(0,1fr)] gap-2.5 pt-1">
      <div className="space-y-1.5">
        <Label htmlFor="task-agent">{t("scheduledTasks.dialog.agent")}</Label>
        <Select
          value={form.agent || CHANNEL_DEFAULT}
          onValueChange={(v) => set({ agent: v === CHANNEL_DEFAULT ? "" : v })}
        >
          <SelectTrigger id="task-agent">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={CHANNEL_DEFAULT}>
              {t("scheduledTasks.dialog.channelDefault")}
            </SelectItem>
            {AGENTS.map((a) => (
              <SelectItem key={a.key} value={a.key}>
                {a.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="task-model">{t("scheduledTasks.dialog.model")}</Label>
        <Input
          id="task-model"
          value={form.model}
          autoComplete="off"
          placeholder={t("scheduledTasks.dialog.channelDefault")}
          onChange={(e) => set({ model: e.target.value })}
        />
      </div>
      <div className="col-span-2 space-y-1.5">
        <Label htmlFor="task-cwd">{t("scheduledTasks.dialog.cwd")}</Label>
        <Input
          id="task-cwd"
          value={form.cwd}
          className="font-mono"
          autoComplete="off"
          placeholder="~/work/project"
          onChange={(e) => set({ cwd: e.target.value })}
        />
      </div>
    </div>
  );
}
