# 竞品调研 —— 可观测、审计与治理 + MCP 安全

> 中文版：本文件 · English: [observability-governance.md](./observability-governance.md)
>
> 面向 Coffer 审计/retention/调用日志 + 本地安全原语的内部竞品调研报告。**日期：** 2026-06-16。
> **方法：** deep-research harness（关键结论 3-0 确认）。

## 1. 全景速览

这个领域分为 Coffer 部分横跨的两个角度：

| 角度                     | 是什么                               | 例子                                                                                 |
| ------------------------ | ------------------------------------ | ------------------------------------------------------------------------------------ |
| **(A) Agent/LLM 可观测** | 追踪模型+工具调用、token、成本、延迟 | Langfuse、LangSmith、Helicone、Arize Phoenix、AgentOps；**OpenTelemetry GenAI 约定** |
| **(B) MCP 安全 / 治理**  | 检测工具投毒、rug-pull、提示注入     | Invariant `mcp-scan`、Lasso MCP Gateway、Prompt Security                             |

### (A) 可观测

- **Langfuse**（MIT，经 Docker Compose / Kubernetes 免费自托管）—— 捕获 agent 迹/图、
  会话/线程 + 用户追踪、**所有层级（含免费 Hobby 层）的 token + 成本追踪**。值得注意：它
  **把审计日志 / SSO / RBAC 锁在企业版后面**——即*治理*面是付费墙。
- **OpenTelemetry GenAI 语义约定** —— 新兴的厂商中立标准：`gen_ai.operation.name`
  （`create_agent` / `invoke_agent` / `plan` / `execute_tool` / 记忆操作）、标准化 token
  用量（input/output + cache-creation / cache-read / reasoning 子类）、延迟、finish-reason、
  duration/token 直方图、工具调用属性。**完整 prompt/参数/结果内容是 Opt-In（最低要求级别）
  且默认关闭以保护隐私。** ⚠ 仍处 **"Development" 成熟度——非 GA**；属性名可在不升主版本号下
  改变；近期迁到独立的 `open-telemetry/semantic-conventions-genai` 仓库。[3-0 确认]

### (B) MCP 安全

- **Invariant Labs `mcp-scan`**（Apache-2.0，**被 Snyk 收购**）—— 检测**工具描述里的提示注入**
  和**工具投毒**；实现 **Tool Pinning**（对工具定义做哈希以捕获 **rug-pull / 静默改定义**）；
  支持静态（"scan"）或运行时（"proxy"/网关）模式。
- **Lasso MCP Gateway**（OSS）—— 代理 + 编排器，应用可配置的请求/响应过滤、**密钥掩码**、
  服务器/工具描述扫描。
- **Prompt Security**（**被 SentinelOne 收购**）—— 运行时提示注入 / 输出操纵 / 模型滥用防御
  - 一个 MCP 网关。
- **研究：** arXiv 2506.01333（ETDI）把这些威胁归因于 MCP **工具定义缺乏可验证的真实性/完整性
  标记**——这正是 Tool Pinning 修补的。

> **信号：MCP 安全领域正向安全大厂整合** —— mcp-scan → Snyk、Prompt Security → SentinelOne。

## 2. 能力对比

| 能力                     | Langfuse | OTel GenAI       | mcp-scan            | Lasso GW | **Coffer**                                   |
| ------------------------ | -------- | ---------------- | ------------------- | -------- | -------------------------------------------- |
| 模型 token/成本/延迟追踪 | ✅       | ✅（标准）       | —                   | —        | **❌ 无**                                    |
| Agent/工具 span 追踪     | ✅       | ✅ 词汇          | —                   | —        | 部分（调用日志）                             |
| **强制审计日志**         | 企业版锁 | —                | —                   | —        | **✅ 免费、actor 标记、每次生命周期变更**    |
| Retention 策略           | 分层     | —                | —                   | —        | **✅ 中央 prunable-table 注册**              |
| 调用记录（谁/何时/结果） | ✅       | ✅               | —                   | —        | **✅ 无参数/结果（不变量）**                 |
| 参数/结果捕获            | ✅       | opt-in（默认关） | —                   | —        | **❌（无 opt-in 逃生口）**                   |
| 请求关联                 | ✅       | ✅ trace ID      | —                   | —        | **✅ X-Coffer-Trace**                        |
| 工具定义完整性 / pinning | —        | —                | **✅ 哈希 pinning** | 部分     | **❌**                                       |
| 工具投毒 / 提示注入扫描  | —        | —                | **✅**              | ✅       | **❌**                                       |
| 密钥掩码 / 拒绝          | —        | —                | —                   | ✅ 掩码  | **✅ 配置密钥模式拒绝**                      |
| 本地安全原语             | —        | —                | —                   | —        | **✅ 仅回环、密文凭证、签名回调、SSRF 防护** |
| 自托管 / 开源            | ✅ MIT   | ✅               | ✅ Apache           | ✅       | ✅                                           |

## 3. Coffer 对比

**Coffer 有竞争力或领先之处。**

1. **治理/审计是一等公民且免费。** 强制的、actor 标记的、覆盖每次资源生命周期变更的审计日志 +
   retention 策略，比这里的可观测领头者*更强*——Langfuse 把审计日志锁在企业版；Coffer 默认就有。
   对单用户金库这正是正确侧重。
2. **"无参数/结果捕获"不变量站在隐私默认的正确一侧。** OTel 让内容捕获 opt-in 且默认关闭*以保护
   隐私*——Coffer 把同样的默认作为硬不变量强制执行。是对齐，不是缺口。
3. **本地安全原语在可观测工具里无对应物**——仅回环绑定、仅密文凭证、签名渠道回调、SSRF 防护出站、
   配置密钥模式拒绝，是这些云工具不涉及的、连贯的本地优先安全姿态。

**Coffer 落后 —— 具体借鉴。**

1. **无 MCP 工具定义完整性 / Tool Pinning（头号安全借鉴）。** mcp-scan 对工具定义做哈希以检测
   rug-pull / 静默改定义，并扫描工具描述里的提示注入 / 投毒。Coffer **聚合上游 MCP 服务器且已经
   实时查询其能力（ADR-004）**——它正好处在能在网关哈希 + pin 工具定义并对漂移告警的位置。这是最
   契合使命、最该加的安全特性。
2. **无 opt-in 的参数/结果捕获用于调试。** 这个不变量作为*默认*是对的，但每个调试流程都需要逃生口。
   借鉴 OTel 模型：opt-in、默认关闭、仅本地的参数/结果捕获。
3. **无 LLM 层可观测。** Coffer 不追踪其内部模型（ADR-024）调用——token/成本/延迟。若要加追踪，
   **采用 OpenTelemetry GenAI 约定**（同时注意它们仍是 Development、非 GA）。
4. **无运行时策略/护栏引擎。** Lasso/Prompt Security 强制请求/响应过滤；Coffer 有原语但无策略层。

## 4. 给 Coffer 的关键结论

1. **以治理/审计作为优势头条** —— 强制免费的审计 + retention 胜过可观测领头者（它们把审计设付费墙）。
   对金库，问责是正确头条。
2. **加入 MCP 工具定义 pinning（mcp-scan 风格）** —— 在网关哈希 + pin 上游工具定义，对 rug-pull/
   静默改定义告警，扫描工具描述的注入。你的网关 + ADR-004 能力追踪让这成为自然、高价值的补充；威胁真实
   且在整合（Snyk/SentinelOne）。
3. **加入 opt-in、默认关闭的参数/结果捕获**用于调试（OTel 内容捕获模型）——保留隐私不变量为默认，
   同时解锁调试。
4. **若加模型调用追踪，用 OpenTelemetry GenAI 约定** —— 但当作仍在发展（非 GA）的标准对待。

## 5. 来源

可观测：

- github.com/open-telemetry/semantic-conventions-genai · opentelemetry.io/blog/2026/genai-observability/ · opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-agent-spans（已重定向）
- langfuse.com（自托管、定价、追踪）· langsmith / helicone / arize phoenix / agentops 文档

MCP 安全：

- github.com/invariantlabs-ai/mcp-scan（Tool Pinning；Snyk 收购）· lasso.security（MCP Gateway）· prompt.security（SentinelOne 收购）
- arXiv 2506.01333（ETDI —— 工具定义完整性）

## 核查更新（2026-06-19）

> 五条主要论断（1 条本地 + 4 条网络）均经一手来源**确认**；仅本地"强制"
> 措辞上还有一处细节存疑。

### ✅ 已确认

- **Coffer 免费且无载荷的调用日志。** `MCPInvocation` 领域模型明确写着
  "NEVER carries args or result content"（绝不携带参数或结果内容）；其字段为
  timestamp / resource_name / capability_type / capability_key / duration_ms /
  status / error_message / session_id —— 没有参数/结果列，持久化模型与之一致。
  `repo:backend/coffer/domain/mcp/capability.py:57-69` · `repo:backend/coffer/infrastructure/mcp/invocation_writer.py:32-49`
- **免费、actor 标记的审计日志。** `AuditService`/`AuditEntry` 记录带 actor 标记的
  生命周期事件（event_type、resource_kind/name、actor、details），代码中无任何
  分层限制 —— 即在自托管产品中免费。`repo:backend/coffer/application/audit_service.py:13-58`
- **Langfuse 把治理面设为付费墙。** 审计日志查看器是企业版功能；细粒度的项目级
  RBAC 需要企业版授权密钥；SSO/SCIM + 高级审计日志都在企业版（SSO 也可经付费
  Teams 附加项获得）。定价：Hobby $0 / Core $29 / Pro $199 / Enterprise 定制
  （约 $2,499+）。https://langfuse.com/docs/administration/audit-logs · https://github.com/orgs/langfuse/discussions/8147
- **OTel GenAI 约定仍为 "Development"（非 GA）且已迁仓。** 新仓库的
  `gen-ai-agent-spans.md` 在文档级与各 span 级（Create agent、Invoke agent、
  Invoke workflow、Plan、Execute tool）都标注 "Status: Development"；旧的
  `opentelemetry.io/docs/specs/semconv/gen-ai/` 页面现已显示"已迁移……不再维护"。
  https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-agent-spans.md · https://opentelemetry.io/docs/specs/semconv/gen-ai/
- **两起收购均已完成（closed）。** Snyk 于 2025 年 6 月宣布收购 Invariant Labs
  （mcp-scan 作者）；mcp-scan 在 Snyk Agent Scan 下仍开源。SentinelOne 于
  2025-09-05 完成对 Prompt Security 的收购（约 $1.8 亿，8 月 5 日宣布）。
  https://snyk.io/news/snyk-acquires-invariant-labs-to-accelerate-agentic-ai-security-innovation/ · https://investors.sentinelone.com/press-releases/news-details/2025/SentinelOne-to-Acquire-Prompt-Security-to-Advance-GenAI-Security-and-Agent-Security-Strategy/default.aspx
- **mcp-scan Tool Pinning 能捕获 rug-pull。** 它在首次扫描时对每个工具的定义
  （来自 `tools/list` 清单的 name、description、input schema）做哈希，并在后续
  扫描时比对；任何差异即告警 —— 正对准"一次性批准后被静默改定义"的工具。
  https://invariantlabs.ai/blog/introducing-mcp-scan · https://github.com/invariantlabs-ai/mcp-scan

### ❓ 仍待核查

- **日志是否"强制"/ 不可禁用。** "免费"与"无载荷"两点已在代码中确认（无载荷是
  docstring 明示的硬领域不变量），但未找到强制"记录本身不可被禁用"的代码（未见
  opt-out 开关或配置闸门）。因此"强制"措辞相对代码可直接确认性而言略带愿景色彩。
  `repo:backend/coffer/infrastructure/mcp/invocation_writer.py:139-152`
