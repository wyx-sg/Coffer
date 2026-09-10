# 网关侧的预算驱动工具分层

> English: [budget-driven-tool-tiering.md](budget-driven-tool-tiering.md)

**状态**：Accepted
**日期**：2026-09-09
**决策者**：Yuxing Wu
**修订**：[Tool Retrieval](tool-retrieval-for-overload.zh.md) —— 其「绝不在服务端隐藏」条款由预算驱动分层取代
**关联**：[Built-in Agent Is Internal](builtin-agent-is-internal-capability.zh.md)（语义排序）、[Per-Agent Resource Scope](per-agent-resource-scope.zh.md)（machine × agent scope）、[Capability State Model](capability-state-model.zh.md)（能力偏好）、已撤销的 per-agent MCP 服务器 scope 决策（该 ADR 已移除）、[spec `mcp-gateway`](../../specs/mcp-gateway/spec.zh.md)、[`docs/research/mcp-ecosystem.zh.md`](../research/mcp-ecosystem.zh.md)

## 背景

[Tool Retrieval](tool-retrieval-for-overload.zh.md) 交付了 `coffer__search_tools` 作为聚合过载的答案，并押了一个明确的赌注：

> **Additive。** Coffer 继续原样广播完整的上游目录；服务端不隐藏任何东西。工具延迟加载（tool deferral）若发生，那是客户端自己的选择。

这个赌注在真实使用中已被证伪。本 vault 上的实测：

| 信号 | 数值 |
| --- | --- |
| 已注册服务器上发现的上游工具 | 316 |
| 触达一个实际 Claude Code 会话的上游工具 | 约 125 |
| 历史上真正被调用过的不同工具 | 44 |
| 一次日志轮转内的 `mcp.gateway.list_tools.upstream_failed` | 180 |

两件事出了问题。

**客户端的 deferral 是无差别的。** 面对来自单一服务器的约 125 个工具，Claude Code 把整个 `mcp__coffer__*` 命名空间挪到了它自己的 tool-search 间接层后面——**其中包括 `coffer__search_tools` 自己**。Tool Retrieval 的逃生舱，最终被锁在了它本要打开的那扇门后。把决定权交给客户端，前提是客户端会**有选择地**折叠；它不会，也做不到，因为它没有可供判断的使用信号。Coffer 有。

**没有任何东西告诉过 agent Coffer 的存在。** 网关的 `initialize` 应答不带 MCP `instructions` 字段，因此没有任何客户端在系统提示层面收到过「Coffer 是什么」或「该先调 `search_tools`」的说明。Tool Retrieval 的契约只写给人看，从未投递给真正需要遵守它的那个 agent。

Tool Retrieval 自己引用的研究就是标定值：agent 的工具选择准确率在目录超过 **30–50 个工具**后急剧下降。Coffer 一直在提供该数字的二到四倍，并指望客户端来收拾。

先例在此很重要。一份此后已被移除的 ADR 做过 per-agent MCP 服务器 scope，因过度复杂被撤销；业界的「strategy 1」（ContextForge virtual server、MetaMCP namespace、MCPJungle tool group、Docker profile）无一例外要求用户手工策展一个子集。[Per-Agent Resource Scope](per-agent-resource-scope.zh.md) 此后恢复了 machine × agent 的 `scope` 轴，但它以整台服务器为粒度，且和所有手工方案一样——不配置就不生效。而默认安装恰恰是过载真正咬人的地方。

## 决策

**网关列出聚合目录中一个按预算裁剪的切片，而非全部。该切片由真实调用历史算出，无需任何用户配置，且被隐藏的东西一律仍可调用。**

四个部分。

### 1. 分层策略

一个纯函数，输入是（聚合工具列表，各工具调用次数）：

- Coffer 自己的 `coffer__*` 内置工具与 `search_tools` **永远**列出。
- `budget`（**默认 50**，取自 Tool Retrieval 自身的 30–50 结论）**只计上游工具**；恒定列出的内置工具叠加在它之上。
- 若上游工具数不超过 `budget`，全部列出——与今天行为完全一致。
- 超预算时：按滑动窗口内（**默认 90 天**）的调用次数排序取头部，再按服务器轮询补足余额，并保证**每台启用的服务器至少保留一个工具**，使任何服务器都不会整体消失。
- 服务器内部，未被调用过的工具按该服务器自身 `tools/list` 的顺序取用，因此在目录不变时，选择结果确定且跨会话稳定。调用次数相同时同样保持目录顺序。
- 其余不列出。

### 2. 隐藏不等于禁用

未列出的工具仍完全可调。`tools/call` 校验的是 `mcp_capability_preferences.enabled`（[Capability State Model](capability-state-model.zh.md)），从不校验是否在列表中；`search_tools` 检索的仍是**完整**目录。工具离开的是列表，不是网关。正是这一条使分层可以安全地默认开启，也正是它与 strategy 1 的手工白名单的分野。

### 3. 契约投递给 agent

`initialize` 返回 MCP `instructions` 字符串，说明 Coffer 是什么、常用工具已直接列出、其余经 `search_tools` 触达。它按会话生成，因此能报出当前未列出工具的真实数量；并设上限（约 800 字符）——它会落进每一个会话的系统提示，所花的 context 必须远小于分层省下的 context。

### 4. 降级可恢复，而非静默

单个服务器的发现超时目前会在整个会话生命周期内丢掉该服务器的全部工具列表：客户端缓存了 `tools/list`，而 `notifications/tools/list_changed` 永远不会到达，因为那台服务器压根没连上。改为：失败的服务器记为 degraded，在后台重试，恢复后网关 invalidate 缓存并发出 `notifications/tools/list_changed`，客户端于会话中途重新拉取。5 秒的 per-server 预算**不变**——缺陷在于不可恢复，不在阈值。失败日志补上服务器名与错误，这是当前基于 `extra` 的调用点从未渲染出来的。

**逃生开关。** 一个 `mode: auto | off` 设置；`off` 精确恢复 Tool Retrieval 的语义。若使用统计查询失败，分层降级为全部列出——一个出故障的统计层，绝不允许让工具消失。

## 后果

**正面**

- **默认安装不再压垮客户端。** 列出的上游切片从约 125 降到至多 `budget`；加上恒定列出的 Coffer 内置工具，一个会话列出约 50 + 17 ≈ 67 个而非约 142 个，且上游切片落在 Tool Retrieval 的 30–50 准确率区间内。这是否越过了某个特定客户端的 deferral 阈值，Coffer 无从得知——此处的主张仅仅是：它远低于今天所提供的量。
- **逃生舱变得可达。** `search_tools` 与 `coffer__*` 内置工具由构造保证被钉进列出切片。
- **冷启动安全。** 新 vault 没有调用历史，但工具也少，因而走「未超预算」分支、看到全部。使用历史只在其数量足以产生意义时才起作用。
- **降级可恢复。** 一次缓慢的冷启动代价是一轮 list 往返，而非一整场会话对该服务器的访问。
- **Coffer 拿到了 strategy 1，且没有 per-agent MCP scope 的代价。** 子集由观测到的行为策展，而非由用户策展——后者正是当初让那份已退役决策得不偿失的那一步。

**负面**

- **列表不再是上游的纯粹映射。** `tools/list` 变得依赖策略，于是「为什么 agent 看不到工具 X」多了一层要排查的东西。缓解手段是 `mode: off` 与在 `instructions` 中报出未列出数量。
- **使用历史会自我强化。** 从未被调用的工具排名低、于是保持未列出、于是继续不被调用。每服务器保底与覆盖全目录的 `search_tools` 是对冲，但这个偏置是真实的：一台繁忙服务器上真正新增的工具，只能经搜索被发现。
- **分层在 `tools/list` 路径上引入一次使用统计查询。** 热路径多一次 DB 读；它是 `mcp_invocations` 上的单次带索引聚合，且失败时降级为「全部列出」。

## 备选方案

**保持 Tool Retrieval 不变，依赖客户端 deferral。** 否决：这正是被实测且失败的那个选项。客户端折叠掉了 Tool Retrieval 新增的那个工具本身，且它没有任何信号能做出更好的选择。

**只做手工 per-agent 白名单（业界的 strategy 1，或把 Per-Agent Resource Scope 的 agent 轴下沉到工具粒度）。** 作为主机制否决：不配置就不生效，而未配置的默认态恰恰是故障发生地。已退役的 per-agent MCP scope 决策已经证明手工 scope 在此处不值其复杂度。Per-Agent Resource Scope 的服务器级轴仍然保留并与分层组合——scope 决定会话看到哪些服务器，分层决定它们的哪些工具被列出。

**隐藏全部上游工具，强制一切调用先经 `search_tools`。** 否决：它破坏了 agent 高频使用的那批工具的直接调用，让每一次例行的 `jira_get_issue` 都赔上一轮搜索往返。实测的 44 个常用工具，恰恰是应该保持一步之遥的那些。

**调大 per-server 发现超时。** 作为第 4 部分的修复否决：5 秒预算的存在是为了让一台死掉的上游无法拖住整个聚合列表，并行 fan-out 的理由依然成立。这个故障模式要的是恢复，不是更大的阈值。
