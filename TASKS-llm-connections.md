# 临时任务清单 — LLM 连接 / 聊天模型 重构（spec 011 收尾）

> **临时文件**，做完整块全部合并后即可删除。前置 PR #200、#202 已上线。
> 不新建 spec：所有改动 **amend `specs/011-provider-switching/` + `docs/decisions/ADR-032-provider-switching.md`**。

## 怎么用这个清单（loop 驱动）

每次迭代：取**第一个未勾选**的 `## 块N`，做完它的完整 PR 周期（spec/契约先改 → 代码跟上 → 自测 → 真实环境实测 → 开 PR → review → CI 绿 → squash-merge），把该块的 `- [ ]` 改成 `- [x]` 并入到该 PR 的 commit 里，然后下一块。一块 = 一个 PR = 一个 commit。

**每块开工前必读**（不要跳）：
1. memory `project_connections_optional_overrides`（核心设计现状）
2. `specs/011-provider-switching/spec.md` 的「Amendment 2026-06-22」小节（完整设计 + 已做/未做清单）
3. 本文件下面的「全局约束/坑」——**每块都适用**

**设计已定，别再问**：连接 = 可选覆盖；聊天起 agent 自己的 SDK/CLI，没连接走内置登录；连接只投射进 `~/.claude/settings.json` 或 `~/.codex/config.toml`；同一 agent 同时只有一个 active（内置 或 一个连接，#202 已做反投射）。

**授权**：每块自己测试 + review + 开 PR + CI 绿后合并。

---

## Loop 驱动提示词

在仓库根目录跑（自定步频，不带 interval；做完一块自动排程下一块）：

```
/loop 读 TASKS-llm-connections.md，取第一个未勾选（- [ ]）的「## 块N」，本次迭代只做这一个块。若没有未勾选块 → 报告「全部完成」并停止（不要再排程）。

对该块执行完整 PR 周期：
1. 先读「每块开工前必读」3 项 + 「全局约束/坑」(都适用)。
2. off origin/main 开该块的建议分支（worktree 按全局约束：前端 symlink node_modules、后端 PYTHONPATH 影子 venv）。
3. SDD 顺序：先改 spec.md/.zh + contracts/api.openapi.yaml + data-model/plan/quickstart（块6 改 specs/006，其余改 specs/011 + ADR-032），再写代码；acceptance scenario 名与 spec.md 逐字一致。
4. 自测 + 真实环境实测（make dev + 我的 Agnes key）。
5. push 前本地跑：mypy + ruff check + ruff format --check + check_file_sizes + 前端 tsc/eslint/vitest。
6. 把该块的 - [ ] 改成 - [x]，连同代码改动入到同一个 commit（一 PR 一 commit，标题 ≤72）。
7. 开 PR → 独立 review → CI 绿（落后就 git merge origin/main，禁 force-push）→ squash-merge。
8. 合并后 git checkout main && git pull --ff-only。

遵守本文件「全局约束/坑」全部条目。一次只做一个块，做完即结束本次迭代让 loop 排下一块。
```

> 注：本仓库的 `/next-task` 命令是从 `PLAN.md §11` 取行的，格式不同——**用上面这个 `/loop` 提示词**，不要用 `/loop /next-task` 跑本清单。

---

## 全局约束/坑（每块都适用）

- **SDD 顺序**：先改 `spec.md`/`spec.zh.md` + `contracts/api.openapi.yaml`（手写契约）+ `data-model.md`/`plan.md`/`quickstart.md`（及 `.zh`），**再写代码**；代码 conform spec。acceptance marker 的 scenario 名要和 spec.md `### Scenario:` **逐字一致**（`scripts/audit_acceptance.py`）。
- **新增/改 HTTP 路由** → 同步 `specs/011-provider-switching/contracts/api.openapi.yaml`。
- **i18n**：key 要**同时**加 `zh.json` + `en.json`。
- **codex 死路**：codex 0.130/0.141 只支持 OpenAI **Responses** API；Agnes/apihub 只兼容 **chat-completions** → codex+Agnes 跑不通，别花时间。codex 要聊天就用「内置」或换 Responses endpoint。
- **worktree 干活**：off `origin/main` 开 worktree；前端 `ln -s <main>/frontend/node_modules <wt>/frontend/node_modules`（`git worktree remove` 前先 `rm -f` 这个 symlink）；后端 `PYTHONPATH=<wt>/backend <main>/.venv/bin/python3 -m pytest`（main 在跑 make dev，worktree 无 .venv）。
- **PostToolUse ruff-autofix** 会删「刚加还没用」的 import → import 和用法放同一次 Edit，或最后再补 import。
- **check_file_sizes**：backend `.py` ≤ 400 行（`service.py` 已贴边，超了就抽模块）。
- **禁 force-push**（harness 拦截）：分支落后 main 用 `git merge origin/main`（**不要 rebase**）；改动追加新 commit，靠 squash-merge 收敛成一个。
- **main = strict 保护 + 8 必需检查 + 移动快**：常需 1–2 轮 merge-main。merge commit 若没触发 ci.yml（只剩 verify），推一个空/小 commit 重新触发；CLEAN 后再 squash-merge。`gh pr merge --delete-branch` 从 worktree 会报错但其实已合并 → 不带该 flag 合并后手动清理。
- **push 前本地跑**：mypy + ruff check + ruff format --check + check_file_sizes + 前端 tsc/eslint/vitest（CI 都会跑；`make verify` 跳过 Playwright e2e，路由/选择器变了要顺手改 `e2e/web/specs/*`）。
- **一 PR 一 commit**；commit subject + PR title ≤ 72 字符。
- **docs-site Vue build**：specs/** 里以 `<name>` 开头的换行续行会编译失败 → 反引号命令保持单行。
- **每块用真实环境实测**：`make dev` + 用户的 Agnes key，再开 PR。

---

## 块1 — 连接「添加/编辑」弹窗重构

- [x] 完成（建议分支 `feat/011-connection-dialog`）— PR #206 已合并

**目标**：连接弹窗只填 名称 + 协议 + base_url + key；加「测试连接」「拉取模型」「编辑」。

**改动**
- 去掉弹窗里的「模型」字段（模型移到 agent 页选 → 块3）。
- 加「测试连接」按钮：调后端 `POST /api/v1/models/test-connection`。
- 加「拉取模型」→ 把 endpoint 模型拉成下拉框：调后端 `POST /api/v1/models/list-models`。
- ⚠️ 这两个端点目前**只收 `credential_ref`**；要让「保存前」就能测/拉，需**扩展端点接受明文 `secret_value`**（后端 + 契约 + 测试都要改）。
- 连接卡片加「编辑」按钮（复用弹窗，预填现有值）。
- 前端主要文件：`frontend/src/components/settings/ProviderForm.tsx`、`frontend/src/pages/settings/LlmConnectionsPage.tsx`（按实际为准）。

**自测**：弹窗能新建/编辑；保存前点「测试连接」对 Agnes key 返回成功；「拉取模型」拉到下拉列表；契约/acceptance 覆盖明文 `secret_value` 分支。

---

## 块2 — 一网关供多 agent：共享凭据的双连接（简化，2026-06-22 改）

- [ ] 完成（建议分支 `feat/011-shared-credential`）

> **2026-06-22 决定（cc-switch 调研后）**：放弃原「连接声明多协议集合 + 数据迁移 + 按协议分别投射」的重方案。cc-switch 自身也**没有**多协议连接——它是单协议 provider + 通用作用域。Coffer 现有能力已基本覆盖目标：后端 create 已支持传 `credential_ref` 复用现有凭据；删除只清自己拥有且无其他引用的凭据（`service.py` `find_credential_citations`，共享 ref 已安全）；连接保留单 `wire_format`。**不改数据模型、不改 ADR-032 核心不变式、不做迁移。**

**目标**：「一个网关同时给 Claude Code 和 Codex 用」= 建**两个连接**（anthropic + openai，同一 base_url，**共享同一份凭据**）。本块只补上让用户能「复用现有凭据」的 UI + 文档定调。

**改动（聚焦前端 + 文档）**
- 前端 `ProviderForm`：密钥区给「**新建密钥** / **复用现有连接的凭据**」二选一；选复用时从现有连接的 `credential_ref` 列表里挑，提交发 `credential_ref`（而非 `secret_value`）。
- i18n（zh+en）。
- spec 011 + ADR-032：记「多 agent 经共享凭据的双连接达成；**不引入协议集合**」为选定模型（amend，supersede 早先的协议集合设想）；加一条 acceptance scenario「create a connection reusing an existing credential」（后端已支持，补前端/契约覆盖即可）。
- 后端：**基本无改动**（create 已收 `credential_ref`、删除已对共享 ref 安全）；如缺「列出可复用凭据」只读端点再按需加。

**自测**：建连接 A(anthropic,新 key) → 建连接 B(openai) 复用 A 的凭据；删 A 时若 B 仍引用则凭据不被删；两者各自按 wire 投射。无数据迁移、无协议集合。普通严格度（非「最严测」）。

---

## 块3 — agent 页模型选择（claude code 双模型槽）

- [ ] 完成（建议分支 `feat/011-agent-model-slots`）

**目标**：claude code 两个模型槽：`ANTHROPIC_MODEL` + `ANTHROPIC_SMALL_FAST_MODEL`；支持「一个 provider 两个模型」或「两个 provider 两个模型」。

**改动**
- agent 详情页：模型选择 UI 从单槽 → 双槽，每槽可独立选连接 + 模型。
- 投射：两个槽分别写对应环境变量/config。
- spec/契约/data-model 同步（双槽语义）。

**自测**：两槽各选不同连接+模型，投射出正确的 `ANTHROPIC_MODEL` / `ANTHROPIC_SMALL_FAST_MODEL`；切回内置时两槽都反投射清掉（沿用 #202 行为）。

---

## 块4 — internal_default 拆成 LLM 连接页内独立选择器

- [ ] 完成（建议分支 `feat/011-internal-default-selector`）

**目标**：「内部引擎用哪个连接」(internal_default) 变成 LLM 连接页里的**独立选择器**；连接卡片去掉内部引擎徽章/星标。

**改动**
- LLM 连接页加一个「内部引擎使用的连接」下拉/选择器。
- 删除连接卡片上的 internal_default 徽章/星标标记。
- spec/契约同步（选择器的读写端点；可能复用已有 internal_default 字段，仅改 UI 呈现）。

**自测**：选择器切换 internal_default 生效；卡片不再有星标；内部引擎（embedding/检索等）实际用所选连接。

---

## 块5 — 聊天页模型选择固定（不自由输入）

- [ ] 完成（建议分支 `feat/011-chat-model-fixed-select`）

**目标**：聊天页模型只能在 `{内置模型列表} ∪ {该 agent 已连接的模型}` 之间选；不允许自由输入；改模型一律去 agent 页。

**改动**
- 聊天页模型选择器：自由输入 → 固定下拉（并集来源）。
- 若并集为空或要改，引导去 agent 页。
- spec/契约同步（聊天可选模型的来源定义）。

**自测**：下拉只含内置 + 该 agent 连接的模型；无法输入任意字符串；换 agent 时列表随之变化。

---

## 块6 — 向量模型 (Embedding) 重构（涉及 spec 006）

- [ ] 完成（建议分支 `feat/006-embedding-dialog`）

**目标**：`EmbeddingSettings.tsx` 改成「添加」按钮 + 独立弹窗风格；默认**只能一个**模型；弹窗含测试连接 + 拉取模型；「启用向量 embedding」开关移到「分块设置」旁。

**改动**
- 文件：`frontend/src/pages/settings/EmbeddingSettings.tsx`。
- 弹窗风格对齐块1（测试连接 + 拉取模型）。
- 默认单模型：换模型 = 全部重新 embedding → **加确认对话框**（警告会重建全部向量）。
- 把「启用向量 embedding」开关从当前位置移到「分块设置」旁。
- ⚠️ 这块涉及 **spec 006**（`specs/006-knowledge-base/`）：spec/契约同步要改 006，不是 011。

**自测**：能添加/测试/拉取 embedding 模型；切换模型弹确认；开关在分块设置旁；不破坏现有 embedding 流程。

---

## 块7 — SSE 对账 bug（不要加后端 turn 超时）

- [ ] 完成（建议分支 `fix/008-chat-sse-reconcile`）

**目标**：修「AI 回复闪现又消失 / 一直思考中、要发下一条才出上一条」。根因是**前端 SSE 流投递丢 `turn_done`**（流断丢事件）。

**改动**
- 只改**前端**：`frontend/src/lib/hooks/useChatTurn.ts` + SSE subscribe / 流断重连逻辑。
- 见 memory `project_chat_turn_no_timeout_sse_reconcile` 和 PR #169。
- ❌ **不要加后端 turn 超时**（会杀长 Claude Code 任务）。
- 对账思路：流恢复/断开时主动对账后端真实 turn 状态，补齐丢失的 `turn_done`。

**自测**：复现「思考中卡住」场景后验证修复；`useChatTurn.test.tsx` 用确定性 waitFor（参考 memory `feedback_flaky_usechatturn_thinking_test`，别让它再 flaky）；真实 make dev 多轮对话不再丢消息/卡思考中。

---

**全部 7 块合并后**：删除本文件（`git rm TASKS-llm-connections.md`），可顺手在 spec 011 Amendment 的「未做清单」打勾收尾。
