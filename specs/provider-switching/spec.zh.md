# 功能规范：Provider Switching

> English: [spec.md](./spec.md)

**Feature Branch**: `feature/G9-provider-switching`
**Created**: 2026-06-21
**Status**: Draft

## 一句话总结

统一的 **LLM connection** 让用户只需配置一次密钥（名称、wire 格式、base URL、加密凭证、模型），并以两种方式使用它：既投影到对应 agent 的本地配置文件，也让 Coffer 自身的内部 LLM 引擎在其上运行。一条 connection 即退役独立的 `ModelConfig`/`chat_models` 注册表，将内部引擎的模型选择折叠进同一条记录。相比 `claude switch` 或各工具的独立脚本，Coffer 的优势在于统一注册表加治理层——Fernet 加密凭证、完整审计日志、可检视的导出/导入 bundle——而非各工具各管各的。

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

除按 agent 激活外，一条 connection 还可以携带单一的全局 `internal_default` 标志（所有 connection 中 ≤1），标记 Coffer 自身内部 LLM 引擎（memory organizer、reorg、distill）使用的 connection。第三种 wire `ollama` 仅供内部：它从不投影到任何 agent；且因其没有 API key，其 `credential_ref` 不存在——只需一个 `base_url`。因此 `credential_ref` 是**可选**的：anthropic/openai 必填，ollama 不存在。一条 connection 可以**同时**是活跃的（投影到其 wire 的 agent）和 `internal_default`（供内部使用）——一份密钥，两种用途。

### 决策 B——凭证隔离；明文密钥不得写入原生配置

与现有 MCP `credential_refs` 模式及"凭证隔离"原则保持一致。原始密钥始终留在 Fernet vault 中，按需解密，从不持久化到原生配置文件：

- **Claude Code**：在 `settings.json` 中写入 `apiKeyHelper = "coffer provider key --wire anthropic"`。Claude Code 调用此命令获取密钥。由于 Claude Code 会定期重新调用 `apiKeyHelper`，该设计使未来的 hot-switch 几乎可以无代价实现——此处仅作前瞻性说明。
- **Codex**：在 TOML 的 `[model_providers.coffer]` 表中写入 `env_key = "COFFER_PROVIDER_KEY"`。Codex 在运行时从该环境变量读取密钥。**本 PR 不修改 Codex 的启动逻辑**；用户需要手动 export 该变量（见 Quickstart）。明确说明：**Codex 独立运行时需要在 shell 中设置 `COFFER_PROVIDER_KEY`；将 key 自动注入 Coffer 启动的 Codex 进程与 hot-switch 一同延期。** 这是选择决策 B（凭证隔离）可接受的代价。

原始密钥绝不写入 `settings.json`、`config.toml` 或任何其他原生配置文件。

### 决策 C——分阶段交付；本 PR 不包含 hot-switch

本 PR 交付：注册表 + 投影 + 切换操作 + 审计 + 导出/导入接入。

Hot-switch（对正在运行的 Claude Code 或 Codex 进程的会话内热重载）是**单独的后续 PR**，明确**不在本 PR 范围内**。

## 修订 2026-06-22b — 连接是「带凭据的 endpoint」；模型与协议离开连接

> 状态：Draft。**Supersede 决策 A 的「model 在连接上」与早先 amendment 的 D2（多协议集合）。**
> cc-switch 调研 + 与用户敲定后记录。交叉引用
> [Provider Switching](../../docs/decisions/provider-switching.md) amendment D8/D9。

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
（多协议集合——已废弃，见 [Provider Switching](../../docs/decisions/provider-switching.zh.md)
D8：一网关供两 agent = 两条连接）。

**仍不在范围（不变）：** proxy / 热切换 / 协议转换。

## Amendment 2026-06-23 — 按连接的兼容 agent；按连接的密钥解析；按 agent 类型激活

> 状态：草案。**取代 E5 的按-protocol 兼容性过滤与 per-protocol 单激活不变式。** 与用户设计讨论后记录。
> 交叉引用 [Provider Switching](../../docs/decisions/provider-switching.md)。

**为什么。** 把投射绑定到连接探测出的 `protocol`，无法表达「这个 openai 兼容网关（如 agnes）应当驱动
Claude Code」。更糟的是密钥解析按 `wire + is_active` 绑定（`apiKeyHelper = coffer provider key --wire
anthropic`，Codex 注入 `resolve_active_key(OPENAI)`），所以把这种连接路由到「错」的 wire 的 agent 会
静默解析到**另一条**连接的 key——凭证错配。修复办法：把「连接投射到哪些 agent」与「endpoint 说哪种
wire」解耦，并按**连接**解析密钥。

- **F1 — 连接上的 `compatible_agents`。** 连接显式携带 `compatible_agents ⊆ {claude_code, codex}`
  （`null` ⇒ wire 默认：所有带凭据的 wire 都是两者，ollama 为 `[]`——它仅供内部使用）。添加/编辑
  对话框同样按此预填复选框——默认全部勾选——由用户收窄（或把 openai 网关路由给 Claude Code）。
  JSON 载荷——无需 DB 迁移。
- **F2 — 投射 writer 按 AGENT 类型选，不按 protocol。** 兼容 `claude_code` 的连接写 Claude 的
  `settings.json`（anthropic 形态）；兼容 `codex` 写 Codex 的 `config.toml`。`protocol` 现仅用于模型
  自省与是否需要 key。
- **F3 — 按连接解析密钥。** Claude Code 投射的 `apiKeyHelper` 为
  `coffer provider key --connection <name>` → `GET /providers/{name}/key`，所以 agent 永远读到正是被
  激活那条连接的 key。Codex 的 `COFFER_PROVIDER_KEY` 为「对 Codex 激活」那条连接的 key
  （`resolve_active_key_for_agent(codex)`）。旧的 `--wire` helper / `/active-key/{wire}` 保留作向后兼容，
  按 wire 对应的 agent 解析。
- **F4 — 激活按 AGENT 类型。** 不变式：每个 agent 类型至多一条激活连接。激活一条连接会把它投射到其所有
  兼容 agent，并从之前激活的连接手里接管这些 agent（把那条连接从新连接不覆盖的 agent 上 deproject）。
  `use-builtin/{wire}` 还原该 wire 背后的 agent；兼容多个 agent 的连接作为整体还原（单个 `is_active`
  标志是全有或全无）。
- **F5 — 连接页移除每行「切换」。** 激活按 agent，落在 Agent 详情 → 概览页（按 `compatible_agents`
  过滤连接）。连接页是库：增 / 改 / 删 + 展示每条连接的兼容 agent。

**Supersede：** E5（按-protocol 匹配的兼容性过滤——现为显式 `compatible_agents` 集合）；决策 A /
FR-011 的 per-protocol 单激活（现为 per-agent-type）。**仍不在范围：** proxy / 热切换 / 协议转换。

## 修订 2026-06-23c — 选连接是草稿；先测试、再确认切换

> 状态：Draft。在「为 Claude Code 激活了 agnes 连接但没绑模型」之后记录。交叉引用
> [Provider Switching](../../docs/decisions/provider-switching.md)。

**为什么。** 按 E3/E4，模型落在 per-agent 绑定上，激活只投影 endpoint + 密钥。Agent 页过去**一选中连接
就立即激活**、且没绑模型——于是一条 endpoint 用自己模型 id 的连接（agnes 场景：路由到 Claude Code 的
openai 网关）会让 `ANTHROPIC_MODEL` 留空，Claude Code 继续拿内置 `claude-*` id 去打这个 endpoint，
结果 Coffer 的两个槽位和 Claude Code 自己的 `/model` 选择器里**每个模型都失败**，报 "model may not
exist or you may not have access"。用户既没机会选一个该 endpoint 支持的模型，也拿不到任何信号说明问题在
这次切换、而非自己的账户。仅仅改个下拉就激活，也等于一键把未验证的 endpoint 变成线上配置。

- **G1 — 在 Agent 页选连接 / 模型是「草稿」。** 选连接或选模型不再激活、也不再 PATCH，只是暂存一个选择。
  选中非内置连接时 introspect 其 endpoint 并暂存一个默认模型——Claude Code 的主模型 + 快速模型、以及
  Codex 的单槽位，都默认成 endpoint 返回的**第一个**模型——好让用户有东西可测。
- **G2 — 先「测试连接」，再「确认切换」。** 自定义连接必须先通过 test-connection 探测
  （`POST /models/test-connection`，带上暂存的模型）才能确认。在当前草稿测试通过前「确认切换」不可点；
  改连接或改模型会重置测试结果。「确认切换」先 PATCH per-agent 绑定（model + fast_model）再激活连接
  ——这是唯一写原生配置的一步。切回内置登录无需测试（没有 endpoint 可达），直接确认即可。

**Supersede：** E4 隐含的「一选中就立即激活」——激活现在被显式的测试 + 确认门控，且绑定不会留空。
**仍不在范围：** proxy / 热切换 / 协议转换。

## 修订 2026-09-09 — Agent 的模型清单由后端提供

> 状态：Draft。**Supersede D4 的「精选内置清单」及其二选一的选项规则。** 在一次线上会话里，
> 一个 Claude Code 对话只被提供 `agnes-*` 模型 id 之后记录。交叉引用
> [Provider Switching](../../docs/decisions/provider-switching.md)。

**缺陷。** D4 所说的「精选内置清单」实际上只是一个硬编码常量——`["opus", "sonnet", "haiku"]`
——在 `frontend/src/lib/api/providers.ts` 和 `backend/coffer/surfaces/http/channel_wiring.py`
里各有一份。两份拷贝、无人负责，而且已经过时：Claude Code 的 `--model` 还接受 `fable`、`opusplan`
和 `default`，于是 `fable` 在 Coffer 里根本无法选到——选择器是固定下拉、没有自由输入（D4），
常量里没有的 id 也无法手输。D4 的选项规则更让事情雪上加霜，因为它是二选一的：当有连接覆盖该 agent
时，选择器**只**显示这条连接 introspect 出来的模型，把 agent 自己的模型藏了起来。线上观察到的现象：
一条 `is_active` 的 openai 连接被路由到 `claude_code`，而 `~/.claude/settings.json` 里
根本没有 Coffer 的任何投影——也就是说 agent 实际跑在内置登录上——但聊天里只给出 `agnes-*` 这些
id，而这些 id 该 agent 一个都用不了。

- **H1 — 模型清单是后端的一个接口，按 agent 提供，且 Coffer 自己不写死任何模型名。**
  `AgentModelCatalogueService` 按 agent 回答该 agent 可以被切到的模型。（它最初以 `GET
  /api/v1/agent-providers/{agent_key}/models` 暴露在 HTTP 上；该路由随下文 2026-09-12 的撤回
  一同移除，清单如今只通过内部端口读取——`/model` 卡片是它唯一的读者。）每一项——id、
  显示名、描述——都是从**已安装的 agent 那里读回来的**，绝不写进 Coffer：写在这里的清单会在 CLI
  下一次发版时过期，而且分不清同一档位的两个版本。共有三个来源，它们的顺序就是选择器的顺序：
  Claude Code 可执行文件内嵌的带版本模型目录——那是唯一写着各版本显示名的地方；Codex 自己的
  `model/list` app-server RPC；以及各 CLI 的原生配置，用于只有它才知道的本地选择
  （Claude Code 在 `~/.claude.json` 里发布 `additionalModelOptionsCache`；Codex 的
  `config.toml` 里写着它配置的模型）。清单**只列真实模型**：CLI 的档位**别名**（`sonnet`、
  `opus`、`haiku`、`fable`、`best`、`sonnet[1m]`、`opus[1m]`、`fable[1m]`、`opusplan`）
  不再列出，因为每个别名都解析到清单里已经有的模型——Claude Code 自己在比较两个模型名之前就会
  把结尾的 `[1m]` 去掉——两者都列只会让选择器多出九个没有标签的重复项，紧挨着它们所指向的真实
  模型。这不会让任何东西变得不可达：凡是可以手输模型名的地方（`/model <名字>`、agent 自己的
  配置）仍然接受别名，由 CLI 负责校验。已知并接受的代价：`best` 和 `opusplan` 是**路由行为**
  而非单个模型，因此今后只能手输名字来设置，不能从列表里点选。每一项带
  `id`（原样传给 CLI）、`label` 和 `description`。每个来源都
  各自静默降级——CLI 没装、bundle 结构变了、agent 没登录或卡住，代价只是少了这个来源本来会补上的
  模型，仅此而已。没有任何 provider 认领的 `agent_key` 根本拿不到清单。
- **H2 — 单一事实来源。** 前端常量被删除；channel 的 `/model` 卡片读同一份清单。清单只在一处维护，
  而且由 agent 自己拥有，因此新发布的模型完全不需要 Coffer 发版就能到达每个界面。
- **H3 — 选项是并集，不是二选一。** 聊天选择器的选项 = agent 的模型清单（H1）∪ 当前生效连接
  introspect 出的模型（`POST /models/list-models`）∪ 该对话当前的取值。D4 禁止自由输入这一条**保持
  不变**——选择器仍是固定下拉，且当前值始终可选。于是连接是往选择器里**增加** id，而不是把 agent
  自己的模型藏起来。
- **H4 — Agent 页在内置登录下不提供任何模型控件。** 这些槽位绑的是**连接**的模型（E3/E4）：
  只有当 Coffer 投影了一条连接时才会读 `agent.model`。因此内置登录下既没有选择器也没有清单，
  只留一句话说明模型在别处选：聊天里的模型选择器，或聊天中的 `/model`——
  让「这里什么都没有」有解释，而不是看起来像坏了。（两次被取代：2026-09-11b 曾把这个面板变成
  策展控件，其 2026-09-12 的撤回又把控件整个去掉——策展先是搬到了 channel 上，随后在那边也被
  移除，于是再没有任何东西策展 agent 的模型。）
- **H5 — Coffer 会告诉 agent 它跑在哪个模型上。** Coffer 每轮追加的 system prompt 现在会说明
  Coffer 把 agent 切到了哪个模型——或者说明 Coffer 没有设置任何覆盖——以及有哪些 id 可用。触发这条的
  事件：在一次真实的 channel 会话里被问到时，agent 很自信地报出了一个它并没有在跑的模型，因为它的
  上下文里没有任何信息说明真实情况。**仅限 Claude Code。** Codex 的 app-server 不接受按线程注入的
  instructions——它的 `ThreadSettings` 只有 approval/sandbox/model/effort 等字段，没有提示词入口——
  除非把说明塞进对话的第一条用户消息里污染对话，否则无处安放。Codex 拿到的是准确的模型清单（H1），
  但没有这条说明。

- **H6 — 连接是否 active，以 agent 自己的配置为准。** `is_active` 是 Coffer 数据库里的一行，但它
  真正的含义是几个键，写在一个不属于 Coffer 的文件里——agent 自己的 CLI、其它工具、用户本人、以及
  从备份整体恢复，都会重写它。没有任何东西把 Coffer 的键放回去，也没有任何东西发现它们不见了。现在
  Coffer 在启动时会检查：对每个存在 active 兼容连接的 agent 类型，该 agent 的原生配置里是否真的带着
  投影；如果没有，就**清掉这个标志**——agent 实际跑在内置登录上，所有界面从此如实反映。它只朝一个方向
  修复：**绝不**把投影写回去，因为一个上次会话遗留的标志并不足以构成把用户的 agent 悄悄改道到某个
  网关的理由（同步的 post-import hook 仍然做投影，因为一次导入承载的是用户明确的切换动作）。反向漂移
  ——文件里有 Coffer 的键但注册表说未激活——只报告，不静默删除。
  修订 0051 同时清理连接 `compatible_agents` 里已下线的 agent 类型（`cursor` / `opencode` /
  `openclaw` / `hermes`）：修订 0048 删掉了这些 agent 自己的行，却把它们的名字留在了连接里，而
  `ProviderConfig` 不接受这些值——于是在真实安装上，升级后第一次校验就会抛错，一个本来正常的连接变得
  不可读。

**Supersede：** D4 的精选内置清单（现在改为后端的模型清单）及其二选一的选项规则（现在是 H3 的并集）。
D4 的固定下拉 / 禁止自由输入规则不变。**仍不在范围：** proxy / 热切换 / 协议转换。

## 修订 2026-09-11 — 连接自己策展「提供哪些模型」

> 状态：Draft。**这是对 E1/E3「模型不存在连接上」的细化，而非推翻。**
> **2026-09-12b 再细化：** 每条策展条目变成 `{id, modality}` 对象；下文每处 `list[str]`
> 都读作这份对象列表。与用户做过一轮设计
> 讨论后记录。交叉引用 [ADR provider-switching](../../docs/decisions/provider-switching.md)。

**为什么。** E3 把模型移到使用处，2026-09-09 修订又把选择器的选项做成「一切可用之物」的并集。
两者都对，但合在一起，用户拿到的是一份自己没挑过的菜单：一个网关账号常常服务几十个模型，
而它的主人只打算用其中两三个。没有任何东西收窄过这份清单，因为设计里只有两种状态——
「一个模型、钉死在连接上」（选得太早）和「endpoint 提供的所有模型」（太多）。中间那种状态
——*这个 endpoint 的哪些模型是我真的会用的*——属于账号本身，是稳定的，也正是连接这个位置
该记录的东西。

- **J1 —— 连接上的 `models: list[str]`：是**提供**集合，不是选中的模型。** 连接依然不存它
  *运行*的模型：E1/E3 成立，选择仍发生在每个使用处（按 agent 的绑定、内部引擎选择器、频道
  `/model` 卡片）。`models` 只说明这个选择能从哪些 id 里挑。**空表示不限制**——即 endpoint
  的完整目录——这是默认值，是修订 0059 之前创建的每条连接的取值，因此对不做策展的人来说，
  这次升级什么都没变。
- **J2 —— 在连接详情页策展，由下游每个选择器落地。** 用户在连接本身上，从实时 introspection
  （`POST /api/v1/models/list-models`）里勾选。下游任何提供该连接模型的选择器，非空时就只提供
  这份策展集合，为空时提供 endpoint 的全部。这收窄的是 H3 并集里的**连接**那一项；agent 自身
  清单那一项不受影响——策展集合绝不会藏起 agent 用自己内置登录就能用的模型。
- **J3 —— id 依旧不透明；Coffer 依旧不写死任何模型名。** 策展集合只校验**形状**（id 非空白、
  按序去重、有合理上限），并原样透传给厂商。Coffer 绝不拿 id 去比对自己的名单——2026-09-09
  修订的规则不变；endpoint 不再提供的某个 id 只是一条过期菜单项，不是配置错误。
- **接口形状。** `ProviderOut.models: list[str]`；`ProviderCreate.models: list[str] | None`
  （`null` ⇒ 空）；`ProviderPatch.models: list[str] | None`，与 `compatible_agents` 一样是
  **整值替换**（`null` 保持不变，`[]` 清除限制）。不新增路由——create 与 patch 承载它。
- **审计。** 不新增事件：策展集合就是普通的连接配置，因此对它的修改搭乘
  `ResourceService.update_config` 已经发出的 `resource_updated` 事件，其 `before`/`after`
  详情原样携带 config（provider kind 不声明 redactor，因为它的 config 不含 secret）。
- **迁移 0059** 为每一条既有 `kind='provider'` 行写入 `models: []`，让每条连接自己陈述答案
  ——不限制——而不是依赖读取方的默认值。按房规一次性完成：不留 load-time 垫片。

**细化：** E1/E3（模型离开连接——对**选中的**模型依然成立）与 H3（选择器并集——其连接项在存在
策展集合时改为该集合）。**仍不在范围内：** proxy / hot-switch / 协议转换；Coffer 仍不拿任何模型
id 去比对自己写死的名单。

## 修订 2026-09-11b — agent 自己策展「从自己的清单里提供哪些模型」

> 状态：**2026-09-12 部分撤回。** K1（退役过滤）保留。本条引入的**逐 agent** 策展集合
> K2–K4 **已撤回**：它先搬到了「有受众的那个面」——**channel**——随后在那边也一并移除，
> 于是 Coffer 里再没有任何东西策展 agent 的模型。下面的条目已改写为「还剩下什么」。
> 交叉引用 [ADR provider-switching](../../docs/decisions/provider-switching.md)。

**为什么。** H1 让清单成为 agent 自己的答案，这一条是对的、现在仍然是对的——但那个答案是
**累积的**，而且**对账号无感**。在当前安装上，Claude Code 内嵌的目录有十九个模型，而这位用户的
账号实际只能跑其中九个。另外十个一选就失败，选择器却完全看不出谁是谁。

是否可以自动排除这十个，已经查过：不行。十九条目的每一个字段都与已知可用的九个做过对比：
`pricing` 分不开（`claude-opus-4-5` 和 `claude-opus-4-6` 同为 `tier_5_25`，一个死一个活），
`capabilities` 也分不开（能用的 `claude-haiku-4-5` 只有 `context_management`，不能用的
`claude-mythos-5-1` 反而字段齐全），`knowledge_cutoff` 不行，上下文窗口不行，任何版本号规则也不行
（opus 保留四个版本，sonnet 保留两个）。CLI 自己的过滤跑在 `e.config.models` 上——那是**服务端下发
的账号配置**，而本机 `~/.claude.json` 里的 `modelAccessCache` 是空的。**一个账号能跑哪些模型是账号
事实，不是本机事实。** 把名单写死在 Coffer 里，一个月内就会过时：Claude Code 每隔几周就发新模型，
而用户完全无从知道为什么新模型一直不出现。当时给出的答案是：Coffer 展示清单，由用户勾选；
下面 2026-09-12 的撤回把这条反转了——Coffer 整份展示、什么都不勾，于是账号跑不了的模型仍会被
提供，并在被选中时失败。

- **K1 — 二进制自己说已经死掉的模型，直接去掉。** Claude Code 的 bundle 在目录旁边还带着第二张表，
  把模型 id 与各 provider 的退役日期对应起来，并为那些会被 CLI 静默改道的模型记下它 `remappedTo`
  的档位。Coffer 套用 CLI 自己的判定：带 `remappedTo`，或 **`firstParty`** 退役日期已过，即视为
  已消失。只用 `firstParty`——其余各列（bedrock、vertex、foundry……）描述的是 Coffer 不配置的部署，
  日期也不同。读法与目录完全一致：按结构定位；一旦锚点不再匹配，该来源返回**未过滤的**清单，而不是
  用半张表拼出来的过滤器。这缩短了用户需要策展的列表，不花任何代价，并随每次 CLI 升级自动更新。
- **K2 — 已撤回：agent 上的 `models: list[str]`。** 那个勾选集合存在 `AgentConfig` 上，并收窄
  每一个问到这个 agent 的选择器。前提是对的——一份累积且对账号无感的清单确实需要用户来回答——但
  **放置的位置**错了：agent 没有受众，在它身上策展会同时收窄「手机上的一个聊天」和「打开 agent
  页面的那个人」。该字段、它的形状校验、以及修订 0060 的回填现已全部移除，由**修订 0063** 剥除，
  不留 load-time 垫片（房规）。答案随后搬到了 **channel** 上，又在那边被撤回（修订 0067）：
  没有任何资源策展模型，每个面提供的都是经 K1 过滤的整份清单。
- **K3 — 关于模型，已经没有任何问题要通过 HTTP 问一个 agent 了。**
  `GET|PUT …/models/selection` 连同 `AgentModelSelectionIn` / `AgentModelSelectionOut`
  最先**移除**：对一个 agent 已经没有第二个问题可问了。
  `GET /api/v1/agent-providers/{agent_key}/models` 在 2026-09-12 随之移除——channel 的对话框是
  它最后一个读者，而它们不再问了。经 K1 过滤的完整清单仍然照旧装配（仍按 agent **类型**寻址，
  仍由该类型下第一个已启用的 agent resource 作答），但只存在于 `/model` 卡片所读的那个内部端口后面。
  `/api/v1/agent-providers` 下剩下的只有注册表列表本身。
- **K4 — 收窄「提供」曾是「面」的职责，而现在没有任何面在收窄。**「这个 agent 能被切到哪些模型」
  只有一个答案——`offered()` / `suggest()` 返回 agent 的清单（或激活连接的策展集合，见 2026-09-11c
  修订）——而每个面都把这个答案整份提供出去：channel 的 `/model` 卡片只是分页翻阅它，不拒绝任何 id。
  任何地方模型名都仍是原样透传——CLI 接受清单之外的名字（档位别名，以及比已安装二进制更新的模型），
  坏名字由 CLI 自己报错。
- **接口。** 什么都不剩：`AgentModelsOut` 随路由在 2026-09-12 一同移除，
  `/api/v1/agent-providers` 回到只有注册表列表。契约见
  [`specs/channels/contracts/api.openapi.yaml`](../channels/contracts/api.openapi.yaml)，
  agent-provider 的路由就在那里。
- **审计。** 无可记录：已经没有逐 agent 的策展集合会被改动。
- **迁移 0060** 曾为每一条 `kind='agent'` 行写入 `models: []`；**迁移 0063** 再把这个键从每一行
  上取下来——`AgentConfig` 禁止多余键，仍带着它的行在加载时会校验失败。

**细化：** H1（清单仍然是 agent 自己的答案，只是减去了 agent 自己说已退役的部分）与 H4（Agent 页
在内置登录下不再提供任何模型控件——既无选择器也无勾选清单，只留一句话说明模型在哪里选）。
**仍不在范围内：** 在本机推导账号权限——它推导不出来；
Coffer 仍不写下任何属于自己的模型名。

## 修订 2026-09-11c — 有激活连接时，由它回答「选择器该提供什么」

> 状态：Draft。**细化 2026-09-11b**：那一条让选择器只展示**账号**跑得动的模型，这一条回答的是
> 「谁的账号」。起因是一次实际使用：Coffer 已经把 agent 指向了某个网关，频道里的 `/model` 卡片
> 却仍在提供该网关根本不提供的 `claude-opus-5`。

**缺陷。** `AgentModelCatalogueService` 是所有「提供模型选择」界面共用的唯一清单，但它只问 agent，
对 Coffer 已经为该 agent 激活的连接一无所知。于是把 openai 兼容网关路由给 `claude_code` 之后，
卡片给出的是 Claude 自己的模型名，而那个端点一个都不提供；点下去 id 被原样透传给 SDK，发往
`ANTHROPIC_BASE_URL`，这一轮直接失败。此前已有的两条收窄规则——退役表与逐 agent 的策展集合（后者已撤回，见 2026-09-11b）——
描述的都是 **agent 自己登录的那个账号**，而这些请求根本没发往那里。

- **K1 —— 激活连接的策展集合「就是」选择器提供的内容。** 当一条连接 `is_active`、与该 agent 类型
  兼容、且带有策展模型集合时，`offered()` / `suggest()` 直接以那些 id 作答，按用户的顺序，不看
  agent 的 catalogue。`catalogue()` 不变，仍然报告 agent 自己的模型：它是详情页呈现的完整事实，
  而选择器如何使用它是 `offered()` 的事。
- **K2 —— 激活但未策展则什么都不变。** Coffer 知道请求发往哪里，但不知道那个端点提供什么，并且
  刻意不问：这次读取发生在每次渲染卡片、每一轮对话时，introspect 会把一次网络往返放到 daemon 的
  事件循环上（CODE-034）。此时仍以 agent 自己的答案为准；用户想要准确，就去这条连接上策展模型集合。
- **K3 —— 没有兼容的激活连接即「agent 自己的登录」**，答案就是清单（减去 2026-09-11b K1 的退役过滤）。一条 Coffer
  解析不了的 provider 行会退化到这种情况，而不是让读取失败。
- **K4 —— Codex 还会把这份清单送进它「自己的」选择器。** 把一条已策展的连接投影给 Codex 时，
  Coffer 会在它的 `config.toml` 旁写一份 Coffer 所有的 catalogue 文件，并让 `model_catalog_json`
  指向它。这个键会**替换** Codex 的内置模型列表（已对 Codex 0.139.0 实测：写入单模型 catalogue 后
  `model/list` 只返回该模型），而这正是想要的效果——agent 现在调用的端点并不提供那些内置模型。
  取消投影时指针被删除、文件被退役，Codex 自己的模型随即回归。指针**仅在**它指向 Coffer 所有的
  那个文件名时才会被删除，与 `apiKeyHelper` 采用同一套归属判定。未策展的连接不写 catalogue，
  理由见 K2。
  - 该文件是**与另一个程序之间的接口契约**：Codex 解析器要求的每个字段都会写出，并由测试钉住。
    写坏了并不会大声失败——Codex 会告警并回落到内置列表，也就是投影**静默失效**。
  - 那些 Coffer 无从推导的字段一律取「主张最少」的值，并在旁边记下猜错的代价。其中一个有真实
    后果：`base_instructions` 是 Codex 存放它**整个 agent 系统提示词**的地方，而 Coffer 写空——
    Codex 于是不发送 `instructions` 字段。它仍会发送权限、skills、环境这几条 developer 消息和
    完整工具集，agent 能正常工作，但少了 Codex 的人格提示词。另一种做法（把 OpenAI 的提示词抄进
    Coffer 写的文件里）会把某一个 Codex 版本的提示词钉死，并静默覆盖之后的每一个版本；Coffer
    不替另一个产品编写系统提示词。
  - Claude Code 没有对应能力。唯一形似的 `~/.claude.json` 里的 `additionalModelOptionsCache`
    是 Claude Code 对自己 API 响应中某字段的**缓存**，会被刷新覆盖；它不是对外契约，写进去的东西
    会被冲掉。所以对 `claude_code` 而言，Coffer 这一侧的界面仍是仅有的选择入口。

**细化：** 2026-09-11b 的 K1 退役过滤（在 agent 使用自己登录时仍然适用）与 H1（清单只
读取、不编写——在有激活连接时改为向连接读取）。**仍不在范围内：** 读取选择器清单时 introspect
端点；Coffer 仍不拿任何模型 id 去比对自己写死的名单。

## 修订 2026-09-11d — `wire_api` 只剩一个合法值

> 状态：Draft。**Supersede D7 的「`wire_api ∈ {chat, responses}` 可选」。** 起因是在验证另一项
> 改动时顺手检查了本机安装的 Codex。

**缺陷。** `AgentConfig` 接受 `wire_api = "chat"`，而 `ProviderProjector` 会把它写进
`[model_providers.coffer]`。Codex 0.139.0 并不是忽略这个值——它**拒绝加载 `config.toml`**
（`wire_api = "chat" is no longer supported`，并指名 `responses` 是修法），于是被 Coffer 投影的
那个 agent 的 CLI 根本起不来。而 Coffer 全程不吭声：这个值在 `PATCH /api/v1/agents/{name}` 被
接受、被存下、被写进一个 Coffer 从不回读的文件，故障最终表现为「agent 坏了」，而不是「某项设置
填错了」。D7 其实已经知道 `chat` 被废弃——codex-cli 0.130 先动手时，它把默认值改成了
`responses`——但仍然把另一个值留作可选。

- **L1 —— `responses` 是唯一接受的值**，在 `AgentConfig` 上强制，于是 `chat` 在用户设置它的那一刻
  就是一个看得见的 422。已对本机安装的 CLI 实测：其他任何拼写都会被 Codex 自己的解析器拒绝
  （`unknown variant, expected \`responses\``），而 `chat` 有一条专属报错。这是故障仍然可读的
  唯一边界；越过它之后，Coffer 写的是一个只有 Codex 会读的文件。
- **L2 —— 不采用「投影时映射」的修法。** 在写出时把 `chat` 改写成 `responses`，会让存储的值、
  以及每一个报告它的 `AgentOut`，都在说一件与 Coffer 实际投影不符的事。一项设置不该对自己撒谎。
- **L3 —— migration 0061 修掉已经带着这个值的行。** 按房规一次性完成：不留 load-time 垫片。
  revision 0037 在 `wire_api` 还挂在**连接**上时做过同样的翻转；0040 随后把该字段移到 agent 上，
  而 agent 的 PATCH 路径一直接受 `chat` 直到这次改动，所以那些行从未被覆盖。选择翻转而不是剥除，
  是为了保住这项设置**本来想表达**的意思——使用 Codex 的 Responses API——也就是它现在唯一能说的话。

**附注（不是决策）：** 只剩一个合法值意味着这个逐 agent 覆盖项只可能等于它自己的默认值，实际已经
是摆设。退役该字段是另一次改动——它在公开 API 与 OpenAPI 契约上——这里**刻意不做**。

## 修订 2026-09-12 — 连接可以改名；模型自己列出来

> 状态：草案。新增改名操作；**推翻编辑对话框所隐含的「名字不可变」假设**，也推翻
> 模型 tab 里的手动拉取。

**A1 — 名字可编辑，而改名是一次完整操作。** 名字是用户手里唯一的把手，却恰恰是编辑
对话框拒绝修改的那一个字段。它同时也是**身份**：连接自有的 vault 条目是
`provider/<name>/key`，审计行记在 `provider:<name>` 名下，名字还被原样写进 Coffer 投影
出去的 agent 配置里（Claude Code 的 `apiKeyHelper` →
`coffer provider key --connection <name>`，Codex provider 的 `display_name`）。
所以改名**必须**把这四处一起搬走——这也是
它是 `POST /api/v1/providers/{name}/rename` 而不是又一个 `PATCH` 字段的原因：patch 改的
是连接的设置，而撞上另一条连接已占用的名字必须是 409，而不是一次把两条连接悄悄合并的
编辑。

- 自有的 vault 条目随名字迁移——先按新 ref 写入，行迁移之后再删旧的，任何一步失败都不
  会让连接指向一个不存在的 secret。若**另一个**资源也引用了同一个 ref，则保持原样：改
  它会弄坏那个引用方。
- 审计轨迹跟着资源走。日志记的是「这条连接发生了什么」，改名之后它仍然是同一条连接，
  把历史留在一个已经解析不到的名字底下就等于丢了它；改名本身记为 `resource_renamed`，
  同时写下新旧两个名字，所以什么都没被抹掉。
- **激活中**的连接会按新名字重新投影，这样 Coffer 放上去的 agent 仍能解析到密钥，而不
  是拿一个已经不存在的连接名去调 shim。
- 改成当前名字是 no-op，不是错误。

**A2 — 模型 tab 打开即探测；没有「拉取模型」按钮。** 一个端点提供哪些模型，是关于端点
的事实，和 MCP server 的工具清单完全同类——而 Coffer 打开 server 的那一刻就把工具列出来
了。先让用户按一次按钮，意味着最常见的情形（打开 tab、什么都没有、猜不出到底是端点没有
模型还是压根没问过）与「端点确实空」无法区分。所以 tab 打开时就探测，每次访问一次，探测
期间表格会说明自己正在加载。

- 探测失败**必须**可见且可重试：表格点名失败原因，并提供重试。自动拉取之后保持沉默是不
  可接受的结果。
- 探测失败或返回为空，**必须**保持已策展的选择不变；FR-025 的「空 = 不限制」语义不受
  影响——空仍然表示端点提供的所有模型都可用。

**A3 — 两处界面订正，都来自「这个页面是干什么的」。**

- 模型提供商**列表**行上的「Coffer 引擎」徽章移除。那个页面管理的是提供商；Coffer 自己
  的引擎恰好跑在哪一条上，是关于引擎的事实，它应当在被设置的地方（内部引擎设置面板）以
  及该连接自己的详情页头部陈述。
- 详情页头部改用共享的 `ScopeControl`，取代只读的启用/停用徽章：此前列表能停用一条连接，
  而它自己的页面不能。`provider` 不声明按 agent 的 scope，因此该控件渲染为两段式
  停用/启用降级形态——并且现在它是这一状态**唯一**被展示和被修改的地方。

## 修订 2026-09-12b —— 策展条目要说明它是哪一类模型

> 状态：Draft。**把 J1 的 `models: list[str]` 细化为对象列表**；策展集合的含义（提供集合、
> 空 = 不限制）不变。

**为什么。** 一个 provider endpoint 提供的不只是 chat 模型。同一个 base URL、同一把 key 也
回答 embedding、image、video 与 audio 模型，而策展集合没有说明哪个是哪个——于是用户策展的
每个 id 都被提供给了每一个来问的面，一个 embedding 模型可以被选成某个 agent 的 chat 模型。
现在策展条目会说明它是**哪一类**模型，于是选择器只要它需要的那一类，而不是把每个 id 都端给
每一个面。

- **L1 —— `models: list[CuratedModel]`，其中 `CuratedModel = {id, modality}`。**
  `Modality` 是一个 `StrEnum`，共五个取值——`text`（默认）、`embedding`、`image`、`video`、
  `audio`。id 保留 J3 给它的一切性质：不透明、原样透传给厂商、只校验形状。modality 是
  Coffer 自己对这个 id 的标注，不是厂商告诉它的。
- **L2 —— **存储的** modality 就是真相；读取时不推断。** Coffer 只在两处推断 modality，
  且两处都是用户可在连接编辑器里改正的便利：把已存的纯字符串条目转换过来的那一条一次性
  Alembic 迁移，以及 endpoint introspection（`POST /api/v1/models/list-models`）——后者在
  每个发现的 id 旁返回一个推断出的 modality，让编辑器预填一个合理值。**不留 load-time
  垫片**：读取已存的行绝不重新推导 modality，这符合「迁移是一次性的」这条房规。
- **L3 —— 一条推断规则，两处共用。** 先把 id 转小写，然后：含 `embed` → `embedding`；
  含 `dall`、`image`、`imagen` 或 `flux`，或带有 `sd` / `sd<数字>` 词元 → `image`；
  含 `video` 或 `sora`，或带有 `veo` / `veo<数字>` 词元 → `video`；含 `whisper` 或
  `audio`，或带有 `tts` / `tts<数字>` 词元 → `audio`；其余 → `text`。长名按子串匹配；
  短名（`sd`、`veo`、`tts`）按完整词元匹配（id 以非字母数字切分），以免误标无关的 id。
- **L4 —— 每一个 CHAT 模型选择器都把策展集合收窄到 `text`。** 喂给
  `AgentModelCatalogueService.offered()` / `suggest()` 的激活连接策展 id（Web 选择器、
  频道 `/model` 卡片、回合内提示），以及 Coffer 投影进 agent 原生配置的 Codex 模型清单，
  一律只取 `text` 条目。`embedding` / `image` / `video` / `audio` 条目绝不会作为 chat
  模型出现。不做任何策展的连接仍然表示不限制，与此前完全一致。
- **接口形状。** `ProviderOut.models`、`ProviderCreateRequest.models`、
  `ProviderPatchRequest.models` 与 `ProviderModelsOut.models` 全部变为 `{id, modality}`
  对象数组（新增 `ProviderModel` component schema；`modality` 是默认值为 `text` 的枚举）。
  空依然表示不限制，patch 语义不变：`null` 保持集合不动，`[]` 清除限制。
- **L5 —— 界面：Models 标签页多出一列「类型」。** 连接详情页的模型表每一行现在读作
  模型 id · 类型 · 是否提供，其中类型是一个五选一的 Select，由 introspection 的猜测
  预填、就地改正——「provider 也应该支持图片、视频、embedding 模型」的答案就是这一列，
  而不是再开一张表。已经勾选提供的行上改类型会立刻 PATCH 策展集合；尚未勾选的行上改
  类型先留在界面上，等该行的开关被打开时一并写进条目。「类型」筛选器与既有的「是否提供」
  筛选器并排。下游每一个读这个集合的 chat 选择器——agent Overview 面板的模型 /
  fast-model 下拉框、内部引擎卡片的模型下拉框——只提供 `text` 条目；对于做了策展但其中
  没有 `text` 条目的连接，视为不提供任何 chat 模型，而不是回退到 endpoint 的完整清单
  （与 daemon 的行为一致）。

**细化：** J1/J2（策展集合与读取它的选择器）。**不变：** J3——Coffer 依旧不写死任何模型
**名字**，也不拿 id 去比对自己的名单；modality 是类别，不是名字。

## 范围

### 在范围内

- 后端 `provider` resource Kind（通过 ResourceService 实现 CRUD，自动审计 + 自动进入导出/导入）；凭证处理（将 secret 存入 Fernet vault，只保留 ref）；投影服务（将原生配置写入匹配 agent）；切换/激活操作；`PROVIDER_SWITCHED` 审计事件；导出/导入接入（注册 kind）；Claude `apiKeyHelper` 使用的密钥解析。
- 内部引擎 connection 选择：全局 `internal_default` 标志、`set_internal_default(name)` + `resolve_internal_connection()`、`provider_internal_default_set` 审计事件，供 Coffer 内部 LLM 引擎（memory organizer / reorg / distill）消费。
- 连接的策展 `models` 集合（2026-09-11 修订）：存在 `ProviderConfig` 上，由 create + patch 承载，由修订 0059 回填为空，并由每个提供该连接模型的选择器落地。
- 退役过滤（2026-09-11b 修订）：agent 自己的清单，减去已安装二进制自己的退役表说已经死掉的模型。该修订同时引入的逐 agent 策展 `models` 集合已**撤回**——模型策展先搬到 channel 上，随后在那边也被移除，于是再没有任何东西策展模型；agent 上的字段已移除，修订 0063 把它从既有行里剥掉。
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

### Config 字段（导出的 `config` 字典；确定性，不含机器本地 id）

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

> 本表记录的是**最初**的形状。修订 E1 移除了 `model` / `fast_model` / `wire_api`，并把
> `wire_format` 变成探测出的 `protocol`；2026-06-23 修订新增 `compatible_agents`；
> 2026-09-11 修订新增策展的 `models` 集合（空 = 不限制）。当前字段清单见
> [data-model.md](./data-model.md)。

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

与按 agent 激活分开，全局 `internal_default` 标志（所有 connection 中 ≤1）选择 Coffer 自身内部 LLM 引擎使用的 connection——memory organizer、reorg 和 distill。

- `set_internal_default(name)`：清除所有其他 connection 的 `internal_default`，再设置目标（顺序 clear-then-set，由单进程 daemon 串行化，保证全局单一内部默认不变量），并发出 `provider_internal_default_set` 审计事件。
- `resolve_internal_connection() -> ProviderConfig | None`：返回 `internal_default` connection 的 config，或在无 connection 被标记时返回 `None`。为 `None` 时，内部引擎（memory organizer / reorg / distill）是干净的 no-op 而非报错。
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

## 导出 / 导入（复用，几乎零引擎改动）

将 `provider` 建模为 ResourceService Kind，它就会自动进入导出 bundle（[Vault Export and Import](../../docs/decisions/vault-export-import.zh.md)）：

- `SyncExporter` 列出所有 kind → 通过 `resource_to_doc` 将每行序列化为 `resources/provider/<name>.yaml`。
- `SyncImporter` 按 `(kind, name)` 进行 reconcile。
- 凭证已以 Fernet 密文形式随行于 `credentials/<ref>.enc`，且仅在用户选择连同凭证一起导出时才出现。

接入点：定义 Kind，添加 `wire_provider_kind(...)` 辅助函数（镜像 `surfaces/http/wiring.py` 中的 `wire_kb_kind`），在 `surfaces/http/app.py` 的 composition root 中注册到 `app.state.kinds`。无需新迁移，无需 SCHEMA_VERSION bump。

## 审计（复用）

`ResourceService` create / update 自动发出 `RESOURCE_*` 事件（kind-redacted config）。需在 `backend/coffer/domain/audit.py` 的 `AuditEventType` 中添加 `PROVIDER_SWITCHED = "provider_switched"`，并在切换操作中通过 `AuditService.record(AuditEventType.PROVIDER_SWITCHED.value, ref=ResourceRef(kind="provider", name=<name>), actor=..., details={...})` 发出。同样添加 `PROVIDER_INTERNAL_DEFAULT_SET = "provider_internal_default_set"`，并从 `set_internal_default` 发出。

## HTTP API

手写 OpenAPI；005 风格——不做 contract-test 门控，手动同步。完整规范见 [contracts/api.openapi.yaml](./contracts/api.openapi.yaml)。

- `GET  /api/v1/providers` → 列出所有 profile（`{ "providers": [ ProviderOut, ... ] }`）
- `POST /api/v1/providers` → 创建（见下方凭证来源规则）
- `GET  /api/v1/providers/{name}` → 获取单条 profile
- `PATCH /api/v1/providers/{name}` → 更新可变字段（`base_url`、`compatible_agents`、`models`、`secret_value`）；`wire_format`/`protocol` 和 `credential_ref` 不可变；`secret_value` 可轮换存储的 secret；`models` 为整值替换（`[]` 清除策展集合）
- `POST /api/v1/providers/{name}/rename`（`{new_name}`）→ 改名；在一次操作中迁移自有 vault 条目、重指审计轨迹，并对激活中的连接重新投影。名字已被另一条连接占用时 409，本连接不存在时 404，名字未变时为 no-op
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
- **Model providers** 页（路由 `/model-providers`，位于侧边栏 RESOURCES 组——`provider` 是一个带列表 UI 的 resource kind，spec ui-shell 的 IA 规则把它放在那里）即 connection 库：一个 `DataTable`（复用共享组件；参见 SkillsPage / MCP 页），列 name / wire_format / base_url / model / active / internal，顶部操作 create，行操作 switch / set-internal-default / delete，外加 Embedding 卡片。该页只显示 connection（provider + model）信息——无 agent 名称、无 presets、无 modality 拆分。编辑 connection 通过 CLI（`coffer provider edit`）和 PATCH API 实现，Web 页不需要内联编辑功能。
- 逐 agent 的 connection + model 选择位于 **agent detail 页（Overview tab）**，按该 agent 的 wire 过滤，复用 activate API。Model providers 页不绑定 agent。
- 旧的 `/settings/models`、`/settings/providers` 与 `/settings/llm-connections` 路由重定向到 `/model-providers`。
- 新 hook 的测试需添加 `vi.mock`。

> **修订 2026-06-23（提供方预设）。** 添加连接的表单不再从 base_url + 密钥自动探测
> `protocol`，改为提供**提供方预设**选择（OpenAI / Anthropic / Google Gemini /
> DeepSeek / OpenRouter / Ollama），选中即填入接入地址与协议；另有
> **自定义**选项，会显示手动协议选择器，用于任意其他 OpenAI/Anthropic 兼容端点。
> 存储的数据模型不变（`protocol` 仍是 `ProviderConfig` 字段），仅创建时的选择方式改变。
> `detect-protocol` 探测端点保留供其他调用方使用，但表单不再使用它。

> **修订 2026-09-11（界面说清它管的是什么）。** 该页不再把这些东西叫「LLM 连接」——
> 在 UI 中它们就是**模型提供商**，也就是侧栏与 spec ui-shell 早已使用的名字。由此带来
> 四点界面变化，都不触及存储模型与 API：
>
> - 列表第二列及其筛选改为**厂商**（OpenAI、Anthropic……），而非 wire protocol。厂商不
>   存储，而是拿 `base_url` 去匹配预设列表**推导**出来——匹配不上任何预设的端点显示为
>   自定义；用户改掉某个预设的接入地址后同样会退回自定义。protocol 仍显示在详情页，
>   在那里它回答的是「这个端点怎么调」，而不是用来给列表分类。
> - **名称**列仍显示用户自己起的名字：它是路由与 CLI 寻址用的唯一 id，改成厂商名会把
>   同一厂商的两把 key 折叠成一行。
> - 详情页正文拆为**概览**与**模型**两个 tab，与 agent、MCP server 详情页一致。模型
>   tab 是一个 `DataTable`——每个模型 id 一行，行内开关控制是否提供，另有搜索与状态
>   筛选——因为「精选某个真实端点的模型」本来就是一个列表，而 Coffer 的每个列表都是
>   这张表。空选择仍然表示**不限制**。
> - **Moonshot (Kimi)** 预设已移除。

> **修订 2026-09-11b（2026-09-12 撤回之后的界面）。** Agent 页的「概览」标签在内置登录下没有任何
> 模型控件：`AgentModelSelection` 面板以及支撑它的 `GET|PUT …/models/selection` 客户端代码都已删除，
> 该分支只渲染一行灰字，说明模型按会话选择——在聊天的模型选择器里，或在频道里用 `/model <id>`。
> 非内置分支原样保留：选了连接，仍然由连接自己的模型填那两个模型 / 快速模型下拉框。
> catalogue 接口也已移除：网页上再没有任何界面向 agent 问它的模型清单，唯一还需要这份列表的卡片
> 在进程内直接读它。

> **修订 2026-09-12（A1–A3 之后的界面）。** 编辑对话框的「名称」字段可编辑，提交时先发
> 改名、再发 patch，详情页随后跟到新 URL（路由本身就是名字）。模型 tab 没有拉取按钮——
> 打开即探测，失败时提供重试。列表行不再有「Coffer 引擎」徽章，详情页头部只读的启用/
> 停用徽章由共享的 `ScopeControl` 取代。

## Acceptance Scenarios

根据 `agents/sdd.md`，本节每个场景都必须有至少一个测试携带
`@pytest.mark.acceptance(spec="provider-switching", scenario="…")`（Python）
或 `acceptance("provider-switching", "…", …)`（TypeScript）标记。

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

### Scenario: switch a wire back to the agent built-in login

- **Given** 一条 anthropic connection 处于活跃并已投影进 Claude Code，
- **When** 用户把该 wire 切回内建登录（`POST /providers/use-builtin/{wire}`），
- **Then** Coffer 托管的密钥被从 agent 的原生配置中移除，使其回落到自己的登录，且该
  connection 不再活跃；该操作幂等（无活跃项时为 no-op）。参见
  [Provider Switching](../../docs/decisions/provider-switching.md) 修订 D1/D3
  （connection 是可选的覆盖项）。

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
- **When** exporter 运行，随后在全新 DB 上运行 importer，
- **Then** profile 行以相同的 `config` 字段被还原，凭证密文出现在 `credentials/<ref>.enc`，bundle 明文中无 secret 暴露。

### Scenario: the command line covers create, list, and switch

- **Given** daemon 正在运行，
- **When** 用户从 CLI 运行 `coffer provider add`、`coffer provider list --json`、`coffer provider switch`，
- **Then** 每个操作与 HTTP API 效果相同，`list --json` 返回机器可读输出。

### Scenario: the connections page lists profiles and their compatible agents

- **Given** 连接页以两条 mock 连接渲染（各带 `compatible_agents` 集合），
- **When** 页面渲染时，
- **Then** 列出两条连接及其兼容 agent 标签，且**无**每行「Switch」操作——激活按 agent，落在 Agent 概览页
  （TypeScript acceptance 测试）。

### Scenario: route an openai-compatible connection to Claude Code via compatible_agents

- **Given** 已注册一个 Claude Code agent，并创建一条 `openai`-wire 连接，`compatible_agents = ["claude_code"]`（agnes 场景），
- **When** 用户激活该连接，
- **Then** 它投射进 Claude Code 的 `settings.json`（anthropic 形态），且
  `apiKeyHelper = "coffer provider key --connection <name>"`，
  `GET /providers/{name}/key` 返回正是该连接的 key。

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

### Scenario: list a provider's models

- **Given** 正在新增或编辑一条连接，已填入 provider（以及该 provider 需要的
  base URL / credential ref）
- **When** 拉取该 provider 的模型
- **Then** Coffer 返回该 provider 暴露的模型 id 供选择；若一个都列不出，
  则返回空列表并附一条消息，用户仍可手动输入模型 id

### Scenario: test a model connection

- **Given** 一条连接的 provider、模型 id 和（需要时的）credential ref
- **When** 测试该连接
- **Then** Coffer 向 provider 发一个最小请求，报告成功或一条人话化的失败消息，
  且不持久化任何东西

### Scenario: test or fetch models with an inline unsaved secret

- **Given** 连接对话框已打开，尚未保存任何连接（也无对应 credential ref），
- **When** 用户输入明文 API key 并触发「测试连接」或「拉取模型」（`POST
  /models/test-connection` / `POST /models/list-models` 携带 `secret_value`、
  不含 `credential_ref`），
- **Then** introspection 服务将明文 key 直接传给 provider、不查 credential vault，
  探测成功，拉取到的模型填入可选下拉框（见
  [Provider Switching](../../docs/decisions/provider-switching.zh.md) amendment D6）。

### Scenario: the agent's model picker offers a fixed list without free-form entry

- **Given** 一个绑定到无覆盖连接的 agent 的会话，
- **When** 打开模型选择器，
- **Then** 它给出一个固定下拉（无自由输入「Custom…」项），选项来自草稿连接自己的模型——有策展集合时
  就是该集合，否则是 introspect 其 endpoint 得到的结果——再加上已暂存的取值，绝不读连接存储的
  `model` 字段（TypeScript 验收测试；「激活连接回答选择器提供什么」见 2026-09-11c 修订）。

### Scenario: curate which of a connection's models are offered downstream

- **Given** 一条以 `models: ["opus", "sonnet", "opus"]` 创建的 LLM 连接，
- **When** 读回它，再 patch 为 `models: ["haiku"]`，然后再 patch 一个无关字段，
- **Then** 创建响应、`GET /api/v1/providers/{name}` 和列表路由都返回
  `["opus", "sonnet"]`（原样存储、去重、保持用户选择的顺序）；patch **整体替换**为
  `["haiku"]`；无关的 patch 不影响它；这次修改可在更新本就发出的 `resource_updated`
  审计条目里看到——没有属于它自己的审计事件。

### Scenario: a connection with no curated models offers every model the endpoint serves

- **Given** 一条创建时不带 `models` 的连接（默认值，也是修订 0059 之前创建的每条连接的取值），
- **When** 读回它，再策展为 `models: ["opus"]`，然后 patch 为 `models: []`，
- **Then** 创建时与 `[]` patch 之后它都返回 `[]`——不限制、即 endpoint 的完整目录——
  `[]` 清除了策展集合。

### Scenario: rename a connection and keep its credential, audit trail and projection

- **Given** 一条激活中的连接 `acme`，带内联 secret，并已投影进一个已注册的 Claude Code agent，
- **When** 调用 `POST /api/v1/providers/acme/rename {"new_name": "acme-eu"}`，
- **Then** 连接在 `acme-eu` 下响应、在 `acme` 下不再响应，其 `credential_ref` 为
  `provider/acme-eu/key` 且 secret 可在该处读到、旧 ref 已消失，agent 被投影的
  `apiKeyHelper` 指向 `acme-eu`，并且以新名字查询时能拿到记在旧名字下的审计行。

### Scenario: reject a rename onto a name another connection already uses

- **Given** 两条连接 `acme` 与 `taken`，
- **When** 把 `acme` 改名为 `taken`，
- **Then** 响应为 409 `RESOURCE_ALREADY_EXISTS`，两条连接仍以各自原名解析、凭据完好。

### Scenario: an agent bound to a renamed connection still resolves its key

- **Given** 一个跑在连接 `acme` 上的 Claude Code agent，
- **When** `acme` 被改名，
- **Then** `GET /api/v1/providers/<新名字>/key` 返回同一个 secret，被投影的配置里指向的
  连接是新名字，且该连接仍处于激活状态、仍与该 agent 兼容。

### Scenario: the models table lists the endpoint's models when it opens

- **Given** 一条端点能列出模型清单的连接，
- **When** 打开其详情页的模型 tab，
- **Then** 无需任何用户操作即完成探测，端点的模型 id 填满表格、每行各有自己的提供/不提供
  开关——不存在「拉取模型」按钮。

### Scenario: a failed model introspection says so and offers a retry

- **Given** 一条端点会拒绝模型列表探测的连接，
- **When** 打开模型 tab，
- **Then** 失败在界面上被说明并附带重试控件，且该连接已有的策展选择原封不动。

### Scenario: curate an embedding model alongside chat models on one connection

- **Given** 一条端点同时提供 chat 与 embedding 模型的连接，
- **When** 以
  `models: [{"id": "gpt-4o"}, {"id": "text-embedding-3-large", "modality": "embedding"}]`
  创建它、读回，并通过 `POST /api/v1/models/list-models` 探测其端点，
- **Then** 存储的集合保留两条条目及其 modality——`gpt-4o` 为 `text`（默认值）、
  `text-embedding-3-large` 为 `embedding`——每次读取返回的都是**存储的** modality 而非读取
  时重新推导的值；探测响应在每个发现的 id 旁携带推断出的 modality 供编辑器预填（含 `embed`
  的 id 回来是 `embedding`，无关的 id 是 `text`）。

### Scenario: a non-text curated model never reaches a chat model picker

- **Given** 一条激活的连接，策展了一个 `text` 模型和一个 `embedding` 模型，
- **When** 向 agent 的模型选择器提供选项（`AgentModelCatalogueService.offered()` /
  `suggest()`、频道 `/model` 卡片），并把 Codex 清单投影进 agent 的原生配置，
- **Then** 三处都只出现那个 `text` 条目——`embedding` 条目不会在任何地方作为 chat 模型被
  提供——而不做任何策展的连接仍然表示不限制。

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

**导出 / 导入**

- **FR-015**：`provider` kind 必须注册到 `app.state.kinds`，使 `SyncExporter`/`SyncImporter` 自动处理。无需新迁移或 SCHEMA_VERSION bump。

**审计**

- **FR-016**：`PROVIDER_SWITCHED`（值 `"provider_switched"`）必须加入 `AuditEventType` 并在每次成功切换时携带 `{from, to, wire_format, agents}` 发出。`RESOURCE_CREATED`、`RESOURCE_UPDATED`、`RESOURCE_DELETED` 由 `ResourceService` 自动发出。

**界面**

- **FR-017**：创建、切换和删除操作必须可通过（a）REST API、（b）`coffer provider ...` CLI（含 `--json`）、（c）Web Providers 页面访问。编辑 profile（PATCH）仅通过 REST API 和 CLI（`coffer provider edit`）提供；Web 页不需要内联编辑功能。
- **FR-018**：CLI `key` 子命令必须支持 `--wire <wire_format>`（按该 wire 的活跃 profile 解析）。不支持位置参数 `<name>` 解析；仅接受 `--wire` 形式。

**内部引擎 connection**

- **FR-019**：`ollama` wire 仅供内部，不投影到任何 agent：`target_for(WireFormat.ollama)` 必须返回 `None`，ollama connection 从不 `is_active`，激活它不写任何原生配置。
- **FR-020**：`credential_ref` 必须可选——anthropic/openai 必填，ollama 不存在。创建时，既不提供 `secret_value` 也不提供 `credential_ref` 仅对 `wire_format=ollama` 合法；对 anthropic/openai，FR-004 的 exactly-one 规则不变。
- **FR-021**：全局最多一条 connection 的 `internal_default=true`。`set_internal_default` 必须先清除所有其他 connection 的 `internal_default`，再设置目标（顺序 clear-then-set，由单进程 daemon 串行化）。导入时若有 >1 内部默认，则归一化：保留最近更新的，清除其余。

  这条不变量必须由**数据库**来保证，而不是只靠那个方法。`internal_default` 就是一个普通的 config 字段，因此通用的资源更新路由、`coffer provider edit`、以及被导入的文档都能绕过 clear-then-set 直接写它——而实测发现一个线上金库里有两条 connection 同时被标记，这让「内部引擎到底用哪条连接」变成一个没有定义的问题。一个作用在 `kind` 上、仅覆盖被标记的 provider 行的部分唯一索引，使第二条在存储层就无法表示，无论是谁写的。
- **FR-022**：`POST /api/v1/providers/{name}/internal-default` 必须将所命名的 connection 设为内部引擎默认（应用 FR-021），发出 `provider_internal_default_set` 审计事件，并返回更新后的 `ProviderOut`。
- **FR-023**：`resolve_internal_connection()` 必须返回 `internal_default` connection 的 `ProviderConfig`，或在无 connection 被标记时返回 `None`。为 `None` 时，内部引擎（memory organizer / reorg / distill）必须是干净的 no-op 而非报错。
- **FR-024**：独立的 `ModelConfig` 注册表（model CRUD REST + `coffer model` CLI）必须退役。内部引擎必须通过 `build_chat_model(connection, ...)`（按 `wire_format` 分派）从内部默认 connection 构建其 chat model。provider introspection 路由（`POST /api/v1/models/list-models`、`/api/v1/models/test-connection`）必须保留。

**策展模型集合**

- **FR-025**：`ProviderConfig` 必须携带 `models`——该连接向下游**提供**的模型 id 集合（最初写作 `list[str]`；**已由 FR-029 细化**为 `{id, modality}` 对象列表）。**空**列表必须表示不限制（endpoint 提供的所有模型），必须是默认值，也必须是修订 0059 之前创建的每条连接的取值。该字段绝不可被当作「选中的模型」读取：选择仍在使用处（E1/E3）。id 只校验形状——非空白、按序去重、至多 200 个且每个至多 200 字符——并且绝不可与 Coffer 自己写死的模型名单比对。
- **FR-026**：`ProviderCreate.models`（`null` ⇒ 空）与 `ProviderPatch.models` 必须承载该集合；`ProviderOut.models` 必须返回它。`PATCH` 必须像 `compatible_agents` 一样整值替换——`null` 保持不变，`[]` 清除限制——且不得为此新增路由。对它的修改必须搭乘 provider 更新本就发出的 `resource_updated` 审计事件。

**改名**

- **FR-027**：连接**必须**可以通过它自己的路由（`POST /api/v1/providers/{name}/rename`）
  改名，而**不是**通过 `ProviderPatch` 的某个字段。该操作**必须**一起迁移：资源行、连接
  自有的 vault 条目（`provider/<name>/key`——除非另有资源也引用该 ref，此时**必须**保持
  原样）、记在 `provider:<old>` 名下的 `audit_log` 行，以及——当连接处于激活状态时——它在
  每个兼容 agent 原生配置中的投影。**必须**记录一条同时写明新旧名字的 `resource_renamed`
  审计事件。名字已被另一条连接占用时，**必须**在写入任何内容**之前**以
  `RESOURCE_ALREADY_EXISTS`（409）拒绝；连接不存在时**必须**为 404；改成当前名字**必须**
  是 no-op。

**连接详情页的模型探测**

- **FR-028**：模型 tab **必须**在打开时自动探测端点，无需用户操作，并**必须**展示它正在
  探测。探测**失败**时**必须**在界面上说明并提供重试——**不得**静默失败。探测失败或返回
  为空时**必须**保持已策展的 `models` 选择不变，且 FR-025 的「空 = 不限制」语义**不得**
  受影响。

**模型 modality**

- **FR-029**：`ProviderConfig.models` **必须**是**对象**列表而非字符串列表：每个条目是一个
  `CuratedModel`，形如 `{id: str, modality: Modality}`，其中 `Modality` 是一个 `StrEnum`，
  取值为 `text`（默认）、`embedding`、`image`、`video`、`audio`。id 保留 FR-025 赋予它的
  一切性质（不透明、原样透传给厂商、只校验形状、按序去重、空列表 = 不限制）。**存储的**
  modality 就是真相：Coffer **必须**只在两处推断 modality——把已存的纯字符串条目转换过来的
  那一条一次性 Alembic 迁移，以及 endpoint introspection（FR-030）——两处都可由用户在连接
  编辑器里改正。**不得**存在 load-time 垫片：读取已存的行**不得**重新推导 modality。两处
  共用的推断规则作用于小写化后的 id：含 `embed` → `embedding`；含 `dall`、`image`、
  `imagen` 或 `flux`，或带有 `sd` / `sd<数字>` 词元 → `image`；含 `video` 或 `sora`，或带有
  `veo` / `veo<数字>` 词元 → `video`；含 `whisper` 或 `audio`，或带有 `tts` / `tts<数字>`
  词元 → `audio`；其余 → `text`。长名**必须**按子串匹配，短名（`sd`、`veo`、`tts`）**必须**
  按完整词元匹配（id 以非字母数字切分），以免误标无关的 id。
- **FR-030**：`POST /api/v1/models/list-models` **必须**在每个发现的 id 旁返回一个推断出的
  modality（按 FR-029 的规则），让连接编辑器预填一个用户可改正的合理值；它返回的是建议，
  绝不是已存事实。每一个 CHAT 模型选择器**必须**把激活连接的策展集合收窄到 modality 为
  `text` 的条目——喂给 `AgentModelCatalogueService.offered()` / `suggest()` 的 id（Web 选择器、
  频道 `/model` 卡片、回合内提示），以及 Coffer 投影进 agent 原生配置的 Codex 模型清单。
  `embedding`、`image`、`video` 或 `audio` 条目**绝不可**作为 chat 模型出现。不做任何策展的
  连接**必须**仍然表示不限制。`ProviderOut.models`、`ProviderCreateRequest.models`、
  `ProviderPatchRequest.models` 与 `ProviderModelsOut.models` **必须**全部承载
  `{id, modality}` 对象；patch 语义不变（`null` 保持集合不动，`[]` 清除限制）。

### 关键实体

- **ProviderProfile**：kind 为 `provider` 的一个 Resource，标识符为
  `provider:<name>`。持有 wire format、base URL、可选的 credential ref（ollama
  没有）、它向下游提供的策展 `models` 集合（空 = 不限制）、按 wire 的 `is_active`
  状态，以及全局 `internal_default` 标志。绝不持有原始 secret，也绝不持有某个被选中
  的模型。
- **`CuratedModel` / `Modality`**：一条策展条目 `{id, modality}`，以及它携带的、取值为
  `text` / `embedding` / `image` / `video` / `audio` 的 `StrEnum`（FR-029）。modality 是
  Coffer 自己对一个不透明 id 的标注——存储下来，读取时绝不重新推导——也正是它把一条连接的
  策展集合收窄成选择器可以提供的 chat 模型。
- **`apply_anthropic_settings` / `apply_codex_provider`**：`domain/provider/projection.py`
  中的纯函数，直接返回新的原生配置 TEXT。类比 `domain/agent/mcp_install.py` 的
  `apply_install`。没有 `ProjectionPatch` dataclass，也没有 `build_patch()` 函数。
- **`ProviderService._project`**：`application/provider/service.py` 中的私有方法，调用
  上述纯投影函数并执行文件写入。
- **`ProjectionTarget` / `target_for(wire)`**：`domain/provider/projection.py` 中的
  helper，把 `wire_format` 映射到目标配置文件描述符；对 `ollama` 返回 `None`（仅内部
  使用，不投影）。
- **`ProviderService.resolve_active_key(wire)`**：只接受一个 `wire_format` 字符串；该
  方法上没有按名字解析的路径。
- **`ProviderService.set_internal_default(name)`**：先清掉其他所有 connection 的
  `internal_default` 再设置目标；发出 `provider_internal_default_set`。
- **`ProviderService.resolve_internal_connection()`**：返回 internal-default connection
  的 `ProviderConfig`，或 `None`（⇒ 内部引擎干净地成为 no-op）。
  `build_chat_model(connection, ...)` 据此构建内部引擎的 chat model，按 `wire_format`
  分派。

## 成功标准

- **SC-001**：从全新安装开始，用户可以添加一条 anthropic provider profile，激活它，并通过一条 `coffer provider switch` 命令让 Claude Code 使用新 endpoint。
- **SC-002**：原始 key 不会出现在 `settings.json`、`config.toml` 或导出 bundle（`resources/provider/*.yaml`）中——在集成测试中通过自动扫描验证。
- **SC-003**：每个 Acceptance Scenario 都有至少一个 `acceptance(spec="provider-switching", scenario="…")` 标记的测试，`make verify-acceptance` 报告零遗漏场景。
- **SC-004**：`make verify` 本地和 CI 通过。
- **SC-005**：激活 profile 只写入定义的托管键集，不触碰任何托管集以外的键。
- **SC-006**：当配置了 `internal_default` connection 时，Coffer 内部引擎（memory organize / reorg / distill）在其上运行；当无 connection 被标记 `internal_default` 时，内部引擎是干净的 no-op。

## 假设

- Spec agent-registry（PR #25）已合并；`AgentType`、`AgentConfig`、agent CRUD 和 `on_delete` hook 均可用。
- `EncryptedCredentialStore`（Fernet vault）和 `ConfigFileStore.write_text_atomic` 均可用（spec mcp-gateway）。
- `tomlkit` 已在后端 Python 依赖中（MCP TOML 路径支持时已添加）。
- Coffer 作为单用户个人工具运行；除现有 `X-Coffer-Token` 门控外，无需多用户访问控制。
- 用户的 `~/.claude/settings.json` 和 `~/.codex/config.toml` 对 Coffer 可写。若文件不存在，Coffer 创建只含托管键的文件。
- Provider drift-verify（检查原生配置是否与活跃 profile 一致）延期到 spec 4.9。
