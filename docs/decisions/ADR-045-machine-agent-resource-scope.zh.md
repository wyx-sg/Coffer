# ADR-045 — 机器 × Agent 资源作用域

> English: [ADR-045-machine-agent-resource-scope.md](./ADR-045-machine-agent-resource-scope.md)

- **状态：** Accepted
- **Spec：** [010-sync](../../specs/010-sync/spec.md)（修订；同时修订
  [001-mcp-gateway](../../specs/001-mcp-gateway/spec.md)、
  [004-agent-registry](../../specs/004-agent-registry/spec.md)、
  [005-skill-manager](../../specs/005-skill-manager/spec.md) 与
  [009-channels](../../specs/009-channels/spec.md)）
- **修订：** [ADR-043](./ADR-043-sync-machine-identity-near-real-time.md)
  （把 ADR-043 随机器身份一并预留的「per-resource runtime affinity」后续
  推广为框架级设施，并拓宽出 agent 轴）

## 背景

多机同步（ADR-043）把每个资源收敛到每台机器，但有些资源只在某台机器或
某个 agent 上*可用*：二进制只存在于 MacBook 的 MCP server、只为 Claude
Code 写的 skill。vault 没有通用的方式表达这一点：

- 只有 channel 这一个 kind 有机器亲和性（`runs_on`，ADR-043）。
- Skill 有 per-agent 投递策略（消费者侧 follow 开关 + 排除清单），但没有
  机器维度。
- MCP server 两者皆无：gateway 在每台机器上把每个 server 的工具暴露给
  每个 agent，放错位置的 server 要么失败要么制造噪声。
- 未安装在某机器上的 agent 靠 import gate 隐式处理——永久的 quarantine
  噪声，每次运行重试。

ADR-043 明确把 "per-resource runtime affinity" 预留为挂在机器身份上的
后续修订。本 ADR 就是那个后续，并拓宽出 agent 轴；经 2026-07-10 头脑风暴
会话确认，记录在
[`docs/research/machine-agent-scope.md`](../research/machine-agent-scope.md)。

## 决定

新增一个框架拥有的 `scope` 字段——每机器 × 每 agent 的激活矩阵——挂在
资源模型上；各 kind 声明适用哪些轴并拥有自己的执行点。

1. **框架级 `scope` 矩阵。** 唯一的 `scope` 形状挂在 `Resource` 实体上，
   而非 kind config 内部。语义（实现的单一事实源）：

   ```
   scope == None            → active on every machine, for every agent
   scope == {}              → active nowhere (dormant)
   scope == {"<ulid>": ["claude-code"], "*": "*"}   # dict[str, list[str] | "*"]
   ```

   - 机器 M 的条目查找：精确的 ULID 键优先于 `"*"` 键；没有匹配的键
     则在 M 上不激活。
   - `machine_in_scope(scope, m)` → 条目存在，且值为 `"*"` 或非空
     列表。
   - `agent_in_scope(scope, m, agent)` → 条目值为 `"*"`，或 `agent`
     （名字字符串）在列表中。`agent=None`（无身份会话）只匹配
     `"*"` 值。`scope=None` → 始终为 True。
   - 各 kind 的轴：`mcp_server`（机器、agent）· `skill`（机器、agent）·
     `agent`（机器）· `channel`（机器）· `knowledge_base`、`memory`——
     无此轴（非空 scope 会被拒绝）。
   - 仅机器轴的 kind，条目值只能是 `"*"`。
   - 条目中出现未知的机器 ULID / agent 名称是合法的，只是永远
     不会匹配。
   - 矩阵中引用到的 agent，在计算激活切片（Machines 视图）时还会与该
     agent 自身的机器轴取交集；gateway 本身信任本机 shim 上报的身份，
     不会重新校验该 agent 的机器轴，因为本机 shim 只能运行在该 agent
     已安装的机器上。

2. **同步但不激活。** 被限定作用域的资源仍然同步到并可见于每台机器；
   作用域外只是不激活（不 spawn、不暴露、不投递）。注册表保持单一事实
   源，任何机器都能编辑作用域——与 channel 现有的 `runs_on` 一致。

3. **按 kind 声明轴与执行点。** 各 kind 在自己现有的关卡处查询 scope，
   而非新增一个中心化的关卡：

   | Kind                        | 轴            | 执行点                                                                                                                     |
   | --------------------------- | ------------- | ---------------------------------------------------------------------------------------------------------------------------- |
   | `mcp_server`                | 机器 × agent  | 机器轴：该机器上不 spawn upstream、不列出工具（gateway `_enabled_mcp_servers` + supervisor spawn gate）。agent 轴：gateway 按会话身份过滤该 server 的工具。 |
   | `skill`                     | 机器 × agent  | 投递按矩阵过滤并与现有 per-agent follow 策略求交；作用域外已投递副本被 reconcile 收回。                                        |
   | `agent`                     | 机器          | 作用域外机器不投影 / 不 reconcile / 不装 shim；import gate 作为作用域内缺失 `config_dir` 的兜底保留。                          |
   | `channel`                   | 机器          | `runs_on` 迁移进 scope；channel runtime 改读 scope。                                                                          |
   | `knowledge_base`、`memory`  | 无            | 非空 `scope` 在校验阶段被拒绝。                                                                                               |

4. **Shim 自报的 `--agent` 身份。** shim 安装到 agent 配置时写入
   `coffer-mcp-shim --agent <name>`；shim 在握手时随现有 cwd `_meta` 注入
   通道一并上报名字。无身份的会话（手工配置的 shim）只能看到本机上 agent
   轴为 `"*"` 的 server。**信任边界：** 身份由 shim 进程自报，未经密码学
   验证——在单用户、仅回环的态势下可接受；spec 修订明确写出此边界，而非
   暗示比实际更强的隔离。

5. **Skill scope ∩ follow 策略。** follow 是 agent 侧意愿（"把 skill
   投递给我"）；scope 是资源侧授权（"这个 skill 可以在这里运行"）。投递
   取二者的交集——既在作用域内*又*被 follow，再减去手动排除清单。scope
   是硬性授权，会覆盖手动绑定：即便此前手动投递过，一旦作用域外，该
   skill 也会被收回。

6. **Channel `runs_on` → scope 迁移。** `runs_on: <id>` 变为
   `{"<id>": "*"}`；`runs_on: null` 变为 `{}`。升级时通过数据迁移转换
   既有 channel 资源。`runs_on` 字段**不会**从 schema 中移除——尚未升级
   的机器同步过来的旧 payload / 文档仍须能校验通过——但它变为惰性字段：
   channel runtime 只读 scope，`runs_on` 原地标记为已废弃。

7. **知识与记忆永不限定作用域。** `knowledge_base` 与 `memory` 不声明
   任何轴，且拒绝非空 `scope`——永远在所有机器、所有 agent 间共享。聊天
   记录、audit 日志、runtime 状态与机器本地设置留在本机（维持现状；此处
   重申为边界，而非新决定）。

8. **顶级 Machines 舰队视图。** 新顶级导航项 `Machines` 列出每台已注册
   机器（sync 状态条在上，每台机器一张卡片）；按机器钻取的详情视图渲染
   该机器的激活切片（存在的 agent、生效的 MCP server、各 agent 收到的
   skill、绑定的 channel），由同步来的注册表 + scope 本地算出，任何机器
   都能渲染任何机器的切片。Sync 配置（remote、auto-sync、master key）
   留在 Settings → Sync——本视图关注激活状态，不涉及传输。

9. **Manifest `SCHEMA_VERSION` → 4。** `scope` 原样走现有的 export →
   merge → import 管线、冲突自动裁决、tombstone 与 quarantine——零新增
   同步机制。在资源文档中新增该字段会把 workspace manifest schema 版本
   从 3 bump 到 4，因此尚未升级的构建会按现有 `SyncWorkspaceTooNew` 门
   失败关闭，而不是静默丢弃或误读该字段。

## 曾考虑的替代方案

- **按 kind 各写专属字段**——让每个 kind 长出自己的亲和字段（channel 已
  有 `runs_on`；再给 MCP server 和 skill 各自的）。否决：为同一个概念要
  校验、记文档、写迁移、在 UI 里渲染三种不兼容的形状。框架级字段配合
  各 kind 的轴声明，用一份实现就能获得同样的表达力。
- **消费者侧选择**——让每个 agent 的本地配置决定使用哪些资源（一个
  override，而非注册表字段），类比现有 per-machine JSON Merge Patch
  覆盖处理逐机不同配置值的方式。否决：override 按设计是本地的，从不作为
  意图同步，另一台机器永远看不到也无法编辑某资源的激活状态——注册表将
  不再是"这东西该在哪运行"的单一事实源。

## 后果

- 迁移 0046（新增 `resources.scope_json`）与 0047（channel `runs_on` →
  scope 数据迁移）随本 ADR 的实现一起交付；workspace manifest v4 意味着
  所有机器必须先升级，携带 scope 的文档才能干净同步——与 ADR-043 为 v2
  引入的整队升级要求相同。
- 新增 REST 接口（`GET`/`PUT .../scope`、`GET
  /api/v1/machines/{id}/slice`）与 CLI 接口（`coffer scope
  show|set|clear`、顶级 `coffer machines`），此前该概念没有直接的入口
  （channel 的 `runs_on` 埋在 channel config 里）。
- gateway、skill 投递、agent import/reconcile、channel runtime 各自在
  其现有执行点新增一个 scope 感知分支——不引入新关卡，但四处调用点行为
  改变。
- shim 自报身份是信任边界，不是隔离边界：任何能在 loopback MCP 连接上
  写 `_meta` 的进程都能冒充任意 agent 名。对单用户工具可接受；明确记录
  下来，以免未来的多租户态势悄悄继承这一假设。
- 作用域外的资源是徽标和列表过滤器，绝不是错误态；gateway / 投递静默
  跳过——与今天 `runs_on` 的行为一致，只是被推广了。
- 工具级 per-agent 过滤（工具偏好）与机器注册表条目删除仍不在本 ADR
  范围内；除重申既有边界外，不改变"什么同步、什么留本地"。
