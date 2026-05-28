# ADR-011：可观测性 —— Tracer 端口与 LangFuse adapter

> English: [ADR-011-observability-tracer-port.md](./ADR-011-observability-tracer-port.md)

**Status**: Accepted
**Date**: 2026-05-29
**Deciders**: Yuxing Wu
**Related**: spec `006-knowledge-base`（FR-016、research.md §7），[ADR-002](ADR-002-code-layout-layer-first.md)

## Context

Spec `006-knowledge-base` 引入了真正值得追踪的操作：`ingest` 与 `search` 都是耗时长、步骤多、用户在调试「检索为何这么慢」「上一次查询为何没结果」时一定会想看一眼的东西。LangFuse 是 2025 年这个生态里对 local 部署最友好的 LLM-app 追踪工具（可自托管、MIT 协议、专为 LLM + RAG 仪表化而生），如果我们要做追踪，LangFuse 就是显然的默认后端。

宪法层的问题是：**tracer 接口放在哪一层？** 与既有架构吻合的选项有两条：

1. **Kind 内部**：`Tracer` 端口落在 `application/knowledge_base/`，adapter 落在 `infrastructure/knowledge_base/`。严格遵守「等到第二个 feature 也需要才抽取公共件」的宪法规则。
2. **直接抽成跨层**：在本 PR 里就建好 `application/observability/` 与 `infrastructure/observability/`，预期 spec 007（memory）是第二个消费者。

两种选择都说得通。trade-off 在于：

- (1) 字面上贴宪法 —— 不做超前抽象；credentials、audit、retention 都是这样落地的。等 spec 007 上线时再 refactor 也只是「搬两个文件、改两个 import」。
- (2) 提前回应一个**已经在望**的第二消费者。Spec 007 的草稿已经在算 memory 的 trace；(1) 的 refactor 成本接近一份纯机械搬移 PR。提前做还有一个好处：从一开始就强迫端口设计成 kind-agnostic，而不是等到 007 时再回去补。

另一维度是 **追踪如何被启用**。LangFuse 需要 public/secret key 与 host URL。我们不能让 adapter 在 daemon 启动时把 LangFuse 拖进 import graph —— 一旦用户从未设过相关环境变量，这就破坏了 local-first 不变量。

## Decision

**在本 PR 里就把 `Tracer` 端口抽到 `application/observability/`，比严格的「等第二个消费者」规则提前一步。** 具体形态：

- 端口：`application/observability/tracer.py` 把 `Tracer` 定义为 `typing.Protocol`，三个方法 `start_span(name, attrs) -> SpanHandle` / `record_attrs(handle, attrs)` / `end_span(handle, status)`。端口仅用 stdlib + 一个小的 `SpanHandle` 值类型；任何 LangFuse 形状的东西都不透出。
- 默认实现：同一模块下的 `NoopTracer`。返回一个静态句柄、忽略 attrs、永不 import LangFuse。Composition root 默认就装这一个。
- LangFuse adapter：`infrastructure/observability/langfuse_tracer.py`。adapter 里的 `import langfuse` 写在**构造函数内部**，而非模块顶部 —— 这样除非 composition root 明确选了这个 adapter，daemon 完全不会 import LangFuse。激活条件是 daemon 启动时环境变量 `LANGFUSE_PUBLIC_KEY` 有值；否则装 noop，`langfuse` 永远进不来。
- Span 命名规约：`<kind>.<operation>` —— `kb.ingest_document`、`kb.search`、`kb.delete_document`、`kb.delete`。未来的消费者（spec 007 memory）就走 `memory.<operation>`。这是端口对 kind 的唯一一处妥协，写在 `application/observability/__init__.py` 里。
- 隐私：发给 LangFuse 的 payload 只含尺寸、计数、耗时 —— 永不发送文档正文、查询字符串、片段内容。这条规则靠 code review 保证（暂无自动检查；LangFuse adapter 是唯一的咽喉点）。

包结构故意与 `credentials/` 对齐：端口面紧贴 application 层放在 `application/observability/`，有副作用的 adapter 放在 `infrastructure/observability/`，importlinter 阻止 application 层直接伸进 LangFuse SDK。

## Consequences

**正面**

- Spec 007（memory）把 `memory.<op>` span 插进同一个端口，零 refactor —— 省一份机械搬移 PR。
- 默认 no-op，意味着没有设过 LangFuse 环境变量的用户：零 LangFuse 代码、零出网调用、零日志噪声。Local-first 不变量稳住。
- 懒加载意味着如果用户环境里 LangFuse 装坏了（比如 pin 错了版本），daemon 仍然能起 —— 除非用户主动开了追踪。
- 追踪面是 _kind-agnostic_ 的。端口不假设 RAG；任何未来想追踪自身操作的 kind 直接注入 `Tracer` 就能用。

**负面**

- 比宪法严格语义提前一步。如果 spec 007 被无限期推迟，这个跨层模块就会一直只挂着一个消费者，违背严格意义上的「最小集」精神。我们用「端口很小（3 个方法）+ noop 默认实现只有约 20 行」来兜底：维护成本几乎可以忽略。
- Span 命名规约（`<kind>.<op>`）是约定而非类型系统强制。未来某个贡献者完全可能从非 KB 模块发出 `kb.something`。靠调用点不多 + code review 兜底；尚无自动检查。
- LangFuse 只是几个候选里的一个（Phoenix、Logfire、OpenTelemetry + Tempo）。我们押 LangFuse 是因为它在 2025 年是 RAG/LLM 工作流里 local-friendly 的默认选项；这个押注若过时，adapter 是一个文件可换，端口保持不变。

## Alternatives Considered

**Tracer 留在 `application/knowledge_base/`，等 spec 007 落地再抽。** 严格符合宪法。被否的理由：007 上线时的 refactor 成本纯机械（重命名模块、改两处 import），提前做反而能让端口形状不被第二个消费者的具体需求绑架。「等第二个消费者再抽」规则的好处 —— 防止投机抽象 —— 在第二个消费者已知且临近的情况下并不成立。

**用 OpenTelemetry 作为进程内 tracing API。** v1 否决。OpenTelemetry 在大规模场景里是对的，但 Python SDK 依赖不轻，对 RAG / LLM 工作流的开发者体验也弱于 LangFuse。未来若 Coffer 想做 APM 风格的分布式 trace，端口可以再长一个 OTLP adapter，不会动到调用点。

**把追踪做成必需而非可选。** 否。宪法的「local-first、不出网做意外的事」原则意味着追踪必须 opt-in，被某个明确的环境变量门控。默认 no-op 是兑现这条原则的唯一方式。

**LangFuse 在模块加载时就 eager import。** 否。Eager import 会让一个 `pip install langfuse` 失败或版本冲突直接打挂从未想用追踪的用户的 daemon。懒加载是硬约束，不是风格选择。
