// src/components/scheduled-tasks/TaskSessionFields.tsx — the agent, model and directory every run of a task opens its new conversation with.
//
// The agent is required; the model lists the agent's catalogue, with the
// agent's own default first; the directory is picked like every other folder
// in Coffer (the native dialog, or typed), and left empty is Coffer's workspace.
import { useTranslation } from "react-i18next";

import { FolderPickerField } from "@/components/FolderPickerField";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useQuery } from "@tanstack/react-query";
import { agentModelsApi } from "@/lib/api/agentModels";
import { agentProviderModelsKey } from "@/lib/api/queryKeys";
import { useAgentResolvedDefault } from "@/lib/hooks/useAgentModels";
import { AGENTS, type TaskForm } from "@/lib/scheduledTasks/format";

// Radix Select forbids an empty item value, so "the agent's default" is this sentinel.
const AGENT_DEFAULT = "__agent_default__";

interface Props {
  form: TaskForm;
  set: (patch: Partial<TaskForm>) => void;
}

export function TaskSessionFields({ form, set }: Props) {
  const { t } = useTranslation();
  const catalogue = useQuery({
    queryKey: agentProviderModelsKey(form.agent),
    queryFn: () => agentModelsApi.list(form.agent),
    enabled: form.agent !== "",
  });
  const resolved = useAgentResolvedDefault(form.agent).data ?? null;
  const models = catalogue.data?.models ?? [];
  const model = form.model.trim();
  // A stored id the catalogue does not list still shows as itself.
  const options =
    model && !models.some((m) => m.id === model)
      ? [...models, { id: model, label: model, description: "" }]
      : models;
  return (
    <div className="grid grid-cols-[140px_minmax(0,1fr)] gap-2.5">
      <div className="space-y-1.5">
        <Label htmlFor="task-agent" required>
          {t("scheduledTasks.dialog.agent")}
        </Label>
        <Select value={form.agent} onValueChange={(agent) => set({ agent, model: "" })}>
          <SelectTrigger id="task-agent">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
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
        <Select
          value={model || AGENT_DEFAULT}
          onValueChange={(v) => set({ model: v === AGENT_DEFAULT ? "" : v })}
        >
          <SelectTrigger id="task-model">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={AGENT_DEFAULT}>
              {resolved
                ? t("scheduledTasks.dialog.agentDefaultNamed", { model: resolved })
                : t("scheduledTasks.dialog.agentDefault")}
            </SelectItem>
            {options.map((m) => (
              <SelectItem key={m.id} value={m.id}>
                {m.label || m.id}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="col-span-2 space-y-1.5">
        <Label htmlFor="task-cwd">{t("scheduledTasks.dialog.cwd")}</Label>
        <FolderPickerField
          inputId="task-cwd"
          value={form.cwd || null}
          onChange={(cwd) => set({ cwd: cwd ?? "" })}
          placeholder={t("scheduledTasks.dialog.workspaceFolder")}
          clearable
          typeable
        />
      </div>
    </div>
  );
}
