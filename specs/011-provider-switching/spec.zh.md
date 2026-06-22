# 功能规范：Provider Switching

> English: [spec.md](./spec.md)

**Feature Branch**: `feature/G9-provider-switching`
**Created**: 2026-06-21
**Status**: Draft

## 一句话总结

统一的 **LLM connection** 让用户只需配置一次密钥（名称、wire 格式、base URL、加密凭证、模型），并以两种方式使用它：既投影到对应 agent 的本地配置文件，也让 Coffer 自身的内部 LLM 引擎在其上运行。一条 connection 即退役独立的 `ModelConfig`/`chat_models` 注册表，将内部引擎的模型选择折叠进同一条记录。相比 `claude switch` 或各工具的独立脚本，Coffer 的优势在于统一注册表加治理层——Fernet 加密凭证、完整审计日志、git 同步——而非各工具各管各的。

## 为什么要做

Claude Code 和 Codex 各有自己的原生配置文件（`~/.claude/settings.json`、`~/.codex/config.toml`），需要填写不同的 provider 密钥和 base URL，而 Coffer 的内部引擎过去还另有一份并行的模型注册表（`chat_models`）。今天手动切换 provider 意味着编辑多个文件、以明文存储密钥、并丢失审计记录——而且为某个 agent 配置的密钥无法被内部引擎复用。Coffer 集中管理 connection：配置一次，投影到匹配 agent（切换），将其中一条标记为内部引擎默认，全程可审计。

## 已确认决策

以下三条决策在撰写规范前已锁定，不得重新讨论。

### 决策 A——单 wire connection、按 agent 激活、单一内部默认

一条 connection 持有 `{name, wire_format, base_url, credential_ref, model, fast_model, wire_api, is_active, internal_default}`。一条 connection 只投影到其 `wire_format` 匹配的 agent：

- `anthropic` → Claude Code（`~/.claude/settings.json`）
- `openai` → Codex（`~/.codex/config.toml`）
- `ollama` → 仅内部；从不投影到任何 agent

每种 wire format 最多同时存在一条活跃 connection（与已退役的 chat-model 注册表中 `ModelConfig.is_default` 的模式类似）。Claude Code 和 Codex"共用"同一注册表，一个 `credential_ref` 可被多条 connection 复用，但绝非用一条记录同时驱动两个 agent。

除按 agent 激活外，一条 connection 还可以携带单一的全局 `internal_default` 标志（所有 connection 中 ≤1），标记 Coffer 自身内部 LLM 引擎（memory organizer、reorg、distill、`coffer__ask`）使用的 connection。第三种 wire `ollama` 仅供内部：它从不投影到任何 agent；且因其没有 API key，其 `credential_ref` 不存在——只需一个 `base_url`。因此 `credential_ref` 是**可选**的：anthropic/openai 必填，ollama 不存在。一条 connection 可以**同时**是活跃的（投影到其 wire 的 agent）和 `internal_default`（供内部使用）——一份密钥，两种用途。

### 决策 B——凭证隔离；明文密钥不得写入原生配置

与现有 MCP `credential_refs` 模式及"凭证隔离"原则保持一致。原始密钥始终留在 Fernet vault 中，按需解密，从不持久化到原生配置文件：

- **Claude Code**：在 `settings.json` 中写入 `apiKeyHelper = "coffer provider key --wire anthropic"`。Claude Code 调用此命令获取密钥。由于 Claude Code 会定期重新调用 `apiKeyHelper`，该设计使未来的 hot-switch 几乎可以无代价实现——此处仅作前瞻性说明。
- **Codex**：在 TOML 的 `[model_providers.coffer]` 表中写入 `env_key = "COFFER_PROVIDER_KEY"`。Codex 在运行时从该环境变量读取密钥。**本 PR 不修改 Codex 的启动逻辑**；用户需要手动 export 该变量（见 Quickstart）。明确说明：**Codex 独立运行时需要在 shell 中设置 `COFFER_PROVIDER_KEY`；将 key 自动注入 Coffer 启动的 Codex 进程与 hot-switch 一同延期。** 这是选择决策 B（凭证隔离）可接受的代价。

原始密钥绝不写入 `settings.json`、`config.toml` 或任何其他原生配置文件。

### 决策 C——分阶段交付；本 PR 不包含 hot-switch

本 PR 交付：注册表 + 投影 + 切换操作 + 审计 + sync 接入。

Hot-switch（对正在运行的 Claude Code 或 Codex 进程的会话内热重载）是**单独的后续 PR**，明确**不在本 PR 范围内**。

## 修订 2026-06-22b — 连接是「带凭据的 endpoint」；模型与协议离开连接

> 状态：Draft。**Supersede 决策 A 的「model 在连接上」与早先 amendment 的 D2（多协议集合）。**
> cc-switch 调研 + 与用户敲定后记录。交叉引用
> [ADR-032](../../docs/decisions/ADR-032-provider-switching.md) amendment D8/D9。

**为什么。** 连接回答的是「哪个网关账号」= endpoint + key。*用哪个模型*、*agent 说哪种协议*
是「使用」的属性，不是账号的属性：Claude Code 永远说 Anthropic Messages wire、Codex 永远说
OpenAI，所以协议在投射时由 agent 决定；模型则按 agent 槽 / 内部引擎 / 聊天轮次现选。把
`model` 和手动 `wire_format` 挂在连接上，逼用户过早回答这些问题，也把账号和它的用途混在一起。

- **E1 — 连接实体瘦身为 `{name, base_url, credential_ref, protocol}`。** 从连接上**移除**
  `model`、`fast_model`、手动 `wire_format` 选择器；`wire_api`（Codex chat/responses）也移到
  Codex 绑定，不在连接上。
- **E2 — `protocol` 是探测出来的，不是用户填的。** create/edit 时 Coffer 探测 endpoint
  （复用 introspection 路径）判为 `anthropic`-wire / `openai`-wire / `unknown`。所以添加对话框
  只显示 **名称 + base_url + key + 「测试连接」**——无类型选择器、无模型字段。
- **E3 — 模型在「使用处」现选。** 按 agent 绑定（Agent 页双槽 → `ANTHROPIC_MODEL` +
  `ANTHROPIC_SMALL_FAST_MODEL`）、内部引擎默认选择器、聊天面各自从所选连接拉取的模型里挑。
  连接上不存模型。**内部引擎模型**自成一个全局单例（一行），经
  `GET`/`PUT /api/v1/internal-engine-config` 读写，审计为 `internal_engine_model_set`；
  `resolve_internal_connection()` 在内部引擎构建 chat model 前，把该模型覆盖到解析出的
  `internal_default` 连接上；过渡期内（E1 落地前）连接仍带 `model`，内部引擎模型为空时回退到连接的 model。
- **E4 — 投射输入 = 连接（endpoint + key + protocol）+ 绑定（模型）。** 为某 agent 激活/投射
  时，从连接读 endpoint/key/protocol，从该 agent 的绑定读模型。某 agent 无绑定则不投射。
- **E5 — 兼容性过滤 + 诚实兜底。** Agent 页只列出探测 `protocol` 与该 agent wire 匹配的连接；
  当连接 protocol 为 `unknown`（探测不确定）时，**对所有 agent 都显示、由用户决定**——Coffer 不
  静默隐藏一个可能可用的连接。
- **迁移（方案 A——丢弃）**：现有连接丢掉 `model` / `fast_model`；其 `wire_format` 重解释为探测
  `protocol`（或 `unknown` 待下次探测）。用户原先配的模型**不**带进绑定——升级后在 Agent 页重选。
  这是用户选定的「干净切断」，而非尽力迁移。

**Supersede：** 决策 A（「一条连接持有 … model、fast_model …」与「连接只投射到 wire_format 匹配的
agent」——现在由 agent 的 wire 驱动投射、连接的 protocol 只是探测出的兼容性提示）；amendment D2
（多协议集合——已废弃，见 ADR-032 D8：一网关供两 agent = 两条连接）。

**仍不在范围（不变）：** proxy / 热切换 / 协议转换。

## 范围

### 在范围内

- 后端 `provider` resource Kind（通过 ResourceService 实现 CRUD，自动审计 + 自动 sync）；凭证处理（将 secret 存入 Fernet vault，只保留 ref）；投影服务（将原生配置写入匹配 agent）；切换/激活操作；`PROVIDER_SWITCHED` 审计事件；sync 接入（注册 kind）；Claude `apiKeyHelper` 使用的密钥解析。
- 内部引擎 connection 选择：全局 `internal_default` 标志、`set_internal_default(name)` + `resolve_internal_connection()`、`provider_internal_default_set` 审计事件，供 Coffer 内部 LLM 引擎（memory organizer / reorg / distill / `coffer__ask`）消费。
- 退役独立的 `ModelConfig` 注册表（model CRUD REST + `coffer model` CLI），将内部引擎的模型选择折叠进 connection。provider 的 introspection 路由（`list-models`、`test-connection`）保留。
- CLI：`coffer provider list|add|show|edit|remove|switch|key|internal-default`
- HTTP API：`/api/v1/providers`（list / create / get / patch / delete）以及 `/api/v1/providers/{name}/activate` 和 `/api/v1/providers/{name}/internal-default`
- 前端：最简 Providers 资源页——`DataTable`（name、wire format、base URL、model、active），行操作包括 create / switch / delete，与 Skills 和 MCP 资源页保持一致。
- 跨层测试；acceptance 标记对应下方场景；本 spec bundle 每个文档都有中文版。

### 不在范围内（明确非目标）

- **Hot-switch / 进程内热重载**——延期到后续 PR。
- **显式停用 / 原生配置还原**——无"恢复默认"操作。
- **Provider drift-verify**——spec 条目 4.9，单独规范。
- **超出 wire 匹配的逐 agent provider 覆盖**——`wire_format` 不匹配的 profile 不投影到该 agent，无手动绑定。
- **代理 / 故障转移 / 格式转换**——不代理；无 fallback 链；不做 anthropic↔openai 协议转换。
- **将 `COFFER_PROVIDER_KEY` 自动注入 Coffer 启动的 Codex 进程**——与 hot-switch 一同延期。

## 实体——ProviderProfile（Kind = `"provider"`）

Resource `name` = profile 名称（在 kind 内唯一，经 `validate_name` 校验）。

### Config 字段（同步的 `config` 字典；确定性，不含机器本地 id）

| 字段 | 类型 | 说明 |
|---|---|---|
| `wire_format` | `"anthropic" \| "openai" \| "ollama"` | 必填。决定该 connection 投影到哪个 agent。`ollama` 仅供内部——不投影到任何 agent（`target_for` 返回 None）。 |
| `base_url` | `str` | 必填（所有 wire）。上游 LLM endpoint。 |
| `credential_ref` | `str \| None` | 可选。anthropic/openai 必填（Fernet vault ref；格式 `^[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)*$`；通常为 `provider/<name>/key`；多条 connection 可共用一个 ref）。ollama 必须不存在（无 API key）。 |
| `model` | `str` | 必填。主模型 ID → `ANTHROPIC_MODEL`（Claude）/ `model`（Codex）；当此为内部默认时，即 Coffer 内部引擎运行的模型。 |
| `fast_model` | `str \| None` | 可选。`ANTHROPIC_SMALL_FAST_MODEL`（仅 anthropic wire）；openai wire 忽略。 |
| `wire_api` | `"chat" \| "responses"` | 可选，默认 `"chat"`。仅 openai/Codex（`[model_providers.*].wire_api`）。 |
| `is_active` | `bool` | 每种 `wire_format` 最多一条活跃。ollama 从不投影，故 ollama connection 始终非活跃。导入时若某 wire 有多条活跃，则确定性归一化（保留最近更新的）。 |
| `internal_default` | `bool` | 全局最多一条 connection 为内部引擎默认。导入时若 >1，则归一化（保留最近更新的）。 |

- `audit_redactor`：config 中不含 secret（只有 `credential_ref`），审计可原样展示 config。需双重确认 `config` 或 `details` 中无 secret 泄露。

## 投影——写入原生配置

类比 `mcp_injection.py` 中的 `McpInjectionSpec`；以小型显式表格编码。

### anthropic → Claude Code

**文件**：`~/.claude/settings.json`（JSON）；通过 `spec_for(AgentType.CLAUDE_CODE, "settings", cfg_dir)` 解析路径。

Coffer 仅管理以下键，**合并**到现有 JSON（绝不全量替换），通过 `ConfigFileStore.write_text_atomic`（原子写 + `.bak` 备份）写入：

| 键路径 | 值 |
|---|---|
| `apiKeyHelper` | `"coffer provider key --wire anthropic"` |
| `env.ANTHROPIC_BASE_URL` | `profile.base_url` |
| `env.ANTHROPIC_MODEL` | `profile.model` |
| `env.ANTHROPIC_SMALL_FAST_MODEL` | `profile.fast_model`（为 `None` 时省略 / 删除该键） |

**绝不**写入 `ANTHROPIC_API_KEY`（否则会覆盖 helper）。其余所有内容保持原样；通过 `json.dumps(indent=2)` 序列化（与 `mcp_entries.py` 中的 MCP JSON 路径一致）。

### openai → Codex

**文件**：`~/.codex/config.toml`（TOML）；通过 `spec_for(AgentType.CODEX, "config", cfg_dir)` 解析路径。

Coffer 通过 `tomlkit`（保留注释 / 顺序，与 MCP TOML 路径一致）管理以下键：

| 键路径 | 值 |
|---|---|
| `model` | `profile.model` |
| `model_provider` | `"coffer"` |
| `[model_providers.coffer].name` | `"Coffer (<profile name>)"` |
| `[model_providers.coffer].base_url` | `profile.base_url` |
| `[model_providers.coffer].wire_api` | `profile.wire_api`（默认 `"chat"`） |
| `[model_providers.coffer].env_key` | `"COFFER_PROVIDER_KEY"` |

其余所有内容保持原样。

### ollama → （仅内部）

ollama connection 不投影到任何 agent 配置：`target_for(WireFormat.ollama)` 返回 `None`，故激活时不写任何原生配置，且该 connection 从不 `is_active`。它仅供 Coffer 内部引擎使用，当其为 `internal_default` 时通过 `resolve_internal_connection` 触达。

## 切换 / 激活操作

`POST /api/v1/providers/{name}/activate` / `coffer provider switch <name>`：

1. Profile 必须存在，否则返回 404。
2. 通过 `ResourceService.update_config` 逐一清除同 `wire_format` 下所有其他 profile 的 `is_active`，再通过第二次调用将目标 profile 的 `is_active` 设为 `true`。单进程 daemon 对请求串行化，切换操作不会交错。
3. 对所有已启用的已注册 agent——其 `AgentType` 原生 wire 与 `profile.wire_format` 匹配的——执行投影（写入原生配置）。若无匹配 agent，记录 active 但不投影，**不视为错误**（在 skipped 中报告）。
4. 发出值为 `"provider_switched"` 的审计事件，details：`{from: <prev_name|null>, to: <name>, wire_format, agents: [...projected...]}`。
5. 返回 `{activated: <name>, projected: [agent...], skipped: [agent...]}`。

注意：投影（`_project`）在激活标志翻转之前运行；原生配置写入失败会中止切换，注册表保持不变。

## 内部引擎（Coffer 自己的 LLM）

与按 agent 激活分开，全局 `internal_default` 标志（所有 connection 中 ≤1）选择 Coffer 自身内部 LLM 引擎使用的 connection——memory organizer、reorg、distill 和 `coffer__ask`。

- `set_internal_default(name)`：清除所有其他 connection 的 `internal_default`，再设置目标（顺序 clear-then-set，由单进程 daemon 串行化，保证全局单一内部默认不变量），并发出 `provider_internal_default_set` 审计事件。
- `resolve_internal_connection() -> ProviderConfig | None`：返回 `internal_default` connection 的 config，或在无 connection 被标记时返回 `None`。为 `None` 时，内部引擎（memory organizer / reorg / distill / `coffer__ask`）是干净的 no-op 而非报错。
- `build_chat_model(connection, ...)`：内部引擎根据解析出的 connection 构建其 chat model，按 `wire_format`（anthropic / openai / ollama）分派。这取代了已退役 `ModelConfig` 注册表的模型选择。

一条 connection 可以**同时**是 `is_active`（投影到其 wire 的 agent）和 `internal_default`（供内部使用）——一份密钥，两种用途。

## 密钥解析（apiKeyHelper + Codex 环境变量）

`coffer provider key --wire <wire_format>`：

1. 找到给定 wire format 的活跃 profile。
2. 读取 `credential_ref` → 通过 `EncryptedCredentialStore.get(ref)` 解密。
3. 将原始密钥打印到**仅 stdout**。**不得**记录该值到日志。

Claude Code 的 `apiKeyHelper` 调用此命令（`--wire anthropic`）。Codex 用户则需执行：
```bash
export COFFER_PROVIDER_KEY="$(coffer provider key --wire openai)"
```

## Sync（复用，几乎零引擎改动）

将 `provider` 建模为 ResourceService Kind 可自动同步：

- `SyncExporter` 列出所有 kind → 通过 `resource_to_doc` 将每行序列化为 `resources/provider/<name>.yaml`。
- `SyncImporter` 按 `(kind, name)` 进行 reconcile。
- 凭证已以 Fernet 密文形式同步至 `credentials/<ref>.enc`。

接入点：定义 Kind，添加 `wire_provider_kind(...)` 辅助函数（镜像 `surfaces/http/wiring.py` 中的 `wire_kb_kind`），在 `surfaces/http/app.py` 的 composition root 中注册到 `app.state.kinds`。无需新迁移，无需 SCHEMA_VERSION bump。

## 审计（复用）

`ResourceService` create / update 自动发出 `RESOURCE_*` 事件（kind-redacted config）。需在 `backend/coffer/domain/audit.py` 的 `AuditEventType` 中添加 `PROVIDER_SWITCHED = "provider_switched"`，并在切换操作中通过 `AuditService.record(AuditEventType.PROVIDER_SWITCHED.value, ref=ResourceRef(kind="provider", name=<name>), actor=..., details={...})` 发出。同样添加 `PROVIDER_INTERNAL_DEFAULT_SET = "provider_internal_default_set"`，并从 `set_internal_default` 发出。

## HTTP API

手写 OpenAPI；005 风格——不做 contract-test 门控，手动同步。完整规范见 [contracts/api.openapi.yaml](./contracts/api.openapi.yaml)。

- `GET  /api/v1/providers` → 列出所有 profile（`{ "providers": [ ProviderOut, ... ] }`）
- `POST /api/v1/providers` → 创建（见下方凭证来源规则）
- `GET  /api/v1/providers/{name}` → 获取单条 profile
- `PATCH /api/v1/providers/{name}` → 更新可变字段（`base_url`、`model`、`fast_model`、`wire_api`、`secret_value`）；`wire_format` 和 `credential_ref` 不可变；`secret_value` 可轮换存储的 secret
- `DELETE /api/v1/providers/{name}` → 删除；删除自有 secret 前通过 `find_credential_citations` 守卫
- `POST /api/v1/providers/{name}/activate` → 切换；返回 `{activated, projected:[agent...], skipped:[agent...]}`
- `POST /api/v1/providers/{name}/internal-default` → 设置内部引擎默认；返回更新后的 `ProviderOut`

`wire_format` 在请求和响应中接受 `anthropic`、`openai` 或 `ollama`。

**凭证来源规则**：对 anthropic/openai，创建时必须且只能提供 `secret_value`（存入 vault，仅保留 ref）或 `credential_ref`（复用现有）之一；两者都提供或都不提供均以 `422` 拒绝。对 `wire_format=ollama`，凭证是**可选**的——`secret_value` 与 `credential_ref` 均不提供（ollama connection 无密钥）。

`ProviderOut` 绝不含原始 secret；包含 `credential_ref`、`is_active` 和 `internal_default`。

## CLI

`coffer provider list|add|show|edit|remove|switch|key|internal-default`，支持 `--json`。

- `add`：提示输入 / 接受 secret（ollama connection 无密钥，跳过）。
- `key`：打印解析出的 secret（供 `apiKeyHelper` 使用）；需要 `--wire <wire_format>`；按该 wire 的活跃 profile 解析，不支持按名称解析。
- `internal-default <name>`：将一条 connection 标记为 Coffer 内部引擎默认（清除任何先前的）。

## 前端（最简）

- `frontend/src/lib/api/providers.ts`——手写客户端 + TS 类型（`types.ts` codegen 只覆盖 001 gateway spec；此处不期望生成类型）。
- 统一的 **Settings → LLM Connections** 页（路由 `/settings/llm-connections`）即 connection 库：一个 `DataTable`（复用共享组件；参见 SkillsPage / MCP 页），列 name / wire_format / base_url / model / active / internal，顶部操作 create，行操作 switch / set-internal-default / delete，外加 Embedding 卡片。该页只显示 connection（provider + model）信息——无 agent 名称、无 presets、无 modality 拆分。编辑 connection 通过 CLI（`coffer provider edit`）和 PATCH API 实现，桌面页不需要内联编辑功能。
- 逐 agent 的 connection + model 选择位于 **agent detail 页（Overview tab）**，按该 agent 的 wire 过滤，复用 activate API。LLM Connections 页不绑定 agent。
- 旧的 `/settings/models` 和 `/settings/providers` 路由重定向到 `/settings/llm-connections`。
- 新 hook 的测试需添加 `vi.mock`。

## Acceptance Scenarios

根据 `agents/sdd.md`，本节每个场景都必须有至少一个测试携带
`@pytest.mark.acceptance(spec="011-provider-switching", scenario="…")`（Python）
或 `acceptance("011-provider-switching", "…", …)`（TypeScript）标记。

### Scenario: create an anthropic provider profile with an inline secret

- **Given** 不存在名为 `my-provider` 的 provider，
- **When** 用户以 `wire_format="anthropic"`、`base_url`、`model` 和 `secret_value`（原始 API key）创建 profile，
- **Then** profile 以 `credential_ref` 为 `provider/my-provider/key` 持久化，原始 key 在 Fernet vault 中以该 ref 存储，`ProviderOut` 不含 secret 字段，并审计 `RESOURCE_CREATED`。

### Scenario: create a profile that reuses an existing credential ref

- **Given** ref 为 `shared/key` 的凭证已存在，
- **When** 用户提供 `credential_ref="shared/key"`（不含 `secret_value`）创建 profile，
- **Then** profile 以指向现有 ref 的方式持久化，不创建新 vault 条目，`ProviderOut` 中的 `credential_ref` 与所提供的一致。

### Scenario: reject a profile with an unknown wire format

- **Given** daemon 正在运行，
- **When** 用户尝试以 `wire_format="grpc"` 创建 profile，
- **Then** 请求以 `422 Unprocessable Entity` 被拒绝，不创建任何 profile 行。

### Scenario: reject a profile that supplies neither a secret nor a credential ref

- **Given** daemon 正在运行，
- **When** 用户尝试创建一条 **anthropic** connection（neither-rule 适用于 anthropic/openai；ollama 合法地两者都不提供），但既不提供 `secret_value` 也不提供 `credential_ref`，
- **Then** 请求以 `422 Unprocessable Entity` 被拒绝，不创建 profile 行或 vault 条目。

### Scenario: update a provider profile

- **Given** 某 provider profile 已存在，
- **When** 用户 patch `base_url` 和 `model`（不含 `secret_value`），
- **Then** 只更新这两个字段，`credential_ref` 不变，并审计 `RESOURCE_UPDATED`。

### Scenario: list provider profiles

- **Given** 已存在两条 provider profile（一条 anthropic，一条 openai），
- **When** 用户列出所有 provider，
- **Then** 两条均出现在 `ProviderOut[]` 中，均不含原始 secret，每条携带正确的 `is_active` 标志。

### Scenario: delete a provider profile cleans up its owned credential

- **Given** 某 profile 的 `credential_ref` 为 `provider/my-provider/key`（自有，无其他 profile 共用），
- **When** 用户删除该 profile，
- **Then** vault 中该 ref 的条目被删除，并审计 `RESOURCE_DELETED`。

### Scenario: activate an anthropic profile writes Claude Code settings

- **Given** 已注册 Claude Code agent，且存在一条 anthropic profile，
- **When** 用户激活该 profile，
- **Then** `~/.claude/settings.json` 包含 `apiKeyHelper`、`env.ANTHROPIC_BASE_URL`、`env.ANTHROPIC_MODEL`；若 `fast_model` 有值则 `env.ANTHROPIC_SMALL_FAST_MODEL` 存在；`ANTHROPIC_API_KEY` 缺失；profile 的 `is_active` 变为 `true`。

### Scenario: an agent's model binding drives the projected model

- **Given** 已注册 Claude Code agent 且带 per-agent 模型绑定（`model` + `fast_model`），并存在一条 anthropic 连接，
- **When** 用户激活该连接，
- **Then** 投射出的 `env.ANTHROPIC_MODEL` / `env.ANTHROPIC_SMALL_FAST_MODEL` 来自 **agent 的绑定**——模型在使用处、不在连接上（amendment 2026-06-22b E1/E3/E4）。未绑定的 agent 不写 model env，故运行在它自己的默认模型上。

### Scenario: activate an openai profile writes Codex config

- **Given** 已注册 Codex agent，且存在一条 openai profile，
- **When** 用户激活该 profile，
- **Then** `~/.codex/config.toml` 包含 `model`、`model_provider = "coffer"` 以及含 `base_url`、`wire_api`、`env_key = "COFFER_PROVIDER_KEY"` 的 `[model_providers.coffer]` 表；profile 的 `is_active` 变为 `true`。

### Scenario: activating a profile deactivates the previous active profile of the same wire format

- **Given** anthropic profile A 为活跃，anthropic profile B 存在，
- **When** 用户激活 profile B，
- **Then** profile B 变为活跃，profile A 变为非活跃（单进程 daemon 对 clear-then-set 串行化，切换操作不会交错）。

### Scenario: activate a profile whose wire matches no registered agent records active but projects nothing

- **Given** 无已注册的 Codex agent，且存在一条 openai profile，
- **When** 用户激活该 openai profile，
- **Then** profile 的 `is_active` 变为 `true`，不写入任何配置文件，响应中 `skipped: ["codex"]`（或 `projected` 为空）。

### Scenario: switching preserves unrelated native-config keys and writes a .bak backup

- **Given** `~/.claude/settings.json` 中含有 Coffer 不管理的键（如 `theme`、`mcpServers`），
- **When** 用户激活一条 anthropic profile，
- **Then** 这些键在更新后的文件中逐字节保留，写入前创建 `.bak` 备份，只有 Coffer 管理的键被修改。

### Scenario: a provider switch is recorded in the audit log

- **Given** 某 anthropic profile 被激活，
- **When** 用户查询审计日志，
- **Then** 出现一条 `provider_switched` 条目，含 details `{from, to, wire_format, agents}`、时间戳和操作者。

### Scenario: resolve the active provider key for the apiKeyHelper

- **Given** 某 anthropic profile 为活跃，其 secret 已存于 vault，
- **When** 执行 `coffer provider key --wire anthropic`，
- **Then** 原始 key 被打印到 stdout，vault key **不被**记录到日志。

### Scenario: a provider profile round-trips through sync export and import

- **Given** 存在一条含 credential ref 的 provider profile，
- **When** sync exporter 运行，随后在全新 DB 上运行 sync importer，
- **Then** profile 行以相同的 `config` 字段被还原，凭证密文出现在 `credentials/<ref>.enc`，sync workspace 明文中无 secret 暴露。

### Scenario: the command line covers create, list, and switch

- **Given** daemon 正在运行，
- **When** 用户从 CLI 运行 `coffer provider add`、`coffer provider list --json`、`coffer provider switch`，
- **Then** 每个操作与 HTTP API 效果相同，`list --json` 返回机器可读输出。

### Scenario: the Providers page lists profiles and can switch the active one

- **Given** Providers 页以两条 mock profile 渲染，
- **When** 用户点击非活跃 profile 的"Switch"行操作，
- **Then** activate mutation 以正确的 profile name 被调用，表格反映更新后的活跃状态（TypeScript acceptance 测试）。

### Scenario: create an ollama connection without a credential

- **Given** 不存在名为 `local-llm` 的 connection，
- **When** 用户以 `wire_format="ollama"`、`base_url`、`model`，且既不含 `secret_value` 也不含 `credential_ref` 创建 connection，
- **Then** connection 以 `credential_ref` 为 null 持久化，不创建 vault 条目，`ProviderOut` 显示 `internal_default=false`。

### Scenario: set a connection as the internal engine default

- **Given** 存在两条 connection，且无一为内部默认，
- **When** 用户将第二条设为内部默认，
- **Then** 其 `internal_default` 变为 true，另一条保持 false，并记下一条 `provider_internal_default_set` 审计条目。

### Scenario: setting a new internal default clears the previous one

- **Given** connection A 为内部默认，
- **When** 用户将 connection B 设为内部默认，
- **Then** B 的 `internal_default` 变为 true，A 的变为 false（全局单一内部默认不变量）。

### Scenario: choose the model the internal engine runs on

- **Given** 某条 connection 为内部默认，
- **When** 操作者在全局内部引擎配置上设置一个模型（`PUT
  /api/v1/internal-engine-config`），
- **Then** `GET /api/v1/internal-engine-config` 返回该模型，记下一条
  `internal_engine_model_set` 审计条目，且 `resolve_internal_connection()` 将所选
  模型覆盖到解析出的内部默认 connection 上（模型独立于 connection，见下方 amendment）。

### Scenario: test or fetch models with an inline unsaved secret

- **Given** 连接对话框已打开，尚未保存任何连接（也无对应 credential ref），
- **When** 用户输入明文 API key 并触发「测试连接」或「拉取模型」（`POST
  /models/test-connection` / `POST /models/list-models` 携带 `secret_value`、
  不含 `credential_ref`），
- **Then** introspection 服务将明文 key 直接传给 provider、不查 credential vault，
  探测成功，拉取到的模型填入可选下拉框（见 ADR-032 amendment D6）。

### Scenario: the chat model picker offers a fixed list without free-form entry

- **Given** 一个绑定到无覆盖连接的 agent 的会话，
- **When** 打开模型选择器，
- **Then** 它给出该 agent 内置模型的固定下拉（无自由输入「Custom…」项）；当有连接覆盖该 agent 时，
  下拉改为列出该连接 introspect 出的模型，绝不读连接存储的 `model` 字段（TypeScript 验收测试）。

## 需求

### 功能需求

**资源模型**

- **FR-001**：系统必须将每个托管 provider 注册为 kind 为 `provider` 的 Resource，标识符为 `provider:<name>`。
- **FR-002**：系统必须按 kind 专属 schema 校验 provider config（字段：`wire_format`、`base_url`、`credential_ref`、`model`、`fast_model?`、`wire_api?`、`is_active`）。
- **FR-003**：`ProviderOut` 绝不得含原始 secret。`credential_ref` 和 `is_active` 必须包含。

**凭证处理**

- **FR-004**：携带 `secret_value` 创建时，系统必须将原始 key 存入 Fernet vault 的 `provider/<name>/key`，只持久化 ref。`secret_value` 或 `credential_ref` 必须且只能提供一个；两者都有或都没有均以 `422` 拒绝。
- **FR-005**：`PATCH` 携带 `secret_value` 时，系统必须轮换存储的 secret（覆盖 vault 条目），不改变 ref。
- **FR-006**：删除时，若 profile 自有其 credential ref（无其他 profile 引用），系统必须通过 `find_credential_citations` 守卫删除 vault 条目。

**投影**

- **FR-007**：系统必须通过 `ConfigFileStore.write_text_atomic`（原子写 + `.bak`）将激活的 anthropic profile 投影到 `~/.claude/settings.json`，只合并指定键，其余内容保持原样。绝不写入 `ANTHROPIC_API_KEY`。
- **FR-008**：系统必须通过 `tomlkit`（保留注释/顺序）将激活的 openai profile 投影到 `~/.codex/config.toml`，只合并指定键，其余内容保持原样。
- **FR-009**：若 `fast_model` 为 `None`，`settings.json` 中的 `env.ANTHROPIC_SMALL_FAST_MODEL` 键必须省略或删除。
- **FR-010**：域层投影逻辑必须为纯函数（无 I/O）。`domain/provider/projection.py` 中的纯函数 `apply_anthropic_settings(...)` 和 `apply_codex_provider(...)` 直接返回新的原生配置文本；`ProviderService._project(...)` 调用这些函数并执行文件写入。

**单活跃不变量**

- **FR-011**：每种 `wire_format` 最多一条 `is_active=true` 的 profile。激活 profile 必须通过顺序的 `ResourceService.update_config` 调用清除同 wire 下所有其他 profile 的 `is_active`，然后将目标 profile 的 `is_active` 设为 `true`。单进程 daemon 对请求串行化，切换操作不会交错。导入时若某 wire 有多条活跃，则归一化处理：保留最近更新的，其余设为非活跃。

**切换操作**

- **FR-012**：`POST /api/v1/providers/{name}/activate` 必须应用 FR-011，然后投影到所有已启用的已注册 agent（其原生 wire 与 `wire_format` 匹配）。若无匹配 agent，记录活跃并返回非空 `skipped` 列表——不视为错误。
- **FR-013**：系统必须发出值为 `"provider_switched"` 的审计事件，details：`{from, to, wire_format, agents: [...projected...]}`。

**密钥解析**

- **FR-014**：`coffer provider key --wire <wire_format>` 必须找到该 wire 的活跃 profile，通过 `EncryptedCredentialStore.get(ref)` 解密，只打印到 stdout。原始 key 绝不记录到日志。不支持按 profile `<name>` 解析；仅接受 `--wire` 形式。

**Sync**

- **FR-015**：`provider` kind 必须注册到 `app.state.kinds`，使 `SyncExporter`/`SyncImporter` 自动处理。无需新迁移或 SCHEMA_VERSION bump。

**审计**

- **FR-016**：`PROVIDER_SWITCHED`（值 `"provider_switched"`）必须加入 `AuditEventType` 并在每次成功切换时携带 `{from, to, wire_format, agents}` 发出。`RESOURCE_CREATED`、`RESOURCE_UPDATED`、`RESOURCE_DELETED` 由 `ResourceService` 自动发出。

**界面**

- **FR-017**：创建、切换和删除操作必须可通过（a）REST API、（b）`coffer provider ...` CLI（含 `--json`）、（c）桌面 Providers 页面访问。编辑 profile（PATCH）仅通过 REST API 和 CLI（`coffer provider edit`）提供；桌面页不需要内联编辑功能。
- **FR-018**：CLI `key` 子命令必须支持 `--wire <wire_format>`（按该 wire 的活跃 profile 解析）。不支持位置参数 `<name>` 解析；仅接受 `--wire` 形式。

**内部引擎 connection**

- **FR-019**：`ollama` wire 仅供内部，不投影到任何 agent：`target_for(WireFormat.ollama)` 必须返回 `None`，ollama connection 从不 `is_active`，激活它不写任何原生配置。
- **FR-020**：`credential_ref` 必须可选——anthropic/openai 必填，ollama 不存在。创建时，既不提供 `secret_value` 也不提供 `credential_ref` 仅对 `wire_format=ollama` 合法；对 anthropic/openai，FR-004 的 exactly-one 规则不变。
- **FR-021**：全局最多一条 connection 的 `internal_default=true`。`set_internal_default` 必须先清除所有其他 connection 的 `internal_default`，再设置目标（顺序 clear-then-set，由单进程 daemon 串行化）。导入时若有 >1 内部默认，则归一化：保留最近更新的，清除其余。
- **FR-022**：`POST /api/v1/providers/{name}/internal-default` 必须将所命名的 connection 设为内部引擎默认（应用 FR-021），发出 `provider_internal_default_set` 审计事件，并返回更新后的 `ProviderOut`。
- **FR-023**：`resolve_internal_connection()` 必须返回 `internal_default` connection 的 `ProviderConfig`，或在无 connection 被标记时返回 `None`。为 `None` 时，内部引擎（memory organizer / reorg / distill / `coffer__ask`）必须是干净的 no-op 而非报错。
- **FR-024**：独立的 `ModelConfig` 注册表（model CRUD REST + `coffer model` CLI）必须退役。内部引擎必须通过 `build_chat_model(connection, ...)`（按 `wire_format` 分派）从内部默认 connection 构建其 chat model。provider introspection 路由（`POST /api/v1/models/list-models`、`/api/v1/models/test-connection`）必须保留。

## 成功标准

- **SC-001**：从全新安装开始，用户可以添加一条 anthropic provider profile，激活它，并通过一条 `coffer provider switch` 命令让 Claude Code 使用新 endpoint。
- **SC-002**：原始 key 不会出现在 `settings.json`、`config.toml` 或 sync workspace（`resources/provider/*.yaml`）中——在集成测试中通过自动扫描验证。
- **SC-003**：每个 Acceptance Scenario 都有至少一个 `acceptance(spec="011-provider-switching", scenario="…")` 标记的测试，`make verify-acceptance` 报告零遗漏场景。
- **SC-004**：`make verify` 本地和 CI 通过。
- **SC-005**：激活 profile 只写入定义的托管键集，不触碰任何托管集以外的键。
- **SC-006**：当配置了 `internal_default` connection 时，Coffer 内部引擎（memory organize / reorg / distill / `coffer__ask`）在其上运行；当无 connection 被标记 `internal_default` 时，内部引擎是干净的 no-op。

## 假设

- Spec 004-agent-registry（PR #25）已合并；`AgentType`、`AgentConfig`、agent CRUD 和 `on_delete` hook 均可用。
- `EncryptedCredentialStore`（Fernet vault）和 `ConfigFileStore.write_text_atomic` 均可用（spec 001）。
- `tomlkit` 已在后端 Python 依赖中（MCP TOML 路径支持时已添加）。
- Coffer 作为单用户个人工具运行；除现有 `X-Coffer-Token` 门控外，无需多用户访问控制。
- 用户的 `~/.claude/settings.json` 和 `~/.codex/config.toml` 对 Coffer 可写。若文件不存在，Coffer 创建只含托管键的文件。
- Provider drift-verify（检查原生配置是否与活跃 profile 一致）延期到 spec 4.9。
