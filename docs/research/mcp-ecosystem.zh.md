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
