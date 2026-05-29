# ADR-004: MCP 能力状态 —— 偏好持久化于 DB，列表实时查询上游

> English: [ADR-004-capability-state-model.md](./ADR-004-capability-state-model.md)

**Status**: 已采纳 (Accepted)
**Date**: 2026-05-20
**Deciders**: Yuxing Wu
**Related**: spec `001-mcp-gateway` (User Story 2)

## 背景

一个 MCP 服务器会暴露 tools、resources 与 prompts。Gateway 需要知道每个上游
提供了什么、用户选择暴露哪些，以及在上游变化时（升级、插件重载、重启）如何
让两者保持一致。

MCP 协议本身通过 `notifications/tools/list_changed`、
`notifications/resources/list_changed` 与 `notifications/prompts/list_changed`
来表达动态能力。因此能力发现属于**运行时关注点**，而非配置层关注点。

两种极端设计框定选择：

- **将一切缓存在数据库**。工具名、schema、描述以及启用标志全部进入
  `mcp_capabilities` 表。UI 直接从表中渲染。
- **完全不缓存**。每次 list / call 都打到上游。启用/停用状态仅以列表形式
  存在于 `mcp_servers.config` JSON 中。

两者都有失败模式。前者与协议的动态模型对抗，并积累过时 schema；
后者牺牲 UI 响应速度，且在上游离线时丢失有意义的用户状态。

## 决定

**数据库只存用户偏好。能力列表实时查询。**

- `mcp_capability_preferences (resource_id, capability_type, capability_key,
enabled, first_seen_at, last_seen_at)` —— **唯一**持久化的能力状态。
- Tool / resource / prompt 的名称、schema、描述**永不**持久化。每次 `list_*`
  请求时实时拉取，按 session 在内存中缓存，TTL 60 秒。
- 缓存失效触发条件：
  - TTL 到期。
  - 上游 `notifications/*/list_changed`（同时会转发给下游客户端）。
  - 用户主动刷新 (`coffer mcp refresh <name>`)。
  - 上游 session 重启。
- 每次成功 list 后，将偏好与实时列表对账：新出现的 capability key 插入一行
  （依据该服务器的 `auto_enable_new_capabilities` 策略决定是否启用）；
  消失的 capability key **不**会被删除（这样用户的选择能在上游波动中保留下来）。

## 后果

**正面**

- 不存在缓存陈旧的 bug 类。在 60 秒缓存窗口的边界上，UI、gateway 列表和上游
  始终是一致的。
- 不存在 schema 漂移的 bug 类。上游修改某个工具的 `inputSchema` 无需任何迁移；
  下一次 `tools/list` 就能反映出来。
- 用户意图（启用/停用）天然在上游升级时保留 —— 以 capability 名作为键，
  这是当前唯一稳定的身份。
- 与 MCP 协议的动态能力设计保持一致，而非与之对抗。

**负面**

- 当上游离线时，UI 无法为用户已知的 capability 展示 schema 或描述；
  只能给出名字（来自 `last_seen_at`）与启用标志。
- 每次经 gateway 的 `list_*` 在缓存未命中时至少要对每个上游产生一次往返。
  上游多了之后可能给单次客户端请求增加几十毫秒 —— 判断为可接受。
- 那些已永久消失的 capability 的偏好仍会在 DB 中累积。清理留给人工或未来的
  自动化；其总量受限于用户曾经见过的 capability 数量，在单用户场景下规模很小。

## 备选方案

**将完整能力列表缓存到 DB，并定期同步**。被否决。

- 与 `list_changed` 语义相悖 —— 协议本意是动态的。
- 引入可被用户察觉的同步滞后（schema 缓存说一套，上游实际另一套）。
- 上游一旦新增字段就要强制 schema 迁移。
- 相对于内存缓存（已足够快）并无明显收益。

**完全实时（不做任何缓存）**。被否决。当 gateway 注册有 5+ 上游、AI 在
多轮对话中频繁执行 `list_tools` 时，延迟代价会被放大。60 秒的内存缓存能
覆盖常见情形。

**基于 LLM 的语义去重，剔除冗余能力**。被否决。脆弱（名称 vs 描述 vs schema）、
昂贵（每次 list 都要调一次 LLM）、不透明（用户无法预测两个 `read_file` 工具
最终留下哪一个）。用户显式的偏好开关才是正确的控制面。

**持久化 schema + 描述，但靠 `notifications/*/list_changed` 维持新鲜度**。
被否决。许多 MCP 服务器在重启时并不可靠地发出 `list_changed`；这样仍然会
积累过时 schema。我们决定彻底消除这种歧义。
