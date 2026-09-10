# 按 agent 的资源 scope

> English: [per-agent-resource-scope.md](./per-agent-resource-scope.md)

- **状态：** 已采纳
- **Spec：** [vault-export-import](../../specs/vault-export-import/spec.md)（同时修订
  [mcp-gateway](../../specs/mcp-gateway/spec.md) 与
  [skill-manager](../../specs/skill-manager/spec.md)）
- **修订：** [Everything Is a Resource Kind](./everything-is-a-resource-kind.zh.md)（资源现在
  携带 scope）与 [Tool Retrieval](./tool-retrieval-for-overload.zh.md) /
  [Built-in Agent Is Internal](./builtin-agent-is-internal-capability.zh.md)
  （`coffer__search_tools` 的排序感知 scope）

## 背景

有些资源只对某一个 agent *可用*：某个 MCP server 的工具只对 coding CLI 有意义，
某个 skill 是照着 Claude Code 的 frontmatter 写的。而仓库没有通用的方式表达这件
事——网关把每个 server 的工具暴露给每个 agent，放错地方的 server 要么失败、要么
制造噪音。

skill 本来就有按 agent 的分发策略（消费侧的 follow 开关加排除项）。按 agent 的
MCP scoping 此前作为某个 kind 自己的特性被尝试过一次，并在 2026-06-20 的简化中
被撤销，因为把 allowlist 和会话身份塞在单个 kind 内部，其代价大于它在那里带来的
回报。两个 kind 用两种不同方式解决同一个问题，这个信号说明应该把它提到框架层去
解决——在那里身份管道只需付一次代价，此后任何需要它的 kind 声明一下即可。

本 ADR 原本还带一条 **machine** 轴，那是伴随持续多机同步加进来的。该同步已被撤销
（[Vault Export and Import](./vault-export-import.zh.md)），赋予机器身份意义的机器注册表
也随之消失，因此 machine 轴被移除，只留下 agent 轴。

## 决策

在资源模型上增加一个由框架拥有的 `scope` 字段——一个 agent 名字的列表；每个 kind
声明自己是否支持 scope，并各自拥有自己的执行点。

1. **框架级 `scope`。** 唯一的 `scope` 形状位于 `Resource` 实体上，而不在 kind
   config 里：

   ```
   scope == None                       → 对每个 agent 都生效
   scope == []                         → 对任何 agent 都不生效（休眠）
   scope == ["claude-code"]            → 只对列出的 agent 生效
   ```

   - `agent_in_scope(scope, agent)` → 当 `scope is None` 时为 `True`，否则看
     `agent` 是否在列表中。无身份的会话（`agent=None`）只匹配 `scope is None`。
   - 列表里出现未知的 agent 名字是合法的，只是永远匹配不上——可以在某个 agent
     注册之前就把它划进 scope。
   - 不声明 scope 的 kind 在校验阶段拒绝非 null 值（422）。

2. **导出但不激活。** 被 scope 限定的资源照常导出与导入，并在任何地方都保持在
   注册表中可见；在 scope 之外它只是不被激活——不暴露、不分发。注册表仍是唯一
   事实来源，而 scope 就是一个普通的资源字段，原样穿过导出与导入。

3. **各 kind 的支持情况与执行接缝。** 每个 kind 在自己既有的咽喉点查询 scope，
   而不是新设一个中央门禁：

   | Kind | Scope | 执行接缝 |
   | --- | --- | --- |
   | `mcp_server` | agent | 网关按会话身份过滤该 server 的工具。 |
   | `skill` | agent | 分发时用 scope 与既有的按 agent follow 策略取交集；已分发但不在 scope 内的副本会被回收。 |
   | `agent`、`channel`、`knowledge` | 无 | 非 null 的 scope 在校验阶段被拒绝。 |

4. **shim 自报的 `--agent` 身份。** shim 安装时把
   `coffer-mcp-shim --agent <name>` 写入 agent 的配置；shim 在握手时连同既有的
   cwd `_meta` 注入一起上报该名字。没有身份的会话（手工配置的 shim）只能看到
   未被 scope 限定的 server。**信任边界：** 身份由 shim 进程自报，未经密码学
   验证——在单用户、仅 loopback 的姿态下这是可接受的。spec 会明确陈述这条边界，
   而不是暗示一种实际并不存在的更强隔离。

5. **skill 的 scope ∩ follow 策略。** follow 是 agent 侧的意图（「把 skill 发给
   我」）；scope 是资源侧的授予（「这个 skill 可以在这里跑」）。分发取二者的
   交集——既在 scope 内*又*被 follow，再减去手动排除项。scope 是硬性授予，
   压过手动绑定：不在 scope 内的 skill 即便此前是手工分发的也会被回收。

6. **知识永不 scope。** `knowledge` kind 不声明 scope，并拒绝非 null 值——它永远
   对所有 agent 共享。（它自己的 `global` / `project-<ULID>` / 具名集合这条轴是
   知识层对*内容*的 scope，与本框架字段无关；后者管的是*哪个 agent 能看见某个
   资源*。）聊天历史、审计日志、运行时状态与仅本机
   的设置保持机器本地（此处是重申边界，不是新决策）。

## 已考虑的备选方案

- **machine × agent 矩阵**——本 ADR 此前的决策。它的 machine 轴以同步机器注册表
  里的机器 ULID 为键；没有了持续同步，就没有注册表、没有第二台可供「不激活」的
  机器，这条轴也就没有任何含义。随它所属的同步一并撤销。
- **把按 agent 的 scoping 留在各 kind 内部**——不设框架字段，每个 kind 自己实现
  allowlist 与身份处理。这正是 2026-06 被尝试并撤销的那个形状。否决：两个 kind
  已经在同一个问题上分岔，第三个还会再分岔一次。
- **改用 deny-list 而非 allow-list**——「除这些之外的每个 agent」。否决：新加入的
  agent 会静默获得所有被 scope 限定资源的访问权，这对一个「授予」而言是错误的
  默认值。

## 影响

- `scope` 是 `Resource` 上的一个可空列表，按 kind 校验，并作为普通字段随导出/导入
  流转——没有任何专用机制。
- 网关的工具列表变得与身份相关：同一个 server 在同一个仓库里可以对不同 agent
  呈现不同的工具集。
- 反方向上，没有 `--agent` 的手工 shim 不构成提权路径：它看到的严格更少（只有未被
  scope 限定的资源）。
- 把某个 skill 移出 scope 会从已持有它的 agent 那里回收，因此 scope 的编辑有可见的
  文件系统效果——像其他分发变更一样被审计。
