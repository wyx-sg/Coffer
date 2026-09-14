# 实施计划：仓库同步

> English: [plan.md](./plan.md)

同步是一项**横切服务**，不是资源 kind（见
[Vault Sync](../../docs/decisions/vault-sync.md)）。它在四层之间遵循
retention/credentials 的模式，而它唯一拥有的、由用户填写的数据库行就是那一行
`sync_remotes` 配置；收敛 pointer 是仅本机的状态，机器注册表就是工作树本身。

spec 钉死算法；本计划钉死命名、边界与顺序。

**没有任何模块被改名。** `bundle.py` 仍叫 `bundle.py`，`git_mirror.py` 仍叫
`git_mirror.py`，`backup.py` 仍叫 `backup.py`。它们每一个的行为都有实质变化，而把
每个 import 它们的文件里的 docstring 引用统统搅一遍，对此毫无帮助。

## 分层

```
domain/sync/          pure value objects + contracts
  convergence.py      JoinKind, ConvergeStatus, GuardDirection,
                      PendingConfirmation, ConvergeRun                    (new)
  diff.py             ChangeStatus, DocChange, DeletionGuard, DiffSummary,
                      area_of, NON_VAULT_AREAS                            (new)
  machine.py          derive_machine_id, MachineDescriptor                (new)
  fernet_time.py      encrypted_at, is_fresher                        (restored)
  errors.py           the SyncError family, + SyncJoinAmbiguous
  backup.py           BackupRemote (the remote's configuration)
  models.py           AreaCount, ExportSummary
  serialization.py    deterministic Resource <-> doc projection (pure)
  portability.py      ${HOME} normalization / expansion (pure)
  manifest.py         Manifest, SCHEMA_VERSION

application/sync/
  convergence.py      ConvergeRound — the seven steps, plus reverse_to    (new)
  service.py          ConvergeService — remote, lock, audit, key bootstrap (new)
  appliers.py         TreeApplier, ResourceApplier, StateApplier,
                      CredentialApplier                                   (new)
  conflicts.py        ConflictArbiter                                     (new)
  joining.py          JoinResolver, Join                                  (new)
  machines.py         MachineRegistry, MachineView                        (new)
  worker.py           ConvergeWorker — the timer, shaped like RetentionWorker
  exporter.py         SyncExporter — the serializer a round calls at step 1
  ports.py            + ConvergenceStatePort, ConflictResolverPort,
                      VaultApplyPort, SyncRemoteRepoPort

infrastructure/sync/
  git_mirror.py       GitMirror — the one place that runs git
  bundle.py           Bundle — the tree's layout and its document IO
  tree_mirror.py      _mirror_tree / _converge_files — differential, `protected`
  machine_id.py       resolve, MachineIdentity                            (new)
  credentials.py      ciphertext dump/load
  paths.py            the mirrored trees

infrastructure/persistence/
  sync_remote_repo.py the single sync_remotes row
  (+ the ConvergenceStatePort adapter — machine-local, see below)

surfaces/
  http/sync_routes.py + sync_wiring.py    /api/v1/sync/*
  cli/sync_cmd.py                         `coffer sync` group
  frontend/src/pages/sync/                the top-level Sync page
```

六个单元承担主要重量，每个都以它实际做的事命名：

- **`ConvergeRound`**（`application/sync/convergence.py`）拥有第 0–6 步，且这些步骤
  不归任何别的东西所有。它接收一棵已经准备好的工作树、完全不碰数据库，这正是让算法
  能面向一个假 mirror 被测试的原因。加入检测位于它的 `_base` 一步里，**而不是在
  adopt 命令里**：spec 要求它在*任何*没有 pointer 的轮次上都执行，因此在一台忘掉了
  pointer 的机器上执行 `remote set`，与显式 `adopt` 得到同样的待遇。
- **`ConvergeService`** 拥有策略：远端配置、锁、审计轨迹、推送凭据的解析、主密钥
  引导，以及 `confirm` / `reject` / `rollback` 各自意味着什么。它与 `ConvergeRound`
  的切分，正是两者都能各自读懂的原因。
- **那四个 applier** 是唯一往活着的 vault 里写入的东西，每个 bundle 区一个，各自
  拥有一个 `prefix` 和恰好两个操作 —— `upsert` 与 `remove`。是两个而不是一个「同步
  这条路径」，因为**需要被授权的恰恰是删除**；它该出现在接缝上，而不是藏在一个分支
  里。每个都以抛 `CofferError` 的方式报告逐路径失败，由轮次接住。
- **`JoinResolver`** 读远端的注册表并返回一个 `Join`。它单独成一个单元，是因为它做的
  那个判断——新机器还是回归机器——正是唯一一处判断错了会静默丢数据的地方。
- **`MachineRegistry`** 经由 `BundlePort` 读写描述符；`infrastructure/sync/machine_id.resolve`
  负责派生 id。二者分开，是因为 id 必须在任何 git 仓库存在之前就能解析出来，而注册表
  没有仓库就不存在。
- **`ConflictArbiter`** 是一个只面向工作树的单元：它接收路径与一个 mirror，返回
  `(resolved_by_agent, unresolved)`。它从不接触 vault，这正是让 spec 的那条规则从
  「要记住」变成「结构上如此」的原因。

## 重写、删除、保留

| 既有单元 | 去向 |
| --- | --- |
| `domain/sync/backup.py` | **保留** —— `BackupRemote` 就是远端的配置，字段不变。`record_run` 现在收的是 `ConvergeRun` |
| `domain/sync/models.py` | **裁剪** —— `ImportSummary` 随导入器一起去掉；`AreaCount` 与 `ExportSummary` 留下，因为导出器仍然产出它们 |
| `domain/sync/errors.py` | **扩充** —— 新增 `SyncJoinAmbiguous`；bundle 与主密钥相关的错误留下，因为工作树里放的仍然是 bundle 布局 |
| `domain/sync/serialization.py` | **保留**，承载两轴 `scope` |
| `domain/sync/portability.py`、`manifest.py` | **原样保留** |
| `application/sync/exporter.py` | **保留** —— `SyncExporter` 就是第 1 步调用的序列化器。变的是它底下的东西：`Bundle` 现在差分收敛而不再清空 |
| `application/sync/importer.py` | **删除** —— 「bundle 说了算」的整树导入正是本 spec 要移除的操作；由 `appliers.py` 取代 |
| `application/sync/backup_service.py` | **删除** —— 由 `ConvergeService` + `ConvergeRound` 取代 |
| `application/sync/backup_worker.py` | **删除** —— 由 `worker.py` 的 `ConvergeWorker` 取代，形状不变 |
| `application/sync/ports.py` | **扩充** —— 四个新 port（见下）、`GitMirrorPort` 的十二项新增，以及 `BundlePort` 上的 `machines/` 方法。`SyncedStatePort` 新增 `delete_docs`；`CredentialSyncPort`、`MasterKeyPort`、`ImportGate`、`PostImportHook` 不变 |
| `infrastructure/sync/bundle.py` | **原地重写** —— `open_for_write` 什么都不清空；每个区都差分收敛；一个 `held_paths` 回调指出导出必须保留哪些路径；`write_machine_descriptor` / `read_machine_descriptors` / `delete_machine_descriptor` 加入 |
| `infrastructure/sync/git_mirror.py` | **原地扩充** —— askpass/token 处理原封不动；新增 `merge`、`commit_merge`、`abort_merge`、`take_side`、`diff_paths`、`file_count`、`reset_hard`、`tag`、`tags`、`delete_tag`、`read_file`、`read_worktree`，以及 `EMPTY_TREE` 常量 |
| `infrastructure/sync/tree_mirror.py` | **扩充** —— `_mirror_tree` 与 `_converge_files` 接受 `protected`，即那些因为本 vault 尚未吸收而必须在收敛中存活下来的、相对目标目录的路径 |
| `infrastructure/sync/credentials.py`、`paths.py` | **保留** |
| `infrastructure/persistence/sync_remote_repo.py` | **保留** —— 同一行，`last_status` 词汇表更新 |
| `frontend/.../settings/SyncBundleCard.tsx` | **删除**，随导出/导入一起 |
| `frontend/.../settings/SyncBackupCard.tsx` | **重写**进 Sync 页的 Status tab |
| `frontend/.../settings/SyncMasterKeyCard.tsx` | **保留**，移到 Status tab 上 |

0.3.0 那次收敛尝试留下的东西一样都不复活：没有墓碑表、没有 TTL、没有时间戳仲裁、
没有隔离表。diff 就是账本。

### 四个新 port

- **`ConvergenceStatePort`** —— pointer、重试集与「本机不适用」集（`pointer` /
  `set_pointer` / `held_paths` / `hold` / `release`），外加被扣住的那一轮
  （`pending` / `set_pending`）。其中没有一样会随行。
- **`ConflictResolverPort`** —— `available()` 与 `resolve(paths)`。不可用时如实
  报告而不是抛错，因为「停下来交给用户自己的 git」是设计好的兜底，不是错误路径。
- **`VaultApplyPort`** —— `prefix`、`upsert(path)`、`remove(path)`。四个 applier
  在结构上实现它。
- **`SyncRemoteRepoPort`** —— `get` / `set` / `clear` / `record_run` /
  `last_run` / `list_runs`，这样应用层不必 import 任何基础设施。`record_run`
  是一步写两处——远端行的 `last_*` 列与一行 `sync_runs`——在同一个事务里完成，
  因为一轮若被历史漏掉，两边就会对同一个时刻给出不同的说法。

### 收敛状态存在哪

`ConvergenceStatePort` 由**仅本机的 SQLite** 支撑，位于
`infrastructure/persistence/`、`sync_remote_repo.py` 旁边——而不是它自己的一个 JSON
文件。`coffer.db` 本就仅属本机、也本就被排除在 bundle 之外，因此把 pointer 放在那里
不会多出第二个需要推理的存储、第二样需要原子写的东西、第二样要在「什么永远不随行」
清单里解释的东西。它保存一行收敛状态（pointer，以及被扣住的 `PendingConfirmation`
及其 direction、commit、`remote_tip`、breaches 与 paths），外加每条被扣住的路径一行、
带一个 `applicable` 标志把重试集与「本机不适用」集区分开。

### 守卫的豁免

`PendingConfirmation` 带着 **`remote_tip`**：这次扣留是针对哪个远端 tip 提出的。被
确认的一轮是**重新推导，而不是续跑**——序列化是确定性的，因此一个未变的 vault 对着
一个未变的远端，产出的正是当初给用户看的那份 diff——而 `ConvergeRound.run` 只在
`confirmed_tip` 等于当前 tip 时才豁免删除守卫。若远端在这期间动过，守卫会再跑一次，
这一轮被重新扣住。

这是一个决策，不是实现细节。一次确认是对一组特定文档的回答，不是一张长期有效的删除
许可证，而一句活得比它所针对的那份 diff 还久的「是」，正是事故的形状。`reject` 是
另一半：守卫在应用之前运行，所以 vault 从未被碰过，拒绝只需要把工作树 `reset_hard`
回 pointer。

### 一把锁

`ConvergeService.lock` 以 property 暴露，并**与知识 tidy worker 共用**。两者都会改写
vault 内容，而在一次改写进行到一半时取的导出是一份撕裂的快照，git 会把它读成一次
刻意的变更。这正是那把锁可注入而非私有的原因。

## 构建顺序（TDD，每步可独立提交）

1. **scope 的机器轴** —— `domain/scope.py` 变成两轴的 `Scope` 值对象，`excluded_by`
   给出是哪条轴把它拦下的；`mcp_server` 与 `skill` 携带它，gateway 与 supervisor 在
   传 `agent=` 的同时传 `machine=`；`coffer scope set` 长出 `--machines` /
   `--no-machines`，`PUT /resources/{kind}/{name}/scope` 接受对象形态。migration
   `0069` 以**只增不减**的方式改写每一行 `scope_json` —— `["claude-code"]` 变成
   `{"agents": ["claude-code"], "machines": null}`，`NULL` 仍是 `NULL` —— 并把形态
   内联而不是 import 领域模型，这样这个 revision 的含义永远不变。之后没有任何加载期
   垫片会去读旧形态。
2. **机器身份** —— `derive_machine_id`（纯）、`machine_id.resolve`（三个来源及其
   顺序）、带 `derived` 的 `MachineIdentity`。单测：原始主机标识符绝不出现在输出里；
   同一个原始 id 哈希稳定；兜底文件以 `0600` 写出且绝不重写，因为重新生成它会把这台
   机器的身份一分为二。
3. **domain/sync 值对象** —— `convergence.py`、`diff.py`、`machine.py`、
   `fernet_time.py`。单测：`area_of` 覆盖 spec 应用表的每一行，且 `NON_VAULT_AREAS`
   排除 `machines` 与 `manifest`；`DeletionGuard.breached_areas` 在超过比例**或**
   超过下限时触发、把 `totals` 里不存在的区视为整体处于风险中、对没有删除的 diff
   返回空；`MachineDescriptor.from_doc` 容忍更新的构建写下的字段；`is_fresher`
   不需要密钥就能给两个 token 排序，并在打平或头部无法解析时回答 False。
4. **收敛状态适配器** —— `ConvergenceStatePort` 背后的那张 SQLite 表。集成测试：
   pointer、两个被扣住的集合与一个 `PendingConfirmation` 能往返；`hold`/`release`
   让一条路径在两个集合之间移动；`set_pending(None)` 能清空。
5. **`Bundle` 的差分写入** —— `open_for_write` 什么都不清空，`_converge_files` 与
   `_mirror_tree` 尊重 `protected`，机器描述符的方法落地。集成测试：未发生变化的
   vault 产出未发生变化的树；被删除的文档被移除；被**扣住**的路径绝不被移除；未发生
   变化的描述符不会被重写——正是这一点让一台闲置的机器不会提交心跳。
6. **`GitMirror` 的新命令** —— 带冲突列表的 merge、`commit_merge`、`abort_merge`、
   `take_side`、`diff_paths`、`file_count`、tag 系列、`read_file`、`read_worktree`、
   `reset_hard`、`EMPTY_TREE`。集成测试跑在一个真实的本地裸仓库上，因而完全不涉及
   网络。其中三条钉死备份远端本就有的安全规则：token 绝不进入 `.git/config`、绝不
   出现在参数向量里、失败的推送其消息里不含任何密钥。还有一条钉死
   `core.quotepath=false`，因为一个非 ASCII 名字的冲突文件曾经带着 C 引号转义回来，
   把解决器逼进了一个重试循环。
7. **那四个 applier** —— 面向真实的 `ResourceService`、真实的凭据存储与临时 vault
   目录，覆盖应用表的每一行。集成测试：新增会注册并跑完该 kind 的导入门禁；删除会
   移除资源并释放没有其他资源引用的凭据；删除一个本机早已没有的东西是「一致」而不是
   失败；`TreeApplier` 不留下空的 collection 目录；`CredentialApplier` 即便不在合并
   冲突中，也会拒收一份比它手上更旧的密文块。
8. **`ConflictArbiter`** —— 先是凭据规则，然后是那趟有界的 agent 处理。用假 resolver
   的单测：残留的冲突标记被拒；解析不了的资源或状态文档被拒；两边头部都无法排序的
   凭据冲突被留作未解决而不是靠猜；凭据上的「删除 vs 编辑」落到下一层去。没有配置
   模型时，什么也不解决、并把一切如实报告。
9. **`JoinResolver` + `MachineRegistry`** —— 加入判断与注册表。集成测试：描述符不
   存在则以 `NEW` 从 `EMPTY_TREE` 加入；存在且其 commit 可达则以 `RETURNING` 从那个
   commit 加入；存在但 commit 已从历史里消失则抛 `SyncJoinAmbiguous` 而不是猜，而
   `join_choice="keep-local"` 是那个显式答案；一份本构建读不懂的描述符，依然证明这台
   机器来过。注册表的测试：两台机器的描述符合并无冲突；`publish_self` 每个自然日最多
   重盖一次 `last_converged_on`；`retire` 在同一次变更里既删除描述符**又**把该 id 从
   每一处 `scope.machines` 里剥掉，并拒绝退役自己。
10. **`ConvergeRound`** —— 那七步。用假件的单测覆盖步骤顺序与每一个 `ConvergeStatus`；
    集成测试用两个临时 vault 加一个裸仓库充当机器 A 与 B，重放 spec 的场景：新机器
    加入取并集、回归机器恢复 base、陈旧机器不复活删除、干净的 hunk 合并、未解决的
    冲突既不碰 vault 也不动 pointer、应用侧守卫拦下删除、**发布侧**守卫拦下一个被清空
    的 vault、豁免对记录下来的 tip 生效而在远端动过之后失效、`reverse_to` 落到应用前
    快照上，以及漂移的 HEAD 在第 1 步之前被重置回 pointer。还有一条钉死那条让
    「未发生变化的 vault 不产生提交」成立的规则：只涉及 `manifest.json` 的暂存差异是
    一次**重新盖章，不是变化**——`staged_paths` 与 `discard_staged` 正是为此而存在，
    `_serialize_and_commit` 必须在提交之前查一下它们。
11. **`ConvergeService` + `ConvergeWorker`** —— 策略与定时器。`run_once` 对任何可以
    告诉用户的情况都不抛错，因此循环没有判断要做；一轮内部抛出的异常绝不终结它。
    测试：关闭的远端返回 `DISABLED` 且完全不碰 git；被扣住的一轮在下一次 tick 立刻
    返回；`confirm` 带着记录下来的 tip 重新推导；`reject` 重置工作树而不碰 vault；
    `rollback` 从 pointer 到最新快照取差异并应用，且什么都不推送。tidy 设置在这一步
    于 `state/settings/internal-engine.yaml` 里长出它的 owner 机器，非 owner 上的一趟
    处理是空操作，且在存在未解决的冲突或扣留时被跳过。
12. **HTTP + 接线** —— 下面那些操作，每条都有显式的响应模型；`ConvergeWorker` 在
    `_lifespan` 中启动与停止。针对 `contracts/api.openapi.yaml` 的契约测试。有一条
    测试断言远端的负载里只带凭据**引用**。
13. **CLI** —— 经 loopback 客户端实现 `coffer sync remote set|show|clear`、`adopt`、
    `now`、`status`、`restore`、`confirm`、`reject`、`rollback`、`machines`、
    `machine rename|remove`、`key export|import`。`adopt` 接受与 `remote set` 相同的
    远端参数，因为它本来就在配置一个远端；并在继续之前先打印它发现了什么——是哪一种
    加入、本机上次收敛是什么时候。
14. **前端** —— 一个顶级 **Sync** 页，带 **Status** tab（远端表单、上次与下次轮次、
    最近几轮改了什么、一个运行按钮、主密钥卡片）与 **Machines** tab（注册表表格，
    标出本机、用文字说明指纹不匹配，并在 id 来自兜底文件而非主机时给出提示）。冲突
    与扣留在 Status 上渲染为横幅。scope 编辑器长出一个由注册表构建的机器选择列表
    ——绝不是自由文本 id——并说明是哪条轴让某个资源在本机休眠。
15. **文档** —— architecture.md 的横切行、roadmap 状态、docs-site 的 guide 与
    architecture 页面、中文 companion；用验收标记把 `spec.md` 中每个场景与一个测试
    关联。

## API 形状

全都在 `/api/v1/sync` 之下，全都由 loopback token 守卫。schema 名就是 FastAPI 响应
模型的名字，因为 `make verify-contract` 会拿这两者互相核对。这些路由是两个对象的
一层薄投影：`ConvergeService`（`run_once`、`confirm`、`reject`、`rollback`、
`key_fingerprint`、`export_key`、`import_key`）与 `MachineRegistry`（`list`、
`describe_self`、`retire`）。

| 操作 | 请求 | 响应 | 背后是 |
| --- | --- | --- | --- |
| `GET /sync/remote` | — | `SyncRemoteStateOut` | `SyncRemoteRepoPort.get` |
| `PUT /sync/remote` | `SyncRemoteIn` | `SyncRemoteOut` | `SyncRemoteRepoPort.set` |
| `DELETE /sync/remote` | — | `SyncRemoteClearedOut` | `SyncRemoteRepoPort.clear` |
| `POST /sync/run` | `RunIn` | `ConvergeRunOut` | `run_once(join_choice=…)` |
| `POST /sync/adopt` | `AdoptIn` | `ConvergeRunOut` | 先 `set` 再 `run_once` |
| `GET /sync/status` | — | `SyncStatusOut` | `last_run` + 状态 + 注册表 |
| `GET /sync/runs` | `limit` | `SyncRunListOut` | `list_runs`——每一轮，最新在前 |
| `POST /sync/restore` | `RestoreIn` | `ConvergeRunOut` | 经同一批 applier 应用一个更早的修订 |
| `POST /sync/confirm` | — | `ConvergeRunOut` | `confirm()` |
| `POST /sync/reject` | — | `SyncRejectedOut` | `reject()` |
| `POST /sync/rollback` | — | `ConvergeRunOut` | `rollback()` |
| `GET /sync/machines` | — | `MachineListOut` | `MachineRegistry.list` |
| `PATCH /sync/machines/self` | `MachineRenameIn` | `MachineOut` | `describe_self` + 重命名 |
| `DELETE /sync/machines/{id}` | — | `MachineRetiredOut` | `MachineRegistry.retire` |
| `GET /sync/key/fingerprint` | — | `KeyFingerprintOut` | `key_fingerprint()` |
| `POST /sync/key/export` | `EmptyIn` | `KeyMaterialOut` | `export_key()` |
| `POST /sync/key/import` | `KeyMaterialIn` | `KeyImportOut` | `import_key()` |

`confirm` 与 `reject` 各占一条路径，因为它们是两个方法、形状确实不同：确认会重跑
一轮并返回它，而拒绝只是重置工作树、除了「我做了」之外什么也不返回。把它们折进一个
body 字段里，只会把这件事藏起来。

有三个形状承载了设计，值得写在这里而不只是写在 yaml 里：

- **`ConvergeRunOut` 就是 `ConvergeRun`，逐字段对应。** `status` 作为判别式
  （`ok`、`no_change`、`conflict`、`awaiting_confirmation`、`push_failed`、
  `failed`、`disabled`），而 `join` 是 `new` / `returning` / 缺席。`applied` 与
  `published` 都要报告，因为「这一轮拿到了什么」与「这一轮给出了什么」是两个问题，
  而发布侧的守卫让第二个问题变得承重。
- **`PendingConfirmationOut` 说明自己的方向与 tip。** `direction` 是 `apply` 或
  `publish`；`breaches` 是每个被突破的区一条 `(area, deleted, total)`；
  `remote_tip` 是豁免所限定的范围。`GET /sync/status` 两个方向都能报告，因为一次
  扣留活得比提出它的那次请求更久。
- **`MachineOut` 是 `MachineView` 的摊平** —— 描述符的各字段，外加 `is_self` 与一个
  可空的 `key_matches`：任一方尚未发布指纹时它是 `null`，而不是误导性的 `false`。
  注意字段是 `last_converged_on`，一个**日期**：它每个自然日最多重盖一次，因此它的
  含义是「本机上次收敛的那一天」。

错误码及其 HTTP 映射：`BACKUP_REMOTE_INVALID`（422）、`SYNC_JOIN_AMBIGUOUS`（409）、
`SYNC_NOTHING_PENDING`（409）、`SYNC_NOTHING_TO_ROLL_BACK`（409）、
`SYNC_CANNOT_RETIRE_SELF`（422）、`SYNC_BUNDLE_TOO_NEW`（409）、
`SYNC_BUNDLE_INVALID`（422）、`SYNC_SERIALIZATION_INVALID`（422）、
`SYNC_APPLIER_MISSING`（422）、`MASTER_KEY_FILE_INVALID`（422）。

## 已遵守的关键约束

- 每个文件 ≤ 400 行；要盯着的是 `application/sync/convergence.py`，而 `joining.py`
  与 `conflicts.py` 已经从它里面拆了出来。
- `application/` 不得 import `infrastructure/`：git、bundle、收敛状态、远端那一行
  与主机 id 全都以 port 注入。
- `domain/sync` 保持纯粹（不碰 sqlalchemy、不碰文件系统、不起子进程）——包括
  `machine.py`，它只做哈希、不读主机。
- `ConflictArbiter` 从不拿到 vault 的句柄——工作树就是它的全世界，这让 spec 的那条
  规则从「要记住」变成「结构上如此」。
- **网络出站是一条有界例外**（章程 0.6.0）：唯一的出站流量是对用户自有远端的
  `git fetch` / `git push`，来自那唯一一个子进程适配器，凭据只在一次调用期间被解析，
  并在任何错误被记录之前从中抹除两次——一次在适配器里，一次在服务里。
- 每个路由都有 `response_model`；mypy --strict；为 `sync` 包配置 importlinter 契约
  （它不 import 任何其他 kind —— kind 模块经由组合根注册的 `SyncedStatePort` 与
  `ImportGate` 够到它）。
