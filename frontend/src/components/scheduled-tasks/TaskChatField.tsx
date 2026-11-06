// src/components/scheduled-tasks/TaskChatField.tsx — the Runs in field of the task dialog: no chat, or one of the chats the owner already uses with a bot.
//
// A task bound to no chat runs, each time, in a new conversation of its own
// agent and directory, like Claude Code's and Codex's own automations; one in
// a chat runs there and answers there. The chats are the paired ones, by
// channel; with none paired the field says how to get one.
import { useTranslation } from "react-i18next";

import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { ScheduledTask, TaskChat } from "@/lib/api/scheduledTasks";
import { useTaskChats } from "@/lib/hooks/useScheduledTasks";
import { chatKey, NO_CHAT, type TaskForm } from "@/lib/scheduledTasks/format";

interface Props {
  form: TaskForm;
  set: (patch: Partial<TaskForm>) => void;
  existing?: ScheduledTask;
}

function byChannel(chats: TaskChat[]): [string, TaskChat[]][] {
  const out = new Map<string, TaskChat[]>();
  for (const chat of chats)
    out.set(chat.channel_name, [...(out.get(chat.channel_name) ?? []), chat]);
  return [...out.entries()];
}

export function TaskChatField({ form, set, existing }: Props) {
  const { t } = useTranslation();
  const { data, isPending } = useTaskChats();
  const chats = data ?? [];
  const known = chats.some((c) => chatKey(c.channel, c.chat_id) === form.chat);
  return (
    <div className="space-y-1.5">
      <Label htmlFor="task-chat" required>
        {t("scheduledTasks.dialog.chat")}
      </Label>
      <Select
        value={form.chat || undefined}
        onValueChange={(chat) =>
          // No chat has no channel to choose the agent: start it on Claude Code.
          set(chat === NO_CHAT && !form.agent ? { chat, agent: "claude_code" } : { chat })
        }
      >
        <SelectTrigger id="task-chat" disabled={isPending}>
          <SelectValue placeholder={t("scheduledTasks.dialog.chatPlaceholder")} />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={NO_CHAT}>{t("scheduledTasks.dialog.noChat")}</SelectItem>
          {existing && form.chat && form.chat !== NO_CHAT && !known ? (
            <SelectItem value={form.chat}>
              {existing.channel_name} · {existing.config.chat?.chat_id}
            </SelectItem>
          ) : null}
          {byChannel(chats).map(([channel, rows]) => (
            <SelectGroup key={channel}>
              <SelectLabel>{channel}</SelectLabel>
              {rows.map((c) => (
                <SelectItem
                  key={chatKey(c.channel, c.chat_id)}
                  value={chatKey(c.channel, c.chat_id)}
                >
                  {c.label} · {t(`scheduledTasks.chatKind.${c.chat_kind}`)}
                </SelectItem>
              ))}
            </SelectGroup>
          ))}
        </SelectContent>
      </Select>
      <p className="text-xs text-text-muted">
        {form.chat === NO_CHAT
          ? t("scheduledTasks.dialog.noChatHint")
          : !isPending && chats.length === 0
            ? t("scheduledTasks.dialog.noChats")
            : t("scheduledTasks.dialog.chatHint")}
      </p>
    </div>
  );
}
