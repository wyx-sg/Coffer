# ADR-008：信息架构 — 一切皆 resource kind

> English: [ADR-008-everything-is-a-resource-kind.md](./ADR-008-everything-is-a-resource-kind.md)

**Status**: Accepted
**Date**: 2026-05-28
**Deciders**: Yuxing Wu
**Related**: [ADR-001](ADR-001-resource-framework-upfront.md)，spec `002-ui-shell`

## Context

Spec `001-mcp-gateway` 在一个 kind-agnostic 的 Resource 框架（见 [ADR-001](ADR-001-resource-framework-upfront.md)）之上引入了 `mcp_server` 这一 resource kind。框架的设计预留了后续更多 kind 的可能 (`skill`、`memory`、`knowledge_base`、`channel`、`agent`，以及内建的 `chat` surface)。

Spec `002-ui-shell` 需要决定这些未来的 kind——以及一些并非严格意义上"资源"的用户可见概念（集成 / 频道 / chat surface / 审计日志）——如何呈现在导航中。最朴素的做法是在 IA 中再引入一条轴：在"resource kind"之外再有一条"surface"轴，让侧栏呈现为两组毫无关联的入口 (Resources vs Features)。本次重设计的目标恰恰相反：**一种随着新 kind 上线可线性扩展、无需每次重做 IA 的统一导航模型。**

另一个相关问题是：尚未实现的 kind 如何在侧栏里呈现？很容易想到把它们以"敬请期待"占位项的方式列出来，让用户看到规划。实际效果却是侧栏被一堆灰色占位项占据三分之二，让产品看起来像未完成的脚手架。

## Decision

**采用单轴的信息架构：所有用户可见的受管理实体都是一种 resource kind，并通过同一个侧栏分组呈现。**

具体后果：

- 当前侧栏只有两组——**Resources**（resource kind）与 **System**（横切工具：Observability、Settings）。新 kind 上线时落入 Resources 组；不引入新的分组。
- 那些口语上不算"资源"的概念——Seatalk 频道、agent、内建 Chat——同样建模为 resource kind。**channel** 是一份已注册、已配置、有自己生命周期的集成。**agent** 既消费能力也可被暴露为能力，这种双重角色是 agent resource 自身的属性，而不是拆分导航的理由。
- 未来的内建 **Chat** surface 在上线时获得一个置顶入口，独立于两个分组之上；置顶只是视觉上的让步，不构成 IA 上的第二条轴。
- **侧栏策略：不放"敬请期待"占位项。** 规划中的 kind 在其 feature spec 上线之前不在侧栏呈现。IA 文档（spec.md 的 `## Information Architecture` 一节）记录了规划中的 kind 以备日后参考；渲染出来的 UI 只展示当下可用的部分。

## Consequences

**Positive**

- 未来的 spec（003 desktop shell、004 agent registry、005 skill manager、006 knowledge base、007 memory 等）只需在 Resources 组里加一个导航入口即可接入——每个 spec 都不再为 IA 谈判。
- 侧栏永远读作"Coffer 现在能做什么"，而不是"Coffer 计划要做什么"。第一次访问的用户看到的是一个产品，不是一份待办列表。
- 来自 [ADR-001](ADR-001-resource-framework-upfront.md) 的 Resource 框架是 UI 唯一需要理解的抽象；不需要再维护一份独立的"surface"注册表。

**Negative**

- "resource"一词被迫承载一些用户口语里未必叫"资源"的概念（频道、作为提供方的 agent、chat）。每份 spec 需要用一行话先解释这个用语。缓解办法是面向用户的标签使用各 kind 自身的名词 (MCP server、Skill、Channel、Agent、Chat)，而不是"resource"这个词。
- "不在侧栏放规划中的 kind"用 day-one UI 的清爽，换取了路线图发现性的下降。需要看路线图的用户去读 `.specify/memory/roadmap.md`，不指望从侧栏里看。

## Alternatives Considered

**在 resource kind 之外再设一条"surface"轴。** 拒绝。

- IA 复杂度翻倍而毫无所得：我们考察过的每一个"surface" (Chat、Observability、Settings) 要么是单个固定入口（Observability、Settings 由 System 组承担），要么本身建模为 kind 更合适（Chat 依附在一个 agent resource 之上）。
- 迫使每份未来 spec 先回答"它是 kind 还是 surface？"——这是一个对用户没有任何价值的决策。

**把规划中的 kind 以禁用/"敬请期待"占位项的形式放在侧栏。** 拒绝。

- 读起来就是一个未完成的脚手架（这恰是 spec 002 动机里明确反对的）。day-one 侧栏会有三分之二是死的。
- 路线图发现性的收益真实存在但有限，且已经由 `.specify/memory/roadmap.md` 与 spec 自身的 `## Information Architecture` 一节提供。

**按 kind 各自独立顶层导航（不设 Resources 组）。** 拒绝。

- 在只有一个 kind 时（即今天）尚可，但等五个规划中的 kind 都接入后，侧栏就退化成没有分组的扁平清单。Resources / System 的分组让侧栏在 kind 增加时仍然可读。
