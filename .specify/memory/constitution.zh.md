# Coffer 章程

> English: [constitution.md](./constitution.md)

> Coffer 是一个本地优先的 AI agent 仓库 (vault)：开发者沉淀下来的 AI 资产
> 全部留在本机，任何 AI agent（Claude Code、Codex、未来的新成员）都通过
> 同一个安全接口进行读取与贡献。
>
> 本章程仅约定**脚手架层级**的不变量：技术栈、工作流、许可证立场与架构
> 风格。产品行为本身——资源模型、安全/审批规则、对外暴露的接口面 (surface)
> 清单、各类数据的落盘位置——由 `specs/` 下的逐 feature 规范定义。

## 核心原则 (Core Principles)

### 原则 1：本地优先 (Local-First, 不可妥协)

所有用户数据都驻留在用户本机。云服务仅作为 LLM 与工具的提供方——它们
绝不充当任何仓库状态的事实记录方 (system of record)。HTTP API 仅绑定
到 `127.0.0.1`。若要把用户态复制到任何由厂商掌控的云端，必须走章程修订
流程。

**例外——用户自掌控的同步介质。** 允许把仓库状态同步到**用户自有、用户
掌控的介质**（例如用户自己的 git 仓库），但必须**同时**满足以下全部条件：

1. **不产生新的事实记录方。** 每台参与机器都持有完整的仓库状态；该介质
   只作传输与历史，绝不成为唯一或权威的 system of record——抹掉该介质后，
   每台机器仍拥有自己完整的仓库。
2. **凭证只以密文离机。** 任何离开本机的凭证材料只能是 Fernet 密文。加密
   master key **绝不**通过同步介质离开本机；它通过带外通道逐台引导到各机器。
3. **用户主动开启且自有。** 同步默认关闭，且指向用户自行提供并掌控的 remote。
   Coffer 不提供任何托管/厂商同步端点；提供它仍需另行修宪。

此例外不削弱「厂商掌控的云端不得充当 system of record」这一禁令；它仅授权
满足上述三项条件的用户自有传输介质。

### 原则 2：规范即真理 (Spec-as-Truth, Spec-Driven Development)

`specs/` 目录下的规范是产品契约的唯一权威。任何会改变对外可见行为的 PR
都必须**先**更新对应规范，再改代码。规范不是「文档」——它就是实现的
契约；当代码与规范不一致时，错的是代码。

### 原则 3：从第一天起就为开源做好准备 (Open-Source-Readiness from Day One)

许可证 (MIT)、治理规则、贡献流程、Conventional Commits 必须从 v0.0.1
起就存在于仓库中，而不是事后补齐。任何会让这份清单变短的改动——引入
未经豁免的闭源依赖、省略 AI 生成内容的署名——都视为违反本原则，必须
通过章程修订并附带明确的迁移方案。

## 技术与架构约束 (Technology & Architectural Constraints)

- **语言。** 后端、CLI 及任何 MCP 适配层使用 Python 3.12+；前端使用
  TypeScript 5.x。在未走章程修订的情况下，不引入其他主语言。
- **架构。** 分层：`surfaces → application → domain → infrastructure`。
  `domain/` 不得 import `infrastructure/`、`surfaces/` 或任何外部 SDK；
  `application/` 不得 import `surfaces/`。跨层公共模块只在第二个 feature
  也需要它时才抽取。（例外：Resource 框架——见
  [ADR-001](../../docs/decisions/ADR-001-resource-framework-upfront.md)。）
- **持久化。** SQLite 是控制面状态的事实记录方。批量用户内容（按规范
  引入时）以文件形式存放于本地文件系统，按需建立索引。
- **凭据。** 密钥**只**以 Fernet 密文形式存放于 `credentials` 表；明文仅在
  解密与拉起子进程/注入 header（消费密钥处）之间短暂存在于内存。Fernet 主
  密钥由 `coffer.infrastructure.credentials` 独占管理——默认为 DB 旁的
  `0600` 文件，opt-in 时通过 `keyring` 存于操作系统钥匙串。`keyring` 的
  import 仅限该模块。其他代码一律只持有凭据引用 (credential ref)。任何密钥
  明文都不得进入数据库、日志、审计或任何结构化事件。
- **网络默认值。** 仅监听 loopback。一旦需要发起对外 HTTP，必须经过一
  个具备 SSRF 防护的客户端。一旦需要对公网暴露任何 surface，必须以独立
  进程运行，并仅限于经过签名校验的回调路径。

## 质量门槛 (Quality Gates)

只有在**全部**满足以下条件后，一项变更才算「完成」：

- 相关的 `spec.md` 已更新到与代码一致。
- `spec.md` 中的验收场景覆盖了新增行为并能通过。
- `make verify` 在本地与 CI 均通过。
- 文件大小限制 (见 `agents/stack.md`) 仍然成立。
- 架构边界未被破坏。

## 治理 (Governance)

本章程**优先于** `AGENTS.md`、`CONTRIBUTING.md` 或任何单个规范文档中
任何相冲突的指引。出现分歧时，以章程为准。

**修订流程 (Amendments)。** 对任何 Core Principle、Technology &
Architectural Constraints 或 Quality Gate 的修改，必须满足：

1. 一个提案 PR，说明动机、当前行为、拟定行为、下游影响、备选方案。
2. PR 描述中明确记录决议。
3. 该 PR 同步更新本文件，并提升下方的 **Version** 字段。

**PR 评审。** 每个 PR 描述都应在适用时点出它所触及的章程原则或约束，
并解释该变更为何尊重 (或正式修订) 它们。

**Version**: 0.3.0

> **0.3.0 修订（spec 010-sync）。** 为原则 1 增加*用户自掌控同步介质*例外，
> 在三项条件（不产生新的 system of record、凭证只以密文离机、用户主动开启
> 且自有）下授权基于用户自有 git 仓库的多机同步。动机：让单一用户在自己的
> 多台机器间保持同一个仓库一致，且不放弃 local-first 保证。当前行为：多机
> 同步原为明确非目标。拟定行为：在上述受限例外下允许。下游影响：新增 spec
> 010-sync（同步引擎、CLI/HTTP 接口、daemon 自动同步 worker）；不改动凭证
> 静态存储与 loopback 绑定规则。备选方案：点对点（Syncthing 式）与用户自有
> 对象存储——为获得内建历史、diff 与合并能力，选择 git。决议由项目所有者记录。
