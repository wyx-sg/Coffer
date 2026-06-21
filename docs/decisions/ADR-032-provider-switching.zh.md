# ADR-032：Provider Switching

**Status**: Proposed
**Date**: 2026-06-21
**Spec**: [specs/011-provider-switching/spec.md](../../specs/011-provider-switching/spec.md)

## 背景

Claude Code 和 Codex 各自需要在独立的原生配置文件中配置 provider 信息（`~/.claude/settings.json`、`~/.codex/config.toml`）。用户若想切换 LLM provider（例如从默认 Anthropic endpoint 切换到第三方 OpenAI 兼容 endpoint，反之亦然），今天必须手动编辑多个文件，以明文存储 API key，并丢失审计记录。凭证也无法跨机器同步。

## 决策

### A——单 wire profile，按 agent 激活

*provider profile* 是一条记录，持有 `{name, wire_format, base_url, credential_ref, model, fast_model, wire_api, is_active}`。其 `wire_format` 为 `"anthropic"` 或 `"openai"`，决定了它确切地投影到哪个原生 agent：

- `anthropic` → Claude Code（`~/.claude/settings.json`）
- `openai` → Codex（`~/.codex/config.toml`）

同一 `wire_format` 下最多一条 profile 处于活跃状态。Claude Code 和 Codex 共享同一 profile 注册表，可共用 `credential_ref`，但各自由独立的 profile 记录驱动，不存在同时驱动两个 agent 的单条记录。

### B——凭证隔离：明文密钥不得写入原生配置

原始 API key 只存于 Fernet vault，通过两种机制按需解密：

- **Claude Code**（`apiKeyHelper`）：`settings.json` 写入 `apiKeyHelper = "coffer provider key --wire anthropic"`，Claude Code 调用此命令获取 key。原始 key 绝不写入 `settings.json`。由于 Claude Code 会定期重新调用 `apiKeyHelper`，此设计使未来的 hot-switch 对 Claude Code 几乎可以无代价实现。
- **Codex**（`env_key`）：`config.toml` 写入 `[model_providers.coffer].env_key = "COFFER_PROVIDER_KEY"`，Codex 在运行时从该环境变量读取 key。原始 key 绝不写入 `config.toml`。用户需在启动 Codex 前 export `COFFER_PROVIDER_KEY`（见规范 quickstart）。将 key 自动注入 Coffer 启动的 Codex 进程与 hot-switch 一同延期。

此决策与现有 MCP `credential_refs` 模式一致。原始 key 也不会出现在 sync workspace（`resources/provider/*.yaml`）中。

### C——分阶段交付：hot-switch 延期

本 ADR 涵盖：provider 注册表、投影（原生配置文件写入）、切换/激活操作、`PROVIDER_SWITCHED` 审计事件、sync 接入。

**Hot-switch**（对正在运行的 Claude Code 或 Codex 进程的会话内热重载）明确**不在本 ADR 范围内**，将在单独的后续 ADR 和 PR 中处理。

### D——一条 LLM connection，agent 与 Coffer 内部引擎共用

provider profile 与 Coffer 旧的 `ModelConfig`/`chat_models` 注册表本是同一形状（key + endpoint + model）戴着两顶帽子。二者统一为单一的 **LLM connection** = provider resource。独立的 `ModelConfig` 注册表——model CRUD REST 与 `coffer model` CLI——**退役**（其行迁移为 provider resource；保留 provider 的模型内省路由 `list-models` / `test-connection`）。为此：

- `wire_format` 新增第三个取值 `ollama`：**仅内部**，不投影到任何 agent（`target_for` 返回 `None`），且无密钥——故 `credential_ref` 变为可选（anthropic/openai 必填，ollama 不存在）。
- 新增全局 `internal_default` 标志（所有 connection 中 ≤1），标记 Coffer 内部 LLM 引擎（memory organizer、reorg、distill、`coffer__ask`）使用的 connection，经 `POST /providers/{name}/internal-default`（审计事件 `provider_internal_default_set`）/ `coffer provider internal-default` 设置。一条 connection 可以**同时**是 `is_active`（投影到其 wire 的 agent）和 `internal_default`——一份密钥，两种用途。
- `build_chat_model` 改吃 connection（`ProviderConfig`），按 `wire_format` 分派，取代对 `ModelConfig` 的依赖。这修复了一个真 bug：旧的 anthropic/openai builder 丢弃了 connection 的 `base_url`，导致自定义/代理 endpoint 被忽略。内部消费者从 `ModelService.get_default()` 改指 `ProviderService.resolve_internal_connection()`；未配置 `internal_default` 时内部引擎是干净的 no-op（与此前一致）。

per-conversation 的 `Conversation.model_id` 列现为遗留 vestigial 列（保留，不再对注册表校验）。

## 后果

### 投影写入（及绝不写入）的内容

**anthropic → Claude Code**——Coffer 将以下键合并入 `~/.claude/settings.json`（JSON，通过 `ConfigFileStore.write_text_atomic` 原子写 + `.bak` 备份，保留所有其他键）：

| 托管键 | 值 |
|---|---|
| `apiKeyHelper` | `"coffer provider key --wire anthropic"` |
| `env.ANTHROPIC_BASE_URL` | `profile.base_url` |
| `env.ANTHROPIC_MODEL` | `profile.model` |
| `env.ANTHROPIC_SMALL_FAST_MODEL` | `profile.fast_model`（为 `None` 时省略） |

**绝不写入** `ANTHROPIC_API_KEY`。

**openai → Codex**——Coffer 将以下键合并入 `~/.codex/config.toml`（TOML，通过 `tomlkit` 原子写 + `.bak` 备份，保留所有其他键）：

| 托管键 | 值 |
|---|---|
| `model` | `profile.model` |
| `model_provider` | `"coffer"` |
| `[model_providers.coffer].name` | `"Coffer (<profile name>)"` |
| `[model_providers.coffer].base_url` | `profile.base_url` |
| `[model_providers.coffer].wire_api` | `profile.wire_api` |
| `[model_providers.coffer].env_key` | `"COFFER_PROVIDER_KEY"` |

### 明确的非目标

- **代理 / 故障转移 / 格式转换**：不做代理；无 fallback 链；不做 anthropic↔openai 协议转换。
- **Hot-switch / 进程内热重载**：延期到后续 PR。
- **Provider drift-verify**：延期到 spec 4.9。
- **显式停用 / 原生配置还原**：无"撤销切换"操作。
- **超出 wire 匹配的逐 agent provider 覆盖**：与 agent wire 不匹配的 profile 不投影到该 agent，无手动绑定。
- **将 `COFFER_PROVIDER_KEY` 自动注入 Coffer 启动的 Codex 进程**：与 hot-switch 一同延期。

### Codex 环境变量缺口——决策 B 的可接受代价

Codex 需要在启动前在 shell 中设置 `COFFER_PROVIDER_KEY`。这是永不将原始 key 写入 `config.toml` 的可接受代价。Claude Code 通过 `apiKeyHelper` 不存在此缺口。自动注入延期。

### Sync

将 `provider` 建模为 ResourceService Kind 使 sync 以零引擎成本自动实现。无需新迁移或 `SCHEMA_VERSION` bump。

### 激活顺序

激活通过顺序的 `ResourceService.update_config` 调用清除同 wire 下其他 profile 的 `is_active`，然后将目标 profile 的 `is_active` 设为 `true`。单进程 daemon 对请求串行化，切换操作不会交错。投影（`ProviderService._project`）在激活标志翻转之前运行；原生配置写入失败会中止切换，注册表保持不变。

### 域层纯粹性

投影逻辑由 `backend/coffer/domain/provider/projection.py` 中的纯函数 `apply_anthropic_settings` 和 `apply_codex_provider` 组成，直接返回新的原生配置文本（镜像 `domain/agent/mcp_install.py` 的 `apply_install`）。不存在 `ProjectionPatch` 数据类，也不存在 `build_patch()` 函数。所有 I/O（文件写入）由 `ProviderService._project` 执行。

## 已考量的备选方案

完整的备选方案枚举（A1/A2/A3、B1/B2/B3、C1/C2）及拒绝理由见：
[specs/011-provider-switching/research.md](../../specs/011-provider-switching/research.md)
