# 机器 × Agent 资源作用域 — 设计

> English: [machine-agent-scope.md](./machine-agent-scope.md)

将机器身份（spec 010 / ADR-043）推广为资源框架级 **scope** 设施的设计笔记，
外加顶级 **Machines** 舰队视图。经 2026-07-10 头脑风暴会话确认；本笔记是后续
ADR + spec 修订（承载产品契约）的输入。

## 问题

多机同步把每个资源收敛到每台机器，但有些资源只在某台机器或某个 agent 上
*可用*：二进制只存在于 MacBook 的 MCP server、只为 Claude Code 写的 skill。
今天 vault 无法表达这一点——

- 只有 channel 这一个 kind 有机器亲和性（`runs_on`，ADR-043）。
- Skill 有 per-agent 投递策略（消费者侧 follow 开关 + 排除清单），但没有
  机器维度。
- MCP server 两者皆无：gateway 在每台机器上把每个 server 的工具暴露给每个
  agent，放错位置的 server 要么失败要么制造噪声。
- 未安装在某机器上的 agent 靠 import gate 隐式处理——永久的 quarantine
  噪声，每次运行重试。

ADR-043 明确把 "per-resource runtime affinity" 预留为挂在机器身份上的后续
修订。本设计就是那个后续，并拓宽出 agent 轴。

## 决策（与用户确认）

1. **同步但不激活。** 被限定作用域的资源仍然同步到并可见于每台机器；作用域
   外只是不激活（不 spawn、不暴露、不投递）。注册表保持单一事实源，任何
   机器都能编辑作用域。（与 channel `runs_on` 一致。）
2. **完整矩阵。** 作用域是每机器 × 每 agent 的矩阵，不是两个独立轴——
   "MacBook 上给 Claude Code、台式机上给 Codex" 可以表达。
3. **agent 也有机器轴。** agent 声明自己存在于哪些机器；import gate 降级为
   兜底，作用域设置正确后 quarantine 噪声消失。
4. **框架级设施。** 资源框架拥有唯一的 `scope` 形状；各 kind 声明适用哪些
   轴并拥有自己的执行点。channel 的 `runs_on` 迁移进来。
5. **知识与记忆永不限定作用域。** `knowledge_base` 与 `memory` 不声明任何
   轴——永远在所有机器、所有 agent 间共享。聊天记录、audit 日志、runtime
   状态与机器本地设置留在本机（维持现状，作为边界重申）。
6. **顶级 Machines 舰队视图。** 新顶级 tab 列出每台机器并提供按机器钻取
   （矩阵按机器切片）。Sync 配置（remote、auto-sync、master key）留在
   Settings → Sync。

## 数据模型

资源上可选的、框架拥有的 `scope` 字段：

```yaml
scope: null                       # 默认：所有机器、所有 agent 激活
scope:
  "01HXX…MACBOOK": ["claude-code"]        # MacBook：仅 Claude Code
  "01HYY…DESKTOP": ["codex", "opencode"]  # 台式机：这两个
scope:
  "*": ["claude-code"]            # 所有机器，仅 Claude Code
scope:
  "01HXX…MACBOOK": "*"            # 仅 MacBook，该机所有 agent
scope: {}                         # 处处休眠
```

- 键是机器 ULID 或 `"*"`；值是 agent 名列表或 `"*"`。
- 求值：`active(M, G)` ⇔ scope 为 `null`，或 `M` 的条目（精确 ULID 键优先
  于 `"*"`）包含 `G` 或为 `"*"`。
- kind 轴声明：`mcp_server` 机器 × agent；`skill` 机器 × agent；`agent`
  仅机器；`channel` 仅机器；`knowledge_base` / `memory` 无。仅机器轴的
  kind 只接受 `"*"` 作为 agent 值（schema 强制）。
- 引用未知机器 ID 或 agent 名的条目保留但永不匹配（对方机器可能尚未同步；
  agent 可能以后才注册）。
- 矩阵引用的 agent 额外与该 agent 自身的机器轴求交。

## 执行点（按 kind）

| Kind         | 轴            | 作用域外行为                                                                                                              |
| ------------ | ------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| `mcp_server` | 机器 × agent  | 机器轴：该机器上不 spawn upstream、不列出工具。agent 轴：gateway 按会话身份过滤该 server 的工具。                              |
| `skill`      | 机器 × agent  | 投递按矩阵过滤并与现有 per-agent follow 策略**求交**（follow = agent 侧意愿，scope = 资源侧授权）；作用域外已投递副本被 reconcile 收回。 |
| `agent`      | 机器          | 作用域外机器不投影 / 不 reconcile / 不装 shim；import gate 作为作用域内缺失 `config_dir` 的兜底保留。                          |
| `channel`    | 机器          | 现有 `runs_on` 迁移（`runs_on: <id>` → `{"<id>": "*"}`；`runs_on: null` → `{}`）；API 字段保留为兼容别名。                  |

**Gateway 会话身份。** shim 安装到 agent 配置时写入
`coffer-mcp-shim --agent <name>`；shim 在握手时随现有 cwd `_meta` 注入通道
一并上报名字。无身份的会话（手工配置的 shim）只能看到本机上 agent 轴为
`"*"` 的 server。身份是自报的——在单用户、仅回环的态势下可接受；spec 明确
写出此边界。

## 同步语义 — 零新机制

`scope` 是资源文档的一部分：原样走现有的 export → merge → import 管线、
冲突自动裁决、tombstone 与 quarantine。在任何机器上编辑作用域，像任何其他
资源编辑一样传播。workspace manifest schema 版本 bump（资源文档新增字段），
老构建按现有 `SYNC_WORKSPACE_TOO_NEW` 门失败而不是误读文档。

## Machines 舰队视图（顶级 tab）

- 新顶级导航项 **Machines**（`/machines`）：sync 状态条（状态、最后同步、
  手动触发、指向 Settings → Sync 的链接）在上，每台机器一张卡片（显示名、
  平台、最后同步、"本机"徽标、重命名）在下。
- 机器详情（`/machines/:id`）：该机器的**激活切片**——存在的 agent、生效
  的 MCP server、各 agent 收到的 skill、绑定的 channel。由同步来的注册表 +
  scope 本地算出，任何机器都能渲染任何机器的切片。本机额外显示**实际状态**
  （quarantine、安装态）；远端机器只显示意图。
- 资源详情页新增 **Scope 卡片**：矩阵编辑器（注册表中每台机器一行，每行
  agent 多选或"全部"），形状由 kind 轴声明决定，一键还原"处处生效"。

## Surfaces

- **REST：** `scope` 随资源 CRUD 载荷进出（框架级，按 kind 轴校验）；
  `GET /api/v1/machines/{id}/slice` 返回激活切片。
- **CLI：** `coffer scope show|set|clear <kind>:<name>`；`coffer machines`
  提升出 sync 组（`coffer sync machines` 保留为别名）。

## 边界

- 本机作用域外的资源是徽标（"未在此机器生效"）和列表过滤器，不是错误态；
  gateway / 投递静默跳过。
- `scope: {}`（处处休眠）合法——道义上等价于 channel 今天的
  `runs_on: null`。
- 从注册表删除机器条目不在本次范围（注册表今天也没有删除语义）。

## Local-first 态势与文档影响

本功能不削弱 local-first——经用户自有介质的多设备同步本来就是 local-first
的核心理想之一（每台机器持有全量 vault；介质只是传输 + 历史；constitution
0.3.0 三条件均成立）。变化的是措辞："local = 这一台机器" 成熟为 "local =
用户的一组机器，一个 vault，每台完整"。

| 文档                                 | 改动                                                                                              |
| ------------------------------------ | -------------------------------------------------------------------------------------------------- |
| `constitution.md`                    | 0.3.x 编辑性修正：Principle I "the user's machine" → "the user's machines"。原则不变。              |
| `architecture.md`                    | 机器身份提升为框架核心概念；`scope` 设施与 kinds 表并列记述。                                        |
| `AGENTS.md` / `README.md`            | 定位语补 "one vault across the user's machines"。                                                   |
| 新 ADR（amends ADR-043）             | 作用域矩阵语义、shim 身份、follow 策略求交、`runs_on` 迁移。                                         |
| Specs 010 / 001 / 004 / 005 / 009    | 按上方执行点表分别修订，各带验收场景，中英双语对。                                                    |

## 测试

- **单元：** scope 求值（通配优先级、未知引用、仅机器轴 kind 拒绝 agent
  列表）。
- **集成：** gateway 按会话过滤；skill 矩阵 ∩ follow 投递与收回；channel
  `runs_on` 迁移；agent 轴与 import gate 兜底。
- **契约：** scope 载荷校验；slice 端点。
- **E2E：** 双机作用域往返——在 A 上改 scope，B 上激活状态翻转。

## 不在范围内

- 工具级 per-agent 过滤（工具偏好仍是独立的共享机制）。
- 机器注册表条目的删除 / 退役。
- 除重申边界外，不改变"什么同步、什么留本地"。
