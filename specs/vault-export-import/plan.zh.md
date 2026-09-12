# 实施计划：仓库导出与导入

> English: [plan.md](./plan.md)

导出/导入是一项**横切服务**，不是资源 kind（见
[Vault Export and Import](../../docs/decisions/vault-export-import.md)）。它在四层之间遵循
retention/credentials 的模式，并且不拥有任何持久化状态。

## 分层

```
domain/sync/          pure value objects + contracts
  manifest.py         Manifest, SCHEMA_VERSION
  models.py           ExportResult, ImportResult, ResourceFailure, area counts
  serialization.py    deterministic Resource <-> dict projection (pure)
  paths.py            ${HOME} normalization / expansion (pure)
  errors.py           SyncError family (codes for the error envelope)

application/sync/
  ports.py            BundleLayout, SyncedStatePort protocols
  exporter.py         vault -> bundle (files, resources, state, ciphertext)
  importer.py         bundle -> vault (mirror+reindex, reconcile, ciphertext)
  service.py          SyncService: export / import / key export / key import

infrastructure/sync/
  bundle.py           file mirror + manifest read/write + ciphertext dump/load

surfaces/
  http/sync_routes.py + sync_wiring.py    /api/v1/sync/*
  cli/sync_cmd.py                         `coffer sync` group
```

备份远端（spec `## 备份`，章程 0.5.0）在这幅图上只增加四样东西，别无其他：

```
domain/sync/backup.py                    BackupRemote、BackupRun、redact（纯）
application/sync/ports.py                + GitMirrorPort
application/sync/backup_service.py       configure / run_once / restore
application/sync/backup_worker.py        定时器，形状照搬 RetentionWorker
infrastructure/sync/git_mirror.py        唯一执行 git 的地方
infrastructure/persistence/
  sync_remote_repo.py                    那一行 sync_remotes
```

没有墓碑表、没有机器身份、没有文件监听、没有冲突仲裁——那些属于收敛，
而收敛仍未建造。

## 构建顺序（TDD，每步可独立提交）

1. **删除迁移** —— 删掉 `sync_config`、`sync_state`、`machine_identity` 与
   `sync_tombstones`，并移除读取它们的代码。集成测试：在上一个 revision 上创建的仓库
   能干净升级。
2. **domain/sync** —— manifest、确定性序列化、路径归一化、结果模型、错误。单元测试：
   序列化确定性（键排序、排除字段、往返），以及两种路径形态下 `${HOME}` 的归一化/展开。
3. **infrastructure/sync bundle** —— 面向临时目录的文件/manifest/密文 IO。集成测试：
   写出并重新读回一个 bundle。
4. **application/sync exporter + importer** —— 使用真实的 `ResourceService`、真实的凭据
   存储与临时仓库目录。集成测试：导出 → 导入往返能复现资源、文件、状态区与可解密的
   凭据；对未发生变化的仓库再次导出，除 `created_at` 外字节一致；导入绝不删除仅存在于
   本地的资源；无法在本机应用的资源被报告且不导致整次运行失败。
5. **application/sync service** —— 编排这两个操作以及密钥的导出/导入。集成测试：两个
   临时仓库模拟机器 A 与 B；断言 bundle 说了算、没有密钥时凭据保持锁定，且 bundle 中
   绝不含有主密钥。
6. **surfaces http + wiring** —— 路由、schema、错误码；在 `_lifespan` 中接线。没有
   worker 需要启动。为 `/api/v1/sync/*` 写契约测试。
7. **surfaces cli** —— 经 loopback 客户端实现 `coffer sync export|import` 与
   `coffer sync key export|import`。契约测试。
8. **frontend** —— 设置 → Sync：一个导出按钮和一个导入按钮，基于守护进程托管的原生
   目录选择器（spec agent-registry FR-042）、一份结果摘要，以及主密钥卡片 —— 卡片本身用浏览器
   自己的下载与 `<input type="file">`，因此密钥材料走 API、守护进程不打开任何路径。fleet view 以及 remote/自动同步/冲突相关的 UI 一并
   移除。
9. **docs** —— architecture.md 的横切行、roadmap 状态、docs-site 的 guide 与
   architecture 页面、中文 companion；用验收标记把 `spec.md` 中每个场景与一个测试关联。

## 构建顺序——备份远端

每一步都是一个带自己测试、可独立提交的块。

1. **domain/sync/backup.py** —— `BackupRemote` 及其校验、`BackupRun` 与
   `BackupRunStatus`、以及 `redact`。单测：默认值与 spec 一致、非法的
   interval/url/branch 被拒、脱敏能去掉每一处出现。
2. **`sync_remotes` 表** —— 模型、migration、`SqlAlchemySyncRemoteRepo`。
   「只有一行」是一条检查约束（`id = 1`），不是靠约定记住的规矩。集成测试：
   set/get 每个字段都能往返、set 两次仍只有一行、记录过的运行能读回来。
3. **`GitMirrorPort` + `GitMirror`** —— init 或接管、暂存、提交、推送、拉取、
   clone、解析修订号或日期、detach 与回到分支。集成测试跑在一个真实的本地
   裸仓库上，因而完全不涉及网络。其中两条测试专为钉死安全规则而存在：token
   绝不进入 `.git/config`，失败的推送其消息里不含任何密钥。
4. **`BackupService`** —— 一次运行：导出进工作树、只在导出结果发生变化时提交、
   推送、记录。用假 mirror 的单测覆盖四种结果，包括「推送失败保留提交、下一次
   运行把它推上去而不再产生第二次提交」。
5. **`BackupWorker`** —— 启动时补跑一次，之后按配置的间隔；一次运行内部抛出的
   异常绝不终结循环。
6. **HTTP** —— `/sync/remote`、`/sync/push`、`/sync/restore`、`/sync/status`，
   每条都有显式的响应模型。有一条测试断言远端的负载里只带凭据**引用**。
7. **CLI** —— `coffer sync remote set|show|clear`、`push`、`restore`、`status`。
   `remote set` 在启用之前先打印一次推送会包含什么。
8. **UI** —— 设置 → Sync 里的一张备份卡，形状照搬保留策略卡：自动保存、上次
   运行状态，以及一个「立即备份」按钮。

## 已遵守的关键约束

- 每个文件 ≤ 400 行；`exporter.py`/`importer.py` 变大就拆分。
- `application/` 不得 import `infrastructure/`：bundle IO 以 `BundleLayout` port 注入。
- `domain/sync` 保持纯粹（不碰 sqlalchemy、不碰文件系统）。
- 新增错误码加入 HTTP 错误信封的 `_STATUS` 映射。
- **完全没有网络出站** —— 导出与导入只触碰本地文件系统，因此该切片既不需要出站 HTTP
  例外，也不需要 git 子进程例外。
- 每个路由都有 `response_model`；mypy --strict；为 `sync` 包配置 importlinter 契约
  （它不 import 任何其他 kind）。
