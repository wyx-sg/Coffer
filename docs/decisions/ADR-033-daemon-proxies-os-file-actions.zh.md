# ADR-033 — 本地 daemon 代理 OS 文件动作

> English: [ADR-033-daemon-proxies-os-file-actions.md](./ADR-033-daemon-proxies-os-file-actions.md)

- **状态:** Accepted
- **日期:** 2026-06-21
- **决策者:** Yuxing Wu
- **Spec:** [004-agent-registry](../../specs/004-agent-registry/spec.zh.md) 拥有 `/fs` 路由与共享 FileActions 操作栏(FR-038、新增 FR-039);并改动 [005](../../specs/005-skill-manager/spec.zh.md) FR-006 / 新增 FR-030，以及 [007](../../specs/007-memory/spec.zh.md) FR-020 / FR-021（知识层 spec，现同时拥有文档与条目两个界面）中的 open/reveal 回退条款 —— 不新增 spec 编号;`spec.md` 在实现前先更新。
- **取代:** 004 FR-009/FR-038、005 FR-006、006 FR-020、007 FR-021 中"web 端 open/reveal 回退到 copy-path"的立场。

## 背景

Coffer 的文件查看器是**只读**的(spec 002/004/005/006/007):用户在自己的编辑器里改,经由共享的 `FileActions` 操作栏把受管文件(或其所在文件夹)带到 OS —— **在外部编辑器打开**、**在文件管理器中显示**、**复制绝对路径**。

这些界面背后是两类不同的文件系统操作:

- **选取(Picking)** 一个输入路径 —— agent 的 `config_dir`(FR-023/FR-024)与"添加 Skill"的导入路径。界面经 daemon 驱动的文件夹浏览器(`GET /api/v1/fs/browse`)选取,返回绝对路径。
- **作用(Acting)** 于一个已有路径 —— 在编辑器打开 / 在文件管理器中显示。它此前被规定**回退到 copy-path**,前提是浏览器承载的界面根本够不到 OS。

这条回退基于一个前提 —— 006 FR-020 里写的 *"the daemon cannot act on the user's machine"*、以及 `FileActions.tsx` 里写的 *"a browser cannot touch the filesystem"*。浏览器那半句是对的;daemon 那半句对 **Coffer 的架构而言是错的**。Coffer daemon 是**仅环回**(`127.0.0.1`)+ token 守卫(FR-024)的,所以 web 客户端**永远与 daemon 同处用户自己的机器上**。一个本地 daemon 进程完全可以打开文件、在 OS 文件管理器中显示它(macOS `open` / `open -R`、Linux `xdg-open`、Windows `explorer /select`),与该机器上任何原生进程无异。浏览器的限制只约束浏览器**直接**执行的操作;而 Coffer 始终经由一个具备完整 OS 能力的本地 daemon 转发。

由此带来两个具体缺口:

1. 四个只读查看器(agent 配置文件、skill 文件、记忆 fact、KB 文档)只显示"复制路径",而非真正的 open/reveal —— 鉴于 daemon 就在本地,这是可避免的降级。
2. "添加 Skill"对话框从未获得 agent `config_dir` 对话框已有的文件夹选择器(FR-023/FR-024);它仍要求用户手敲绝对路径。

## 决策

**把 OS 文件动作经本地 daemon 转发,使浏览器承载的界面执行真正的 OS 动作。**

> **2026-09-09:** 本 ADR 原先还描述了第二条原生分支(打包桌面外壳内的
> `tauri-plugin-opener`)。该外壳已被移除,下面的 daemon 端点现在是唯一机制。

### 1. daemon FS-动作端点(FR-039)

daemon 在只读 `GET /fs/browse` 之外新增两个写侧兄弟端点,沿用同样的环回 + token 守卫:

- `POST /api/v1/fs/open` `{ path, with? }` —— 在某个应用里打开 `path`。`with` 是首选编辑器偏好(002-ui-shell);缺省时使用 OS 默认应用。同时服务于"在编辑器打开文件"和"在编辑器打开文件夹"。
- `POST /api/v1/fs/reveal` `{ path }` —— 在 OS 文件管理器中选中 / 显示 `path`。

两者在动作前都校验 `path` **为绝对路径且存在**,并以**参数向量**方式 shell-out(绝不用 shell 字符串 —— 无插值)。无法打开 / 不存在的路径返回错误,绝不做部分动作。

### 2. FileActions 执行真正的 open/reveal(FR-038 及并列 FR)

共享操作栏暴露一个 `useFsActions()` hook,提供 `open(path, with)` / `reveal(path)`,两者都由上面的 daemon 端点支撑。

首选编辑器值(前端 `localStorage` 设置 `coffer.preferredEditor`)经请求的 `with` 字段传入。操作栏显示完整按钮集 —— 在编辑器打开文件、在文件管理器中显示文件、在编辑器打开文件夹。

**copy-path 被删除。** 它原本只作为 open/reveal 跑不起来时的回退;如今 open/reveal 总能运行,它已无意义,且个人、本地优先的工具应保持界面最小。`copyPath` / `copyFolderPath` 动作及其 i18n 文案被删除,而非降级。

### 3. "添加 Skill"获得文件夹选择器(FR-030)

skill 导入对话框复用已有的 `FolderPicker`(daemon 驱动的文件夹浏览器 —— FR-023/FR-024)。文件夹是**选取**的,不是手敲的;解析出的绝对路径喂给不变的 `POST /skills/import`。

### 4. 选取(Picking)当时不在本次范围内 —— 该表态已退役

本 ADR 统一了 open/reveal 但没统一*选取*:当时 OS 原生目录对话框只在打包的原生外壳里可用,所以浏览器界面继续用内嵌的 daemon 文件夹浏览器。那个原生外壳已不复存在,而 daemon 现在自己会打开宿主的原生**目录**对话框(spec 004 FR-042)。它不代理选文件与存文件对话框:浏览器自带的 `<input type="file">` 与 `<a download>` 已经覆盖,且前者更好——它直接交出文件**内容**,而不是交一个还要 daemon 再去读的路径。文件夹是那个例外,因为浏览器刻意不给出绝对路径。

## 影响

- 真正的 open/reveal 现在覆盖全部四个只读查看器界面;`FileActions` 的消费方不变(它们本就传 `filePath` / `folderPath`)。
- 被改动的 FR 中移除了"daemon cannot act on the user's machine"这个错误前提;理由改为"环回 daemon 就在用户机器上,故代用户执行动作"。
- daemon 上新增 OS-动作面。缓解手段:环回 + token 守卫(与每条 daemon 路由一致)、绝对且存在的路径校验、参数向量 shell-out(无注入),以及 `GET /fs/browse` 本就以同等信任级别暴露了本地文件系统 —— 这里只是新增了"作用于"用户已导航到的路径,并非新的访问面。
- 跨平台的 reveal 在 Linux 上没有通用的"选中文件"原语;daemon 在该平台降级为打开所在文件夹。macOS(`open -R`)与 Windows(`explorer /select`)会选中条目。
- 与个人工具、本地优先的取向一致(ADR-/constitution):daemon 本就代用户执行本地文件系统工作;打开一个 UI 已经呈现的路径是无害的、单用户的。
