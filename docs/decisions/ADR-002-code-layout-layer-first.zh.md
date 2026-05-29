# ADR-002: 代码布局 —— 分层优先，按 kind 分子目录

> English: [ADR-002-code-layout-layer-first.md](./ADR-002-code-layout-layer-first.md)

**Status**: 已采纳 (Accepted)
**Date**: 2026-05-20
**Deciders**: Yuxing Wu
**Related**: `.specify/memory/constitution.md` (Architectural Constraints), [ADR-001](ADR-001-resource-framework-upfront.md)

## 背景

[ADR-001](ADR-001-resource-framework-upfront.md) 承诺在规约 `001-mcp-gateway` 中实现资源框架。在遵守章程
分层架构 (`surfaces → application → domain`，下方为 `infrastructure`) 的前提下，
有两种布局可选：

- **分层优先，按 kind 分子目录** —— 每一顶层 layer 在根目录放与 kind 无关
  的文件，并为每种 kind 提供一个 `<kind>/` 子目录。
- **纵向切片 (vertical slice)** —— 新增顶层目录 `kinds/`，每种 kind 构成完整
  纵向切片，内部各有自己的 `domain/ application/ infrastructure/ surfaces/`。

只要 importlinter 契约强制依赖方向，两者都满足章程。选择的关键是可导航性、
约定，以及「第二个功能时抽取」规则在两种布局下的实际表现。

## 决定

**分层优先，按 kind 分子目录。**

```
backend/coffer/
├── domain/                       # kind-agnostic core
│   ├── resource.py
│   ├── audit.py
│   └── mcp/                      # MCP-specific value objects
├── application/
│   ├── resource_service.py       # kind-agnostic CRUD
│   ├── audit_service.py
│   ├── retention_service.py
│   └── mcp/                      # MCP-specific services
├── infrastructure/
│   ├── persistence/
│   ├── credentials/
│   ├── daemon/
│   └── mcp/                      # subprocess, http upstream client
└── surfaces/
    ├── http/
    │   ├── app.py                # composition root
    │   ├── resource_routes.py
    │   └── mcp/                  # MCP HTTP routes
    ├── cli/
    │   ├── main.py
    │   ├── resource_cmd.py
    │   └── mcp.py
    └── shim/                     # coffer-mcp-shim (MCP-only by nature)
```

每种 kind 在组合根 (composition root) 通过一个显式的 `KindModule` dataclass
注册 —— 没有全局注册表、没有 import 副作用、没有 `kinds/` 目录。

## 后果

**正面**

- 在文件系统中字面上映射了章程所定义的 `surfaces → application → domain (←
infrastructure)` 分层。架构文档读起来与目录树一致。
- 是 Python/FastAPI 的熟悉布局；新贡献者一眼就能认得。
- 当出现跨 kind 关注点时，问题只是「它属于哪一层」—— 一次判断，自然落到对应
  层的根目录。
- 小 kind 不必付出多余仪式（`domain/profile.py` 是单文件；在纵向切片下要写成
  `kinds/profile/domain/profile.py`）。
- Importlinter 规则读起来自然：
  - 禁止 `domain → infrastructure | surfaces`
  - 禁止 `*/mcp → */<other_kind>`
  - 禁止 `domain/*`（与 kind 无关）→ `domain/<kind>/*`

**负面**

- 一种 kind 的代码会跨 4–5 个目录。缓解：IDE 搜索与 grep 让这件事不再是问题；
  用户已确认接受。
- Importlinter 契约要强制两套规则（分层 + 跨 kind），而不是一套。

## 备选方案

**纵向切片 (`kinds/<x>/{domain,application,infrastructure,surfaces}/`)**。
被否决。

- 在章程的四层之外引入了第五个顶层概念 (`kinds/`)；架构文档必须同时解释两者。
- 每次跨 kind 抽取都要做双重决策：「它该放顶层 layer，还是 `kinds/<x>/<layer>/`？」
  —— 两次判断而非一次。
- 大体上贴合 DDD-bounded-context / 模块化单体模式，其动机来自团队隔离、独立
  发布节奏或微服务化拆分 —— 这些都不适用于单用户本地优先的 OSS 应用。
- 「纵向切片更易发现」的优势在 IDE 搜索面前几乎不存在；而代价（布局二元化）
  并不会因此消失。

**按 kind 的扁平模块（kind 内部不再分层）**。被否决。某些 kind 会变大
（MCP kind 预估已达约 1500 行）。扁平模块内的 importlinter 无法强制分层方向。

**插件架构（每种 kind 一个可加载插件，带 manifest、隔离、发现机制）**。
评估后推迟：见 [ADR-001](ADR-001-resource-framework-upfront.md)。它本身不是布局决策；在此仅作为我们考虑过
但否决的「最重」参照物。
