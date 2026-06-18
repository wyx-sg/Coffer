# ADR-026 — 网关侧的每 agent MCP 服务器 scope

> English: [ADR-026-per-agent-mcp-scoping.md](./ADR-026-per-agent-mcp-scoping.md)

- **状态：** Accepted
- **日期：** 2026-06-19
- **决策者：** Yuxing Wu
- **Spec：** 001-mcp-gateway 与 004-agent-registry（实现前更新两份 spec.md）
- **修订：** [ADR-007](./ADR-007-everything-is-a-resource-kind.md)（agent kind 现在携带 scope）以及 [ADR-018](./ADR-018-tool-retrieval-for-overload.md) / [ADR-024](./ADR-024-builtin-agent-is-internal-capability.md)（`coffer__search_tools` 排序现在感知 scope）
- **相关：** [ADR-004](./ADR-004-capability-state-model.md)（能力偏好存于 DB）、[ADR-005](./ADR-005-session-subprocess-model.md)（每会话独立上游子进程）

## 背景

Coffer 把许多上游 MCP 服务器聚合到一个端点之后，再把它们暴露给任何通过 shim 接入的
agent。今天这个面是**全局**的：每个跑 shim 的 agent 都触达同一组启用的服务器，因为网关
根本不知道一个会话另一端是**哪个** agent。来自 [ADR-004](./ADR-004-capability-state-model.md)
的启用/禁用 curation 是网关全局的，而非每 agent 的。

这正是竞品一致都有、而 Coffer 缺失的唯一能力。MCP 生态调研（`docs/research/mcp-ecosystem.md`）
得出一个**确认、一致**的结论：每一个可比网关都让各客户端看到不同的精选服务器/工具子集——
ContextForge 的 **virtual server**、MetaMCP 的 **namespace**、MCPJungle 的 **tool group**、
Docker 的 **profile**。Coffer 是唯一「每 agent 整个网关」的那个。随着用户注册更多服务器，
把全部交给每个 agent 既浪费下游模型的上下文，又暴露了 agent 本不该调用的工具。

阻碍一直是身份：网关会话不携带 agent 身份，因此没有可供 scope 的对象。Spec 004 本就会把一个
`coffer` MCP 条目写进每个 agent 的配置（一键安装），那正是给这个身份盖戳的天然位置。

## 决策

新增**每 agent 服务器 scope**，在网关侧强制执行。四步。

### 1. 身份随会话传递

安装的 `coffer` MCP 条目以 `--agent <name>` 参数携带 agent 名。shim 把它作为
`X-Coffer-Agent` 请求头转发；网关把会话归属到该 agent。**不**出示身份的会话——例如
`coffer__ask` 背后的进程内置 agent（[ADR-024](./ADR-024-builtin-agent-is-internal-capability.md)）
——被视为 **unscoped（完全访问）**，于是每个既有客户端原样工作。

### 2. 两种 scope 模式，及新服务器语义

每个 agent 有一个 scope **mode**：

- **`auto`**（默认，也是当前行为）——该 agent 看到每一台启用的 MCP 服务器。新 agent 默认在此，
  因此该特性完全向后兼容。
- **`selected`**——该 agent 只看到一份显式的服务器 allowlist。

新增的服务器对 `auto` agent **自动**出现，但**绝不**自行加入某个 `selected` agent 的
allowlist——选择更小的面始终是一个深思的决定，新服务器无法悄悄把它撑大。

### 3. 在 list **与** search **与** call 处强制有效 scope

一个 agent 的**有效 scope**（effective scope）= 启用的服务器，在 `selected` 时再与其 allowlist
求交集。网关在任何可能呈现能力的地方都应用它：`tools/list`、`resources/list`、`prompts/list`，
以及 `coffer__search_tools` 排序（让越界工具根本不参与排序）。关键是它**也**拒绝对越界服务器的
**直接** `tools/call` / `resources/read` / `prompts/get`——即便能力名是直接给出的。仅在 list 时
隐藏是一个安全缺口：一个已经知道某 `<server>__<tool>` 名的模型本可绕过它直接调用。调用路径才是
真正的边界。

### 4. 数据模型——两张级联表

`agent_mcp_scope` 每个 agent 一行（其 `mode`，FK 指向 agent 资源）。`agent_mcp_scope_server`
以 `(agent, server)` 行保存 `selected` 的 allowlist，每行都是指向资源的 FK。两个 FK 都
`ON DELETE CASCADE`：删除 agent 会丢掉它的 scope 与 allowlist；删除服务器会把它从每个曾列入它的
allowlist 中丢掉（拥有它的 agent scope 仍在，只是少了那台服务器）。没有以名字为键的字符串，没有
孤儿行。迁移 `0023`。

## 备选方案

A — **按工具而非按服务器的粒度。** 每 agent scope 单个 `<server>__<tool>` 能力，而非整台服务器。
**否决。** ADR-004 已提供网关全局的按工具 curation；每 agent 的**服务器** scope 才是竞品交付、也是
用户真正会去想的那个粗粒度旋钮（「这个 agent 拿到 GitHub 服务器」）。每 agent 每工具是一份没人想维护
的巨大 allowlist；真有需要再说。

B — **默认安全拒绝（新服务器在被允许前隐藏）。** 把 `selected` 设为默认，把每台新增服务器对所有人隐藏，
直到被显式授予。**否决。** 它破坏向后兼容（每个既有 agent 都会变黑），并把零配置承诺反转。`auto` 默认

- 对 `auto` agent 自动纳入让简单路径保持简单；`selected` 是 opt-in。

C — **可复用的命名 scope profile**，跨 agent 共享（类似 ContextForge 的 virtual server）。
**暂否（YAGNI）。** 一个只有少数 agent 的单用户并不需要 profile 注册表；每 agent mode + allowlist 已够。
若日后真的需要跨 agent 共享，命名 profile 层可以在不改变强制接缝的情况下后加。

D — **不带 FK 级联的、以名字为键的 scope 表**（把 agent/服务器名当字符串存）。**否决。** 它会在服务器或
agent 被删时留下孤儿 allowlist 行，并重新引入
[ADR-003](./ADR-003-resource-identifier-format.md) 的代理 id 正要避免的 rename/身份漂移。FK 级联让完整性
自动保持。

## 后果

- **补上唯一一致的竞品缺口。** Coffer 现在在「每客户端精选子集」上与 ContextForge / MetaMCP / MCPJungle /
  Docker 对齐，键于 shim 本就能携带的 agent 身份。
- **天然向后兼容。** `auto` 默认 + 无身份即 unscoped，意味着每个既有 shim 会话与进程内置 agent 在用户把某个
  agent 切到 `selected` 之前，行为与从前完全一致。
- **搜索现在感知 scope**（修订 ADR-018/ADR-024）：`coffer__search_tools` 只对调用方 agent 的有效 scope 排序，
  因此检索不会浮现一个该 agent 随后调不到的工具。
- **调用路径是安全边界，而非 list。** 越界调用在 `tools/call` / `resources/read` / `prompts/get` 处被拒绝，
  所以 list 时隐藏是 UX 便利，不是关卡。
- **新增界面：** spec 004 增加 `GET`/`PUT /agents/{name}/mcp-scope`、一个 agent 详情页控件，以及安装写入器中的
  `--agent` 参数；spec 001 增加网关强制与迁移 `0023`（两张级联表）。停留在默认的 agent 无任何变化。
