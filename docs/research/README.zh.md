# Coffer 竞品调研 —— 索引与综述

> 中文版：本文件 · English: [README.md](./README.md)
>
> 关于 Coffer 所涉产品空间的 12 份竞品调研报告，于 **2026-06-16/17** 经 deep-research
> harness（扇出网络搜索 → 抓取来源 → 对抗式核验 → 综合）产出。每份报告同一结构：
> 产品概览 → 能力对比表 → 与 Coffer 对比 → 关键结论 → 来源引用。（第 12 份"记忆系统"由
> 并行 session 产出，在此一并列出以成完整地图。）
>
> **来源说明（请先读）。** 多次 run 在核验/综合阶段撞到 API 限流或用量上限窗口。凡是 harness
> 自身综合被中断的，报告由我手工依据 harness 的**一手来源、部分核验的 claim** 综合而成。通常
> 每份报告 2–3 条 claim 经三票确认，其余为单一一手来源（行内标注）。**视为有据的初稿；对外引用
> 任何内容前请做轻量复核。**
>
> **核查更新（2026-06-19）。** 每份报告末尾现在都带一个 `核查更新（2026-06-19）` 段——这是一轮
> 复核：把每份报告里决策相关的 claim 对照**当前一手来源**（厂商文档、官方仓库）与 **Coffer 自身
> 的代码 / 规格 / ADR** 重新核验，记录哪些 ✅ 已确认、✏️ 已修正、❓ 仍待核查、➕ 新增覆盖（此前
> 未覆盖的竞品）。多数 claim 站得住；少数修正较关键——例如渠道报告里"被 web 控制台复用的共享审批
> 闸"已在 PR #101（2026-06-18，报告日期两天后）被删除；MCP"唯一带工具检索的网关"被收窄为工具
> 检索**加上**智能 `ask` 组合这一点。阅读每份报告时请连同其末尾的核查更新段一起看。
>
> _快照声明。_ Coffer 的技能 / agent / 知识库子系统正在高频出 PR。各报告的核查段反映的是
> **2026-06-19** 复核时的 `main`；有两个 PR 在本次准备期间合入——**#116**（技能发现——从
> catalog 浏览+安装）与 **#117**（KB 协管文档）——尚未折进各报告段，因此 agent-skills 的"无
> 发现机制"缺口与 KB 报告的部分结论已被推翻。对外引用任何"缺口"或"我们领先"结论前，请对照
> 当前 `main` 复核。

## 报告清单

| #   | 报告                                                                                              | 对应 Coffer 模块    | 一句话头条                                                                            |
| --- | ------------------------------------------------------------------------------------------------- | ------------------- | ------------------------------------------------------------------------------------- |
| 1   | [MCP 生态](./mcp-ecosystem.zh.md) · [en](./mcp-ecosystem.md)                                      | MCP 网关（001）     | Coffer 是唯一**无按客户端范围**的网关——每个对手都按客户端定制。                       |
| 2   | [Agent 配置与规则管理](./agent-config-management.zh.md) · [en](./agent-config-management.md)      | Agent 注册表（004） | Coffer 结构性领先（双向、安全编辑），但**不分发指令**——这是该品类核心功能。           |
| 3   | [Agent 技能](./agent-skills.zh.md) · [en](./agent-skills.md)                                      | 技能管理（005）     | 跨 agent 投递 + SSRF 加固采集领先；**无技能扫描器 / 未对齐标准**是缺口。              |
| 4   | [Agent 插件](./agent-plugins.zh.md) · [en](./agent-plugins.md)                                    | 插件 facet（004）   | "可见性+安全 toggle、不安装"被**验证**正确；**插件→中枢桥**是新颖一招。               |
| 5   | [本地优先控制台](./local-first-control-plane.zh.md) · [en](./local-first-control-plane.md)        | 整体定位            | "管理**全部**资产的金库"独一无二（对手只管 MCP）；借鉴**上游沙箱** + **profiles**。   |
| 6   | [知识库 / RAG](./knowledge-base-rag.zh.md) · [en](./knowledge-base-rag.md)                        | KB（006）           | 文件为真相 + reindex 胜过锁定 embedding 的对手；借鉴 **RRF 融合 + 重排**。            |
| 7   | [消息渠道](./messaging-channels.zh.md) · [en](./messaging-channels.md)                            | 渠道（009）         | 渠道即资源 + 隐身配对有差异化（Anthropic TG 插件是唯一对应物）；借鉴**按会话绑定**。  |
| 8   | [多机同步](./multi-machine-sync.zh.md) · [en](./multi-machine-sync.md)                            | 同步（010）         | **对账而非覆盖**独一无二；借鉴 chezmoi 的**按机器模板**。                             |
| 9   | [凭证与密钥](./credentials-secrets.zh.md) · [en](./credentials-secrets.md)                        | 凭证（015）         | Coffer 已实现 1Password "**访问而不暴露**"理想；借鉴**外部提供者引用**（`op://`）。   |
| 10  | [可观测、审计 + MCP 安全](./observability-governance.zh.md) · [en](./observability-governance.md) | 审计/retention/安全 | 治理/审计**领先**（免费 vs Langfuse 付费墙）；借鉴 **MCP tool-pinning**（mcp-scan）。 |
| 11  | [Agent 评估](./agent-evaluation.zh.md) · [en](./agent-evaluation.md)                              | 评估（ADR-019/017） | **更正：飞轮已落地**（ADR-019 已 Accepted、`evals/` 存在）；借鉴 **LLM-as-judge**。   |
| 12  | [记忆系统](./memory-systems-landscape.zh.md) · [en](./memory-systems-landscape.md)                | 记忆（007）         | _并行 session 产出。_ 该领域分文件为真相 vs 向量为真相两派；Coffer 是有意的混合。     |

## 跨报告共性主题

通读各份，几个模式反复出现：

### Coffer 反复出现的差异化（作为头条）

- **广度：一个金库管理*全部* agent 资产。** 无竞品越过 MCP（控制台）。万物皆资源 + 文件为真相 +
  可重建索引，是它们都讲不出的耐久性故事。
- **双向 采集→中枢→投递。** 每个配置/技能对手都是单向生成；唯有 Coffer 还能*采集*（配置、插件、技能）。
- **设计上即隐私限定。** 无载荷调用日志、仅密文凭证（"访问而不暴露"）、单 owner 隐身渠道、免费强制
  审计（vs Langfuse 设付费墙）。默认即与业界自述的理想对齐。

### 被验证最充分的单一缺口：按客户端 / 按 agent 的范围控制

两份独立报告（MCP 生态、控制台）指向同一点：Coffer 把**整个网关塞进每个 agent**，而 ContextForge
（虚拟服务器）、MetaMCP（命名空间）、MCPJungle（工具组）、Docker（profiles）、mcpm（profiles）都
暴露**按客户端子集**。这既是 UX 修复（它正是 `search_tools` 存在的原因，在给自造的过载打补丁），也是
安全修复（对某 agent 隐藏敏感服务器）。**最高优先级借鉴。**

### 一个跨报告的安全/完整性机会

供应链 / 完整性威胁在三份报告里反复出现——技能（ToxicSkills、OWASP Agentic Skills Top 10、扫描器
绕过）、插件（GlassWorm、Open VSX）、MCP（工具投毒、rug-pull；mcp-scan 的 **Tool Pinning**；该领域正
向 Snyk/SentinelOne 整合）。Coffer 的 SSRF 加固采集是先发优势，但它**不扫描内容、不 pin 工具定义**。
一个"信任/完整性层"（技能扫描 + MCP 工具定义 pinning + 溯源）是一项能在技能、插件、MCP 三处同时收益
的举措——且对"金库"完全契合使命。

### 对齐开放标准

每个空间都有 Coffer 应消费/对齐以获得可移植性的标准：**agentskills.io**（技能）、**AGENTS.md**（指令）、
**官方 MCP Registry**（MCP 发现）、**OpenTelemetry GenAI**（若要做模型追踪——注意仍 pre-GA）。

### 其他反复出现的借鉴

- 给 KB 加 **RRF 混合融合 + 重排**（每个认真的 RAG 同类都做）。
- **外部提供者凭证引用**（`op://`），让用户不必把密钥复制进 Coffer；以及同步的**按机器模板**（chezmoi）。
- **把指令/规则做成中枢投递的资产** —— 唯一的"缺失 kind"（Coffer 做了 MCP + 技能的中枢投递，没做指令）。
- **广度：** 点亮 4 个接好但隐藏的 agent（对手覆盖 12–28）。

### 研究暴露的两处事实更正

- **KB** 暴露的是**四个只读 MCP 工具**（list / search / grep / read），不是单一 `coffer__ask`；
  `ask` 是 ADR-024 叠在其上的 agentic 层。
- **评估不是蓝图** —— ADR-019 已 Accepted（2026-06-14），且本地优先 `evals/` harness 已落地
  （捕获 → 精选 → 金样 → CI 门禁）。

## 覆盖说明

KB run 标记的一处覆盖缺口——AnythingLLM、Onyx、Khoj、Morphik、LlamaIndex 取证不足——已有**针对性补跑**，
其结论已并回 [knowledge-base-rag.zh.md](./knowledge-base-rag.zh.md)。

## 方法

每份报告 = 一次 deep-research run：问题分解为约 5 个搜索角度 → 并行网络搜索 → 抓取头部来源 →
提取可证伪 claim → 三票对抗式核验 → 综合。读取了 Coffer 自身仓库/规格来核对的 run 在对应报告里注明
（KB、评估）。
