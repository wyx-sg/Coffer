# ADR-019：闭合 Eval 飞轮（Loop Engineering）

**状态**：Accepted
**日期**：2026-06-14
**决策者**：Yuxing Wu
**相关**：[ADR-017](ADR-017-industrial-grade-harness-in-layers.zh.md)（分层 harness）、[ADR-018](ADR-018-tool-retrieval-for-overload.zh.md)（工具检索）、`evals/README.md`、`.specify/memory/roadmap.md`

## 背景

ADR-017 分层搭建了 harness，并把 **loop engineering** 锚定为它**之上**的一层：
harness 决定 agent **能做什么**（静态——工具、上下文、护栏）；loop 决定它
**接下来做什么、何时停**（动态——验证时机、重规划、终止）。对 Coffer 而言，
"loop engineering" 具体指**构建 Coffer 自身代码的、AI 辅助的开发期循环**——
不是运行时 agent 循环。

这条开发循环已经有一根很强的确定性脊柱：`/coffer-spec`（立题）→
`writing-plans`（规划）→ TDD（设定验收标准）→ Claude Code（实现）→
`make verify`（4 层测试 + import-linter + acceptance 审计）→ `/code-review` →
CI 把关的 PR（集成）。内层的 edit-verify 循环、以及循环控制
（重规划 / 升级 / 停止 / 预算）**有意交给 Claude Code + superpowers**——
对 solo 项目自建 implement-until-green driver 属于 cargo-cult。

**断掉的**是 Coffer **非确定性**行为（工具路由、检索、chat）的质量飞轮。
ADR-017 的 Layer D 交付了 `evals/`，但它只是个**回归仪表**：每个 suite ~8 条
手写 case、一份 committed baseline、一个相对回归 gate（`evals/run.py`）。
仪表在，但围绕它的飞轮没接上：

- **Capture 缺失。** 没有任何东西把真实使用变成 eval case。更糟的是，本该充当
  capture 源的 `mcp_invocations` 日志**不诚实**：upstream 的 in-band 工具错误
  （格式良好、带 `isError: True` 的 `CallToolResult`，并不抛异常）被记成
  `status=ok`。一份分不清成败的日志，无法作为 capture 源。
- **Curate 缺失。** 没有把捕获的 trace 变成 golden case 的路径。
- **Gate 不在开发主路上。** `make eval` 在 `make verify` 和 CI 之外；没有
  `evals.yml`。
- **Feedback 未文档化。** 把一次生产失败变成永久回归测试的闭环没有合上。

## 决策

为 Coffer 的非确定性面闭合 eval 飞轮，作为一个 ADR 追踪的工程项目（工具，而非
产品 spec——豁免 FE+BE+真实使用的 spec-deliverable 规则，与 ADR-017 一致）。
按**有序、可独立交付的切片**推进：

```
真实使用 ─▶ [诚实的 invocation 日志] ─▶ [capture sink] ─▶ [curate] ─▶ datasets
                                                                        │
   质量提升 ◀── re-baseline ◀── 修复 ◀── 抓到回归 ◀── [eval gate] ◀──────┘
```

- **切片 1 —— 诚实的 capture 地基。** 让 invocation 日志诚实：in-band `isError`
  的工具结果记为 `status=error`，不再是 `ok`。错误文本由 upstream 控制（可能
  回显密钥），因此只持久化一个固定的、Coffer 自己写的标记，绝不存结果内容
  （保住 SC-010 与 roadmap 的非目标"argument/result 内容不进 DB"）。
  *随本 ADR 交付。*
- **切片 2 —— Capture sink。** 一条 **opt-in、仅 dev、本地**的捕获通路，记录真实
  交互中与 eval 相关的形状（工具路由：intent + 目录快照 + 选中工具 + 结果；
  检索：query + 返回的 doc id）。它是**独立于共享 `~/.coffer/coffer.db` 的 sink**
  ——那个库刻意不存 payload；eval curation 需要请求文本，于是给它一个独立的、
  gitignore 的本地文件，而不是去拓宽审计日志。
- **切片 3 —— Curate。** 一个小的 `evals` CLI：读 sink，让开发者确认期望答案
  （能用确定性 ranker 预填的就预填），把带来源标注（real-trace vs 手写）、去重
  后的 case append 进 `datasets/*.jsonl`。
- **切片 4 —— Gate + feedback。** 把确定性 suite（retrieval-keyword、tool-search
  ——无模型、免费）放上开发主路；加一个 `evals.yml`，对触碰
  prompts/agents/retrieval/catalogue 的 PR 跑带模型的 routing suite，按
  **相对 baseline 的回归**把关（复用 `run.py`）。在 `agents/harness.md` 里文档化
  闭环（生产失败 → capture → curate → 抓到回归 → 修 → re-baseline）。
- **附带（可并行）。** ADR-017 承诺过但没建的 verify-before-commit hook；
  per-branch dev DB 路径（修跨分支 `~/.coffer/coffer.db` 损坏）。

## 影响

- invocation 日志变得**诚实**——这是把它（及 capture sink）用作 eval case 源的
  前提，本身也是个正确性修复。
- eval suite 不再是静态仪表，而成为**飞轮**：真实使用增长数据集，gate 阻止
  最高价值、最不确定行为的无声退化。
- 飞轮的产物是**可信的"该修什么"信号 + 回归护栏**——不是 autopilot。优化动作
  （定方案、实现、ship）仍由人 + Claude Code 内循环完成。
- **延后、已锚定：regression→repair assist。** 将来可以加一个**人手动触发**的命令，
  把抓到的回归（失败 case + 上下文）交给 worktree 里的 Claude Code 试修，人来
  review、人来 merge。此处**不建**：自动"把 eval 弄绿"会诱发对指标的过拟合
  （gaming），无人值守 merge 违反 no-AI-merge 规则。这里建的 capture/gate 是它
  的前提，所以接缝留干净。

## 备选方案

- **现在就建半自动修复循环。** 否决：它消费飞轮的信号，所以测量飞轮无论如何要
  先建；且自动把非确定性 eval 弄绿有刷指标风险——一个不诚实的 portfolio 作品。
  改为锚定成延后的、人手动触发的 follow-up。
- **捕获进现有 `mcp_invocations` 表。** 否决：该表是隐私受限的审计日志
  （who/when/how-long/outcome，不存 payload）。eval curation 需要请求内容，于是
  给它独立的 opt-in 本地 sink，而非拓宽一个刻意收窄的审计面。
- **把 routing eval 放进核心 `make verify` / CI。** 否决：它需要模型端点且非确定；
  免模型的 suite 上开发主路，routing 走独立、窄触发的 `evals.yml`。
- **把 loop engineering 建模成编号产品 spec。** 否决：它和 ADR-017 一样是工程
  工具，不是面向用户的增量；ADR + 有序切片更贴切。
