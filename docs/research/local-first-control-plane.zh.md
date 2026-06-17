# 竞品调研 —— 本地优先的 AI-agent / MCP 控制台

> 中文版：本文件 · English: [local-first-control-plane.md](./local-first-control-plane.md)
>
> 关于 Coffer 作为本地优先金库的整体定位的内部竞品调研报告。**日期：** 2026-06-16。
> **方法：** deep-research harness（本轮核验大体成功——多条 claim 经 3-0 确认）。

## 1. 全景速览

2026 年确实存在"AI agent 本地控制台"这个品类，但它**压倒性地以 MCP 为中心**：几乎每个工具
都在解决*按客户端的 MCP 配置散乱*——MCP 服务器如何安装、运行、代理、鉴权——而不是"管理 agent
全部资产的单一金库"。它们沿三个维度分裂：

| 维度                    | 行为                         | 例子                                                      |
| ----------------------- | ---------------------------- | --------------------------------------------------------- |
| **纯配置管理器**        | 集中配置；**无运行时网关**   | mcpm v2                                                   |
| **聚合守护进程 / 网关** | 一个本地端点置于多服务器之前 | 1MCP、Station、ToolHive（vMCP）、unrelated-ai/mcp-gateway |
| **窄鉴权垫片**          | 只挡单个服务器；拒绝聚合     | mcp-auth-proxy                                            |

**本地优先是一个谱系，且市场正漂向团队/云：** ToolHive、1MCP、unrelated-ai 真正可自托管
开源；**Station** 推向其 CloudShip 后端；**Plugged.in** 的代理依赖后端（需独立的 plugged.in
App + API key）；**Toolbase** _弃用了开源 Electron 桌面_，转向托管的 Cloudflare-containers
web 产品。

### 各玩家

- **ToolHive**（`stacklok/toolhive`，OSS）—— 最完整、企业级的本地优先 MCP 控制台，明确定位
  为面向合规的反 SaaS 选项。**把每个 MCP 服务器跑在隔离的 Docker/Podman 容器**里，来源是
  受审注册表 / 任意容器 / 包管理器（`uvx://`、`npx://`、`go://`），前置一个**把上游聚合到
  单端点的 vMCP 网关**，内建密钥管理（加密 OS-keyring、1Password 只读、env）、企业 OAuth、
  网络访问过滤。_注：_ 生产 vMCP 主要经 Kubernetes Operator 运行（团队/集群范围）；
  MCPRemoteProxy + 其 vMCP 鉴权仍在开发中；网络隔离仅 HTTP/HTTPS。vMCP 于 2025-12-11 GA。
  [高置信 —— github.com/stacklok/toolhive；docs.stacklok.com]
- **mcpm**（`pathintegral-institute/mcpm.sh`，MIT CLI）—— 典范级**纯配置管理器**：把 MCP
  服务器一次性装进全局工作区，用**虚拟标签 "profiles"** 组织，并跨 10+ 个命名客户端
  （Claude Desktop、Cursor、Windsurf、VS Code、Cline、Continue、Goose、5ire、Roo、OpenCode）
  同步启停/导入。v2 **有意移除了 v1 的 "Router" 守护进程**——它集中配置，不是运行时网关。
  活跃维护（v2.15.0，2026-05-22）。[高置信]
- **1MCP**（`1mcp-app/agent`，Apache-2.0）—— 干净的本地优先自托管**聚合守护进程**：
  `1mcp serve` 把多个 MCP 服务器合并为一个运行时（stdio 代理 + 可选直连 streamable-HTTP），
  消灭按客户端的接线/鉴权/过滤散乱。npm 安装、可 Docker 自托管、非云。**未记录任何内建密钥库 /
  信封加密**用于上游凭证（OAuth 仅用于鉴权*访问 1MCP*）。[高置信]
- **Station**（`cloudshipai/station`）—— 自托管多端口守护进程，推向 CloudShip 后端。
- **Plugged.in** —— 依赖独立托管 app + API key 的代理。
- **Toolbase** —— 弃用开源桌面，转托管 web 产品。
- **mcp-auth-proxy** —— 单服务器 OAuth/鉴权垫片，明确拒绝聚合。

## 2. 能力对比

| 能力                    | ToolHive                 | mcpm         | 1MCP          | Station | **Coffer**                                |
| ----------------------- | ------------------------ | ------------ | ------------- | ------- | ----------------------------------------- |
| 管理的资产范围          | 仅 MCP                   | 仅 MCP       | 仅 MCP        | 仅 MCP  | **MCP + agent + 技能 + KB + 记忆 + 渠道** |
| 聚合网关                | ✅ vMCP                  | ❌（仅配置） | ✅            | ✅      | ✅                                        |
| 按客户端/profile 范围   | ✅ vMCP 虚拟服务器       | ✅ profiles  | 部分          | ✅      | **❌ 每 agent 全有或全无**                |
| 上游隔离/沙箱           | ✅ 每服务器一容器        | ❌           | ❌            | 部分    | **❌ 裸子进程**                           |
| 密钥管理                | ✅ keyring/1Password/env | ❌           | ❌            | 部分    | **✅ 信封加密库**                         |
| 文件为真相 + 可重建索引 | ❌                       | n/a          | ❌            | ❌      | **✅**                                    |
| 受审服务器注册表/发现   | ✅                       | 部分         | ❌            | ❌      | **❌**                                    |
| 单用户本地优先定位      | 团队/K8s 漂移            | ✅           | ✅            | 云漂移  | **✅ 严格 127.0.0.1 单用户**              |
| 覆盖客户端/agent        | 多                       | 10+          | 多            | 多      | **2 个启用（4 个隐藏）**                  |
| 开源                    | ✅                       | ✅ MIT       | ✅ Apache-2.0 | 部分    | ✅ MIT                                    |

## 3. Coffer 对比

**Coffer 真正独特之处。**

1. **范围。** Coffer 是*唯一*把自己定位为管理 agent **全部**资产金库的工具——MCP servers、
   agents、技能、知识、记忆、渠道，作为一个 resource kind 共享身份/生命周期/审计。每个竞品
   都只管 MCP。这种广度就是护城河。
2. **文件为真相 + 可重建索引。** 无竞品把状态建模为磁盘上的 markdown + 可丢弃 SQLite 索引。
   这是它们都讲不出的耐久性与备份故事。
3. **严格的单用户本地优先。** 当业界漂向团队/云（ToolHive→K8s、Station→CloudShip、
   Toolbase→托管、Plugged.in→后端）时，Coffer 的 127.0.0.1 单用户金库是有意的、愈发独特的
   生态位。

**Coffer 重叠 / 落后 —— 应借鉴之处。**

1. **上游隔离（最大安全缺口）。** ToolHive 把**每个 MCP 服务器跑在自己的容器**里。Coffer
   以裸子进程 spawn 上游、无沙箱。对一个自称"金库"的工具，无沙箱运行不可信 MCP 服务器是最尖锐
   的缺口。借鉴容器/沙箱隔离（至少可选）。
2. **按客户端/profile 范围（修复一个已知 Coffer 限制）。** mcpm 的 _profiles_ 与 ToolHive 的
   *vMCP 虚拟服务器*都能按客户端暴露服务器*子集*。这正是 Coffer "整网关塞给每个 agent" 的解药。
   采用 profile/虚拟服务器概念，让 agent A 拿到 GitHub 而 agent B 没有。
3. **网络出口过滤。** ToolHive 过滤每个服务器的网络访问；Coffer 只守自己的出站（SSRF），不管
   它 spawn 的上游。
4. **受审服务器注册表/发现。** ToolHive 自带受审注册表；Coffer 没有（与 MCP 生态报告同缺口）。
5. **密钥提供者插件。** ToolHive 集成 1Password；Coffer 的库自包含——一个 1Password/keyring
   提供者插件是廉价的对齐。

## 4. 给 Coffer 的关键结论

1. **"管理全部资产、单用户、本地优先"的定位独特且可守**——无竞品越过 MCP。把广度作为头条；
   它就是护城河。
2. **杠杆最高的借鉴：上游沙箱**（ToolHive 每服务器一容器）。无沙箱运行不可信 MCP 服务器削弱了
   "金库"承诺。
3. **第二借鉴：profiles / 虚拟服务器**做 per-agent 范围——Coffer "全有或全无" 网关注入的直接、
   被验证的解药。
4. **团队/云这一段是空的**，因为 Coffer 有意单用户；这是一个要有意识做出的战略选择，而非默认。
5. **对齐性补充：** 受审服务器注册表 + 密钥提供者插件（1Password），对标 ToolHive/mcpm。

## 5. 来源

一手（项目仓库/文档）：

- github.com/stacklok/toolhive · docs.stacklok.com/toolhive _(确认：隔离、vMCP、密钥)_
- github.com/pathintegral-institute/mcpm.sh _(确认：profiles、v2 移除 router)_
- github.com/1mcp-app/agent · docs.1mcp.app _(确认：聚合器、无密钥库)_
- github.com/cloudshipai/station
- plugged.in（文档）· gettoolbase.ai（弃用通告）
- mcp-auth-proxy（项目 README）· unrelated-ai/mcp-gateway
