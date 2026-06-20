# 功能规格：MCP Gateway

> English: [spec.md](./spec.md)

**Feature Branch**: `feature/mcp-gateway`
**Created**: 2026-05-20
**Status**: Accepted
**Scope note**: 本 spec 覆盖后端层——daemon、MCP 网关 (gateway)、REST API 以及 `coffer` CLI。
**Input**: 用户描述: "Coffer's first feature — an MCP server gateway. Like mcpjungle / metamcp: one MCP client (Claude Code / Codex) connects to coffer; coffer aggregates many upstream MCP servers and re-exposes their tools, resources, and prompts as a single namespaced surface. Coffer will later manage other resource kinds (skills, memory, channels, agents) — design the first feature on top of a generic Resource framework so follow-on kinds plug in cleanly."

## User Scenarios & Testing

### User Story 1 — Aggregate multiple MCP servers in one client (Priority: P1)

某位开发者使用某个 MCP 客户端（例如 Claude Code 或 Codex），希望把若干 MCP 服务器（filesystem、GitHub、Postgres……）接入其中。与其每次列表变动都去编辑各客户端的 MCP 配置并重启，不如**只在 coffer 中注册一次**上游服务器 (upstream server)，然后让每个客户端都指向 coffer 提供的同一个 shim。所有上游的工具 (tool)、资源 (resource) 和提示词 (prompt) 都会在各个客户端中以带命名空间的方式出现，互不冲突。

**Why this priority**: 这是整个 spec 的核心。其余一切都是建立在这之上的杠杆。没有它，coffer 就称不上是一个 MCP 网关。

**Independent Test**: 安装 coffer（暂时没有其他界面），通过命令行注册两个真实的上游 MCP 服务器，把其中一个 MCP 客户端配置为使用 coffer 的 shim，重启客户端，观察两台服务器的工具均以 `<server>__<tool>` 名称出现，调用一个工具，验证返回结果。

**Covering scenarios**（完整 Given/When/Then 见下方 `## Acceptance Scenarios`）:

- register a stdio MCP server
- register an HTTP MCP server
- aggregate tools across servers in one client
- route a tool call to the correct upstream
- resources forward through the gateway
- prompts forward through the gateway
- upstream tool list changes mid-session

---

### User Story 2 — Curate which capabilities are exposed (Priority: P1)

开发者并不希望把每一个上游工具都暴露给 AI。有些工具是危险的（force-push、drop-table），有些在两台服务器上重复，有些只是当下不想用。他们需要按工具、按资源、按提示词的开关，并且这些设置要能跨 daemon 重启和上游升级保留下来。

**Why this priority**: 没有筛选 (curation)，聚合反而比不装网关还糟。"装了 30 台服务器仍然好用"这件事是靠 curation 撑起来的。

**Independent Test**: 注册一台有多个工具的服务器，禁用其中一个工具，重启 MCP 客户端，观察被禁用的工具消失；再重新启用，确认它回来。

**Covering scenarios**:

- disable an individual capability
- capability preferences survive upstream changes
- new capabilities default per server policy

---

### User Story 3 — Same operations from the command line (Priority: P2)

开发者会在终端中编写脚本来批量操作——从 dotfile 添加服务器、在 CI 里自动启用/禁用等。

**Why this priority**: Coffer 的目标用户是开发者。完整的 CLI 是脚本化工作流和远程机器的最低标配。

**Independent Test**: 在一个全新安装上，通过终端完整完成注册两台服务器、切换若干工具、查看 audit / invocation 日志——全程不需要 GUI。

**Covering scenarios**:

- command line covers every visual operation
- command line surfaces same errors

---

### User Story 4 — Auditing & activity logs with retention controls (Priority: P3)

开发者想知道发生了什么——什么时候添加了服务器、什么时候禁用了工具、哪些工具在什么时候被调用了——同时不希望日志无限膨胀。

**Why this priority**: 信任和调试都离不开它，但它不是网关基本运行的阻塞项。默认的保留期 (retention) 对大多数用户而言已足够合理，无需调整。

**Independent Test**: 做几次更改后查看 audit；运行几次工具调用后查看 invocation；把某个日志的保留期改短，等下次清理执行，确认更早的条目已被删除，较新的还在。

**Covering scenarios**:

- audit lifecycle changes
- invocation log records calls without arguments
- configure retention per log

---

### User Story 5 — Find the right tool under aggregation overload (Priority: P2)

当开发者注册了许多上游服务器后，聚合后的工具面可能超过 150 个工具。一个 coding agent 的工具选择准确率会在约 30–50 个工具之后急剧下降，因此把整份目录塞进每一次请求既浪费上下文 token，又让 agent 选错。开发者希望 agent 能在实时聚合目录中**搜索**出与当前意图匹配的少数几个工具并直接调用它们，而不是在整张列表上推理。

**Why this priority**: 只有当 agent 在规模化后仍能选得好，聚合才有意义；这把「装了 30 台服务器」从负担重新变回杠杆。它建立在核心网关（User Story 1）之上，不改变任何上游工具的暴露或调用方式。

**Independent Test**: 注册足够多的服务器使聚合目录变大，然后从一个 MCP 客户端用一个意图查询和一个 `top_k` 调用 `coffer__search_tools`；观察返回最多 `top_k` 个排序后的上游工具 schema，agent 用其 `<server>__<tool>` 名称调用其中之一，且该调用照常路由到对应上游。

**Covering scenarios**:

- search the aggregated catalogue for matching tools

具体行为与理据记录在 [ADR-018](../../docs/decisions/ADR-018-tool-retrieval-for-overload.zh.md)。

#### `coffer__search_tools` —— 内置的工具检索

`coffer__search_tools` 是 Coffer 的内置工具，始终与 Coffer 的其他 `coffer__` 内置工具一起在 `tools/list` 中通告。它通过对**实时**聚合的上游目录按意图查询排序、返回 top-k 个**真实**的上游工具 schema 来缓解聚合带来的工具过载，agent 随后直接调用它们。它是一个检索原语 (retrieval primitive)——它返回 schema，**不会**代替 agent 去选择并调用。

契约 (Contract):

```
coffer__search_tools(query: string [required], top_k?: int = 5, max 20)
  -> { tools: [{ name, description, inputSchema, score }], total_searched: N }
```

- 排序是一个纯粹、确定、本地的关键词排序器（在每个工具的 name + description 上做 BM25-lite，name token 权重更高）。无 LLM、无 embedding、无网络。
- 结果**仅含上游**：Coffer 自己的 `coffer__` 内置工具被排除，因为它们不是过载的来源。
- 返回的每个 `name` 就是 agent 会直接调用的 `<server>__<tool>` 带命名空间标识符；路由不变。
- 这次调用像任何其他网关调用一样被记入 invocation 日志。

---

### Edge Cases

下列情况由集成测试覆盖，不参与 acceptance 审计；除非被「提升」到下文的 `## Acceptance Scenarios`（目前已提升的：tool-name collision、daemon port conflict）。

- **Upstream unreachable on register**: 注册必须成功（配置已保存）；发现 (discovery) 和健康检查会报错；该服务器在重新可达前被标为 unhealthy，且不会出现重试风暴。
- **Upstream crashes mid-call**: 正在进行的调用返回错误；该服务器被标为 unhealthy；后续调用会以有界重试 (bounded retries) 重新拉起上游；用户能在 invocation 日志中看到这次失败。
- **Credential missing or master key unavailable**: 注册失败，错误消息会指出缺失的凭据 (credential) 并指引用户去配置凭据的位置。不会留下任何部分写入的状态。（若存在密文但无法解析主密钥，daemon 会以 `MasterKeyMissing` 拒绝启动，而非悄然丢失访问。）
- **Duplicate registration**: 同一 kind 下注册重名的服务器会被拒绝并给出明确错误；不可能产生部分写入。
- **Tool-name collision across servers**: 通过 `<server>__<tool>` 命名空间阻止；客户端永远看不到冲突。
- **Tools-only upstream**: 只实现 `tools`、对 `resources/list` 或 `prompts/list` 返回 JSON-RPC `-32601`（METHOD_NOT_FOUND）的上游，被视为没有 resources / 没有 prompts。单服务器能力视图与聚合列表会返回该服务器的 tools，并将 resources/prompts 置为空集（HTTP 200），而不是报错——因此对于仅支持 tools 的服务器，管理端 / Web-UI 的能力视图依然可用。
- **Daemon port conflict**: daemon 默认端口被占用时，会在一小段范围内挑选下一个空闲端口，把所选端口写入它的 discovery 文件；shim、桌面端、CLI 都会读这个文件。
- **Daemon crash**: 正在运行的 shim 会话会给它们的 MCP 客户端返回干净的错误而不是挂起；监管者 (supervisor) 可以检测崩溃并重启 daemon。
- **Concurrent clients**: 多个 MCP 客户端（例如 Claude Code 和 Codex 同时）可同时连接而互不干扰；每个客户端都拿到独立的上游子进程集合。

## Acceptance Scenarios

按 `agents/sdd.md` 与 `agents/testing.md` 的要求，本节中的每个 scenario 至少被一个标记为 `@pytest.mark.acceptance(spec="001-mcp-gateway", scenario="…")`（Python）或 `acceptance("001-mcp-gateway", "…", …)`（TypeScript）的测试引用。覆盖率由 `make verify-acceptance` 审计。

### Scenario: register a stdio MCP server

- **Given** coffer daemon 已运行且尚未注册任何 MCP 服务器,
- **When** 用户用唯一的名称、命令和参数注册一个 stdio MCP 服务器,
- **Then** 该服务器被持久化、能力 (capability) 被发现，并在服务器列表中显示为 healthy。

### Scenario: register an HTTP MCP server

- **Given** coffer daemon 已运行,
- **When** 用户用 URL 和（可选的）授权头所需的凭据引用注册一个 HTTP MCP 服务器,
- **Then** 该服务器被持久化、能力被发现，且凭据值不会泄露到任何日志或存储字段中。

### Scenario: HTTP-transport MCP server round trip

- **Given** 一台 HTTP MCP 服务器正在运行并已在 coffer 中注册,
- **When** 一个 shim 客户端通过 coffer 的聚合端点列出工具并调用其中之一,
- **Then** 两次请求都在 HTTP 传输上端到端成功，返回合法的 MCP 响应。

### Scenario: aggregate tools across servers in one client

- **Given** 已注册两台 MCP 服务器且均 healthy,
- **When** 一个 MCP 客户端通过 coffer 的 shim 接入并列出工具,
- **Then** 每台已注册服务器上启用的所有工具都会出现，命名为 `<server>__<tool>`，且任意两个工具都不冲突。

### Scenario: route a tool call to the correct upstream

- **Given** 客户端已拿到聚合的工具列表,
- **When** 客户端调用一个带前缀的工具,
- **Then** coffer 把请求转发给对应的上游，并使用上游原始（不带前缀）的名称，再把上游的返回结果原样回传。

### Scenario: resources forward through the gateway

- **Given** 一台上游服务器暴露了资源（不止工具）,
- **When** 客户端通过 coffer URI 读取一个资源,
- **Then** coffer 把读请求路由到对应上游，URI 在向上游一侧被改写回原始形式，并原样回传上游的载荷。

### Scenario: prompts forward through the gateway

- **Given** 一台上游服务器暴露了提示词（不止工具）,
- **When** 客户端用 `<server>__<prompt>` 形式的带前缀名称调用一个提示词,
- **Then** coffer 把请求路由到对应上游并使用上游原始（不带前缀）的提示词名，再把上游的返回结果原样回传。

### Scenario: upstream tool list changes mid-session

- **Given** 一个客户端已连接，且一台上游 MCP 服务器的工具列表发生变化（升级、插件热加载）,
- **When** 上游发出 list-changed 通知,
- **Then** coffer 把该通知转发给所有订阅了该上游的客户端会话，客户端据此重新拉取列表；coffer 缓存的能力 (capability) 会在下一次 list 时刷新。

### Scenario: concurrent clients

- **Given** 两个 MCP 客户端同时接入,
- **When** 它们各自 list 并调用工具,
- **Then** 两边都成功且互不干扰；每个客户端都拿到一份独立的上游子进程集合（通过统计 `~/.coffer/upstream-pids/` 下的条目数验证）。

### Scenario: upstream crash recovery

- **Given** 一台上游 MCP 服务器在会话中途崩溃,
- **When** 客户端在崩溃后再调用一个工具,
- **Then** 网关会重新拉起上游，调用最终成功返回。

### Scenario: disable an individual capability

- **Given** 一台已注册的 MCP 服务器暴露了多个工具,
- **When** 用户禁用其中一个工具,
- **Then** 任意客户端后续的工具列表请求都不再包含它，且尝试调用它会返回 tool-disabled 错误。

### Scenario: disabled capability rejected through the shim

- **Given** 一台已注册的 MCP 服务器有两个工具，其中一个已通过 REST API 禁用,
- **When** 一个 shim 客户端调用 `tools/list`，再对被禁用的工具调用 `tools/call`,
- **Then** `tools/list` 不会列出被禁用的工具但会列出启用的那个；`tools/call` 返回一个 code 为 -32000（TOOL_DISABLED）的 JSON-RPC 错误，而不是成功结果。

### Scenario: capability preferences survive upstream changes

- **Given** 用户禁用了某服务器上的某个工具,
- **When** 该上游服务器升级导致该工具 schema 改变（或短暂消失再出现）,
- **Then** 用户的禁用状态被保留，无需手动重新配置。

### Scenario: new capabilities default per server policy

- **Given** 服务器被配置为自动启用新能力（默认）或不自动启用,
- **When** 升级在该服务器上新增了一个工具,
- **Then** 该新工具按该服务器的策略被启用或禁用，并在 audit 日志中留下记录。

### Scenario: command line covers every visual operation

- **Given** daemon 正在运行,
- **When** 用户调用对应的 `coffer mcp …` / `coffer resource …` / `coffer audit …` / `coffer retention …` 子命令,
- **Then** 效果与对应的管理操作完全一致，且可输出机器可读的 JSON 供脚本使用。

### Scenario: command line surfaces same errors

- **Given** 管理 API 抛出任何错误,
- **When** 通过命令行触发它,
- **Then** 用户看到可执行的提示信息和非零退出码；`--verbose` 显示完整 traceback。

### Scenario: audit lifecycle changes

- **Given** 用户对服务器或能力做了任何 add / enable / disable / update / delete 操作,
- **When** 他们打开 audit 视图（CLI 或 UI）,
- **Then** 每次变更对应一行记录，包含 actor、时间戳，以及描述变更内容的载荷。

### Scenario: invocation log records calls without arguments

- **Given** 某 MCP 客户端调用过工具,
- **When** 用户查看 invocation 日志,
- **Then** 每次调用都在其中，含时间戳、目标能力、耗时和结果，**但调用参数和返回内容都不会被存储**。

### Scenario: configure retention per log

- **Given** audit 与 invocation 日志随时间持续增长,
- **When** 用户为某个日志设置保留期（天数，或 "keep forever"）,
- **Then** 早于该保留期的条目会在下一次周期性清理中被删除，且这次设置变更本身也会被审计。

### Scenario: search the aggregated catalogue for matching tools

- **Given** 有 N 个上游工具通过 coffer 聚合并 healthy,
- **When** 一个 agent 用一个意图查询和一个 `top_k` 调用 `coffer__search_tools`,
- **Then** 它收到最多 `top_k` 个排序后的真实上游工具 schema（仅含上游，排除 Coffer 自己的 `coffer__` 内置工具），每个命名为 `<server>__<tool>`，响应中带有 `total_searched`，且网关记录这次 invocation。

### Scenario: CLI returns non-zero exit on daemon unreachable

- **Given** daemon 未运行,
- **When** 执行 `coffer mcp list`,
- **Then** 进程以退出码 3 退出，且 stderr 明确指出 daemon-unreachable 这一情况。

### Scenario: CLI --json output is machine-readable

- **Given** `coffer mcp list` 或 `coffer mcp invocations` 支持 `--json`,
- **When** 用 `--json` 调用,
- **Then** stdout 是可解析的 JSON 文档，顶层有稳定的 key（`list` → `resources`；`invocations` → `invocations`），不掺杂任何面向人类的格式。

### Scenario: store and reference a credential

- **Given** 用户尚未存入 HTTP 凭据,
- **When** 用户通过 `POST /api/v1/credentials`（或等价 CLI）在请求体里带上 `ref` 与 secret `value` 写入一个 secret，再注册一台 HTTP MCP 服务器，其 `credential_refs` 引用 `{ref}`,
- **Then** 凭据值只以 Fernet 密文形式写入 `credentials` 表（其明文永不进入 SQLite 数据库、任何日志或审计），服务器注册成功，凭据在拉起上游时按需解析（解密）。

### Scenario: delete a credential frees the reference

- **Given** 凭据 `{ref}` 存在，且无任何 MCP 服务器引用它,
- **When** 用户通过 `DELETE /api/v1/credentials/{ref}`（或等价 CLI）删除它,
- **Then** 密文行被移除，删除操作被审计，后续注册可在不冲突的情况下重新使用 `{ref}`。

### Scenario: daemon status reflects ready state

- **Given** daemon 刚刚启动,
- **When** 调用 `GET /api/v1/daemon/status`,
- **Then** 响应中 `status: "ready"`、`port` 非零、`started_at` 为时间戳；同样的值也写入 `~/.coffer/daemon.json`。

### Scenario: rotating the daemon token invalidates the previous one

- **Given** daemon 已发出过认证 token,
- **When** 用户触发 token 轮换操作,
- **Then** 用旧 token 的管理 API 调用返回 401，用新 token 调用成功，且这次轮换被记为 `token_rotated` 类型的 audit 条目。

### Scenario: vault backup captures db + file trees, restore round-trips them

- **Given** `~/.coffer/` 下有一个已填充的 vault——`coffer.db` 加上作为事实源的 markdown 文件树（`knowledge/`、`memory/`、`skills/`）,
- **When** 用户运行 `coffer backup <dest>`，之后再 `coffer restore <dest>` 到一个全新的 vault,
- **Then** 目标目录包含 `coffer.db` 与每一棵文件树；恢复会把它们全部重新放回，使得一个样例 KB 文档与一个样例 memory fact 逐字节往返一致，且恢复后的 `coffer.db` 是这些文件树的一份一致索引。

### Scenario: backup excludes the master key by default

- **Given** vault 中存有解密 `coffer.db` 内凭据密文的 Fernet `master.key`,
- **When** 用户在不带 `--include-master-key` 的情况下运行 `coffer backup <dest>`,
- **Then** `master.key` 不会被写入备份（因此备份可以放心 copy 出机器），命令会提示已存储的凭据需要该 key 才能解密；传入 `--include-master-key` 会在打印明确警告后才把 key 一并打包。

### Scenario: gateway overhead stays under budget

- **Given** 一个既能通过 coffer 也能直连的进程内快工具,
- **When** 同一工具通过 coffer 调用 100 次、直连调用 100 次,
- **Then** 每次调用的网关额外开销（coffer 时延减直连时延）中位数 ≤ 50 ms。

### Scenario: credentials never leak to logs or audit

- **Given** 一台注册了凭据引用的 MCP 服务器,
- **When** 该服务器在一次代表性会话中被拉起、被调用、再被释放,
- **Then** 自动扫描每一行数据库记录、每一条审计、每一条 invocation 记录以及 `~/.coffer/logs/` 下的全部日志文件，凭据字面值零出现。

### Scenario: tool-name collision across servers is prevented

- **Given** 两台已注册的 MCP 服务器暴露了同名工具（例如都叫 `search`）,
- **When** MCP 客户端通过 coffer 列出工具,
- **Then** 客户端看到的是 `<server-a>__search` 与 `<server-b>__search`，互不冲突——不会出现任何未前缀的上游原始名。

### Scenario: daemon port conflict falls back to the next free port

- **Given** daemon 默认端口已被另一个进程占用,
- **When** daemon 启动,
- **Then** 它在支持的端口范围内选择下一个空闲端口，把所选端口写入 `~/.coffer/daemon.json`，并使每个 Coffer 入口（shim、CLI）都无需手动配置就连上该端口。

## Requirements

### Functional Requirements

**Gateway behavior**

- **FR-001**: System MUST 把 coffer 以单一 MCP 服务器的形象呈现给客户端，同时提供 HTTP/SSE 端点和 stdio shim 入口。
- **FR-002**: System MUST 在客户端与上游 MCP 服务器之间转发 MCP 的 `tools`、`resources`、`prompts` 能力 (list、call/read/get，以及 list-changed 通知)。
- **FR-003**: System MUST 给每个上游能力加上其服务器名前缀 (工具和提示词用 `<server>__<tool>`；资源用带服务器前缀的 URI scheme)，使不同服务器的能力不会冲突。
- **FR-004**: System MUST 把客户端对带前缀能力的调用路由到原始上游，并使用上游原始（不带前缀）的标识符。

**Resource lifecycle**

- **FR-005**: Users MUST 能够把 MCP 服务器作为 resource 进行注册、列出、查看、更新、启用、禁用和删除，标识符形如 `<kind>:<name>`。
- **FR-006**: System MUST 用 kind 对应的 schema 校验每一次注册，拒绝同 kind 内重名，校验失败时不持久化任何内容。
- **FR-007**: System MUST 同时支持 stdio 与 HTTP 两种上游 MCP 传输方式。

**Capability curation**

- **FR-008**: Users MUST 能在每台服务器上分别启用或禁用单个的 tool、resource 和 prompt。
- **FR-009**: System MUST 在 daemon 重启、上游升级、上游临时消失等情况下保留用户的启用/禁用决定。
- **FR-010**: System MUST 在发现一个先前未见过的能力时，按每服务器的 "auto-enable new capabilities" 策略（默认为 true）处理。

**Credentials and safety**

- **FR-011**: System MUST 仅把上游服务器的凭据以 Fernet 密文形式存储在 `credentials` 表中（envelope 加密），配置中按名称引用；凭据明文 MUST NOT 写入数据库、任何日志或审计。Fernet 主密钥 MUST 仅由 `infrastructure/credentials/` 管理——默认为 DB 旁的 `0600` 文件，opt-in 时存于操作系统钥匙串。管理 API MUST 提供 credential 端点，使 UI 能管理一个 secret 而其明文不落入任何持久化配置：写入（`POST /api/v1/credentials`）、删除（`DELETE /api/v1/credentials/{ref}`）、存在性检查（`GET /api/v1/credentials/{ref}/exists`）以及一个带审计的读取（`GET /api/v1/credentials/{ref}`）。读取端点返回 secret 值并发出一条 `credential_read` 审计事件，使每次 secret 读取都被记录。
- **FR-012**: System MUST 将所有 HTTP 端点（管理 API 和 MCP 协议端点）仅绑定到 loopback 接口。
- **FR-013**: System MUST 要求每一次管理 API 调用携带认证 token；token 在 daemon 启动时本地生成，以 user-only 文件权限存储，并可轮换。

**审计与活动日志**

- **FR-014**: System MUST 对任何 resource 或 capability 的生命周期变更记录一条 audit 条目，包含 actor (CLI / API / UI / system)。
- **FR-015**: System MUST 对每一次 tool 调用、resource 读取、prompt 获取记录一条 invocation 条目——但不记录参数和返回内容。
- **FR-016**: System MUST 为 audit 与 invocation 日志提供按表的保留期配置（天数，或 "keep forever"），并提供周期性后台清理来删除过期条目。

**Surfaces**

- **FR-017**: Users MUST 能通过 (a) REST API 与 (b) `coffer` 命令行界面两条路径，完成所有管理操作；两者共享同一 daemon，并采用一致的错误模型。

**Distribution**

- **FR-018**: 从源码安装（`pip install ./backend`）MUST 把 `coffer` CLI 与 `coffer-mcp-shim` stdio 入口作为 console script 装到用户的 `PATH` 上，使 daemon 与 shim 无需额外部署步骤即可使用。

### Key Entities

- **Resource**: coffer 内由用户管理的实体，按 `(kind, name)` 标识。本 spec 注册一个 kind: `mcp_server`。每个 resource 携带 kind 特定的配置、enabled 标记、描述以及时间戳。框架本身是 kind-agnostic 的，后续 spec 可在不重新建模的前提下加入新 kind。
- **MCP Server** (kind 为 `mcp_server` 的 resource): 一台上游 MCP 服务器的配置——传输方式（stdio 命令行 或 HTTP URL）、凭据引用，以及每服务器的策略 (auto-enable, timeouts)。
- **Capability**: MCP 服务器暴露的一个 tool、resource 或 prompt。由上游实时发现；仅持久化用户的启用/禁用偏好以及 last-seen 时间戳。
- **Audit Event**: 任意 resource 或 capability 的生命周期变更记录。包含 actor、target、event type、时间戳和结构化载荷。
- **Invocation Record**: 通过网关进行的一次能力调用记录。包含 target、时间戳、耗时和结果——不含参数和返回内容。
- **Retention Policy**: 控制某日志表保留时长的按表设置。audit 默认 365 天，invocation 默认 30 天；两者都可设为 "keep forever"。

## Success Criteria

### Measurable Outcomes

- **SC-001**: 从源码全新安装起，用户能在 5 分钟内注册第一台 MCP 服务器并在 MCP 客户端中用上它，期间查文档不超过一次。
- **SC-002**: 注册了三台上游 MCP 服务器后，通过 coffer shim 连接的 MCP 客户端在一次 tool-list 请求中能列出所有启用的能力，零命名冲突。
- **SC-003**: 通过 coffer 路由的工具调用相比客户端直连上游，单次额外开销不超过 50 ms，按 100 次快速进程内工具调用衡量。
- **SC-004**: 两个 MCP 客户端（例如 Claude Code 与 Codex）同时连接时，在 30 分钟的交互会话中都能成功 discover 并调用工具，互不干扰。
- **SC-005**: 禁用某工具后，任何客户端的下一次 tool-list 响应都不再包含它，对它的任何 in-flight 调用都会被以 tool-disabled 错误拒绝。
- **SC-006**: 超出配置保留期的 audit 与 invocation 日志会被周期性清理删除，更新的条目保留；清理过程不阻塞并发 API 调用。
- **SC-007**: 本文档中的每一条 Acceptance Scenario 至少被一个带 `acceptance(spec="001-mcp-gateway", scenario="…")` 标记的测试覆盖，`make verify-acceptance` 报告零未覆盖 scenario。
- **SC-008**: `make verify`（lint + unit + integration + contract + acceptance audit）在本地与 CI 上均通过；`make verify-all`（增加 e2e）在 macOS 本地与 Linux CI 上均通过。
- **SC-009**: 从源码安装（`pip install ./backend`，需 Python 3.12+）后，`coffer` 与 `coffer-mcp-shim` 均在用户的 `PATH` 上可用，且 daemon 在 `pip install` 之外无任何手工步骤即可到达 "ready" 状态。
- **SC-010**: 任何上游服务器凭据值都不应出现在任何数据库表、日志文件、audit 条目或 invocation 记录里——以一次代表性会话之后对这些产物的自动扫描验证。

## Assumptions

- 单一用户在自己机器上运行 coffer。不存在多租户或远程访问需求。
- MCP 客户端（Claude Code、Codex 等）至少支持 `stdio` 或 `http`/`sse` 中的一种 MCP 服务器配置；coffer 两种入口都提供。
- 上游 MCP 服务器遵循公开的 MCP 协议规范。行为异常的上游被作为故障处理，而不是建模为正式特性。
- Fernet 主密钥在 coffer 启动时可解析（默认为可读的 `~/.coffer/master.key`，钥匙串模式下则是已解锁的操作系统钥匙串）；如不可用，用户会看到明确提示（存在密文但无可解析密钥是致命的 `MasterKeyMissing` 启动错误）。
- 本 spec 只引入一个 resource kind（`mcp_server`）。Resource 框架的设计允许后续 spec 在不重新建模现有数据的前提下加入更多 kind。
- 并发 MCP 客户端负载较小（低个位数）；coffer 不是 fleet 规模的网关。
