# ADR-017：工业级 Harness，分层建设

**状态**：Proposed
**日期**：2026-06-13
**决策者**：Yuxing Wu
**关联**：`.specify/memory/constitution.md`、[`agents/testing.md`](../../agents/testing.zh.md)、[`agents/workflow.md`](../../agents/workflow.zh.md)、[ADR-014](ADR-014-channel-adapter-framework.zh.md)、[ADR-016](ADR-016-multi-machine-sync.zh.md)、specs `009-channels` / `010-sync`

## 背景

「Harness」是包在核心执行体外面、让它能被可靠、可重复、可观测地驱动的脚手架。这个词同时被三种东西使用，混在一起一直在损耗我们的清晰度：

1. **Agent 运行时 harness（①）** —— 包在 LLM 外面的运行时（工具、上下文管理、agentic loop、护栏）。对我们的 coding agent 而言这就是 Claude Code / Codex —— 我们**消费**它，不建它。Coffer 将来会长出自己的内置版本（见「后果」→ 延后层）。
2. **工程 harness（②）** —— 围着代码、让它可构建/可测/可运行且受控可复现可观测的经典脚手架（Makefile `verify`、4 个测试层、pre-commit、CI）。服务人和 CI。
3. **Agent-facing harness（③）** —— 让 coding *agent* 能在本仓库里可靠、安全干活的脚手架（AGENTS.md、`agents/*.md`、`.specify/memory`、ADR）。是 ① 与项目知识之间的接口。

三者的统一原则只有一句：**make the right thing the easy thing；让反馈快、确定、可读。** 最理想状态是 ②③ 收敛 —— 一套确定性的、单命令的、可观测的基建，人、CI、agent 都调它。

Coffer 的 ②（反馈层）和 ③（知识层）已经很强：共用的 `make verify`、integration 为主的 4-tier 测试（单元纯度机械约束）、pre-commit（ruff/prettier/commitlint）、CI，以及顶配的知识面（AGENTS.md + `agents/*.md` + constitution/architecture/roadmap + 双语 ADR）。对照工业级标尺，还剩四个缺口 —— 而且它们成簇、不散：

- **（A）控制层空白。** `.claude/settings.json` 未设；没有 checked-in 的 hooks、skills、权限规则。agent-facing harness 目前是纯**文档式**的（靠 agent 自觉读 AGENTS.md）—— 被动，未强制。
- **（B）Hermeticity 漏。** 没有提交 `uv.lock`（`make lock` 目标在，但产物不在仓库里）；dev DB 是单个共享的 `~/.coffer/coffer.db`，跨分支迁移谱系分叉时会崩；构建环境依赖未钉死的宿主工具链。
- **（C）「真的能跑」那两级缺失。** 每一层都跑在 fake 上。spec 009（channels）、010（sync）和 CLI-agent chat 都是带着 fake-API 覆盖合并、**真实使用留给手动的、带外的验证** —— 一笔反复出现的债。密闭回路里绿 ≠ 对真 Telegram/SeaTalk/git remote 能跑通。
- **（D）没有 AI eval harness。** Coffer 是 AI 产品（工具路由聚合器 + chat agents），最重要的行为是非确定性的，却没有 eval 套件。精确断言覆盖不了工具选择质量或对话质量；`langsmith` 已是依赖但没用于 eval。

## 决策

把 harness 当作一个显式的**五层栈**，并在本项目（三项目中的 Project 1 —— 见「后果」）补齐上述四个缺口。每一层是本 ADR 下可独立交付的子任务，按 **A → B → C → D** 排序（最高 ROI/最独立者先行，确定性地基先于依赖它的那些循环）。这是**工具，不是产品功能** —— 以 ADR + 各层子任务记录，豁免管产品 spec 的 spec-deliverable 规则（FE+BE+real-usage）。

```
观测      canonical log line + append-only 审计            （可选后续）
   ↑
反馈 ②    单命令 verify + 测试金字塔 +（以后）DORA            （已强）
   ↑
真实      adapter→fake→contract test→定时打真服务 smoke        ← 缺口 C
   ↑
确定      lockfile + 钉工具链 + devcontainer + 按分支隔离 DB     ← 缺口 B
   ↑
知识 ③    单一事实源 + 渐进披露                                （已强）
   ↑
控制 ③    hooks + 权限 + repo skills（.claude/）                ← 缺口 A
   +
eval(AI)  golden dataset + code/LLM-judge 打分 + CI 回归卡门      ← 缺口 D
```

各层决策（*做什么*与*为什么*；*怎么做*留给实现 plan）：

- **A —— 控制层（`.claude/`，checked in）。** `settings.json` 带 `permissions`（allow 常用安全命令以砍授权摩擦；deny 破坏性命令做纵深防御）外加 `hooks`：`PostToolUse` 用与 pre-commit 同样的工具自动格式化改动的 `*.py`/`*.ts`；`PreToolUse` 拦危险 Bash 并在 `make verify` 陈旧时守住 commit；`SessionStart` 注入分支/spec/worktree 上下文（对齐 AGENTS.md session 协议）。repo `skills/`（`/coffer-verify`、`/coffer-spec`）—— 用 *skills*，因为 `.claude/commands/` 被 gitignore。新增 `agents/harness.md`（+`.zh`）记录本层；AGENTS.md/CLAUDE.md 指过去（单一事实源）。
- **B —— Hermeticity。** 提交 `uv.lock` + `.python-version`；加 `.devcontainer/`（uv + node + playwright）以消灭「在我机器上能跑」和内网镜像陷阱；dev/test DB 路径按分支派生，切分支不会互相污染。
- **C —— 真实层。** 确认每个外部边界（Telegram、SeaTalk、git-sync remote、各上游 MCP server）都有自有 adapter；加 **contract test**，同一套行为用例既跑 fake 又跑真 client，钉住 fake 的诚实度；加 `make smoke` + 定时/手动的 `smoke.yml`，用一次性账号对真服务做 round-trip（HTTP 形态的用带 re-record interval 的 VCR cassette）。这把三笔「real usage pending」债从手工活变成一条可运行命令。真账号/secret 仍由用户提供。
- **D —— AI eval。** 一个 `evals/` golden dataset（20–50 个任务：聚合 MCP catalog 上的工具路由正确性、对话回答质量、channel 指令处理）；有客观信号处用 code grader，必要时才用 LLM-as-judge；`make eval` + `evals.yml`，对碰 prompt/agent 的 PR 按**相对基线回归**卡门（对非确定性输出，绝对绿是错标尺），用 pass@k。复用已有的 `langsmith` 依赖。

## 后果

- agent-facing harness 从「只是文档」变成**被强制** —— 正确行为是默认路径、破坏性动作被拦、授权摩擦下降。
- 全新 clone 变得可复现（lockfile + devcontainer），消掉一类 flaky /「这里绿那里红」失败和两笔长期环境债。
- 三笔「real usage pending」债拿到**可运行**的收口命令；留在用户身上的缩小到「提供一次性凭据」。
- Coffer 得到对**非确定性**行为的回归网 —— prompt/agent 改动不能再悄悄劣化工具路由或对话质量。
- 新义务：hooks/CI 必须保持快（慢 hook 会训练人去绕过它）；eval 基线和 judge 质量需周期维护；smoke 的 secret 需 CI 安全存储。
- **延后层（在此显式排除，先锚定）：**
  - *Project 2* —— Coffer 自己的**内置 agent 运行时 harness（①）**：包在 Coffer 内置 agent 外面的工具/上下文/agentic-loop/护栏。
  - *Project 3* —— **Loop engineering**：harness *之上*的一层。边界 —— **harness 决定 agent「能做什么」**（静态：工具、上下文、护栏、沙箱）；**loop 决定它「下一步做什么、何时停」**（动态：验证时机、重规划、升级、终止/预算）。其机制（ReAct、Reflexion、evaluator-optimizer、eval flywheel、inner/outer 开发循环）已成熟，尽管「loop engineering」仍是新兴叫法。它**消费**本 harness 的产出：缺口 D 的 evals 是 flywheel 的测量仪器，缺口 A/C 是它的 verify/check gate —— 所以 harness 先于 loop。
- 观测（credential/sync 操作的 canonical log line + append-only 审计）刻意**不**列入四缺口；它是一个具名的可选后续。

## 备选方案

- **什么都不做 / 保持文档式 agent harness。** 否决：文档是被动的；没有 hooks/权限，agent 会跳过约定、跑破坏性命令，真实层与 eval 缺口照旧。
- **一个大爆炸 harness PR。** 否决：四层的爆炸半径和依赖不同；捆一起会毁掉可 review 性和「确定性先于循环」的顺序。一个 ADR 下的分层子任务让每次改动小、理据单一来源。
- **把 harness 当编号产品 spec（走完整 SDD）。** 否决：harness 是工程工具，不是面向用户的产品增量；硬塞进 FE+BE+real-usage 的 spec-deliverable 规则是错配。ADR + 子任务才合身。
- **暂时跳过 AI eval 层。** 否决：对 AI 产品而言，eval harness **就是**那个最有价值、最不确定行为的 test harness，也是未来 loop-engineering 项目的前置测量仪器。略掉它等于让最高价值的行为无测。
- **在本项目里就建 loop engineering / 运行时 harness。** 否决：两者都在本层之上或之旁、都依赖本层先存在；把它们排成 Project 2、3 才能让每个项目自洽。
