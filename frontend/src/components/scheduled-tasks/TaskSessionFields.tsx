// src/components/scheduled-tasks/TaskSessionFields.tsx — the agent, model and folder every run of a task opens its new conversation with.
//
// The agent is required and is one Coffer can run a turn on here (the agents
// the turn platform lists as available, so a type without a driver or not
// installed is never offered); the model lists the agent's catalogue, with the
// agent's own default first. The folder is optional: left empty, every run
// works in the task's own folder, where its PROMPT.md is either way.
import { useEffect } from "react";
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
import { useAgentProviders } from "@/lib/hooks/useAgentProviders";
import type { TaskForm } from "@/lib/scheduledTasks/format";

// Radix Select forbids an empty item value, so "the agent's default" is this sentinel.
const AGENT_DEFAULT = "__agent_default__";

interface Props {
  form: TaskForm;
  set: (patch: Partial<TaskForm>) => void;
}

export function TaskSessionFields({ form, set }: Props) {
  const { t } = useTranslation();
  const providers = useAgentProviders().data ?? [];
  const runnable = providers.filter((a) => a.available || a.agent_key === form.agent);
  // A new task starts on the first agent that can run it.
  const first = providers.find((a) => a.available)?.agent_key;
  useEffect(() => {
    if (form.agent === "" && first) set({ agent: first });
  }, [form.agent, first, set]);
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
    <>
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
              {runnable.map((a) => (
                <SelectItem key={a.agent_key} value={a.agent_key}>
                  {a.display_name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {providers.length > 0 && runnable.length === 0 ? (
            <p className="text-xs text-text-muted">{t("scheduledTasks.dialog.noAgent")}</p>
          ) : null}
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
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="task-cwd">{t("scheduledTasks.dialog.folder")}</Label>
        <FolderPickerField
          inputId="task-cwd"
          value={form.cwd}
          onChange={(cwd) => set({ cwd })}
          placeholder={t("scheduledTasks.dialog.folderPlaceholder")}
          typeable
          clearable
        />
        <p className="text-xs text-text-muted">{t("scheduledTasks.dialog.folderHint")}</p>
      </div>
    </>
  );
}
