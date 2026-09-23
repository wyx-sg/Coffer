// frontend/src/components/workflow/NodeAssignmentBar.tsx
// Who runs this task, on what, before it runs (spec workflow "Choose a task's agent,
// model and effort before it starts").
//
// Once a task has started, the bar above its transcript is the chat layer's
// own: its conversation holds the agent, the model and the effort, and the
// pickers there write them. Before it starts there IS no conversation, which
// made the one moment a developer most wants to say "do this one on the bigger
// model" the one moment nothing could be said.
//
// So this is the same three controls over a different writer: the attempt the
// task will open with. It is deliberately the same pickers — a second dropdown
// offering a different set of models would eventually disagree with the first
// about what this agent can run.
//
// The agent is a plain Select rather than a shared component because nowhere
// else picks one per conversation: chat binds an agent at creation and never
// moves it, and a task's agent comes from its workflow unless this says
// otherwise.
import { useTranslation } from "react-i18next";
import { Bot } from "lucide-react";

import { EffortPicker } from "@/components/chat/EffortPicker";
import { ModelPicker } from "@/components/chat/ModelPicker";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useAgentProviders } from "@/lib/hooks/useAgentProviders";
import { useAssignNode } from "@/lib/hooks/useWorkflowRun";

/** "Whatever the workflow said." Radix forbids an empty item value, and no
 *  agent key looks like this. */
const INHERIT = "__inherit__";

interface Props {
  runId: string;
  nodeKey: string;
  /** What the attempt has been assigned, if anything. */
  agent: string | null | undefined;
  model: string | null | undefined;
  effort: string | null | undefined;
  /** What the workflow says when the attempt says nothing — shown as the
   *  inherited option's words, so "default" is never a mystery. */
  templateAgent: string | null | undefined;
  disabled?: boolean;
}

export function NodeAssignmentBar({
  runId,
  nodeKey,
  agent,
  model,
  effort,
  templateAgent,
  disabled = false,
}: Props) {
  const { t } = useTranslation();
  const agents = useAgentProviders().data ?? [];
  const assign = useAssignNode(runId, nodeKey);
  const busy = disabled || assign.isPending;

  const current = agent ?? null;
  // The pickers need an agent to ask for a catalogue. With none chosen the
  // task will run on the workflow's, so that is the one to ask about.
  const effective = current ?? templateAgent ?? agents[0]?.agent_key ?? "";
  const label = (key: string) => agents.find((a) => a.agent_key === key)?.display_name ?? key;

  const commit = (next: { agent?: string | null; model?: string | null; effort?: string | null }) =>
    assign.mutate({
      agent: next.agent === undefined ? (agent ?? null) : next.agent,
      model: next.model === undefined ? (model ?? null) : next.model,
      effort: next.effort === undefined ? (effort ?? null) : next.effort,
    });

  // Changing the AGENT clears the model and the effort. A model id belongs to
  // one agent's catalogue — `gpt-5-codex` means nothing to Claude Code — so
  // carrying it across would hand the new agent a model it cannot run, and the
  // failure would arrive when the task started rather than when the choice was
  // made.
  const chooseAgent = (next: string | null) =>
    assign.mutate({ agent: next, model: null, effort: null });

  return (
    <div className="flex flex-wrap items-center gap-3 border-b border-border bg-card/50 px-4 py-2">
      <div className="flex items-center gap-1.5 text-sm font-medium text-foreground">
        <Bot className="size-4 shrink-0 text-primary" strokeWidth={1.75} />
        <span>{t("workflow.node.runsOn")}</span>
      </div>

      <Select
        value={current ?? INHERIT}
        disabled={busy}
        onValueChange={(next) => chooseAgent(next === INHERIT ? null : next)}
      >
        <SelectTrigger className="h-8 w-[12rem]" aria-label={t("workflow.templates.agent")}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={INHERIT}>
            {templateAgent
              ? t("workflow.node.fromWorkflow", { agent: label(templateAgent) })
              : t("workflow.templates.defaultAgent")}
          </SelectItem>
          {agents.map((a) => (
            <SelectItem key={a.agent_key} value={a.agent_key}>
              {a.display_name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <ModelPicker
        agentKey={effective}
        value={model ?? null}
        disabled={busy}
        onCommit={(next) => commit({ model: next })}
      />
      <EffortPicker
        agentKey={effective}
        model={model ?? null}
        value={effort ?? null}
        disabled={busy}
        onCommit={(next) => commit({ effort: next })}
      />
    </div>
  );
}
