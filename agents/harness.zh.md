# Harness —— Agent 控制层

> English: [harness.md](./harness.md)

Coffer 提交了一套 checked-in 的控制层，让 agent-facing harness 被强制执行、而非仅靠文档。五层模型见 [ADR-017](../docs/decisions/ADR-017-industrial-grade-harness-in-layers.zh.md)。

## 接入了什么（`.claude/`）

| 文件 | 作用 |
| ---- | ---- |
| `.claude/settings.json` | 权限（allow 安全命令、deny 破坏性命令）+ hook 接线。已提交、团队共享。 |
| `.claude/hooks/auto_format.py` | PostToolUse（Edit/Write）—— 格式化改动的文件（`.py` 用 ruff，`.ts/.tsx/.js/.jsx/.css/.json/.md` 用 prettier）。尽力而为，绝不阻断。 |
| `.claude/hooks/block_dangerous_bash.py` | PreToolUse（Bash）—— 拦截一小撮破坏性命令（递归删 root/home、force/直推保护分支、pipe-to-shell、裸写块设备）。 |
| `.claude/hooks/session_context.py` | SessionStart —— 注入分支、worktree 状态、未提交文件数、session 协议提醒。 |

## Skills

- `/coffer-verify` —— 跑 `make verify` 并如实汇报。开 PR 前用。
- `/coffer-spec` —— 起一个 SDD spec（见 `agents/sdd.md`）。

## 怎么测

hooks 与 settings 由 `backend/tests/integration/harness/` 钉住：subprocess 跑真脚本、喂合成 stdin。它们在 `make verify-integration` 下运行，harness 自测。

## 约定

- hooks 用 Python（免 `jq` 依赖；项目保证 Python 3.12）。hook 绝不能弄坏 agent —— 任何异常都 exit 0、不下决定。
- `.claude/settings.json`、`.claude/hooks/`、`.claude/skills/` 已提交。`.claude/settings.local.json` 是个人覆盖（gitignored）。
