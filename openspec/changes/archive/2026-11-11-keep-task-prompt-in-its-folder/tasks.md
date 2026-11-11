## 1. Backend

- [x] 1.1 `TaskFolderPort` and `TaskFolders` (`infrastructure/channel/task_folders.py`)
- [x] 1.2 `TaskService`: create writes `PROMPT.md`, `set_prompt`, `move_prompts_to_files` at wiring, `TaskView.prompt` / `folder`
- [x] 1.3 Runner reads `PROMPT.md`, fails on a missing or empty file, defaults the directory to the task's folder
- [x] 1.4 `ScheduledTaskConfig` refuses a prompt
- [x] 1.5 Routes: `PUT /{uid}/prompt`, `GET /{uid}/files`, `GET /{uid}/files/content`
- [x] 1.6 Notify `files` (route, service, CLI help); shared `local_files` with `coffer__channel_notify`
- [x] 1.7 CLI `task prompt`, `task files`; contracts, codegen, CLI reference

## 2. Frontend

- [x] 2.1 Tabs Overview / Prompt / History / Files
- [x] 2.2 Prompt tab on `PROMPT.md` through the prompt route; the Edit dialog drops the prompt
- [x] 2.3 History as a DataTable with search, filters and sorting
- [x] 2.4 Files tab with the shared Files card

## 3. Docs

- [x] 3.1 Spec channels and data model, ADR, guides and architecture (en, zh)
- [x] 3.2 Run canvas: tabs, history table, prompt file, files tab
