# ADR-003: 资源标识符格式 —— `<kind>:<name>`，而非 URN

> English: [ADR-003-resource-identifier-format.md](./ADR-003-resource-identifier-format.md)

**Status**: 已采纳 (Accepted)
**Date**: 2026-05-20
**Deciders**: Yuxing Wu
**Related**: [ADR-001](ADR-001-resource-framework-upfront.md)

## 背景

资源 (resource) 需要一个稳定的、对外可见的标识符：

- CLI 中会展示它 (`coffer resource show <id>`)。
- API 在 URL 与请求/响应体里使用它。
- 未来的跨资源引用会持有它（例如某个 Agent 的 `tools` 字段列出它可使用的
  MCP 服务器）。
- DB 需要主键，但磁盘上的表示并不必须与对外形式相同。

候选方案：

- **纯 UUID** —— 全局唯一，但不可读。
- **完整 URN（按 RFC 8141）** —— `urn:coffer:mcp_server:filesystem`。
- **`<kind>:<name>` 冒号分隔** —— `mcp_server:filesystem`。
- **`<kind>/<name>` 路径风格** —— `mcp_server/filesystem`。
- **复合主键，无外部字符串形式** —— 只有 `(kind, name)`。

## 决定

外部标识符使用字符串 **`<kind>:<name>`**，其中 `kind` 与已注册的资源 kind
对应，`name` 由用户选定（在 kind 内部唯一）。

数据库布局：

- 代理主键 `id INTEGER PRIMARY KEY AUTOINCREMENT`，用于联表和外键。
- `UNIQUE (kind, name)` 约束保证外部标识符的唯一性。

`ResourceRef(kind: str, name: str)` 值对象负责在领域边界处的解析与序列化；
原始字符串永远不会进入领域层。

## 后果

**正面**

- 简短、可读。`mcp_server:filesystem` 在调试时不需要任何解码器即可识别。
- 自描述：前缀直接说明该向哪种 kind 询问，在许多代码路径上省去一次查询。
- 干净地映射到 URL：`/api/v1/resources/mcp_server/filesystem`。
- 干净地映射到 CLI：`coffer resource show mcp_server:filesystem`。
- 若日后跨实例配置共享变得重要，与 URN 完全前向兼容 ——
  `urn:coffer:mcp_server:filesystem` 是严格超集，可加性迁移。

**负面**

- 字符串形式中含冒号，而冒号在许多其他场景（URL、环境变量）中也是分隔符。
  消费资源引用的工具必须把*第一个*冒号作为 kind/name 分隔符，并仅当未来规约
  要求时才允许名字内含冒号（当前约定：kebab-case 名字，不含冒号）。
- 「这个字符串是什么？」需要读者了解 Coffer 的约定。IDE 或文档应在每个引用
  附近注明 `<kind>:<name>`。

## 备选方案

**完整 URN（按 RFC 8141）** (`urn:coffer:mcp_server:filesystem`)。被否决。
`urn:coffer:` 前缀宣示了一个命名空间，但 Coffer 是单用户本地优先工具 ——
并不存在另一个 Coffer 需要区分。多出的 12 个字符纯属仪式。若跨实例共享在
未来真的成为问题，本 ADR 会被一份新 ADR 取代，改为采用 URN。

**纯 UUID** (`6ba7b810-9dad-11d1-80b4-00c04fd430c8`)。被否决。不可读、丢掉
kind 的自描述能力，并且每个引用还要额外带一个 `kind` 字段。

**`<kind>/<name>` 路径风格**。功能上等价，论 URL 友好性也说得过去；但因为
斜杠的语义已被严重过载（URL 路径分隔符、文件路径、众多 DSL 中的标识符），
予以否决。冒号让「kind 命名空间 + name」的关系一目了然，并与 `package:symbol`、
`gem:version`、`pip:dist` 等约定保持一致。

**复合主键，从不序列化为一个字符串**。被否决。跨资源引用 (Agent.config) 需要
单一字段承载一个引用；强制到处使用 `{kind, name}` 对象只会让配置和 API
变得臃肿，毫无收益。
