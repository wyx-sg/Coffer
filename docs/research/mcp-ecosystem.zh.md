# 竞品调研 —— MCP 网关、聚合器与注册表

> 中文版：本文件 · English: [mcp-ecosystem.md](./mcp-ecosystem.md)
>
> 面向 Coffer MCP gateway（spec 001）的内部竞品调研报告。**日期：** 2026-06-16。
> **方法：** deep-research harness（25 条 claim 中 24 条经 3 票确认；下文两条头号结论
> 通过了完整对抗式核验）。

## 1. 全景速览

2026 年的 MCP 基础设施市场清晰地分为**两层**，二者常被混为一谈：

| 层                          | 是什么                                             | 例子                                                                                |
| --------------------------- | -------------------------------------------------- | ----------------------------------------------------------------------------------- |
| **注册表 / 目录**（元数据） | 一份*服务器元数据*目录（不是代码），用于发现与安装 | 官方 MCP Registry、Smithery、Glama、PulseMCP、Composio、Docker MCP Catalog          |
| **网关 / 聚合器**（运行时） | 一个把多个上游服务器置于单一端点之后的运行代理     | IBM ContextForge、MetaMCP、ToolHive vMCP、Docker MCP Gateway、MCPJungle、**Coffer** |

**注册表层。** **官方 MCP Registry**（Anthropic + Linux Foundation，2026 年内处于
预览期）是一个开放的、**无需鉴权的只读 REST API，提供服务器元数据**（指向软件包的
指针，而非代码）。聚合器大约每小时抓取一次；下游子注册表重新实现其 OpenAPI 规范，
并注入评分、下载量与安全扫描。宿主应用消费的是*下游市场*（Smithery、Glama、PulseMCP、
Composio、Docker MCP Catalog），而非根注册表。**它明确不是网关。** [3-0 确认]

**网关层。** 五个网关把多个上游置于单一端点之后，**并让不同客户端看到不同的定制工具
子集。** Coffer 是其中之一——命名空间与密钥处理上很强，且是唯一同时提供"搜工具的
工具"和"自主回答的工具"的网关。**它的独特短板：把整个网关一次性塞给每个 agent；
另外四家则让每个客户端获得各自的定制工具集。** [3-0 确认]

### 各网关

- **IBM ContextForge**（`IBM/mcp-context-forge`，OSS）—— 把上游工具的定制子集组合成
  命名的**"虚拟服务器（virtual servers）"**，分别暴露给不同客户端；完整 OAuth/鉴权
  方案（Red Hat 有文档）。自托管。
- **MetaMCP**（`metatool-ai/metamcp`，OSS）—— 把服务器分组为**"命名空间（namespaces）"**，
  以按端点的聚合形式暴露，带中间件做过滤。自托管。
- **ToolHive vMCP**（`stacklok/toolhive`）—— 一个"虚拟 MCP"网关，聚合后端并带容器
  隔离与范围控制（vMCP 于 2025-12-11 GA；生产路径偏 K8s）。_注：_ 本轮核验中 vMCP
  逐实例工具过滤的精确机制未通过验证——描述为"聚合 + 范围控制"，不过度刻画内部细节。
- **Docker MCP Toolkit / Gateway + Catalog** —— 以 Docker 容器运行 MCP 服务器；
  **自定义 catalog 与"profiles"**界定某客户端可见的服务器；内建密钥与安全。
- **MCPJungle**（`mcpjungle/MCPJungle`，OSS）—— 自托管的注册表+网关，用**"工具组
  （tool groups）"**做按客户端的范围控制。

### 对抗工具过载 —— 两种策略

业界用**两种方式**对抗工具过载，领头者两者都做：

1. **静态按客户端定制** —— 虚拟服务器（ContextForge）、命名空间（MetaMCP）、工具组
   （MCPJungle）、profiles（Docker）。客户端只看到你分配给它的子集。
2. **运行时工具检索** —— Anthropic 自己把 **MCP 工具检索带进了 Claude Code**
   （按需加载工具定义）。[tessl.io]

**Coffer 做的是策略 2（`search_tools` + `ask`），但没有策略 1。**

## 2. 能力对比

| 能力                 | ContextForge    | MetaMCP    | ToolHive vMCP     | Docker MCP  | MCPJungle   | **Coffer**                  |
| -------------------- | --------------- | ---------- | ----------------- | ----------- | ----------- | --------------------------- |
| 单端点聚合           | ✅              | ✅         | ✅                | ✅          | ✅          | ✅                          |
| 命名空间             | virtual servers | namespaces | vMCP              | catalog     | tool groups | **`server__tool`**          |
| **按客户端定制子集** | ✅              | ✅         | ✅                | ✅ profiles | ✅          | **❌ 整网关塞给每个 agent** |
| 运行时工具检索       | —               | —          | —                 | —           | —           | **✅ search_tools**         |
| 自主回答工具         | —               | —          | —                 | —           | —           | **✅ ask**                  |
| 密钥处理             | OAuth/secrets   | env        | keyring/1Password | secrets     | —           | **✅ 引用 + 静态密文**      |
| 上游隔离             | —               | —          | ✅ 容器           | ✅ 容器     | —           | **❌ 子进程**               |
| 传输                 | stdio/HTTP      | stdio/HTTP | stdio/HTTP        | stdio/HTTP  | stdio/HTTP  | **stdio(shim) + HTTP 上游** |
| 本地优先单用户       | 团队/服务端     | 服务端     | 团队/K8s          | 桌面+       | 服务端      | **✅ 严格**                 |
| 开源                 | ✅              | ✅         | ✅                | 部分        | ✅          | ✅                          |

## 3. Coffer 对比

**Coffer 有竞争力或领先之处。**

1. **命名空间 + 密钥扎实。** `server__tool` 前缀，以及"配置存引用 / 静态密文 /
   spawn 时物化"的模型，与业界最佳齐平。
2. **它是唯一同时提供运行时工具检索*与*自主回答工具的网关。** `search_tools`
   （BM25 + 可选 embedding）与对 knowledge/memory 的 `ask`，与 Anthropic 给
   Claude Code 选的策略一致——而 `ask`（检索-综合）比任何受访网关更进一步。
3. **严格的单用户本地优先**很有辨识度；多数网关偏服务端/团队/K8s。

**Coffer 落后之处 —— 头号差距。**

1. **没有按客户端定制子集。** 这是唯一被核验、且全票一致的结论：ContextForge
   （虚拟服务器）、MetaMCP（命名空间）、MCPJungle（工具组）、Docker（profiles）都
   让*每个客户端看到不同的范围子集*。Coffer 把**整个网关塞进每个 agent**。这既是
   UX 差距（只需要一个工具的 agent 拿到了全部——这正是 `search_tools` 存在的部分
   原因，某种程度上是在给自造的过载打补丁），也是安全差距（无法对某个 agent 隐藏
   某个敏感服务器）。
2. **没有上游隔离。** ToolHive、Docker 把每个服务器跑在容器里；Coffer 是裸子进程。
3. **没有注册表/发现。** Coffer 没有目录；业界有丰富的注册表层（官方 Registry +
   Smithery/Glama/PulseMCP）。

## 4. 给 Coffer 的关键结论

1. **加入按客户端/按 agent 的范围控制——头号借鉴。** "profile"或"虚拟服务器"概念
   （每个 agent 一份定制的服务器/工具子集）是这一领域被验证最充分的点子；其他每个
   网关都有，唯独 Coffer 没有。它同时解决工具过载的根因和"无法对某 agent 隐藏敏感
   服务器"的问题。
2. **保留工具检索 + `ask` 的优势**——这确实有差异化；让它与定制*并存*，而非替代定制。
3. **消费官方 MCP Registry** 做发现/安装，而不是要求手填配置——它正是为此而生的
   开放、无鉴权元数据 API。
4. **考虑可选的上游隔离**（容器/沙箱），对不可信服务器对标 ToolHive/Docker。

## 5. 来源

网关（一手）：

- github.com/IBM/mcp-context-forge · ibm.github.io/mcp-context-forge/manage/oauth/
- github.com/metatool-ai/metamcp · docs.metamcp.com/en/concepts/namespaces
- github.com/stacklok/toolhive · stacklok.com/blog（Introducing Virtual MCP Server）
- docs.docker.com/ai/mcp-catalog-and-toolkit · docker.com/blog（Docker MCP Gateway / 自定义 catalog 与 profiles）
- github.com/mcpjungle/MCPJungle

注册表（一手）：

- blog.modelcontextprotocol.io/posts/2025-09-08-mcp-registry-preview/
- modelcontextprotocol.io/registry/registry-aggregators · github.com/modelcontextprotocol/registry

工具过载 / 评论：

- tessl.io/blog/anthropic-brings-mcp-tool-search-to-claude-code/
- pulsemcp.com/posts/virtual-mcp-servers-and-gateways
- heyitworks.tech/blog/mcp-aggregation-gateway-proxy-tools-q1-2026 · truefoundry.com/blog/best-mcp-registries
- developers.redhat.com/articles/2025/12/12（MCP 网关的高级鉴权）

## 核查更新（2026-06-19）

> 再核验：除一条已被落地代码推翻外，其余 claim 均成立——"没有按 agent 范围控制"这条
> LOCAL 头号结论已翻转（PR #108 / ADR-026，已于 2026-06-18 合并），下移至 ✏️ 已修正；
> `search_tools`/`ask` 那条 LOCAL 结论仍成立。WEB claim 在两处升级了引用来源、一处
> 收窄了表述后确认。

### ✅ 已确认

- **Coffer 同时提供 `search_tools` 与 `ask`。** `search_tools` 是内建元工具
  （`tool_search_descriptor()` 在 `append_builtin_tools()` 中追加，由
  `dispatch_tool_search()` 派发——默认 BM25，提供 embedder 时走语义检索，依 ADR-024）；
  `ask` 是一个 `BuiltinTool`（对外暴露为 `coffer__ask`），由 `make_ask_tool()`
  构建——一个对 knowledge base + memory 的有界 ReAct 检索-综合循环（仅只读检索工具）。
  二者经由同一网关暴露。
  `repo:backend/coffer/application/mcp/gateway_builtin.py:144-201`、
  `repo:backend/coffer/infrastructure/chat/agentic_rag.py:53-165`、
  `repo:backend/coffer/surfaces/http/wiring.py:253-293`
- **ToolHive vMCP 逐实例工具过滤**（报告中标记其精确机制未通过核验）——现据 Stacklok
  一手文档确认：每个 `VirtualMCPServer` 引用一个 `MCPGroup` 并独立定义自己的聚合配置，
  因此同一批后端上的不同 vMCP 实例可暴露不同的定制子集。关键字段：
  `aggregation.tools[].filter`（按后端的白名单）、`aggregation.tools[].excludeAll`、
  `aggregation.excludeAllTools`（全局隐藏）、`aggregation.tools[].overrides`
  （改名/改描述）。被过滤的工具从 `tools/list` 移除，但仍留在内部路由表中以支持组合式
  工作流。
  https://docs.stacklok.com/toolhive/guides-vmcp/tool-aggregation
- **官方 MCP Registry 截至 2026-06 仍处于预览期。** 2025 年 9 月的发布博文将其定位为
  GA 之前的预览（可能有破坏性变更/数据重置），是一份开放的只读 REST 服务器元数据目录，
  带 OpenAPI 规范（截至 2026-05-24 约 9,652 条记录）。
  https://blog.modelcontextprotocol.io/posts/2025-09-08-mcp-registry-preview/

### ✏️ 已修正

- **"没有按客户端/按 agent 的范围控制"现已过时——Coffer 已落地该能力。** 本报告的
  头号差异点（"唯一把整个网关塞给每个 agent、唯一没有按客户端范围控制的网关"，见
  §1/§2 对比表/§3/§4）已被 **PR #108 / ADR-026**
  （`docs/decisions/ADR-026-per-agent-mcp-scoping.md`）推翻，该 PR 已于 **2026-06-18**
  合并。Coffer 现已支持**按 agent 的 MCP 服务器范围控制**，提供两种模式：`auto`
  （默认——暴露所有已启用服务器，完全向后兼容）与 `selected`（一份按 agent 的显式
  白名单）。agent 身份随会话传递：安装写入器把 `--agent <name>` 写进该 agent 的
  `coffer` MCP 条目，shim 将其作为 **`X-Coffer-Agent`** 请求头转发，网关据此把会话
  绑定到该 agent，并在 `tools/list` / `resources/list` / `prompts/list`、
  `coffer__search_tools` 排序，**以及**直接的 `tools/call` / `resources/read` /
  `prompts/get` 上强制执行有效范围（已启用 ∩ 白名单）——调用路径才是真正的边界，而非
  仅在 list 时隐藏。无身份的会话（如进程内内建 agent）保持不受限。agent 的网关 MCP UI
  现已是一个**可编辑的范围选择器**（auto/selected 单选 + 按服务器的白名单复选框）。
  因此本报告"唯一没有按客户端范围控制的网关"这条头号结论应视为**历史结论**——一处
  Coffer 此后已**补齐**的短板；它已不再把 Coffer 与 ContextForge / MetaMCP /
  MCPJungle / Docker 区分开来。
  `repo:backend/coffer/domain/agent/mcp_install.py:44-91`、
  `repo:backend/coffer/surfaces/shim/main.py:145-150`、
  `repo:backend/coffer/surfaces/http/mcp/protocol_routes.py:150,247`、
  `repo:backend/coffer/application/agent/scope_service.py:33-96`、
  `repo:backend/coffer/application/mcp/gateway.py:165-222`、
  `repo:frontend/src/components/agents/AgentGatewayMcpSection.tsx`、
  `repo:docs/decisions/ADR-026-per-agent-mcp-scoping.md`
- **"唯一带运行时工具检索的网关"对更大范围的业界而言表述过强。** 旧：对比表把运行时
  工具检索标为 Coffer 独有，对五家对手全部记为 `—`。修正：即便越出受访的五家，工具检索/
  渐进披露也并非独有——AIRIS 提供 7 个元工具（find/exec/schema/suggest/route…），
  MarimerLLC/mcp-aggregator 主打"懒加载工具发现（lazy tool discovery）"，MetaMCP 以
  "MCP 工具选择的 Elasticsearch"为卖点，MCPJungle/ContextForge 也有发现/渐进披露能力。
  真正有辨识度的是*组合*：运行时工具检索**加上**对 knowledge/memory vault 的自主检索-综合
  `ask`（RAG 式）回答工具——受访网关中无一提供 RAG 式回答工具。建议把 §1/§3 由"唯一带
  工具检索的网关"改写为"在把工具检索与自主 ask/RAG 回答工具配对上具备辨识度"。
  https://www.heyitworks.tech/blog/mcp-aggregation-gateway-proxy-tools-q1-2026 ·
  https://github.com/MarimerLLC/mcp-aggregator
- **Claude Code 的 MCP 工具检索现已有一手来源。** 旧：仅引用 tessl.io 评论博文。修正：
  官方 Claude Code 文档"Scale with MCP Tool Search"一节指出工具检索默认开启，MCP 工具
  被延迟加载而非一次性预载，Claude 按需检索相关工具（`ENABLE_TOOL_SEARCH`：
  unset/true/auto/false；`auto` = 若占用在上下文窗口 10% 以内则预载）。随 Claude Code
  2.1.7 于 2026-01-14 发布。
  https://code.claude.com/docs/en/mcp（"Scale with MCP Tool Search"一节）
- **"2026 年内处于预览期"是推断，并非官方表述。** 发布博文未给出 GA 时间线，也未逐字
  使用"无需鉴权（unauthenticated）"一词（API 是开放/只读的）。该表述与当前状态一致，
  但应标注为推断，而非引用的承诺。
  https://blog.modelcontextprotocol.io/posts/2025-09-08-mcp-registry-preview/

### ➕ 新增覆盖

- **IBM ContextForge** —— 确认经由统一端点上命名的"虚拟服务器"提供按客户端定制子集；
  开源的注册表+代理，联邦 MCP/A2A/REST/gRPC，带 40+ 插件、护栏与完整 OAuth；支持渐进
  披露/发现，故运行时工具检索并非 Coffer 独有。
  https://github.com/IBM/mcp-context-forge
- **MetaMCP** —— 确认三级层次 Servers → Namespaces → Endpoints；命名空间即暴露给客户端
  的按端点定制聚合，带描述覆盖与中间件过滤；以"MCP 工具选择的 Elasticsearch"为卖点。
  https://github.com/metatool-ai/metamcp
- **MCPJungle** —— 确认自托管的注册表+网关，"工具组（Tool Groups）"支持包含/排除与按
  客户端白名单（即按客户端定制子集），与报告一致。
  https://www.heyitworks.tech/blog/mcp-aggregation-gateway-proxy-tools-q1-2026
- **Docker MCP Toolkit/Gateway + Catalog** —— 以容器运行 MCP 服务器；自定义 catalog 与
  "profiles"界定客户端可见的服务器，内建密钥/安全（按客户端子集 = profiles）。据报告
  所引 Docker 来源刻画，本轮未独立重新抓取。
  https://docs.docker.com/ai/mcp-catalog-and-toolkit
- **ToolHive vMCP（Stacklok）** —— 确认逐实例定制子集：每个基于 `MCPGroup` 的
  `VirtualMCPServer` 应用各自的 `aggregation.tools[].filter` 白名单 /
  `excludeAll(Tools)` / `overrides`；后端容器隔离；vMCP 于 2025 年 12 月引入（Stacklok
  文档未给出明确 GA 日期——见 `local-first-control-plane.md` 中的更正），生产路径偏 K8s。
  https://docs.stacklok.com/toolhive/guides-vmcp/tool-aggregation
