# ADR-007：信息架构 — 一切皆 resource kind

> English: [ADR-007-everything-is-a-resource-kind.md](./ADR-007-everything-is-a-resource-kind.md)

**Status**: Amended (2026-05-30, 2026-06-11) — 见 [Amendment](#amendment-2026-05-30) 与 [Amendment: 前端 kind UI](#amendment-2026-06-11--前端-kind-ui)
**Date**: 2026-05-28
**Deciders**: Yuxing Wu
**Related**: [ADR-001](ADR-001-resource-framework-upfront.md)，spec `002-ui-shell`

## Context

Spec `001-mcp-gateway` 在一个 kind-agnostic 的 Resource 框架（见 [ADR-001](ADR-001-resource-framework-upfront.md)）之上引入了 `mcp_server` 这一 resource kind。`mcp_server` 是当下已交付的 kind。

Spec `002-ui-shell` 需要决定 resource kind——以及一些并非领域意义上"资源"的横切用户可见概念（审计日志、settings）——如何呈现在导航中。最朴素的做法是在 IA 中再引入一个顶层概念：在"resource kind"轴之外再设一条"surface"轴，让侧栏呈现为两组毫无关联的入口 (Resources vs Features)。本次重设计的目标恰恰相反：**一种无需随产品成长而反复重新论证的统一导航模型。**

另一个相关问题是：尚未实现的 kind 如何在侧栏里呈现？很容易想到把它们以"敬请期待"占位项的方式列出来。实际效果却是侧栏被一堆死掉的入口占据，让产品看起来像未完成的脚手架。

## Decision

**采用单轴的信息架构：所有用户可见的受管理实体都是一种 resource kind，并通过同一个侧栏分组呈现。**

具体后果：

- 当前侧栏恰好只有两组——**Resources**（resource kind）与 **System**（横切工具：Observability、Settings）。新 kind 上线时落入 Resources 组；不引入新的分组。
- kind-agnostic 的 Resource 框架是 UI 所建模的唯一抽象；不存在另一份独立的"surface"注册表与之并列。
- **侧栏策略：不放"敬请期待"占位项。** kind 在能用之前不在侧栏呈现。渲染出来的 UI 只展示当下可用的部分。

## Consequences

**Positive**

- 新 kind 接入同一个 Resources 组，只需一个导航入口——不必为每个 kind 重新谈判 IA。
- 侧栏永远读作"Coffer 现在能做什么"，而不是"Coffer 计划要做什么"。第一次访问的用户看到的是一个产品，不是一份待办列表。
- 来自 [ADR-001](ADR-001-resource-framework-upfront.md) 的 Resource 框架是 UI 唯一需要理解的抽象；不需要再维护一份独立的"surface"注册表。

**Negative**

- "resource"一词被迫承载一些用户口语里未必叫"资源"的概念。缓解办法是面向用户的标签使用各 kind 自身的名词（例如 "MCP server"），而不是"resource"这个词。
- "不在侧栏放尚未实现的 kind"用更少噪音的 day-one UI，换取了路线图发现性的下降。需要看路线图的用户去读 `.specify/memory/roadmap.md`，不指望从侧栏里看。

## Alternatives Considered

**在 resource kind 之外再设一条"surface"轴。** 拒绝。

- IA 复杂度翻倍而毫无所得：我们手上的横切 surface (Observability、Settings) 都是单个固定入口，由 System 组承担。
- 迫使每份未来 spec 先回答"它是 kind 还是 surface？"——这是一个对用户没有任何价值的决策。

**把尚未实现的 kind 以禁用/"敬请期待"占位项的形式放在侧栏。** 拒绝。

- 读起来就是一个未完成的脚手架（这恰是 spec 002 动机里明确反对的）。
- 路线图发现性的收益真实存在但有限，且已经由 `.specify/memory/roadmap.md` 提供。

**按 kind 各自独立顶层导航（不设 Resources 组）。** 拒绝。

- 在只有一个 kind 时尚可，但随着 kind 增加，侧栏就退化成没有分组的扁平清单。Resources / System 的分组让侧栏保持可读。

## Amendment (2026-05-30)

原决策把**所有**用户可见的受管理实体都放在单轴上建模为一种 resource kind。实现过程中冒出一个不适配这个模型的概念：**agent**（你使用的 Claude Code / Codex / 内置 agent）。agent 是 vault 资产的*消费者*，而不是 vault 管理的资产——把它压到 resource-kind 轴上就贴错了标签。因此交付的 IA 保留了 kind-agnostic 的 Resource 框架，但为消费者新增了第二条轴，并把侧栏按**角色 (role)** 而不是按"它是不是一种 kind？"来分组。

变更内容：

- **Agent 是独立的一条轴，不是 resource kind。** 它们呈现在 `/agents`（列表）与 `/agents/:name`（详情），归入自己的 **Agents** 侧栏分组。它们**不**出现在 `/resources` 的 kind 浏览器里，因为它们不是 vault 资产。
- **侧栏按角色分组**，不再是单一的 resource-kind 轴：
  - **Agents** — 消费者 (`/agents`)。
  - **Resources** — agent 所依赖的资产，建模为 kind-agnostic 的 resource kind，通过 kind registry 暴露。该导航入口标签为 **"MCP servers"**，只列出注册了列表/卡片 UI 的 kind（今天只有 `mcp_server`）；路由是 `/mcp-servers`（`/resources` 保留为旧书签的 legacy 重定向）。
  - **System** — 横切工具：**Audit log** (`/audit`) 与 **Settings** (`/settings`)。
- **审计日志住在 `/audit`，不是 `/observability`。** 交付的路由把 `/audit` 映射到审计日志页面，并把 `/observability` 保留为指向 `/audit` 的 legacy 重定向。**Observability**（系统健康 / 指标）是一个**独立、预留的未来**界面——它不是审计日志，也尚未进入侧栏。
- **列表界面收敛到同一个可搜索、可分页的共享表格。** 所有列表视图共用同一个 `DataTable` 组件（内建搜索 / 过滤 / 分页），点击一行打开该项的详情页，行内操作是紧凑的图标。卡片只保留给欢迎 / 空态。这取代了早先对 resource 列表的卡片网格描述。
- **未来的分组/入口**（Chat、Channels、Skills、Knowledge、Memory、Observability）已规划但今天不展示。原决策"不放敬请期待占位项"的策略依然成立：侧栏记录角色分组结构，但不添加任何死的导航入口。

从原决策中原样保留的部分：kind-agnostic 的 Resource 框架仍是*资产*的唯一抽象；新的 resource kind 仍以单个导航入口接入 Resources 组；侧栏仍只展示当下已交付的部分。本次修订把"一切皆 resource kind"收窄为"每个**资产**都是一种 resource kind，归在 Resources 下；消费者 (agent) 与横切工具 (System) 各成一个基于角色的分组。"

## Amendment (2026-06-11) — 前端 kind UI

Spec 005 把 **skill** 以后端 resource kind 交付（身份、生命周期、审计、`on_delete` 级联全部走 kind-agnostic 框架），但前端是**专属页面**（`/skills`、`/skills/:name`），没有走前端 kind registry。这让 UI 处在一个未声明的半途状态：registry 承诺"每个 kind 一个通用浏览界面"，而 skill 悄悄绕开了它。

本次修订定案前端模式：

- **后端这条轴不变。** 每个资产都是 resource kind；unify-identity/lifecycle/audit 与 never-unify-invocation 规则（ADR-001）对所有 kind 依然成立。
- **前端 kind registry 是有边界的，不是普适的。** 它服务于 UI 适合通用浏览模式（卡片/表格 + 以配置为中心的详情页）的 kind —— 今天是 `/mcp-servers` 下的 `mcp_server`。它**不是**"每个 kind 都经由它渲染"的承诺。
- **交互模型更丰富的资产 kind 交付专属页面组。** Skill（按 agent 的绑定、文件查看器、漂移校验）住在 `/skills`，拥有自己的页面。这是被认可的模式，不是例外。
- **新 kind 在设计期显式二选一**：注册 kind UI 走通用浏览，或在自己的路由下交付专属页面组。该 kind 的 spec 必须写明选了哪种。

结果："Skills 出现在侧栏 Resources 组"（2026-05-30 修订的未来分组列表中的一项）现已交付 —— Resources 组包含 **MCP servers**（`/mcp-servers`，registry 驱动）与 **Skills**（`/skills`，专属页面）。
