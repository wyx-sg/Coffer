# ADR-007：信息架构 — 一切皆 resource kind

> English: [ADR-007-everything-is-a-resource-kind.md](./ADR-007-everything-is-a-resource-kind.md)

**Status**: Accepted
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
