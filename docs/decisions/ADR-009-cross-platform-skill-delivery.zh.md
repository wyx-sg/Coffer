# ADR-009：跨平台 skill 投递 —— Symlink / Junction / Copy-Fallback

> English: [ADR-009-cross-platform-skill-delivery.md](./ADR-009-cross-platform-skill-delivery.md)

**Status**: Accepted
**Date**: 2026-05-29
**Deciders**: Yuxing Wu
**Related**: spec `005-skill-manager`（FR-009、FR-012、SC-007），spec `004-agent-registry`（`AgentConfig.skill_dir`），[ADR-007](ADR-007-everything-is-a-resource-kind.md)

## Context

Spec `005-skill-manager` 在 `~/.coffer/skills/<name>/` 维护一份规范主副本，并要求每个已注册的 agent 在它"自身的"skill 目录下能看到这些被管理的 skill —— 也就是 `~/.claude/skills/<name>/`、`~/.cursor/skills/<name>/` 等等。这份主副本必须是**唯一可编辑的事实来源**（FR-003），同时每个 agent 仍按其既有约定从自己的路径下读取。

显而易见的投递机制有三种：

1. **复制**：把 master 文件夹拷贝进每个 agent 的 skill 目录。
2. **配置指针**：告诉每个 agent "你的 skill 目录现在指向 `~/.coffer/skills/`"。
3. **目录链接**：在 agent 路径上放一个目录 symlink（POSIX）/ junction（Windows），指回 master。

复制会立刻造成 drift：用户在某个 agent 的 skill 目录里改一笔，并不会传播；每次更新要触动 N 个 agent；`verify` 会从结构性检查降级为内容 diff。配置指针方案被拒绝，因为我们要支持的多数 agent（Claude Code、Cursor、Claude Desktop）把 skill 目录写死，即便允许覆盖，配置也存放在我们无法稳妥触碰的 client-private 配置里。

目录链接在我们要发布的所有平台上都可用，**除了**不支持链接的文件系统。剩下的决策点是：**每个 OS 用哪种链接，以及两种都不可用时怎么办** —— Windows 上的 FAT32 分区、部分 Windows 网络共享、以及一些老旧的 NAS 目标，可能同时拒绝 `os.symlink`（WinError 1314：无权创建符号链接）与 `mklink /J`（目标文件系统不允许 junction）。

## Decision

**`infrastructure/skill/sync_engine.py` 中的单一 `SyncEngine` 在每个平台上按"最优先方案 → 备选方案"逐个尝试，若都失败则降级为复制；每条 binding 实际使用的链接模式持久化到 DB，UI 据此显示 degraded binding。**

具体行为，按 OS 分：

- **POSIX (macOS、Linux)**：`os.symlink(master, link, target_is_directory=True)`，记录 `link_mode = symlink`，正常情况下不需要回退。
- **Windows**：先尝试 `os.symlink(...)` —— 在开启 Developer Mode 或具备 `SeCreateSymbolicLinkPrivilege` 时可成功；遇到 `OSError(WinError 1314)`（或等价错误）则回退到 `subprocess.run(["cmd", "/c", "mklink", "/J", link, master])`，创建目录 **junction**。分别记录 `link_mode = symlink` 或 `link_mode = junction`。Junction 在 NTFS 本地卷上无需权限提升即可使用。
- **任意 OS，二者都失败**（FAT32、某些网络共享、被锁死的 CI runner）：用 `shutil.copytree(...)` 把 master 内容复制到 agent 目标位置，记录 `link_mode = copy_fallback`，并写一条 `degraded=true` 的审计事件。UI 在 degraded binding 上显示警告；`verify` 把它视作独立的 drift 类别，因为对 agent 侧副本的编辑不会回流到 master。

模式按 binding 而非按 OS 决定 —— 同一台用户机器上完全可能混用文件系统（如 NTFS C: 盘加上一个 SMB 挂载的 skill 目录）。`SyncEngine.classify_target` 在 `verify` 时重新读取磁盘形态，是 drift 分类的依据，详见 `specs/005-skill-manager/data-model.md` 中的 `DriftKind` 表。

删除路径与创建对称：`SyncEngine.remove_directory_link` 先识别磁盘形态再删除（symlink 用 `os.unlink`，junction 用 `os.rmdir`，copy-fallback 用 `shutil.rmtree`）。这避开了一个经典 Windows 陷阱 —— 对 junction 直接 `shutil.rmtree` 会递归删除 master。

## Consequences

**正面**

- 只有一份 master，"哪里改都同步"是产品核心承诺，本方案完整保留。
- application 层无需 OS 分支：`SkillService` 调用单一端口，`SyncEngine` adapter 封装所有平台差异。
- Degraded binding 可观测：`link_mode = copy_fallback` 出现在 `SkillBindingOut`、桌面 UI 与审计事件中，用户能看见 FAT32 共享并未实时同步。
- Copy fallback 让 Coffer 在 symlink/junction 都不支持的文件系统上仍可使用，而不是直接报错让用户在 v1 没有任何出路。

**负面**

- Copy fallback 在静默地"次一等"：通过 agent 视角对 skill 的编辑**不会**回到 master。我们用 (a) 审计 `degraded=true`、(b) UI 警告、(c) `verify` 每次都报告这些 binding 来缓解。我们在 v0.6+ 之前不会自动把 copy-fallback "升格"回真正的链接。
- 没有开启 Developer Mode 的 Windows 用户拿到的是 junction，对显式解析目标的工具行为略有差异。我们目前要支持的 agent 都没有把这点当问题，但差异客观存在。
- 三套删除路径让"误删用户 master 文件夹"的可能性增加。我们用 `tests/infrastructure/skill/test_sync_engine.py` 的单测矩阵覆盖每一组 (create, remove) × (symlink, junction, copy_fallback)，并在 POSIX 与 mock 出来的 Windows shim 上分别跑。

## Alternatives Considered

**只用复制，不用链接。** 拒绝。

- 每次更新都需要在每个 agent 上做一次内容同步；本应是元数据的变更被放大为 N 次文件系统遍历。
- 破坏"在 master 上改、各处都能看到"的工作流，而这恰恰是设置中心化 store 的全部理由。

**配置指针（改写每个 agent 的 `skillsPath` 设置）。** 拒绝。

- 多数目标 agent 把 skill 路径存在不稳定、跨版本会变的 private config 里，触碰它很脆弱。
- 部分 agent 完全不允许覆盖路径。
- 即便可行，改第三方工具的配置也是 constitution 明确禁止的信任边界越界。

**用 hard link 代替 symlink/junction。** 拒绝。

- 我们要支持的文件系统（NTFS、APFS、ext4）都不支持目录级 hard link。
- 改为文件级 hard link 会让每个 skill 文件夹内每个文件都进入 binding 的簿记，更新里增删一个文件就要全量重做。

**用 libgit2 / Tauri 文件系统 API 做跨平台链接创建。** 评估过，暂缓。

- 引入 `libgit2` 或 Rust shim 能换来统一的错误模型，但代价是后端为此只为这一件事拉入一个 native 依赖。`os.symlink` + `cmd /c mklink /J` 是一条走得很顺的老路径，依赖足迹也最小。
- 如果未来 Windows junction 的边缘情况积压到需要更丰满的文件系统辅助，我们再回头考虑。
