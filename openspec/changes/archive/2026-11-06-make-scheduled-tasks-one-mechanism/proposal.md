## Why

The owner (2026-11-06): "Coffer 只提供一个定时任务机制，怎么使用是用户的事情", and
"coffer 内置不要保留任何模版，都是用户自己去实现". Binding a task to a chat, the
choice of carrying on a chat's conversation, the follow-ups an agent books in
its thread, the daily report template and the Monday-to-Friday schedule are all
uses of the mechanism that a prompt or a skill can state for itself
("就算我们想让任务跟着聊天走，自己在提示词或者 skill 里写清楚不就好了";
"不同国家工作日都不一样的"). ADR automation-is-a-scheduled-prompt.

## What Changes

- A task is a schedule, a prompt, an agent, an optional model and directory,
  and catch-up. Every run opens a new conversation of its own; nothing is
  posted to a chat. The prompt is sent as written, with one late note when the
  run is late.
- **Removed**: a task's chat and its conversation mode; the follow-up tools
  `coffer__schedule_task`, `coffer__scheduled_tasks`,
  `coffer__cancel_scheduled_task`, the follow-up chain limits and `/status`'s
  list of waiting tasks; the `[SILENT]` rule and the `replied` / `silent`
  outcomes; the `[Scheduled task]` and `[Material]` turn blocks; the daily
  report (template, material, Channels page card, `PUT
  /scheduled-tasks/daily-report`, `coffer task daily-report`); `GET
  /scheduled-tasks/chats` and `coffer task chats`; the `weekdays` schedule.
- Older task files are read without their chat; a weekdays schedule reads as
  its cron; follow-ups are removed at start; `scheduled_task_runs` loses
  `channel_uid` and `chat_id` (migration 0156).
- Web UI: one task list; the dialog drops the chat and conversation fields,
  offers the agent's models in a select and the directory through the folder
  picker, and keeps its footer at the bottom while the body scrolls.

The main specs are edited directly (scenarios are renamed and dropped, which a
`MODIFIED` delta cannot do): channels, channels data model,
experimental-features, web-ui.
