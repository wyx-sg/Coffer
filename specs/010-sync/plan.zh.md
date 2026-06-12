# Spec 010 — 实现计划

> English: [plan.md](./plan.md)

同步是一项**横切服务**，而非一种资源类型（参见
[ADR-016](../../docs/decisions/ADR-016-multi-machine-sync.md)）。它沿用了
retention/credentials 在四个层次上的模式。

## 分层

```
domain/sync/          pure value objects + contracts
  manifest.py         Manifest, SCHEMA_VERSION
  models.py           SyncConfig, SyncState, SyncStatus enum, ConflictInfo
  serialization.py    deterministic Resource <-> dict projection (pure)
  errors.py           SyncError family (codes for the error envelope)

application/sync/
  ports.py            GitPort, ManifestStore, WorkspaceLayout protocols
  exporter.py         vault -> workspace (files, resources, ciphertext)
  importer.py         workspace -> vault (mirror+reindex, reconcile, ciphertext)
  service.py          SyncService: run/status/config/resolve/key orchestration
  worker.py           SyncWorker: debounced + interval auto-sync loop
  config_service.py   SyncConfigService over the sync_config/sync_state rows

infrastructure/sync/
  git_repo.py         GitPort impl over the `git` subprocess (sole net egress)
  workspace.py        file mirror + manifest read/write + ciphertext dump/load
  persistence.py      SyncConfigModel, SyncStateModel + repos

surfaces/
  http/sync_routes.py + sync_wiring.py    /api/v1/sync/*
  cli/sync_cmd.py                         `coffer sync` group
```

## 构建顺序（TDD，每一步都是可提交的代码块）

1. **domain/sync** — models、manifest、确定性序列化、errors。
   单元测试：序列化的确定性（键排序、排除字段、往返一致），以及状态转换。
2. **infrastructure/sync persistence** — config/state 表 + repos + migration
   `0017`。集成测试：行的往返。
3. **infrastructure/sync git_repo + workspace** — git 子进程适配器以及
   file/manifest/ciphertext 的 IO。针对作为 `origin` 的本地**裸（bare）**仓库
   （真实 git）进行集成测试。
4. **application/sync exporter + importer** — 使用真实的 `ResourceService` +
   真实的凭据存储 + 临时 vault 目录。集成测试：export → import
   往返能复现出资源、文件以及可解密的凭据。
5. **application/sync service + config_service** — 编排一次 run、status、
   resolve、key 的导出/导入。集成测试：两个临时 vault + 一个裸仓库
   模拟机器 A 和 B；断言收敛、凭据锁定、冲突的
   stop/resolve，以及 workspace 中绝不包含主密钥。
6. **surfaces http + wiring** — routes、schemas、错误码；在 `_lifespan` 中接线
   并启动 `SyncWorker`（受 `auto` 开关控制）。针对 `/api/v1/sync/*` 的契约测试。
7. **surfaces cli** — 基于 loopback 客户端的 `coffer sync` 命令组。契约测试。
8. **frontend** — 在现有的 API/query-key 约定之上构建 Sync 设置面板
   （config、status、run、resolve）。
9. **docs** — architecture.md 的横切服务行、README 的功能说明行、双语
   配套文档；用验收标记把每个 `spec.md` 场景关联到一项测试。

## 遵守的关键约束

- 每个文件 ≤ 400 行；若 `service.py`/`importer.py` 增长则拆分。
- `application/` 不得 import `infrastructure/`：git/workspace/persistence 以
  `GitPort` / `WorkspaceLayout` / repo 协议的形式注入。
- `domain/sync` 保持纯净（不含 git、不含 sqlalchemy、不含 fs）。
- 新增的错误码加入 HTTP 错误信封的 `_STATUS` 映射。
- 出站 git 通过子进程使用用户环境中现有的凭据，而非 Coffer 的 HTTP
  客户端；不新增 loopback 绑定例外。
- 每个 route 都带 `response_model`；mypy --strict；为 `sync` 包提供
  importlinter 契约（它不 import 任何其他资源类型）。
