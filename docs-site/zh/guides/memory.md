---
title: 记忆
description: 你用的所有智能体共用一份记忆。智能体把学到的关于你和你项目的东西写进你保险库里的 Markdown 文件，Coffer 在每个新会话开始时把该项目的记忆交给它。
---

# 记忆 {#memory}

Coffer 为你用的所有编程智能体保存一份记忆。它是你保险库里的一个 Markdown 文件夹：每个项目一个文件夹，每个主题一个文件。智能体在工作时按 Coffer 在 `coffer-guide` 技能里给出的规则，自己写这些文件。会话在某个仓库里开始时，Coffer 把该项目的记忆交给它。[保险库同步](/zh/guides/vault-sync)把这些文件带到你的其他机器上，所以 Claude Code 今天上午在笔记本上学到的东西，Codex 下午在台式机上就知道。

记忆是一项[实验功能](/zh/guides/experimental-features)：先在**设置 → 功能**里开启它。

## 它怎样工作 {#how-it-works}

1. **智能体写。** 当你告诉智能体关于你自己或你希望它怎么工作的事、纠正它，或者告诉它一个仓库里没有记录的项目事实时，智能体用自己的文件工具，在该项目记忆文件夹里合适的主题文件中加一行。记忆没有 Coffer 工具。
2. **Coffer 交给会话。** 在仓库里开始的每个会话，Coffer 加到每个智能体里的钩子都会把该项目的记忆打印进会话（最多约 4 KB）。放不下的按路径和标题列出，智能体在相关时自己去读。Coffer 自己运行的会话（对话、[消息渠道](/zh/guides/channels)、[定时任务](/zh/guides/scheduled-tasks)）则把同样的文字放进系统提示词。
3. **智能体整理。** 行数会越积越多。记忆页的**整理**把一段提示词交给智能体，让它合并、拆分、精简这些文件，整次整理记成一次你可以撤销的修改。

Coffer 从不读写任何智能体自己的记忆（Claude Code 的自动记忆、Codex 的记忆）。每个智能体自己的记忆继续和 Coffer 的并行工作；见[智能体自己的记忆](#your-agents-own-memory)。

## 记忆、知识还是技能 {#memory-knowledge-or-a-skill}

记忆关于你；[知识](/zh/guides/knowledge)关于世界。按顺序问：

1. 换一个人它还成立吗？不成立，就是**记忆**：你是谁、你喜欢怎样工作（偏好、纠正、你认可的做法）、项目当前的状态和仓库里没有记录的决定。
2. 它是关于外部系统、团队或流程的，或者需要出处吗？那就是**知识**：某个服务或团队怎样运作、有哪些坑、导入的文档，以及任何会过时或值得分享的东西。
3. 它是你反复执行的一串固定步骤吗？那就是**[技能](/zh/guides/skills)**。

仓库里已经写明的、一次性的请求和密钥，哪里都不放。

| | 记忆 | 知识 |
| --- | --- | --- |
| 内容 | 你、怎样和你合作、项目的状态 | 外部系统、团队、流程及其坑 |
| 谁写 | 你的智能体，边学边写 | 你，或智能体替你写下 |
| 组织方式 | 按项目，每个主题一个文件 | 按知识集 |
| 格式 | Coffer 固定 | 每个知识集自定 |
| 怎样到达智能体 | 每个会话开始时交给它 | `coffer-guide` 技能指过去时由智能体自己读 |
| 存储 | `vault/memory/`，和其他保险库内容一样同步 | 保险库，和其他保险库内容一样同步 |

## 中心库 {#the-hub}

```text
~/.coffer/vault/memory/projects/
└── github.com-acme-payments/      每个项目一个文件夹
    ├── testing.md                 每个主题一个文件
    └── release.md
```

一个项目就是一个 git 仓库。它的文件夹以仓库的 `origin` 地址命名，除字母、数字、`.`、`_` 和 `-` 以外的字符都换成 `-`，所以两台机器上的两个克隆共用一个文件夹。没有远端的仓库用它的文件夹名。不在任何仓库里的会话不会拿到记忆。

每个文件是一个主题：属于一起、一起用到的记忆。

```markdown
---
title: Testing
type: feedback
updated: 2026-11-19
---
Run only the failing tests while fixing them; the whole suite only before a push.
Never mock the vault in integration tests: a mocked vault once hid a broken migration.
```

| 字段 | 含义 |
| --- | --- |
| `title` | 用几个词说明主题 |
| `type` | `user`（你是谁）、`feedback`（你希望智能体怎样工作）或 `project`（仓库里没有记录的项目状态） |
| `updated` | 文件最后修改的日期 |
| 正文 | 每行一条记忆，每条最多 400 个字符 |

格式和规则由 Coffer 定，对每个智能体都一样，这样钩子、记忆页和每个智能体读这些文件的方式一致。规则不由你编辑。不符合格式的文件照样会被读取并交给会话；记忆页会指出哪里不对，下一次整理会修好它。

## 会话拿到什么 {#what-a-session-is-handed}

会话开始时，钩子会往会话里打印这样一段：

```text
<coffer-memory project="github.com/acme/payments">
Your memories of this project, kept by Coffer in ~/.coffer/vault/memory/projects/github.com-acme-payments/ …

## Testing (feedback, updated 2026-11-19)
Run only the failing tests while fixing them; …

Not shown here; read a file when it is relevant:
- ~/.coffer/vault/memory/projects/github.com-acme-payments/release.md: Release
</coffer-memory>
```

关于你的记忆排在最前，然后是怎样和你合作，再然后是项目状态；同一类里新的在前。整段不超过约 4 KB。

### 每个智能体里的钩子 {#the-hook-in-each-agent}

记忆开启时，Coffer 在每个已注册智能体里保留一个运行 `coffer memory session-start` 的 `SessionStart` 钩子：

| 智能体 | 位置 |
| --- | --- |
| Claude Code | `~/.claude/settings.json` 里的 `hooks.SessionStart` |
| Codex | `~/.codex/hooks.json` 里的 `hooks.SessionStart` |

Coffer 把自己的钩子加在你自己的钩子旁边，只移除自己的那个。`coffer` 命令的位置变了，它会更新钩子；你关闭记忆或移除智能体时，它会移除钩子。每次变化都会以 `memory_hook_installed` 或 `memory_hook_removed` 记进[审计日志](/zh/guides/activity)。

**Codex 第一次运行新钩子前会请你审核一次**：在命令行里打开 `/hooks`，或在 Codex 应用的**设置 → Hooks** 里批准 Coffer 的钩子。

没有会话开始钩子的智能体，只在 Coffer 自己运行的会话里拿到记忆。

## 让智能体能写这些文件 {#letting-agents-write-the-files}

记忆文件夹在智能体工作的仓库之外，所以智能体可能每次都要请求权限，或者被沙箱挡住。允许一次就好：

- **Claude Code**：在 `~/.claude/settings.json` 的 `permissions.allow` 里加一条该文件夹的 `Edit` 规则：

  ```json
  { "permissions": { "allow": ["Edit(~/.coffer/vault/memory/projects/**)"] } }
  ```

- **Codex**：把该文件夹的绝对路径加进 `~/.codex/config.toml` 的 `writable_roots`：

  ```toml
  [sandbox_workspace_write]
  writable_roots = ["/Users/you/.coffer/vault/memory/projects"]
  ```

被挡住的智能体会说明情况，并按 `coffer-guide` 技能告诉你这些做法。

## 智能体自己的记忆 {#your-agents-own-memory}

Claude Code 和 Codex 各自有自己的记忆。Coffer 不读、不写、也不关闭它，两者之间不同步。是否保留智能体自己的记忆由你决定：

- **保留**：智能体可能把一些经验写进它自己的记忆，另一些写进 Coffer 的。只有 Coffer 里的会到达你的其他智能体和机器。
- **关闭**：所有记忆都在一处。Claude Code 里，在 `~/.claude/settings.json` 设 `"autoMemoryEnabled": false`（或在 `/memory` 里关闭）。Codex 的记忆默认关闭，除非你开启过（`~/.codex/config.toml` 里的 `[features] memories`，或应用里的**设置 → Personalization**）。

## 记忆页 {#the-memory-page}

侧边栏的**记忆**列出存有记忆的项目，以及每个项目的文件数和不符合格式的文件数。选一个项目，就能看到它的主题文件：标题、类型和最后更新时间，可以搜索，也可以按类型筛选。选一个文件，会在抽屉里打开它，顶部写明哪里不符合格式。

- **编辑**打开整个文件（包括 frontmatter），保存为一次修改。如果在此期间智能体改过这个文件，保存会被拒绝，你重新加载即可。
- **删除**移除这个文件。可以从历史里找回。
- **历史**（在 **⋯** 里）列出记忆的每次修改，无论来自智能体、你还是一次整理，并可以恢复任何更早的版本。

页面标题下写明这些文件存放在哪里。

## 整理 {#tidying}

**整理**把一段提示词交给你选的智能体。智能体先运行 `coffer memory tidy-start`，然后逐个项目处理：合并属于一起的主题，拆开混了多个话题的主题，删掉重复、过时或被新内容推翻的行，把关于外部系统的行移进知识，修好每个不符合格式的文件，最后运行 `coffer memory tidy-finish` 并附上一段简短报告。

整理进行中，页面会显示出来，智能体的修改会被攒在一起：结束时它们作为一次修改提交，带上报告，所以历史里一次整理就是一条，可以一次撤销。闲置 30 分钟的整理，或被守护进程重启打断的整理，会被关闭，已做的修改照样提交。

**设置定期整理…**（在 **⋯** 里，[定时任务](/zh/guides/scheduled-tasks)开启时出现）会打开一个带整理提示词的新定时任务，默认每周一次。保存前可以改时间、智能体或提示词。Coffer 自己没有整理定时器。

## 在命令行上 {#on-the-command-line}

[`coffer memory`](/zh/reference/cli/memory) 列出项目（`state`）、某个项目的主题文件及其问题（`topics`）和单个文件（`show`）；`tidy-start` 和 `tidy-finish` 开始和结束一次整理；`session-start` 是钩子运行的命令。编辑文件就是编辑文件：用任何编辑器都行。

## 从记忆同步升级 {#upgrading-from-memory-sync}

早期版本会把记忆同步进每个智能体自己的记忆。这个版本第一次启动时，Coffer 会移除它写进你智能体里的东西：每个 Claude Code `MEMORY.md` 里它的那段（以及因此变空的文件）、它的 `coffer_*.md` 文件，以及每个 Codex 记忆文件夹里它的文件夹。你智能体自己的记忆不受影响。早期版本发布到中心库的条目（每条记忆一个文件）会就地改写成主题文件；之后一次整理会把它们合并成主题。

## 关闭记忆 {#turning-memory-off}

在**设置 → 功能**里关闭**记忆**，会从每个智能体里移除 Coffer 的钩子，记忆页和它的 API 不再可用，`coffer-guide` 里也不再有记忆规则。文件留在你的保险库里，重新开启记忆会把钩子装回去。

## 故障排查 {#troubleshooting}

**会话没有拿到记忆。** 检查记忆已开启、智能体已注册，并且会话是在某个 git 仓库里开始的。在 Codex 里，到 `/hooks` 批准 Coffer 的钩子。用标准输入传 `{"cwd": "<仓库路径>"}` 运行 `coffer memory session-start`，就能看到在那里开始的会话会拿到什么。

**智能体不写记忆。** 检查 `coffer-guide` 技能已送达这个智能体（智能体的**技能**标签页），并且允许写记忆文件夹（见[让智能体能写这些文件](#letting-agents-write-the-files)）。你也可以直接对智能体说"记住这个"。

**某个文件显示格式问题。** 运行整理，或在记忆页上编辑这个文件。

**两台机器改了同一个文件。** 主题文件和其他保险库文件一样同步。两台机器各自追加的行通常会自动合并；真正的冲突会像其他冲突一样让[保险库同步](/zh/guides/vault-sync)停下来等你处理。

## 相关内容 {#related}

- [知识](/zh/guides/knowledge)
- [智能体](/zh/guides/agents)
- [保险库同步](/zh/guides/vault-sync)
- [定时任务](/zh/guides/scheduled-tasks)
- [记忆架构](/zh/architecture/memory)
- [`coffer memory`](/zh/reference/cli/memory)
- [记忆规格](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/memory/spec.md)
- [把记忆集中放在保险库里，由智能体自己写](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/keep-memory-in-one-place-agents-write-themselves.md)
