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

- `/coffer-spec` —— 起一个 SDD spec（见 `agents/sdd.md`）。

## 怎么测

hooks 与 settings 由 `backend/tests/integration/harness/` 钉住：subprocess 跑真脚本、喂合成 stdin。它们在 `make verify-integration` 下运行，harness 自测。

## Eval harness（Layer D）

非确定性的 AI 行为——检索质量与工具路由——在 [`evals/`](../evals/README.md) 下评测：`make eval`（本地、确定性）与 `make eval-routing`（需本地 LLM）。它是 prompt / 模型 / 检索改动的回归网；层次模型见 [ADR-017](../docs/decisions/ADR-017-industrial-grade-harness-in-layers.zh.md)。

## Eval 飞轮（loop engineering）

[ADR-019](../docs/decisions/ADR-019-close-the-eval-flywheel.zh.md) 闭合了循环，让 eval 套件不只是静态仪表，而是自我喂养的循环——即让 Coffer 非确定性行为不漂移的开发期循环：

1. **Capture** —— 设 `COFFER_EVAL_CAPTURE`，真实的 `coffer__search_tools` 调用会把其 `(query → 排序工具)` 形状记入本地、gitignore 的 JSONL sink（opt-in；默认关；绝不记工具参数/结果）。前置先把 invocation 日志变诚实（in-band `isError` → `status=error`），失败才可读。
2. **Curate** —— `make eval-curate` 把捕获的 query 变成带标注的 `datasets/*.jsonl` golden case（对现有 dataset 去重；你标哪些返回的工具相关），打 `"source": "captured"` 标签。
3. **Gate** —— `evals.yml` workflow 对触碰 prompts / mcp / 检索 / catalogue 的 PR 跑确定性、免模型套件，按**相对 committed baseline 的回归**失败（`evals/run.py`）。需模型的 routing 套件留按需（`make eval-routing`），不进 CI。
4. **Feedback** —— 一次真实使用失败 → 捕获 case → curate 成 golden case → gate 抓到的 baseline 回归 → 修复 → `python -m evals.run --update-baseline`。数据集随真实使用棘轮式上升；修复仍由人 + Claude Code 内循环负责（飞轮负责测量与护栏，不自动优化——见 ADR-019 延后的 repair-assist）。

## 约定

- hooks 用 Python（免 `jq` 依赖；项目保证 Python 3.12）。hook 绝不能弄坏 agent —— 任何异常都 exit 0、不下决定。
- `.claude/settings.json`、`.claude/hooks/`、`.claude/skills/` 已提交。`.claude/settings.local.json` 是个人覆盖（gitignored）。
