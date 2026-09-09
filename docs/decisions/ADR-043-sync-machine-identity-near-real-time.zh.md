# ADR-043 — Sync v2：机器身份与近实时收敛

> English: [ADR-043-sync-machine-identity-near-real-time.md](./ADR-043-sync-machine-identity-near-real-time.md)

- **状态：** Accepted
- **Spec：** [010-sync](../../specs/010-sync/spec.md)（修订；后续切片同时修订
  [007-memory](../../specs/007-memory/spec.md) 与 [009-channels](../../specs/009-channels/spec.md)）
- **修订：** [ADR-016](./ADR-016-multi-machine-sync.md)（保留 git 介质与
  export→merge→import 引擎；替换仅按间隔的自动同步与「缺席即删除」的导入规则）

## 背景

ADR-016 交付了基于用户自有 git 仓库的全 vault 同步，面向的是「轮流使用」的机器。
实际用法是**两台机器并行使用**，且**用户名/目录布局不同**，期望数十秒内收敛。
对照这个目标审计已交付的引擎，发现：

1. 自动同步仅按间隔运行（默认 300 秒）；ADR-016 承诺的「变更触发 + 防抖推送」从未实现。
2. channel 资源带着 `enabled: true` 同步，而 runtime 会启动每一个 enabled 的
   channel——两台机器抢同一个 Telegram bot，配对状态（`channel_peers`）也留在原机。
3. 导入按「缺席」删除：在一台机器上导入*失败*的资源（如机器本地路径），随后会在
   所有机器上被*删除*。
4. 配置里的绝对路径——以及 memory 的项目 ID（git-root 绝对路径的哈希）——在
   home 不同的机器间失效。
5. 共享意图（MCP 工具偏好、引擎配置、skill 投递意图、channel 配对）从不同步。
6. 模型里没有「机器」这个概念可以承载上述任何东西（`machine_id` 只是 commit
   message 里的 `platform.node()`）。

## 决定

保留 git 传输与引擎骨架；增加一层**轻量机器身份**并修复上述发现。各部分作为独立
切片交付：

- **机器身份。** 每个安装实例一个稳定 ULID + 可编辑显示名（DB 单例，永不作为数据
  同步）。workspace 新增 `machines/<id>.json` 注册区，每台机器只写自己的注册项——
  可见性且无冲突。
- **运行时亲和。** channel 配置携带 `runs_on: <machine_id>`；只有被绑定的机器启动
  适配器；配对身份随同步传播，改绑无需重新配对。`null`（升级后的默认值）表示在任何
  机器上都不运行，直到用户选定一台。
- **路径可移植。** 导出/导入时对配置字符串值做 `${HOME}` 正规化，另有
  `machines/<id>/overrides/` 下的每机 JSON Merge Patch 覆盖，处理真正逐机不同的值。
  memory 项目 ID 改由正规化的 `origin` remote URL 派生（无 remote 回退路径哈希 +
  一次性别名迁移），同一仓库在每台机器映射到同一个记忆库。
- **墓碑式删除。** 删除以显式的 `tombstones/resources/<kind>/<name>.json` 文件传播；
  仅凭缺席永不删除。导入失败的资源被隔离并保留，而非丢弃。
- **近实时引擎。** daemon 内变更通知 + 对三棵文件树的 `watchfiles` 监听（agent 可能
  经 symlink 绕过 daemon 直写 memory）喂给防抖推送；轻量的 `git ls-remote` HEAD 探测
  （默认每 15 秒）触发拉取。间隔轮询保留为兜底。预期收敛 ≈ 15–30 秒。

机器身份只承担三个职责——亲和、覆盖、可见性——外加墓碑上的溯源标签。它**不是**
记录级版本方案。

## 曾考虑的替代方案

- **记录级版本向量 / 操作日志**——发现 3 的教科书解法；但对单用户工具是分布式系统税，
  否决。git 对逐 ULID 文件的 3-way merge 已很好地覆盖文件树域。
- **hub / leader 机器**——一台常开机器运行一切并中继状态；否决：破坏对称性（笔记本
  合盖 → channel 死亡），也不解决路径问题。
- **仅迁移（backup/restore）**——重新界定范围时考虑过；因两台机器并行使用而否决，
  覆盖写语义会丢弃另一台机器的改动。
- **真正的推送传输（relay / P2P）**——秒级收敛，但要重开 ADR-016 的介质决策；数十秒
  在现有 constitution 姿态内即可达成，暂不。

## 后果

- 同步 workspace 布局新增 `machines/`、`tombstones/`、`state/` 区；manifest schema
  版本随墓碑切片升到 2，因此首次 v2 同步前所有机器必须升级 Coffer。
- 新后端依赖 `watchfiles`；自动同步开启期间，`git ls-remote` 轮询成为持续的小额网络
  出口。
- channel runtime 开始参考机器身份——第一个以机器为键的 kind 级行为。
- 改绑传播期间 channel 可能短暂双跑；对单用户工具可接受。
- 聊天历史、审计日志与运行时状态按设计保持机器本地。
