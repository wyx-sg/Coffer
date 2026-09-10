# 参考文档

本节是项目的**权威文档，在构建时从代码仓库同步生成** — 它是规范、决策、
项目记忆和工程规范的唯一可信来源。如需了解各部分如何协作，请参阅
[架构](/zh/architecture/overview)章节；参考文档则提供原始的、权威的细节。
可在左侧边栏浏览全部内容，或使用顶部搜索框快速定位。

## 规范 (Specs)

| 规范                | 状态                          | 阅读                                            |
| ------------------- | ----------------------------- | ----------------------------------------------- |
| MCP Gateway         | 已采纳 — 代码已随 PR #14 合并 | [spec](/zh/reference/specs/mcp-gateway/spec)    |
| UI Shell 与视觉语言 | 已采纳 — 代码已随 PR #23 合并 | [spec](/zh/reference/specs/ui-shell/spec)       |
| Agent Registry      | 已采纳 — 开发中               | [spec](/zh/reference/specs/agent-registry/spec) |

MCP Gateway Desktop 规范已**退役**：Tauri 桌面外壳被移除，值得保留的需求被吸收进 MCP Gateway 规范，
成为 FR-022 – FR-026（单层级发布压缩包、聚合 `SHA256SUMS`、守护进程提供 Web UI、`coffer open`，
以及 frozen 启动时的二进制部署）。参见[分发](/zh/architecture/distribution)。

每个规范目录下还包含补充文档 — 计划、数据模型、快速上手、研究等 —
视规范情况而定；这些内容在侧边栏对应规范条目下可见。

## 架构决策记录 (ADR)

所有已记录的架构决策，包含背景与影响分析：
[全部 ADR](/zh/reference/adr/)

## 项目记忆

定义项目持久原则与当前状态的核心文档：

- [章程](/zh/reference/project/constitution) — 项目不变量与指导原则
- [路线图](/zh/reference/project/roadmap) — 在役规范及其状态
- [架构](/zh/reference/project/architecture) — 当前架构快照

## 工程规范

所有贡献者遵循的编码与流程标准：
[规范文档](/zh/reference/conventions/workflow)
