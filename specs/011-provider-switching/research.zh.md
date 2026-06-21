# 研究记录——011 Provider Switching

> English: [research.md](./research.md)

记录已考量的设计备选方案、达成的决策及关键选择的理由。对应 ADR-032。

## 问题陈述

Claude Code 和 Codex 各自从格式不同的原生配置文件中读取 provider 设置（`~/.claude/settings.json` JSON；`~/.codex/config.toml` TOML）。今天手动切换 provider 意味着：

- 手动编辑多个文件。
- 以明文将原始 API key 存储在配置文件中。
- 丢失统一的审计记录。
- 无跨机器一致性（key 是机器本地的）。

## 决策 A——单 wire profile，按 agent 激活

### 考量的方案

**A1（已选）：一条 profile = 一种 wire format；每种 wire 最多一条活跃。**
一条 profile 知道自己的 wire format，最多投影到一个原生 agent。Claude Code 和 Codex 共享注册表，可共用 credential ref，但由独立的 profile 记录驱动。

*理由*：简单、显式，与 `ModelConfig.is_default` 中的现有单活跃模式一致。无隐式多 agent 扇出，避免部分失败导致状态不一致。每条 profile 可独立测试。

**A2：一条 profile 同时驱动两个 agent。**
单条 profile 同时注入 `settings.json` 和 `config.toml`。

*拒绝*：强迫每条 profile 承载大量字段（claude_model、codex_model、wire_api、fast_model 混杂）。当一个 wire 成功而另一个失败时，"active"的语义不清晰。违反项目"最简"和"显式"的偏好。

**A3：按 agent 独立管理 provider，无共享注册表。**
每个 agent 独立维护自己的 provider 列表。

*拒绝*：丢失治理收益（统一审计、sync、加密）。这实际上是现状。

## 决策 B——凭证隔离（明文密钥不得写入原生配置）

### 考量的方案

**B1（已选）：Claude Code 用 apiKeyHelper；Codex 用 env_key。**
原始 key 只存于 Fernet vault。Claude Code 通过 `apiKeyHelper` 命令行钩子读取 key；Codex 从环境变量读取。

*理由*：与现有 MCP `credential_refs` 模式一致。原始 key 永不落盘（除加密 vault 外）。审计日志和 sync workspace 永不含明文 secret。`apiKeyHelper` 是 Claude Code 为此目的而设计的原生特性。

*Codex 的可接受代价*：Codex 没有等同于 `apiKeyHelper` 的机制；最接近的是命名环境变量。Coffer 将 `env_key = "COFFER_PROVIDER_KEY"` 写入 `config.toml`，用户启动 Codex 前需手动 export 该变量。已在 quickstart 中记录。将原始 key 写入 `config.toml` 的备选方案因违反凭证隔离原则而被拒绝。

**B2：将原始 key 写入原生配置文件。**
向 `settings.json` 写入 `ANTHROPIC_API_KEY`，向 `config.toml` 写入 `api_key`。

*拒绝*：违反项目"凭证隔离"原则（MEMORY 记录："MCP credential_refs 模式"）。明文 key 在配置文件中会被 sync、备份和 git 历史暴露。与 MCP server 的管理方式不一致。

**B3：Coffer 作为本地代理（key 永不离开 Coffer 进程）。**
Coffer 暴露一个本地 endpoint；`apiKeyHelper` 命中代理，代理注入 key 后转发请求。

*拒绝*：超出已确认设计范围，明确列为非目标（不做代理 / 格式转换）。增加延迟、复杂度和新的基础设施依赖。

### 关于 hot-switch 的前瞻说明

由于 Claude Code 在每次请求前（或周期性地）重新调用 `apiKeyHelper`，切换 Coffer 中的活跃 anthropic profile 会立即影响下一次 Claude Code 请求——apiKeyHelper 设计使 Claude Code 的 hot-switch "几乎可以无代价实现"。此处仅作前瞻性说明；hot-switch 明确不在本 PR 范围内。

## 决策 C——分阶段交付；hot-switch 延期

### 考量的方案

**C1（已选）：本 PR 交付注册表 + 投影 + 切换 + 审计 + sync；hot-switch（会话内热重载）放到后续 PR。**

*理由*：投影步骤（文件写入）本身已是原子且即时的。Claude Code 用户通过 `apiKeyHelper` 无需额外工作即可实现等效的 hot-switch。Codex 用户需手动重新 export 环境变量，已记录在文档中。延期 hot-switch 让本 PR 能够交付干净、可审计、经过充分测试的基础。

**C2：本 PR 同时交付 hot-switch。**
需要检测正在运行的 Claude Code / Codex 进程，向其发信号，并处理部分失败。复杂度显著增加。

*拒绝*：违反项目"最简"原则。注册表 + 投影基础可独立交付，本身即有价值。

## Wire format 设计理由

### anthropic wire → Claude Code

Claude Code 的 `~/.claude/settings.json` 是规范配置文件。关键选择：

- **`apiKeyHelper`**：Claude Code 原生特性；通过调用辅助命令获取 key。这是避免在 `settings.json` 中存储 key 的推荐方式。
- **`env.*` 键**：Claude Code 从 `env` 节读取这些键，在启动底层 SDK 进程前将其 export。托管键为 `ANTHROPIC_BASE_URL`、`ANTHROPIC_MODEL`、`ANTHROPIC_SMALL_FAST_MODEL`。
- **绝不写 `ANTHROPIC_API_KEY`**：写入此键会覆盖 `apiKeyHelper` 并将 key 暴露在文件中。
- **合并而非替换**：Coffer 只接触定义的托管键。其余所有内容（theme、`mcpServers`、`permissions` 等）均保持不变。

### openai wire → Codex

Codex 的 `~/.codex/config.toml` 使用命名 provider 模型。关键选择：

- **`model_provider = "coffer"`**：告知 Codex 在 `[model_providers]` 中查找 `coffer` 条目。
- **`[model_providers.coffer]`**：命名 provider 块，含 `name`、`base_url`、`wire_api`、`env_key`。Codex 从 `env_key` 环境变量读取 key。
- **`wire_api`**：允许在 Chat Completions API（`"chat"`）和 Responses API（`"responses"`）之间切换，作为 Codex 的原生协议。
- **`tomlkit`**：用于合并，以保留文件中的注释和顺序。字符串替换方案因脆弱且会破坏用户自定义而被拒绝。

## 为什么不做代理 / 故障转移 / 格式转换

- **不做代理**：添加本地代理服务会增加延迟、引入新的管理组件，并需要客户端重新配置以访问代理。超出范围。
- **不做故障转移 / fallback 链**：按 profile 激活是显式且确定性的。添加 fallback 链会使活跃 provider 语义模糊，审计困难。
- **不做格式转换**：`wire_format` 为 `anthropic` 的 profile 原生使用 Anthropic API。将其转换为 OpenAI 形状的请求（反之亦然）需要拦截代理，明确是非目标。若用户想在 Claude Code 中使用 OpenAI 兼容 endpoint，应创建 `openai` profile 和 Codex agent，而不是要求 Coffer 实时转换。

## Sync 与审计设计

**Sync**：将 `provider` 建模为 ResourceService Kind 是支持 sync 的最小路径。`SyncExporter` 和 `SyncImporter` 自动处理所有 kind；添加 `provider` 只需在 composition root 注册一个 Kind，以及一个 `wire_provider_kind` 辅助函数。无需新迁移，因为 `resources` 表已通过 `kind` 列支持任意 kind。

凭证 sync：凭证已以 Fernet 密文（非明文）同步，路径为 `credentials/<ref>.enc`。主密钥永不离开本机。与 MCP server 凭证（spec 001）的模式相同。

**审计**：`RESOURCE_CREATED`、`RESOURCE_UPDATED`、`RESOURCE_DELETED` 由 `ResourceService` 自动发出。将 `PROVIDER_SWITCHED` 作为独立的专用事件（而非复用通用切换事件）是有意为之：它携带结构化 details（`{from, to, wire_format, agents}`），使审计者无需扫描资源更新 diff 即可重建完整的切换历史。

## 本规范中未包含的备选方案

- **Provider drift-verify**：检查实时的 `settings.json` / `config.toml` 是否与活跃 profile 一致。延期到 spec 4.9。本 PR 不实现，因为投影步骤本身即为权威来源；只有用户在切换后手动编辑配置文件才会产生 drift。
- **将 `COFFER_PROVIDER_KEY` 自动注入 Coffer 启动的 Codex 进程**：需要 Coffer 的进程启动逻辑读取活跃 openai profile 并注入变量。与 hot-switch 一同延期。
- **显式停用 / 原生配置还原**："撤销"切换，将配置恢复到 Coffer 介入前的状态。`.bak` 备份提供手动恢复能力。自动还原延期（复杂度高；用户在切换后可能又有额外编辑，语义不清）。
