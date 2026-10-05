---
title: 技能
description: 在 Coffer 里维护一个符合 AgentSkills 标准的技能库——从文件夹、压缩包或 Git 仓库添加——并把每个技能投递到你选定的智能体的技能目录中。
---

# 技能 {#skills}

Coffer 在你的机器上维护一个技能主库，并把每个技能链接到所有应该拥有它的智能体的技能目录里。本页介绍：从文件夹、压缩包或 Git 仓库添加技能，从仓库更新技能，把智能体已有的技能纳入托管，选择技能的生效范围，查看和编辑技能文件，技能需要的命令，技能名称，检查智能体手里的副本，以及 Coffer 自带的内置技能 `coffer-guide`。底层原理见[技能架构](/zh/architecture/skills)页面。

## 技能是做什么的 {#what-skills-are-for}

技能是智能体按需加载的一个文件夹：一个写着指令的 `SKILL.md`，加上它需要的脚本或参考文件。Claude Code 和 Codex 都原生地从各自配置目录下的 `skills/` 文件夹读取技能。没有 Coffer 的话，同一个技能会被分别拷进 `~/.claude/skills/` 和 `~/.codex/skills/`，几份副本慢慢就不一样了。

Coffer 在 `~/.coffer/vault/skills/<name>/` 下为每个技能保留唯一一份主副本，并在每个智能体的技能文件夹里放一个指向它的目录链接。你只改一次，每个智能体读到的都是同样的字节。

Coffer 按开放的 [AgentSkills](https://agentskills.io) 格式管理技能。不符合该格式的文件夹无法导入。

## 前提条件 {#prerequisites}

- Coffer 守护进程正在运行（见[运行守护进程](/zh/guides/daemon)）。
- 要从 Git 仓库添加，这台机器上需要装有 `git`。
- 至少注册了一个智能体（见[智能体](/zh/guides/agents)）。Coffer 把技能投递给 Claude Code 和 Codex。

## 技能格式 {#the-skill-format}

技能文件夹必须包含一个 `SKILL.md`，其 YAML frontmatter 至少要有 `name` 和 `description`：

```markdown
---
name: release-checklist
description: Walks through this team's release checklist — version bump, changelog, tag, and the smoke tests to run before announcing.
license: MIT
allowed-tools: Bash, Read
---

# Release checklist

1. Bump the version in `pyproject.toml` ...
```

Coffer 接受每个文件夹之前都会校验：

| 规则 | 限制 |
| --- | --- |
| 存在 `SKILL.md` | 必需 |
| `name` | 小写字母、数字和 `-`；以字母或数字开头；最多 64 个字符 |
| `description` | 非空，最多 1024 个字符 |
| 文件夹内的符号链接 | 不能指向文件夹之外，也不能指向某个文件夹（指向文件的链接按该文件的字节数计） |
| 文件夹总大小 | 最多 50 MB |

Coffer 还会读取可选的 `license` 字段、实验性的 `allowed-tools` 字段（列表，或以逗号或空格分隔的字符串），以及 `requires:`——技能驱动的命令行工具，Coffer 会在这台机器上检查它们，并显示在技能的 **依赖** 标签页和[命令行工具页面](/zh/guides/clis)上，它需要的 Coffer 密钥（见[技能需要的密钥](#secrets-a-skill-needs)），以及它调用的 MCP 服务器和自定义工具（见[技能需要的工具](#tools-a-skill-needs)）。其他 frontmatter 键会保留但被忽略。

违反规则的文件夹会被拒绝并给出原因，保险库里不会写入任何东西。

## 技能放在哪里 {#where-skills-live}

| 路径 | 是什么 |
| --- | --- |
| `~/.coffer/vault/skills/<name>/` | 主文件夹。这是你唯一需要编辑的副本。 |
| `<config_dir>/skills/<name>` | 每个智能体中投递的链接，例如 `~/.claude/skills/release-checklist` 或 `~/.codex/skills/release-checklist`。它指向主文件夹。 |

因为投递的路径是一个链接，从 `~/.claude/skills/<name>/` 里面编辑 `SKILL.md`，改的就是主副本，其他每个智能体下次读取时都会看到改动。在那里删掉一个文件，也会从主副本里删掉。

## 技能页面 {#the-skills-page}

**技能**（侧边栏的能力分组下）左边是你的技能库，右边是你正在看的技能。左侧列表有一个搜索框和 **检查副本**，并把技能按需要你处理的程度分组：**需要处理**、**使用中**、**未使用**、**已关闭** 和 **内置**。每一行显示技能的名称和用徽标表示的生效范围（描述在技能详情页里），名称下面只在有事要你处理时显示那一件事：**主文件夹不见了**、**Codex 中有文件夹挡住**、**需要 jq · 未安装**、**工具已关闭**、**缺少密钥**、**无法访问来源** 或 **有可用更新**。搜索框下方的 **生效范围** 筛选可以把列表缩小到对某一个智能体生效的技能（智能体的技能 tab 会带着这个智能体跳到这里，`/skills?agent=<uid>`）。勾选行（悬停时会出现复选框）可以一次设置多个技能的生效范围或删除它们；选中的内容会以一条工具栏显示在搜索框下方和阅读窗格中。`~/.coffer/vault/skills/` 中没有被任何技能认领的文件夹会单独列在 **不在技能库中** 下（见[下文](#folders-not-in-your-library)）。

打开的技能的页头有它的名称、一个状态标签（**使用中**、**已关闭**、**主文件夹不见了**、**有文件夹挡住**、**缺少命令**、**工具已关闭**、**缺少密钥**、**无法访问来源**），以及两个固定的按钮：**生效范围** 和一个 **⋯** 菜单，里面有 **在编辑器中打开**、**在 Finder 中显示**、**复制主文件夹路径**、**检查智能体的副本**、**关闭**（从所有智能体中移除，但保留你选过的智能体）和 **删除…**。标签页上方的横幅会说明需要你处理的事——有文件夹挡住、缺少命令、工具已关闭、有更新——并给出唯一对应的操作。

选中一个技能会在右侧打开它，有自己的地址（`/skills/<name>`），包含四个标签页：

| 标签页 | 显示内容 |
| --- | --- |
| **文件** | 技能的文件列表和打开的文件，默认打开渲染后的 `SKILL.md`。**预览 / 源码** 在渲染视图和原始文本之间切换 Markdown 文件，**在编辑器中打开** 会用你的编辑器打开它。二进制文件提供 **用默认应用打开** 和 **在 Finder 中显示**；特别大的文件只显示开头部分，只读。来自 Git 的技能会在文件上方显示其来源。 |
| **投递** | 每个智能体及其副本的状态：**已链接**、**已复制，未链接**（不允许链接的地方）、有文件夹挡住（附带 **查看…**），或未投递及原因。**重新检查** 重新检查每一份副本。 |
| **依赖** | 技能声明需要的东西，分成四个列表：**命令**（每个带状态和指向命令行工具页面的链接）、**密钥**（是否已设置，带 **打开密钥**）、**工具**（它调用的 MCP 服务器和自定义工具分组，各自开或关，并链接到它的页面）和 **技能**（它会加载的其他技能）。安装和登录在命令行工具页面上进行。从未声明过任何东西的技能会显示为依赖未知，见[声明与否](#declared-or-not)。 |
| **历史** | 技能文件夹的各个版本，最新的在最上面，每个都写明做了什么、谁写的、什么时候，以及选中版本的差异，并有**恢复此版本…**。见[回看较早的版本](#look-back-at-an-earlier-version)。Coffer 的内置技能也有这个标签，上面写着它没有历史：它在每次启动时由运行中的版本重建，不存放在保险库里。 |

技能页面只列出 Coffer 托管的技能。智能体拥有但 Coffer 没有托管的技能，在该智能体的 **技能** 标签页上，你可以在那里把它们纳入托管（见[下文](#adopt-skills-an-agent-already-has)）。

## 添加技能 {#add-a-skill}

技能可以来自三个地方。无论用哪种，Coffer 都会先显示它找到了什么——一个或多个技能、它们的名称和描述、哪些无法添加及原因、哪些名称已被占用——在你确认之前什么都不添加。关闭对话框不会留下任何东西。

### 从文件夹 {#from-a-folder}

```text
Skills → Add skill → From a folder → paste the path, or Choose… → Add skill
```

Coffer 从 `SKILL.md` 的 frontmatter 读取技能名称，并把文件夹拷到 `~/.coffer/vault/skills/release-checklist/`。它会记录来源路径，但之后不再跟踪：源文件夹后来的改动，要等你再添加一次才会被读入。在 Web 界面中，如果文件夹顶层没有 `SKILL.md` 而子文件夹里有，会把这些子文件夹列出来供你选择。

### 从压缩包 {#from-an-archive}

```text
Skills → Add skill → From an archive → Choose file… (or drop a .zip or .skill file) → Add skill
```

一个 `.zip` 或 `.skill` 压缩包，只要 `SKILL.md` 位于压缩包顶层或往下一层文件夹，就算包含一个技能。包含多个技能的压缩包会把它们全部列出，由你挑选要添加哪些。

只要有条目使用绝对路径或路径中含 `..`、有条目是符号链接、或者解压后会超过 50 MB，Coffer 就会在解压任何内容之前拒绝整个压缩包，并列出这些条目。顶层和往下一层都没有 `SKILL.md` 的压缩包会以相应的提示被拒绝。

### 从 Git 仓库 {#from-a-git-repository}

```text
Skills → Add skill → From Git → Repository URL, and optionally Branch or tag and Folder → Add skill
```

Coffer 用这台机器自己的 `git` 克隆仓库，把你给出的分支、标签或提交（没给就用默认分支）解析为一个具体的提交，然后按与压缩包相同的规则，在你指定的文件夹里查找技能。像 `https://github.com/acme/agent-skills/tree/main/terraform-plan` 这样的 GitHub 文件夹地址，会被解读为仓库、分支和文件夹。

技能被**固定**在它拷贝时所用的那个提交上。仓库变了，它也不会变；见[从仓库更新技能](#update-a-skill-from-its-repository)。

::: info Coffer 能访问哪些仓库
Git 在不弹提示的情况下运行，Coffer 不给它任何凭据，也不保存任何凭据。公开仓库总能访问。私有仓库只要这台机器的 git 本来就能克隆它就行——通过 macOS 钥匙串之类的凭据助手，或 SSH 密钥——因为 Coffer 用的是你自己的 git 配置。如果 git 要求输入密码，添加就会失败，并显示 git 的报错信息。带用户名或密码的仓库 URL（`https://user:token@…`）会被拒绝，因为 URL 会存进保险库并显示在技能页面上；请让凭据助手或 SSH 密钥来提供凭据。压缩包里的脚本保留压缩包记录的可执行位。
:::

### 名称已被占用时 {#when-the-name-is-taken}

添加一个 `name` 已存在的技能会因冲突被拒绝。要用新内容替换已有技能，请在对话框中该行选择 **替换**。主文件夹的内容会一步替换完成，技能的生效范围和已投递的链接都保留。

新添加的技能默认启用，并对所有已注册的智能体生效，所以会立即链接到每个智能体的技能文件夹里。

## 从仓库更新技能 {#update-a-skill-from-its-repository}

从 Git 仓库添加的技能会在它的页面上显示来源：仓库、文件夹、固定的提交，以及是否有更新在等待。Coffer 按你在**设置 › 通用 › 检查技能更新**里选的计划在后台检查仓库——**每 6 小时**（默认）、**每天**、**每周**或**仅在我要求时**——你也可以随时用**检查更新**检查，在任何设置下都可以。这个选择只保存在这台机器上（`~/.coffer/daemon-config.json`），不同步，立即生效。

```text
Skills → the skill → Check for updates, then Hand off to <Agent> to update when an update is available
```

当分支或标签上有新的提交改动了技能文件夹，技能会在技能页和技能自己的页面上显示**有可用更新**，并写明从固定提交到新提交的提交范围。**Coffer 自己不应用更新。**没有更新预览，没有**保留我的**、**采用对方的**或**对比**，也没有它自己的合并：把上游的新内容带进一个可能带着你的改动的文件夹，是你的智能体的活。

更新在等待时，技能还提供**在编辑器中打开**（主文件夹）和**查看上游改动**：对 GitHub 或 GitLab 仓库，它是指向托管站点上从固定提交到新提交的对比页的链接；其他托管站点则改为显示可复制的提交范围和各提交的主题。Coffer 自己不画任何 diff。技能提供一个主按钮**交给 &lt;Agent&gt; 更新**（菜单里有另一个已安装的智能体和**复制提示词**），不论你是否编辑过这个技能。提示词在你按下按钮时才由 Coffer 构造，所以从不过时。它写明技能的主文件夹是唯一可以编辑的地方、固定提交和新提交及其主题、读取更新用的仓库、分支和文件夹（只读，URL 里不带凭据），以及你在固定之后编辑过的文件，或者说明没有。智能体把新提交的内容带进主文件夹，保留你改动的用意，在两边真正冲突之处问你，并给你看 diff；它自己不记录这次合并。

文件看起来没问题时，选按钮旁边的**我已合并**并确认。这会把固定点移到新提交，并让主文件夹保持智能体改完的样子。你的改动仍算作相对新固定点的本地改动，所以下一次更新的提示词会恰好列出你带过来的改动。只有正在等待的那次更新可以被记录：固定的提交，或不在该分支上的提交，会被 `SKILL_UPDATE_NOT_PENDING` 拒绝。

**API：** `POST /skills/{uid}/source/check` 检查，`POST /skills/{uid}/source/handoff` 返回最新提交和提示词（没有更新的提交改动文件夹时以 `SKILL_UPDATE_NOT_PENDING` 拒绝），`POST /skills/{uid}/source/merged` 记录合并。

如果仓库不能再访问，技能继续使用它的固定副本工作。它的页面会显示 git 的消息和上次检查成功的时间，在检查再次成功之前什么都不变。

要把一个 Git 技能换到另一个仓库、分支或文件夹，使用其来源块里的**更改来源…**。Coffer 会克隆新的来源，并列出相对你当前文件夹会新增、移除或改变的文件名（只有文件名，没有 diff）；你确认之前什么都不会被替换，确认后文件夹立即被换入，技能保留它的名称、生效范围和链接。取消则一切照旧。（`POST /skills/{uid}/source/change`，然后 `…/source/change/apply`。）

从文件夹或压缩包添加的技能没有可供更新的来源：用 **替换** 重新添加即可。

## 把智能体已有的技能纳入托管 {#adopt-skills-an-agent-already-has}

智能体身上会积攒一些 Coffer 没有托管的技能——你手动拷进 `~/.claude/skills/` 的文件夹，或者某个工具装进 Codex 的 `~/.agents/skills/` 的技能。Coffer 把它们列为**未托管**技能，你可以把它们纳入技能库，或者删掉。

Coffer 扫描：

- 每个智能体的 `<config_dir>/skills/`，以及
- Codex 的 `~/.agents/skills/`，Codex 也会读这个位置。

其中不是 Coffer 托管链接的都算未托管。Codex 自己的 `.system` 条目从不列出。

### 列出未托管的技能 {#list-unmanaged-skills}

```text
Agents → choose the agent → Skills tab → the agent's own skills
```

每一项显示名称、路径、位置，以及它的 `SKILL.md` 是否有效。无效的条目会显示原因。

### 预览一个 {#preview-one}

在决定怎么处理之前，先读一读这个未托管的技能。这里的任何操作都不会改动文件夹。

```text
Agents → choose the agent → Skills tab → click the row
```

详情页有一个 **概览** 标签页（`SKILL.md` 中的描述、文件夹的路径和位置）和一个 **文件** 标签页（文件夹的目录树，以及每个文件的只读预览）。无效的文件夹也能打开，顶部会显示原因。页头有 **纳入托管** 和带 **删除…** 的 **⋯** 菜单；标题栏的后退箭头回到智能体的技能标签页。文件显示在和其他地方相同的文件树与查看器里，所以在编辑器中打开或显示文件在查看器上。文件读取仅限于该文件夹内，和托管的技能一样。

### 纳入托管一个 {#adopt-one}

纳入托管会把文件夹移到 `~/.coffer/vault/skills/<name>/`，将其注册为技能，并在智能体期望的位置放一个托管链接。

```text
Agents → choose the agent → Skills tab → Adopt on the row, or Adopt on the skill's page
```

纳入托管会打开一个小表单，填**在 Coffer 中的名称**（输入时会对照技能库检查，默认是文件夹自己的名字）和技能一开始的**生效范围**——所有智能体、只有你选的智能体，或关闭。出错会留在表单里。

- 从 `<config_dir>/skills/` 纳入托管的文件夹，会被原地替换成链接。
- 从 `~/.agents/skills/` 纳入托管的文件夹，会被移出该目录，链接放在 `<config_dir>/skills/` 中。Codex 两个位置都读，所以它仍能看到这个技能。

当文件夹没有有效的 `SKILL.md`、名称与技能库中已有的技能相同、或条目是一个指向 Coffer 存储之外的符号链接（显示为 **外部链接**）时，纳入托管会被拒绝，什么都不会移动。如果在技能注册之前有任何一步失败，原来的文件夹会原封不动地留在原处。

纳入托管之后，这个技能就是一个普通的托管技能，遵循和其他技能一样的投递规则：在默认生效范围下它属于每个智能体（通过 REST，纳入托管的调用带同样的 `name` 和 `reach`），其他智能体会在下一次调和时拿到链接（见[何时投递](#when-delivery-happens)）。

### 删除未托管的技能 {#delete-an-unmanaged-skill}

要从磁盘删除一个未托管的文件夹而不纳入托管：

```text
Agents → choose the agent → Skills tab → ⋯ › Delete… on the row, or ⋯ › Delete… on the skill's page
```

这只删除那个文件夹，绝不会碰主库。Coffer 从不自行删除未托管的文件夹。

## 选择哪些智能体获得技能 {#choose-which-agents-get-a-skill}

技能上有两项设置决定它投递到哪里，除此之外没有别的：

- **启用**——被禁用的技能哪里都不投递。
- **生效范围**（技能的 scope）——它面向哪些智能体。

| 生效范围 | 效果 |
| --- | --- |
| 所有智能体（无 scope） | 投递给每个已注册的智能体，包括之后注册的。这是默认值。 |
| 指定智能体 | 只投递给你挑选的智能体。 |
| 未选中智能体（指定智能体但一个都没勾选） | 不投递给任何智能体。技能仍留在技能库中，照常列出和同步。 |

当且仅当技能已启用**并且**其生效范围包含某个智能体时，技能才会投递给该智能体。没有“这个智能体不要任何技能”这种按智能体的开关；想让某个智能体远离某个技能，就把它排除在该技能的生效范围之外。

```text
Skills → the Reach button on the skill's row (or on its detail page)
       → Off | All agents | Chosen agents
```

生效范围按钮上用徽标显示当前的设置——智能体的标记、**所有智能体** 或 **关闭**，从不显示数量。面板里的每次修改都会立即保存（先显示“正在应用…”，再显示“✓ 已保存”）；**所有智能体** 也包括以后注册的智能体。保存后按智能体逐个投递：如果某个智能体的副本放不进去，它那一行会说明原因，并提供 **重试** 或 **取消勾选**。要一次修改多个技能，选中它们的行，用选择栏里的生效范围控件。

::: info 生效范围按机器设置
生效范围和启用标志只作用于你设置它们的那台机器。[保险库同步](/zh/guides/vault-sync)会把技能本身——文件和元数据——带到你的其他机器上，但每台机器保留自己的生效范围。
:::

### 何时投递 {#when-delivery-happens}

只要影响投递的东西发生变化，Coffer 就会调和某个智能体的技能：技能被导入、移除、启用、禁用或修改了生效范围；智能体被注册或修改了配置目录；或者一轮同步导入了新技能。每次调和会创建智能体应有的链接，删除它不该再有的链接。删除链接从不碰主文件夹。

配置读不出来的智能体会被原样保留，直到它重新能读：它的链接既不新增也不删除。

### 链接、联接点还是副本 {#link-junction-or-copy}

| 平台 | 技能如何投递 |
| --- | --- |
| macOS、Linux | 目录符号链接。 |
| Windows | 目录符号链接；不允许时用目录联接点（junction）；文件系统两者都不支持时（FAT32、某些网络共享），完整拷贝一份。 |

拷贝方式的投递会在下一次修复时跟随主文件夹更新。技能的 **投递** 标签页会把该智能体的副本显示为 **已复制，未链接**，并附上原因。

如果 `<config_dir>/skills/<name>` 处已经有一个不是 Coffer 链接的东西，Coffer 会为该技能报告冲突（有文件夹挡住），并保留已有的文件或文件夹不动。其余技能照常投递。见[处理挡路的文件夹](#resolve-a-folder-in-the-way)。

## 查看和编辑技能文件 {#view-and-edit-skill-files}

主文件夹就是一个普通目录，所以编辑技能的方法就是在你的编辑器或 shell 里打开 `~/.coffer/vault/skills/<name>/`。改动在智能体下次读取时生效，不需要导入步骤。技能的 **⋯** 菜单里有 **复制主文件夹路径**。

```text
Skills → choose the skill → Files tab → pick a file → Open in editor
```

文件标签页是只读的。它对文本文件提供 **在编辑器中打开** 和 **在访达中显示**，对二进制文件提供 **用默认应用打开** 和 **在 Finder 中显示**（你系统的文件管理器）；技能的 **⋯** 菜单可以打开或显示整个文件夹。在编辑器中打开用的是**设置 › 通用**里选择的编辑器。

Coffer 不会替你写技能文件夹里的任何文件，所以不存在与你的编辑器或智能体冲突的保存：它们保存了什么，标签页下次就显示什么，每一次这样的编辑都会成为保险库历史里的一个版本。见[手工编辑保险库](/zh/guides/vault-files)。要给技能添加文件，请用编辑器或 shell 在主文件夹中创建。

### 回看较早的版本 {#look-back-at-an-earlier-version}

要回看技能的较早版本，打开它的**历史**标签。它是一张卡片，中间有一条可以拖动的分隔线。左边是该技能文件夹的各个版本，最新的在最上面，标题是**版本**并带着数量。每一行说明这个版本做了什么（*新增 &lt;file&gt;*、*删除 &lt;file&gt;*、*改动了 &lt;file&gt;*、*改动了 N 个文件*，或*恢复了 &lt;日期&gt; 的版本*）、谁写的、什么时候，以及它改动的行数（+N −M）。写入者显示为**你**、**在磁盘上编辑**（你的编辑器、shell，或智能体自己的文件工具）、按产品名显示的智能体、**Coffer** 或**同步**。最新的一个标着**当前**，打开标签时默认选中它。右边是选中版本的短 id、写入者和时间，以及它改动的每个文件的差异；对其他版本，一个开关可以切换**本版本的改动**和**与当前版本对比**。

**恢复此版本…**会先询问：文件夹里的每个文件都会恢复成那个版本，之后新增的文件会被删除，全部**作为一个新版本**保存，所以历史里的内容都不会丢。它会记入[活动](/zh/guides/activity)。如果文件夹在你打开标签之后又变了，恢复会被拒绝并返回 `VAULT_FILE_STALE`；重新打开标签再试即可。你也可以用 git 读同样的版本：`git -C ~/.coffer/vault log -p -- skills/<name>/`。见[找回较早的版本](/zh/guides/knowledge#bring-back-an-earlier-version)。

## 技能需要的命令 {#commands-a-skill-needs}

技能可以在 frontmatter 中用 `requires` 声明它依赖哪些命令行工具：

```yaml
---
name: gh-triage
description: Label new issues, find duplicates, ask for missing details.
requires: [jq, "gh>=2.40", uv]
---
```

每个条目是一个命令名，可选附带最低版本（`gh>=2.40`）；`requires: {commands: [...]}` 以及 `{command: gh, version: "2.40"}` 这样的条目也能读取。技能的 **依赖** 标签页会列出它们，每个都链接到它在命令行工具页面上的位置。声明依赖不会改变投递：无论命令装没装，技能都会投递。

## 技能需要的密钥 {#secrets-a-skill-needs}

如果技能的命令需要某个令牌或密钥，就在 `requires` 的映射形式中用 `secrets:` 写出这个 Coffer 密钥的名称：

```yaml
---
name: gh-triage
description: Label new issues, find duplicates, ask for missing details.
requires:
  commands: [jq, "gh>=2.40"]
  secrets: [GITHUB_TOKEN]
---
```

每个条目是 Coffer 密钥存储中一个密钥的名称，绝不是它的值。只有映射形式能带 `secrets:`；列表形式（`requires: [jq, gh]`）只声明命令。密钥存储不接受的名称，或重复写出的名称，会被跳过并给出警告；`commands`、`secrets` 和 `tools` 之外的键会被拒绝：Coffer 把它报告为警告，不读取它下面的任何内容。

值由你自己在[密钥页面](/zh/guides/secrets)设置；技能的命令在 `coffer run --secret` 下运行时拿到它，这个值只设置在该命令的环境中：

```sh
coffer run --secret GITHUB_TOKEN -- gh issue list
```

技能的 **依赖** 标签页在命令下方列出每个声明的密钥，显示为 **已设置**，或“密钥 GITHUB_TOKEN 未设置”并附 **打开密钥**。Coffer 只按名称向密钥存储查询，从不读取值。有未设置密钥的技能还会在它的列表行和标签页上方的横幅中说明，并出现在总览的 **需要你处理** 列表中，其操作会打开密钥页面。和命令一样，无论密钥是否已设置，技能都会投递。

## 技能需要的工具 {#tools-a-skill-needs}

调用 MCP 服务器或自定义工具的技能，在 `requires` 的映射写法里用 `tools:` 声明它，位置紧挨着 `commands:` 和 `secrets:`：

```yaml
---
name: invoice-chaser
description: Find overdue invoices and draft reminders.
requires:
  commands: [jq]
  secrets: [BILLING_TOKEN]
  tools: [github, {name: billing-api, why: Reads invoices.}]
---
```

每一项是 MCP 服务器或自定义工具分组在 Coffer 里的名字，可以只写名字，也可以写成带 `why` 一行的映射。只有映射写法才有 `tools:`。Coffer 不认识的名字（没有叫这个名字的 MCP 服务器或工具分组）会被跳过并给出警告，警告显示在[命令行工具页面](/zh/guides/clis)上；它从不阻止技能被导入或投递。

技能的**依赖** tab 在**工具**下列出每个工具，标明开、关或出错，并链接到它的页面。被依赖的工具关闭时，技能会进入**需要处理**，横幅是**工具已关闭**，它的操作就是把工具打开。和命令、密钥一样，不管工具开没开，技能都会被投递。

## profile 声明的依赖 {#profile-declared-requirements}

技能库可以为每个技能在 `<技能文件夹>/profiles/<name>.md` 保存 profile：一个 `default.md`，外加每个环境一个文件，每个都带 YAML frontmatter（原因见[编写技能库](/zh/guides/writing-skill-libraries)）。profile 的 frontmatter 可以带和 `SKILL.md` 一样的 `requires:`，包括命令、密钥和工具：

```yaml
---
carrier: Skill(example-log-search)
requires:
  commands:
    - command: gh
      login_check: gh auth status
  secrets: [EXAMPLE_TOKEN]
---
```

智能体运行时选定一个 profile，而 Coffer 无从得知选的是哪个。所以 Coffer 每次都读取 `SKILL.md` 的 `requires:` 与每个 `profiles/*.md` 的 `requires:` 的并集，并说明每一项由哪个 profile 声明：**依赖** 标签页在该行显示“in profile example-org”（界面文字），[命令行工具](/zh/guides/clis)的**被谁需要**显示 `skill-name · example-org`。`SKILL.md` 自己声明的项不带 profile。在多处声明的命令、密钥或工具合并为一条依赖；对命令，Coffer 保留最高的最低版本，以及第一个非空的 title、`why` 和登录检查。profile 里的警告会写明它的文件 `profiles/<name>.md`。Coffer 只读取这些文件声明的内容，从不扫描它们去猜测。

## 声明与否，以及让智能体检查 {#declared-or-not}

Coffer 区分“声明了不需要”和“没有声明”。`SKILL.md` 和所有 `profiles/*.md` 里都没有 `requires:` 键的技能是**未声明**：它的**依赖**标签页写明依赖未知，因为它没有说，并提供**让智能体补充依赖声明**。任何地方有 `requires:` 键的技能就是已声明，哪怕是空的 `requires: []`；空表示它什么都不需要，标签页写**没有依赖**。“未知”只显示在**依赖**标签页：技能列表、需要处理项和总览都不提，投递也不变。

已声明技能的标签页顶部有**让智能体检查规范**，技能列表的选择栏对勾选的技能也有同一个按钮，一次生成一份提示词。这个按钮就是通常的交给智能体拆分按钮（**交给 \<智能体\>**，菜单里有**复制提示词**）。提示词在你按下按钮时由 Coffer 生成，写明每个技能的主文件夹、它有没有声明，以及它的来源；对 Git 导入的技能，会说明改动作为本地修改在更新后保留，并建议也向上游提出。

智能体说的一切都只是建议，你可以拒绝。它会读完整个技能文件夹，提出打算改什么、为什么，问你采纳哪些，只改主文件夹里你同意的部分，给你看 diff，不提交任何东西。它不会重构技能、增加 profiles 文件夹或重命名文件；文件里已有的密钥值或个人信息，你想保留就保留，它最多指出来并建议使用 Coffer 的密钥存储。Coffer 只读取 `requires:` 声明；可选的约定见[编写技能库](/zh/guides/writing-skill-libraries)，Coffer 从不强制它们。

## skill 的脚本把文件放在哪里 {#where-a-skill-s-scripts-keep-their-files}

skill 的脚本把产生的日志、操作记录和临时文件写在 `~/.coffer/skill-data/<skill-name>/` 下，每个 skill 一个文件夹；`coffer path skill-data` 会打印这个目录。它在保险库之外，所以都不会同步，skill 不得写进自己的文件夹（那是保险库）或 `~/.coffer` 里的其他位置。文件超过 **Skill 临时数据** 保留窗口（默认 30 天，在**设置 → 数据 → 历史**）就会被 Coffer 删除，所以需要长期保留的东西不该放在这里。`coffer-guide` skill 也会把这一点告诉智能体。

## 技能名称与描述 {#skill-names-and-descriptions}

技能的名称来自其 `SKILL.md` 中的 `name` 行，技能注册后就固定不变。它既是智能体加载技能所用的目录名，也是智能体调用它时的标识，所以引用它的指令、其他技能和权限规则都会因改名而失效。改名请求会以 `NAME_IMMUTABLE` 被拒绝。要换个名字，就移除这个技能，再用新名字重新添加，这会重置它的生效范围和已投递的链接（即它的绑定）。这一决定记录在决策记录（ADR）“names-visible-to-agents-are-fixed”中。

技能没有单独的显示标题：Coffer 的页面显示的都是它的名称。它的**描述**就是其 `SKILL.md` 的 `description` 行，也就是智能体用来判断何时使用该技能的文字，所以 Coffer 显示它，自己不另存描述。技能记录上没有任何可编辑的内容。要修改描述或技能的其他任何东西，请编辑主文件夹（`~/.coffer/vault/skills/<name>/`）里的 `SKILL.md`；技能的 **文件** 标签页会在你的编辑器里打开它。

## 检查偏移并修复 {#check-for-drift-and-repair-it}

偏移指 Coffer 记录的投递状态与磁盘上的实际情况之间的任何不一致。Coffer 识别五种：

| 类型 | 发生了什么 | 自动修复 |
| --- | --- | --- |
| `missing_link` | 智能体技能文件夹里的链接被删了。 | 是 |
| `tampered_link` | 链接现在指向主文件夹以外的地方。 | 是 |
| `replaced_with_regular` | 链接路径上现在是一个真实的文件或文件夹。 | 否——Coffer 从不碰你的内容 |
| `missing_master` | `~/.coffer/vault/skills/` 下的主文件夹不见了。 | 否 |
| `orphan_master` | `~/.coffer/vault/skills/` 中的某个文件夹没有对应的 Coffer 记录。 | 否 |

### 启动时自动修复 {#automatic-repair-at-startup}

每次守护进程启动时，Coffer 都会重建缺失的链接，并把被篡改的链接重新指回去。每次修复都以系统身份记入审计日志。其他三种保持原样，连同技能、智能体、路径和原因写入守护进程日志。这项检查中的任何失败都不会阻止守护进程启动。

### 手动检查 {#check-by-hand}

技能页面上的 **检查副本** 运行检查报告，列出每项发现，包括技能、智能体（或技能库）、哪里不一致，以及是否需要你处理。缺失或被改指向的链接有 **修复**，可以把它放回去（被篡改的链接会先被挪到 `~/.coffer/content/backup/skills/<agent>/<name>.coffer-backup-<timestamp>`，在智能体的技能目录之外，智能体不会加载它）；有文件夹挡住、主文件夹缺失和不在技能库中的文件夹则有 **查看…**，打开处理它的地方。技能的 **投递** 标签页有 **重新检查**，只针对该技能的副本做同样的事。

后三种需要一个 Coffer 不替你做的判断——两个文件夹留哪个、一个来路不明的文件夹是什么、丢失的主副本能在哪里找到——所以每一种还提供一段给智能体的提示词，在发现旁、对比对话框中、文件夹窗格上和主文件夹不见了的技能的横幅上都有 **交给 &lt;Agent&gt;**（菜单里有 **复制提示词**）。智能体负责查看并告诉你该按哪个按钮；它自己不移动、不删除、不编辑任何东西。同样的提示词也出现在总览的“需要你处理”列表中。

### 处理挡路的文件夹 {#resolve-a-folder-in-the-way}

当智能体的副本是一个真实的文件夹而不是 Coffer 的链接时——你或智能体用一份改过的副本替换了链接——技能会显示一条横幅，它的投递行提供 **查看…**。对话框会把该文件夹与主副本对比，给出两个选择，执行前都会确认：

| 选择 | 结果 |
| --- | --- |
| **换成 Coffer 的链接** | 先把该文件夹移到 `~/.coffer/content/backup/skills/<agent>/`，然后在原处链接主副本。什么都不会丢。 |
| **收编这个文件夹** | 它的文件成为主副本，所以其他每个智能体也会拿到它们；然后该文件夹同样被备份并换成链接。 |

diff 显示你没保留的那一边会发生什么。Coffer 从不自己做这个选择。拿不准留哪个？对话框里的提示词会让你的智能体对比该文件夹和主副本，并推荐二者之一。

### 不在技能库中的文件夹 {#folders-not-in-your-library}

`~/.coffer/vault/skills/` 中没有被任何技能认领的文件夹——手动拷进来的，或者被中断的导入留下的——不会投递给任何智能体。它列在 **不在技能库中** 下，显示其 `SKILL.md` 是否有效、包含多少个文件以及 Coffer 何时发现它。它的文件在和技能**文件** tab 相同的锁定文件树和查看器里打开，只读。**加入技能库…** 原地添加它，**在 Finder 中显示** 显示它，**删除文件夹…** 在询问后把它移到 `~/.coffer/content/backup/skills/orphans/`。窗格中的提示词会让你的智能体读一读这个文件夹，告诉你该选两者中的哪一个。

### 主文件夹不见了 {#when-the-master-folder-is-gone}

如果某个技能的主文件夹在 Coffer 之外被删除，技能会显示 **主文件夹不见了**。它页面上的横幅提供两条出路。**交给 &lt;Agent&gt;**（以及**复制提示词**）会给你的智能体一段提示词，让它去找一份副本——在 `~/.coffer/content/backup/skills/` 中、在某个智能体的技能文件夹中、在保险库的 git 历史里、或在技能的来源处——并在你同意后把它拷回 `~/.coffer/vault/skills/<name>/`；Coffer 在下一轮会再把它链接到你的智能体。**删除技能…** 则会删除它的记录和设置。

## 内置技能 `coffer-guide` {#the-built-in-coffer-guide-skill}

Coffer 自带一个技能 `coffer-guide`。它是智能体用好 Coffer 要读的说明书：

- Coffer 自己的 MCP 工具，以及各自在什么时候用。
- 没出现在智能体工具列表里的工具，仍然可以通过 `coffer__search_tools` 调用。
- [知识](/zh/guides/knowledge)：知识根目录在哪里、如何用智能体自己的文件工具读取、如何往里写入并整理，以及每个知识集中每篇文档的目录，附带路径、标题和描述。
- [记忆](/zh/guides/memory)：Coffer 读取智能体的记忆但从不写入；Coffer 的笔记是记忆根目录下的 Markdown，智能体用自己的文件工具 grep 它们。
- [命令行工具](/zh/guides/clis#what-your-agents-see)：`coffer cli list` 打印 Coffer 管理的命令行工具——每个是做什么的、谁需要它、在本机是否就绪。
- 没有任何 Coffer 工具会等待人工批准。

它的 frontmatter 描述写明了 Coffer 的工具和你各个知识集的主题（取自每个知识集的 `README.md`），让模型有具体的东西可以匹配。描述保持在 1024 个字符以内；知识集放不下时，会从末尾整条去掉主题。

除此之外它就是一个普通技能。它位于 `~/.coffer/derived/skills/coffer-guide/`，在 **技能** 页面上带 **内置** 标记，投递、生效范围、校验和修复都和导入的技能完全一样。

### 它会被重新生成，所以编辑保留不住 {#it-is-regenerated-so-edits-do-not-survive}

Coffer 在每次守护进程启动时、以及知识目录发生变化时（创建或删除知识集时，以及每次知识扫描时，以便读入手工添加的文档），都会根据正在运行的构建重写 `coffer-guide`。内容完全相同时跳过重写。因此：

- 它的文件在 Web 界面中是只读的。
- 你在磁盘上做的任何编辑都会在下一次重写时被替换。

这个技能不会随[保险库同步](/zh/guides/vault-sync)传播。每台机器根据自己的知识集和设置渲染自己的一份。

### 它不能被删除，但你可以控制它的生效范围 {#it-cannot-be-deleted-but-you-control-its-reach}

在任何入口删除 `coffer-guide` 都会以 `RESOURCE_PROTECTED` 被拒绝，因为下次启动时它又会被写回来。你能改的是谁拿到它：禁用它，或者收窄它的生效范围，和其他技能完全一样。

## 移除技能 {#remove-a-skill}

移除技能会删除所有已投递的链接，然后删除主文件夹和技能的记录。这次移除会连同技能配置的快照一起记入审计。

```text
Skills → the skill → ⋯ → Delete… → confirm "Delete release-checklist?"
```

::: danger 主文件夹是唯一的副本
移除技能会删除 `~/.coffer/vault/skills/<name>/`。Coffer 不保留你当初导入时的源文件夹。如果你想保留技能但停止投递，请改为禁用它，或把它的生效范围设为不给任何智能体。
:::

如果某个智能体的副本已经不是 Coffer 的链接（现在是一个普通文件夹），Coffer 不会删除它。删除会以“什么都没有删除”停下并写明那个文件夹；对话框随后提供**删除，保留 <智能体> 的文件夹**，也就是删除技能并把那个文件夹留给该智能体，或者你先取消、看一下改动（见[处理被文件夹挡住的链接](#resolve-a-folder-in-the-way)）。一次选中多个技能再点**删除…**，会逐个报告结果：对话框显示“已删除 N/M 个”，并指出被拒绝的那些，对其余的提供**删除 N 个技能，保留它们的文件夹**。

从 Coffer 中移除一个智能体，也会移除该智能体的技能链接。主文件夹保留。

## 工作原理 {#how-it-works}

每个技能都是 Coffer 注册表中的一个 `skill` 资源，由一个不可变的 uid 标识。它的名称注册后就固定，描述就是其 `SKILL.md` 的描述（见[技能名称与描述](#skill-names-and-descriptions)）。

Coffer 在内部记录中登记每个已投递的链接（链接路径、链接方式、链接时间）。磁盘上的链接是实时的真实状态；记录是 **检查副本** 拿来比对的依据。每次导入、投递、移除链接、移除技能和修复都会写入审计日志，你可以在[活动](/zh/guides/activity)页面查看。

Coffer 不通过 MCP 暴露任何技能工具。两个受支持的智能体都从磁盘读取技能，再加一条基于工具的路径会绕过每个技能的生效范围。

启用和生效范围背后的资源模型，见[资源框架](/zh/architecture/resource-framework)。

## 故障排查 {#troubleshooting}

**智能体看不到某个技能。** 检查技能是否已启用、其生效范围是否包含该智能体（技能的 **生效范围** 按钮）。然后用 **检查副本**，看它的链接是否缺失或被一个外来的文件夹挡住。

**从 Git 添加技能失败。** 对话框会显示 git 自己的报错信息。`could not read Username` 或 `Permission denied (publickey)` 表示这台机器的 git 没有该仓库的凭据：先在终端里确认 `git clone <url>` 能成功。不存在的 ref 或文件夹也会在信息中指出。

**压缩包被拒绝。** 信息会列出可能写到压缩包之外的条目、符号链接，或它会超出的大小上限。直接从技能的文件夹重新打一个压缩包。

**添加技能被拒绝。** 报错会指出文件夹违反了哪条规则；如果是 frontmatter 的问题，还会指出字段和未通过的检查（例如 `description: String should have at most 1024 characters`）。最常见的原因是 `name` 中有大写字母或点、`description` 缺失或过长，或文件夹内有指向外部的符号链接。

**技能显示“已复制”标记。** 智能体所在的文件系统不支持链接（只在 Windows 上会发生）。副本不会跟随主副本的编辑。编辑之后，触发一次新的投递，比如先禁用再重新启用该技能。

**检查副本报告 `replaced_with_regular`。** 有 Coffer 以外的东西在链接路径上放了一个真实的文件夹。自己把它挪开（想保留的话先纳入托管），然后在技能的 **投递** 标签页选择 **重新检查**。

## 相关 {#related}

- [知识](/zh/guides/knowledge)——`coffer-guide` 携带的目录
- [记忆](/zh/guides/memory)
- [智能体](/zh/guides/agents)
- [保险库同步](/zh/guides/vault-sync)
- [CLI 参考](/zh/reference/cli)
- [技能管理器规格](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/skill-manager/spec.md)
- [跨平台技能投递](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/cross-platform-skill-delivery.md) 和 [Coffer 以技能资源的形式发布自己的说明书](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/coffer-ships-its-own-skill.md)
