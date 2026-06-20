# ADR-029 — 消费官方 MCP Registry 做服务器发现

> English: [ADR-029-consume-official-mcp-registry.md](./ADR-029-consume-official-mcp-registry.md)

- **状态：** Reverted（2026-06-20）——见下方撤销说明
- **日期：** 2026-06-19
- **决策者：** Yuxing Wu
- **Spec：** 001-mcp-gateway（实现前更新 spec.md）
- **相关：** [ADR-004](./ADR-004-capability-state-model.md)（列表实时查询、不做镜像）、[ADR-015](./ADR-015-envelope-encrypted-credential-store.md)（secret 转为凭据引用）

> **⚠️ 已撤销 2026-06-20。** 在线 MCP Registry 浏览/自动填充功能（PR #114）已移除（简化积压项 1.7）：它只省去了一次粘贴，却依赖一个外部 preview API。添加 MCP 服务器现在重新通过 **paste-JSON** 路径（标准 `mcpServers` 配置）完成。以下原始决策保留为历史记录。

## 背景

今天往 Coffer 添加一台 MCP 服务器意味着手工粘贴 `mcpServers` JSON——用户必须事先知道
服务器的 id、运行命令、参数，以及它需要哪些环境变量。没有任何发现路径。

MCP 生态调研（`docs/research/mcp-ecosystem.md`）把这标记为一个真实缺口：**Coffer 没有
catalog，而这个领域有一层丰富的 registry**（官方 Registry，加上 Smithery / Glama /
PulseMCP 等下游 marketplace）。**官方 MCP Registry**
（`https://registry.modelcontextprotocol.io`，Anthropic + Linux 基金会）是一个开放、
无需认证的元数据 API——它正是下游 marketplace 们去抓取的那个根。它明确**不是**网关，
只是一个 catalog，而那恰恰是 Coffer 缺的那一层。

两个约束塑造了设计。其一，注册表是 **preview** API：其 schema 未冻结，字段会增减——最
突出的是 `packages[].runtimeHint` 常常缺失，因此我们不能依赖它来得知如何启动一台服务器。
其二，Coffer 是 local-first 的：前端只与 localhost 通信，所以出站调用不能从浏览器发起。

## 决策

通过一个薄的 daemon 侧代理消费官方 MCP Registry，并自动填充一份服务器配置 draft。五步。

1. **daemon 侧只读代理。** 新增 `GET /api/v1/mcp-registry/search?q=&limit=`。由 daemon
   对注册表发起出站调用；前端只与 localhost 通信。响应是一份匹配的服务器列表，每个都带
   一个 `installable` 标记和一份可编辑的配置 `draft`。

2. **从 `registryType` 而非 `runtimeHint` 推断运行命令。** 由于 `runtimeHint` 常常缺失，
   mapper 从每个包的 `registryType` 推导启动命令：

   | `registryType` | 推断的命令               | 可安装 |
   | -------------- | ------------------------ | ------ |
   | `npm`          | `npx -y <package>`       | 是     |
   | `pypi`         | `uvx <package>`          | 是     |
   | `oci`          | `docker run -i --rm <…>` | 是     |
   | `nuget`        | `dnx <package>`          | 是     |
   | `cargo`        | —                        | 否     |
   | `mcpb`         | —                        | 否     |

   `cargo` 与 `mcpb` 包不可自动安装；这类服务器以 `installable: false` 返回、没有可运行的
   draft（用户仍可手工编辑）。

3. **实时查询 + 短缓存，不持久化。** 注册表结果实时获取，仅有一层短 TTL 的内存缓存。关于
   注册表的任何内容都不写入 SQLite——没有镜像、没有新表、没有迁移 revision。只有用户真正添加
   的服务器才经由常规注册路径落入 `resources`。

4. **secret 走凭据引用，绝不内联。** 被标记 `isSecret` 的 `environmentVariables[]` 条目在
   draft 中转为一个凭据引用，绝不是内联值，于是自动填充路径继承
   [ADR-015](./ADR-015-envelope-encrypted-credential-store.md) 的保证：secret 明文绝不落入
   任何持久化配置。

5. **优雅降级。** 当注册表不可达或超时，端点返回清晰、非致命的 `502 REGISTRY_UNAVAILABLE`。
   发现纯粹是叠加在既有流程之上的杠杆——注册表宕机时，手工录入的 paste-JSON 路径仍完全可用。

## 备选方案

A — **前端直接调用注册表。** 让浏览器自己去 fetch 注册表 API，跳过 daemon 这一跳。**否决。**
它破坏 local-first 契约（前端将发起跨源出站调用），暴露在 CORS 之下，并把防御性解析散落进 UI。
daemon 才是出站调用与那个唯一宽容 mapper 的正确位置。

B — **把注册表镜像进 SQLite。** 周期性地把整个注册表同步进一张本地表并搜索它。**否决。** 为了
缓存一个用户偶尔才碰的 catalog，它新增了一个同步任务、一份 schema，以及一个数据陈旧窗口，而这
份数据本就是一次快速的实时查询。实时查询 + 短内存缓存便宜得多，且永不陈旧。

C — **把下游 marketplace 也聚合进来**（Smithery / Glama / PulseMCP）。查询多个 catalog 并合并。
**暂否。** 官方注册表是其他人去抓取的那个根；一个开放、无需认证的源已覆盖需求，无需为每个
marketplace 处理认证、限流和分叉的 schema。若某个 marketplace 暴露了根注册表没有的服务器，再说。

## 后果

- **补上发现缺口。** 用户可以按关键词找到并自动填充一台服务器，而不必手工粘贴需要从别处获取的
  JSON；粘贴路径作为兜底与手工逃生口保留。
- **mapper 必须防御。** 因为注册表是 **preview** API，缺失或被改名的字段是预期内的；mapper 容忍
  缺失的 `runtimeHint`、缺失的 `title`/`version`/`homepage`，以及未知的 `registryType`（当作
  不可安装），而非让搜索失败。
- **preview-API 风险。** 注册表 schema 可能在我们脚下变动；一个破坏性变更会降级发现（最坏情况是
  一切都 `installable: false`），但绝不会拖垮 paste-JSON 路径。契约把每个字段都视为可选。
- **无新增持久化。** 没有表、没有迁移、没有镜像——注册表结果只在内存里活短短一个 TTL，因此没有任何
  东西需要备份、清理或保持同步。
- **secret 天然安全。** `isSecret` 环境变量流向凭据引用，因此新的自动填充界面无法引入内联 secret 的
  回归。
