# Spec 010 — 快速上手

> English: [quickstart.md](./quickstart.md)

通过你自己拥有的 git 仓库，让一个 Coffer vault 在多台机器之间保持同步。
主密钥永远不会经由 git 传输；你需要在每台新机器上以带外（out-of-band）方式
亲手导入一次。

## 1. 创建一个你自己拥有的远程仓库

新建一个空的私有仓库（GitHub、GitLab 或自托管均可），例如
`git@github.com:you/coffer-vault.git`。Coffer 使用你平常的 git 凭据
（SSH key 或 token）——也就是 `git push` 已经在用的那一套。

## 2. 在机器 A 上初始化 sync

```bash
coffer sync init git@github.com:you/coffer-vault.git
```

这会创建 sync 工作区（`~/.coffer/sync/`）、记录远程仓库，并执行
第一次同步。检查一下：

```bash
coffer sync status        # -> clean，最近一次同步 <time>
```

## 3. 把主密钥带到机器 B（带外传输）

在机器 A 上：

```bash
coffer sync key export ~/coffer-master.key
```

通过你信任的渠道（U 盘、密码管理器、安全拷贝）把该文件转移到机器 B——
**不要**经由 sync 仓库传输。在机器 B 上：

```bash
coffer sync key import ~/coffer-master.key
```

## 4. 在机器 B 上拉取 vault

```bash
coffer sync init git@github.com:you/coffer-vault.git
coffer sync status        # -> clean；由于密钥已就位，凭据可以解密
```

机器 B 现在拥有与机器 A 相同的知识库、记忆、已注册资源以及
凭据。

> 如果你跳过第 3 步，sync 仍然可以工作，但凭据会保持**锁定**状态：
> `coffer sync status` 会把它们列在 `credentials_locked` 下，需要这些凭据的
> 资源在你导入密钥之前不会启动。

## 5. 日常使用

```bash
coffer sync               # export -> pull -> (if clean) push -> import
```

每次切换机器时运行它。或者开启免手动模式：

```bash
coffer sync config --auto on --interval 300
```

开启自动同步后，守护进程会（去抖后）推送你的改动，并按设定的间隔拉取
其他机器的改动——无需手动执行命令。

## 查看你的机器

```bash
coffer sync machines                    # 该 vault 关联的所有机器
coffer sync machines --rename studio    # 重命名本机
```

每台机器在同步时登记自己（名称、平台、上次同步时间）；这份列表同样出现在
桌面端的同步面板中。

## 冲突自动解决

如果你在同步之前在两台机器上编辑了同一个资源/文件，同步运行会把每个冲突
路径自动解决为较新的一次编辑并直接完成——无需手动操作。极少数引擎无法
处理的路径会让运行停在 `conflicted`，界面会指引你到自己的仓库（如
GitHub）解决；CLI 兜底仍然可用：

```bash
coffer sync status        # -> conflicted，列出相关路径（罕见）
coffer sync resolve --theirs resources/mcp_server/confluence.yaml   # 或 --ours，或编辑后用 --resolved
coffer sync               # 完成
```

## REST / 桌面端

以上所有功能同样可通过 `/api/v1/sync/*` 使用，也可在桌面端的
**Sync** 设置面板中操作（配置远程仓库——保存即校验、开关自动同步、
查看带行动指引的状态、触发一次同步运行、跨机器比对 master key 指纹）。
