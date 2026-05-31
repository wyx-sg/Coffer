# 功能规范：Built-in Agent & Chat

> English: [spec.md](./spec.md)

**Feature Branch**: `feature/008-builtin-agent-chat`
**Created**: 2026-06-01
**Status**: Draft
**Input**: 用户描述：「Coffer 的第八个 feature —— 给 Coffer 自己一个内置 agent 和一个 chat 界面。在此之前 Coffer 只是通过存储配置来*管理*外部 agent（claude_code / codex），它自己从不跑 LLM。这个 feature 加上 (a) 一个内置 agent —— 一个真正的 LLM 循环，引擎用 LangGraph 以便任意主流模型都能跑，接到 Coffer 自己的 MCP 网关上，于是它能用 vault 管理的每一个 MCP server / skill / knowledge base / memory；以及 (b) 一个 chat 界面，用户可以在其中跟内置 agent 对话，或者跟一个由 Coffer 管理、并由 Coffer 作为本地无头子进程驱动的外部 agent（claude_code、codex）对话。会话与消息在本地持久化。streaming 是实时的。敏感工具调用可以暂停下来等人在环（human-in-the-loop）确认，会话还会自动生成标题。另一份规范（009）将把外部消息渠道桥接到这个 chat。基于与 kind 无关的 Resource 框架（001）构建；内置 agent 是它自己独立、增量的 `builtin_agent` resource kind，chat 的目标把它与外部 `agent` kind（004）取并集。」

## 用户场景与测试

### User Story 1 — Chat with Coffer's built-in agent（优先级 P1）

开发者打开 Coffer 的 chat 界面，针对内置 agent（「Coffer」）开一个新会话，问一个需要用到 vault 的问题 —— 例如「搜一下我的 memory 看我喜欢分支怎么命名，然后列出我注册过的 MCP server」。内置 agent（一个 LangGraph 循环）推理、调用 Coffer 自己的网关工具，再把答案逐 token 流式吐回来。会话和每一条消息都持久化，所以以后重新打开它能看到完整历史。

**为什么是这个优先级**：这是本规范的核心 —— Coffer 拥有自己的 agent，把 vault 管理的一切都吃自己的狗粮（dogfood）。没有它就没有任何可对话的对象。

**独立可测**：从一份配好了 LLM provider key 的全新安装开始，给已 seed 好的内置 agent 发一条消息，观察到一段流式的 assistant 回复，其中至少调用了一个 `coffer__*` 网关工具；重启 daemon，重新打开会话，看到消息历史完好无损。

**代表性场景**：

- a built-in agent is seeded on first startup
- chat with the built-in agent streams a reply
- the built-in agent can call Coffer gateway tools
- conversation and messages persist across daemon restarts

---

### User Story 2 — Chat with a Coffer-managed external agent（优先级 P1）

开发者已经把 `claude_code`（和/或 `codex`）作为 agent 注册进了 Coffer。在 chat 界面里他选这个 agent 作为会话目标并发消息。Coffer 在本地以无头 streaming 模式拉起该 agent 的 CLI，转发消息，并把 agent 的输出流式吐回同一个 chat UI。因为 Coffer 已经把它的 MCP 网关装进了那个 agent 的配置里，所以这个外部 agent 也能用到同一套 vault 工具。

**为什么是这个优先级**：用户明确希望内置 agent 和 Coffer 管理的 agent 共用一个 chat 界面。这正是让 Coffer 去*驱动*（而不只是存储）它的 agent 的关键。

**独立可测**：注册 `claude_code`（二进制在 PATH 上），开一个以它为目标的会话，发一条消息，观察到由被拉起的 `claude` 子进程产生的流式输出；停掉 daemon，确认没有残留的孤儿子进程。

**代表性场景**：

- chat with an external agent streams its subprocess output
- external agent binary missing is surfaced as a clear error

---

### User Story 3 — Manage conversations（优先级 P1）

开发者保留着好几个会话，重命名它们，归档过时的，删掉用完即弃的。每个会话都记得它针对哪个 agent，以及用到的 model 快照。

**为什么是这个优先级**：一个没有会话管理的 chat 产品，过了第一条消息就没法用了。

**独立可测**：建三个会话，重命名一个，归档另一个，删掉第三个；列出会话，观察到正好是预期的集合且 status 正确。

**代表性场景**：

- create / list / rename / archive / restore / delete a conversation
- a conversation records its target agent and model snapshot

---

### User Story 4 — Approve or deny sensitive tool use（优先级 P2）

当一个 agent（内置或外部）正在干活时，它打算运行一个用户标记为需要审批的工具（例如写/删类工具）。这一轮暂停，chat 上显示一张确认卡片，写明工具名和它的参数。用户批准（工具运行、本轮继续）或拒绝（工具不运行、并告知 agent 被拒了）。一个一直没被回应的确认不会破坏会话。

**为什么是这个优先级**：信任。内置 agent 能够触及破坏性的 vault 工具；用户必须始终掌控。（明确纳入 v1 范围。）

**独立可测**：把内置 agent 配置成对某个选定工具要求确认，发一条会触发它的消息，观察到 stream 暂停并出现确认请求，拒绝它，然后观察到工具没被执行且 agent 优雅地继续。

**代表性场景**：

- sensitive tool use pauses for confirmation
- approving a confirmation runs the tool and resumes the turn
- denying a confirmation skips the tool and informs the agent

---

### User Story 5 — Conversations get a readable title（优先级 P2）

在第一轮 user/assistant 往返之后，会话会基于其内容拿到一个短的、人类可读的标题（而不是「New chat」），让会话列表更易扫读。

**为什么是这个优先级**：会话列表的可扫读性。（明确纳入 v1 范围。）

**独立可测**：开一个会话，发一条有实质内容的消息，观察到标题从占位符变成一个由这次往返推导出来的短标题。

**代表性场景**：

- a new conversation gets an auto-generated title after the first exchange
- title generation failure falls back to a truncated first message

---

### User Story 6 — Use chat from the desktop app（优先级 P2）

开发者更喜欢可视化界面：一个会话列表、一个带 tool-call 行和确认卡片的 streaming 消息视图、一个输入框、一个目标选择器，以及一个 Stop 按钮。

**为什么是这个优先级**：非 CLI 用户需要它；chat 本身在 UI 里更自然。

**独立可测**：启动 Coffer，打开 Chat，选一个目标，发一条消息，看它流式吐出来，中途 stop，然后在 UI 里重命名并删除该会话 —— 全程在 UI 完成。

**代表性场景**：

- desktop chat lists conversations and opens one
- desktop chat streams a reply and can stop it
- desktop target picker lists built-in + chat-capable managed agents

---

### User Story 7 — Use chat from the command line（优先级 P2）

开发者写脚本或在无头环境下工作：建一个会话，发一条消息并在终端里看它流式吐出来，把历史以 JSON 打印出来。

**为什么是这个优先级**：CLI 对等能力，以及脚本化 / 调试支持。

**独立可测**：在终端里 `coffer chat new --agent coffer`、`coffer chat send <id> "hello"` 并观察到流式输出，然后 `coffer chat history <id> --json`。

**代表性场景**：

- CLI create / send (streaming) / history
- CLI JSON output for piping

---

### User Story 8 — Configure the built-in agent（优先级 P3）

开发者改内置 agent 的 model、system prompt、temperature，或者它能不能触及网关 —— 通过 `builtin_agent` resource 正常的 config 编辑路径。

**为什么是这个优先级**：定制化；seed 出来的默认值开箱即用，所以这一项不是阻塞项。

**独立可测**：编辑 seed 出来的内置 agent 的 model 和 system prompt，发一条消息，观察到新 model 被用上了（反映在会话的 model 快照里）。

**代表性场景**：

- edit built-in agent model / system prompt
- the last built-in agent cannot be deleted (re-seeded if absent)

---

### Edge Cases

- **没有配置 LLM provider/key（内置 agent）**：`send` 被以 503 拒绝，携带 `LLM_NOT_CONFIGURED` 并指向配置文档。列出 / 读取会话仍然可用。
- **外部 agent 二进制缺失 / 不在 PATH 上**：`send` 以一个清晰的错误快速失败；消息被标记为 `failed`；没有僵尸进程。
- **stream 被用户停止**：进行中的 assistant 消息被标记为 `canceled`，保留已有的部分内容；子进程（如有）被终止。
- **stream 中途出现运行时错误**：消息被标记为 `failed` 并带结构化错误；会话不会损坏；随后的一次 send 能正常工作。
- **确认一直没被回应 / 超时**：待处理的工具不运行；本轮以工具被拒结束；会话保持可用。
- **对一个已经在 streaming 的会话并发 send**：以 409 拒绝；用户在当前进行中的一轮结束后重试。
- **会话目标指向一个已被删除的 agent**：会话对新一轮变为只读；send 返回一个清晰的错误，指出缺失的那个 agent。
- **空 / 仅空白的消息**：在 API 边界被拒绝；什么都不持久化。
- **超过上限的消息**：在 API 边界被拒绝（`reason = "too_long"`）；什么都不持久化。

## Acceptance Scenarios

每个场景都映射到至少一个标了 `@pytest.mark.acceptance(spec="008-builtin-agent-chat", scenario="…")` 的测试。

### Scenario: a built-in agent is seeded on first startup

- **Given** 一份没有任何 `builtin_agent` resource 的全新安装，
- **When** daemon 启动，
- **Then** 正好存在一个已启用的 `builtin_agent` resource（默认名例如 `coffer`），带一个有效的默认 model 和 system prompt，并记入一条 audit 条目。

### Scenario: chat with the built-in agent streams a reply

- **Given** 一个内置 agent 以及一个已配置的 LLM provider，
- **When** 用户建一个以它为目标的会话并发一条消息，
- **Then** 响应以增量事件的形式流式吐出，一条 user 消息和一条 assistant 消息被持久化，且 assistant 消息以 status `complete` 结束。

### Scenario: the built-in agent can call Coffer gateway tools

- **Given** 一个已启用网关访问、且至少有一个内置 `coffer__*` 工具可用的内置 agent，
- **When** 用户发一条需要查 vault 的消息，
- **Then** 流式的这一轮里至少包含一个针对 `coffer__*` 工具的 tool-call 事件，且其结果被纳入回复。

### Scenario: conversation and messages persist across daemon restarts

- **Given** 一个带消息的会话，
- **When** daemon 被停掉并重启，
- **Then** 会话及其消息历史被原样返回，不重跑任何一轮。

### Scenario: chat with an external agent streams its subprocess output

- **Given** 一个已注册的 `claude_code` agent，其 CLI 可用，
- **When** 用户建一个以它为目标的会话并发一条消息，
- **Then** Coffer 以无头 streaming 模式拉起该 agent CLI，并把它的输出作为流式 assistant 内容转发，像任何其他一轮那样持久化。

### Scenario: external agent binary missing is surfaced as a clear error

- **Given** 一个以某外部 agent 为目标的会话，其二进制不在 PATH 上，
- **When** 用户发一条消息，
- **Then** 本轮以一个结构化错误失败、指出缺失的二进制，assistant 消息被标记为 `failed`，且没有残留的孤儿进程。

### Scenario: create / list / rename / archive / restore / delete a conversation

- **Given** daemon 正在运行，
- **When** 用户建若干会话，然后重命名、归档、恢复、删除它们，
- **Then** 每一步操作都被持久化，并在随后的列举里以正确的 `status` 反映出来。

### Scenario: sensitive tool use pauses for confirmation

- **Given** 一轮 agent 提议调用一个被标记为需要确认的工具，
- **When** 这一轮走到那个 tool call，
- **Then** stream 发出一个 `confirmation` 事件、写明工具名和参数，且这一轮挂起等待决定。

### Scenario: approving a confirmation runs the tool and resumes the turn

- **Given** 一轮挂起、等待确认，
- **When** 用户批准它，
- **Then** 工具执行，其结果被回喂给 agent，本轮恢复并完成。

### Scenario: denying a confirmation skips the tool and informs the agent

- **Given** 一轮挂起、等待确认，
- **When** 用户拒绝它，
- **Then** 工具不执行，agent 被告知该调用被拒，本轮无错误地结束。

### Scenario: a new conversation gets an auto-generated title after the first exchange

- **Given** 一个带占位标题的新会话，
- **When** 第一轮 user/assistant 往返完成，
- **Then** 会话的标题被一个由这次往返推导出来的短标题替换。

### Scenario: a streaming turn can be stopped

- **Given** 一轮 assistant 正在 streaming，
- **When** 用户发出 stop，
- **Then** streaming 停止，assistant 消息被标记为 `canceled` 并保留其部分内容，任何被拉起的子进程被终止。

### Scenario: send returns 503 when no LLM provider is configured

- **Given** 一个内置 agent，其解析出的 provider 没有配置 key/endpoint，
- **When** 用户发一条消息，
- **Then** 该调用被以一个携带 `LLM_NOT_CONFIGURED` 的 503 拒绝，且会话的读路径继续工作。

### Scenario: concurrent send on a streaming conversation is rejected

- **Given** 一个会话有一轮正在 streaming，
- **When** 对同一个会话发出第二次 send，
- **Then** 它被以 409 拒绝，且进行中的那一轮不受影响。

### Scenario: built-in agent runtime is engine-isolated

- **Given** 当前代码库，
- **When** 分析其 import，
- **Then** `coffer.application.*` 或 `coffer.domain.*` 下没有任何模块 import `langgraph` / `langchain*`；引擎只存在于 `coffer.infrastructure.*` 之下。

> **推迟到未来的测试工作**：以下场景属于契约的一部分，但它们的测试将随 e2e/UI 基础设施一起落地，而不在本 PR 里。`make verify-acceptance` 不对它们设门禁。
>
> - desktop chat lists conversations and opens one
> - desktop chat streams a reply and can stop it
> - desktop target picker lists built-in + chat-capable managed agents
> - CLI create / send (streaming) / history
> - CLI JSON output for piping
> - title generation failure falls back to a truncated first message
> - edit built-in agent model / system prompt
> - the last built-in agent cannot be deleted (re-seeded if absent)

## Requirements

### Functional Requirements

**Built-in agent（resource）**

- **FR-001**：System MUST 支持一个新的 resource kind `builtin_agent`，其 config 用一个 Pydantic schema 校验，字段为：`model`（provider 限定，例如 `anthropic:claude-sonnet-4-6`）、`system_prompt`（可选）、`temperature`（可选）、`max_tokens`（可选）、`credential_ref`（可选）、`use_gateway`（bool，默认 true）、以及 `confirm_tools`（需要人工确认的工具名 glob 模式列表；seed 出来的默认值覆盖破坏性模式，例如 `*delete*`、`*clear*`、`*remove*`、`*write*`）。
- **FR-002**：启动时 System MUST 确保至少有一个已启用的 `builtin_agent` resource 存在，若一个都没有则 seed 一个默认值（名为 `coffer`），并且 MUST 拒绝删除最后一个剩下的 `builtin_agent`（若它不知怎么没了，则在下次启动时重新 seed）。除此之外，built-in agent 通过既有的、与 kind 无关的 Resource 生命周期（create / update / enable / disable / delete）管理，全部审计。
- **FR-003**：一个 `builtin_agent` 的可编辑 config MUST 包含 `model`、`system_prompt`、`temperature`、`max_tokens`、`credential_ref`、`use_gateway`、`confirm_tools`。

**Agent runtime 抽象**

- **FR-004**：System MUST 定义单一的 `AgentRuntime` port —— 给定一段会话历史和一条新的 user 消息，产出一个有序的异步 runtime 事件流：text delta、tool-call start、tool result、confirmation request、error、done。chat/会话层 MUST 只依赖这个 port，绝不依赖任何具体 runtime。
- **FR-005**：System MUST 在该 port 背后提供两个 `AgentRuntime` 实现 —— 一个内置 runtime（内部 LLM 循环）和一个外部 agent runtime（子进程）—— 由会话目标 agent 的类型来选择。

**Built-in runtime（LangGraph）**

- **FR-006**：内置 runtime MUST 用 LangGraph 实现，从 agent 的 `model` 字符串解析出 model，于是引擎支持的任何主流 provider 都能跑（Anthropic、OpenAI、本地 Ollama、……），凭据通过 Coffer 的 keychain 解析。
- **FR-007**：当 `use_gateway` 为 true 时，内置 runtime MUST 通过用 daemon token 连接本地网关 endpoint，把 Coffer 自己的 MCP 网关工具暴露给 agent，于是 agent 能用 vault 管理的每一个已启用 MCP server / skill / knowledge base / memory 工具。
- **FR-008**：LangGraph / LangChain MUST 被限制在 `coffer/infrastructure/` 内。Domain 和 application 层 MUST NOT import 它们；交互通过 `AgentRuntime` port（由 importlinter 强制）。

**External-agent runtime（子进程）**

- **FR-009**：System MUST 支持与 `claude_code`、`codex` 类型的、被管理的外部 agent 对话 —— 在本地以无头 streaming 模式拉起它们的 CLI，并把它们的流式输出映射成 `AgentRuntime` 事件。
- **FR-010**：external-agent runtime MUST 在该 agent resource 既有的 config（其 `config_dir`）下运行每个 agent，MUST 流式产出增量输出，MUST 支持停止（终止子进程），并且当一轮结束、出错、被停止、或 daemon 关闭时 MUST NOT 留下孤儿进程。

**会话与消息**

- **FR-011**：System MUST 在 SQLite 中持久化会话（`id`、`target_ref` = `builtin_agent:<name>` 或 `agent:<name>`、`title`、`status` ∈ {active, archived}、`model_snapshot`、时间戳）和消息（`id`、`conversation_id`、`role` ∈ {user, assistant, tool}、`content`、`tool_calls`、`status` ∈ {streaming, complete, failed, canceled}、`error`、`created_at`）。一个会话精确地针对一个 agent，在创建时选定并连同 model 快照一起记录。
- **FR-012**：用户 MUST 能够 create、list（带分页）、get（带消息历史）、rename、archive、restore、delete 会话。删除一个会话会移除它的消息。
- **FR-013**：user 消息文本 MUST 至少 1 个字符、至多 32768 个字符；空 / 仅空白以及超长输入在 API 边界被拒绝，什么都不持久化。

**Streaming 与一轮的控制**

- **FR-014**：发送一条消息 MUST 把这一轮 agent 以 Server-Sent Events 的形式流式传给调用方；只有最终确定的消息内容和 tool-call 元数据被持久化（streaming 的 delta 是瞬态的）。
- **FR-015**：对一个已经有进行中 streaming 一轮的会话，System MUST 以 409 拒绝第二次并发 send。
- **FR-016**：用户 MUST 能停止一轮进行中的对话；assistant 消息随后被标记为 `canceled` 并保留部分内容。

**人在环确认（Human-in-the-loop）**

- **FR-017**：当一轮提议调用一个其名字匹配目标 agent `confirm_tools` 策略的工具时，runtime MUST 挂起这一轮并发出一个 confirmation request（工具名 + 参数）；在收到决定之前这一轮 MUST NOT 执行那个工具。对内置 runtime，这直接强制（Coffer 控制工具执行）；对 external-agent runtime，则在 agent CLI 暴露了 permission-prompt 钩子的地方强制，否则该 agent 在它自己配置的权限策略下运行（并向用户呈现）。
- **FR-018**：用户 MUST 能批准（工具运行、结果返回给 agent、本轮恢复）或拒绝（工具被跳过、agent 被告知）一个待处理确认。一个没被回应的确认 MUST NOT 破坏或阻塞 store；这一轮以工具被拒结束。

**自动标题**

- **FR-019**：在一个带占位标题的会话里完成第一轮 user/assistant 往返之后，System MUST 生成并持久化一个由这次往返推导出来的短标题，若生成不可用或失败则回退为截断后的首条 user 消息。

**界面**

- **FR-020**：用户 MUST 能通过 (a) `/api/v1/conversations/` 下的 REST API、(b) `coffer chat …` 子命令、以及 (c) 一个桌面 chat UI 来执行会话操作并 send/stream/stop 消息。目标选择器 MUST 列出内置 agent 加上所有已启用、支持 chat 的被管理 agent（目前是 `claude_code` 和 `codex`）。
- **FR-021**：会话和 built-in-agent 的生命周期变更 MUST 被审计；内置 runtime 通过网关发起的工具调用 MUST 与其他网关工具调用共用同一套 invocation-logging 界面（除工具名外不记录参数或返回内容）。

### Key Entities

- **Built-in Agent**（一个 kind 为 `builtin_agent` 的 resource）：Coffer 自己 LLM agent 的配置 —— model、system prompt、采样参数、credential ref、网关开关。始终至少有一个存在。
- **Conversation**：一个精确针对一个 agent 的 chat 线程。持有 id、target ref、title、status、model 快照、时间戳。
- **Message**：会话里的一条记录 —— role、content、tool calls、status、可选 error、created_at。
- **Tool Call**（嵌在一条消息里）：工具名、参数摘要、结果摘要，以及它是否需要 / 收到了确认。
- **Confirmation Request**（瞬态的一轮状态）：等待批准/拒绝决定的待处理工具名 + 参数。
- **Runtime Event**（瞬态，不持久化）：一个流式单元 —— text delta、tool-call start、tool result、confirmation request、error、或 done。

## Success Criteria

### Measurable Outcomes

- **SC-001**：从一份配好 provider key 的全新安装开始，用户能给内置 agent 发出他们的第一条消息，并在打开 Chat 后 10 秒内看到流式回复。
- **SC-002**：一轮需要用到 vault 的 built-in-agent 对话完成一次 `coffer__*` 工具调用并纳入其结果，可作为 stream 中的 tool-call 事件被观察到。
- **SC-003**：用户能与一个已注册的 `claude_code`（或 `codex`）agent 对话，并收到由被拉起的 CLI 产生的流式输出；停掉 daemon 不留下孤儿子进程。
- **SC-004**：停止一轮 streaming 在 1 秒内停止输出，并把部分 assistant 消息保留为 `canceled`。
- **SC-005**：一个需确认的工具在没有显式批准的情况下绝不执行，由一个 acceptance 测试验证。
- **SC-006**：引擎隔离由 importlinter 强制：`coffer.application.*` 或 `coffer.domain.*` 下没有任何模块 import `langgraph` 或 `langchain*`。
- **SC-007**：每个 Acceptance Scenario 都被至少一个标了 `acceptance(spec="008-builtin-agent-chat", scenario="…")` 的测试覆盖（上面明确推迟的那些除外）。
- **SC-008**：`make verify` 在本地和 CI 都通过。

## Assumptions

- 用户在自己的机器上跑 Coffer；与云端 LLM provider 通信是允许的（local-first 指的是用户*数据*留在本地 —— 见 `.specify/memory/constitution.md`）。
- LangGraph / LangChain 保持积极维护；API 变动只在 `infrastructure/` 里消化。
- 对外部 agent chat，用户已自行安装该 agent 的 CLI（Coffer 不打包 `claude` 或 `codex`）；Coffer 检测其存在，缺失时清晰报告。
- `cursor` 以及其他没有文档化无头 streaming 模式的已注册 agent 类型，在本规范里不是 chat 目标。
- Channels（把外部消息平台桥接进这个 chat）不在此处范围内，由规范 009 覆盖。
- 单用户并发量很小；每个会话一轮进行中的 streaming 就够了。
