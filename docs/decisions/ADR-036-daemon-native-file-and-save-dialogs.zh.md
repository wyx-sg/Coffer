# ADR-036 — daemon 原生「选文件 / 存文件」对话框扩展选择器

> English: [ADR-036-daemon-native-file-and-save-dialogs.md](./ADR-036-daemon-native-file-and-save-dialogs.md)

- **状态：** 已接受
- **日期：** 2026-06-21
- **决策者：** Yuxing Wu
- **规格：** [004-agent-registry](../../specs/004-agent-registry/spec.md) 拥有 `/fs`
  路由，新增「选文件 / 存文件」选择器的 FR；[010-sync](../../specs/010-sync/spec.md)
  在「带外」主密钥传输里复用它们。不新建 spec 编号；`spec.md` 在实现前先更新。
- **取代：** [ADR-033](./ADR-033-daemon-proxies-os-file-actions.md) §4 的
  「选择器刻意保留双路径 / 不把选择器收敛到 daemon」表态。该表态在 ADR-033 之后
  发布的 `POST /fs/pick-folder` daemon 端点中其实已被推翻；本 ADR 把这个新方向
  写明，并把它从「文件夹」扩展到「文件」。

## 背景

ADR-033 把 OS 文件**动作**（打开 / 在文件管理器中显示）经环回 daemon 代理，让 Web
界面与桌面应用一致；但 §4 刻意把**选择**保留为双路径：桌面用 OS 原生目录对话框，
Web 用应用内 daemon 文件夹浏览器。其后的一次改动（`POST /fs/pick-folder`、
`FsPickService`）就文件夹而言已经打破了这一表态——Web 上 daemon 现在会打开宿主的
**原生**目录对话框（macOS 用 `osascript`，Linux 用 `zenity`/`kdialog`），仅当宿主
没有原生对话框工具时才退回应用内浏览器。

仍有一个缺口：**没有原生的「选文件」或「存文件」对话框**，只有「选文件夹」。因此
每个需要*文件*路径的地方，要么自己手搓一个仅限桌面的 Tauri 对话框，要么强迫用户把
绝对路径打进文本框。最显眼的是「带外」主密钥卡片（spec 010）：Web 上它显示一个原始
的 `/path/to/coffer-master.key` 输入框，导入/导出按钮就对用户手打的内容操作。手打
绝对路径，正是当初引入文件夹选择器要消除的摩擦。

## 决策

**把 daemon 选择器从文件夹扩展到文件：新增原生「选文件」与「存文件」对话框，沿用与
文件夹选择器相同的调用方式。**

### 1. 两个新的 daemon 端点（spec 004）

`FsPickService` 新增 `pick_folder` 的两个兄弟方法，沿用同样的环回 + token 守卫，
各自在 `asyncio.to_thread` 中执行（对话框是模态、会阻塞）：

- `POST /api/v1/fs/pick-file` `{ start? }` —— 打开宿主原生**选文件**对话框，返回
  所选文件的绝对路径。
- `POST /api/v1/fs/save-file` `{ suggested_name?, start? }` —— 打开宿主原生**存
  文件**对话框（带建议文件名），返回所选的目标路径。

两者复用既有的三态契约，以 `{ available, path }` 返回：

- `available=false` —— 宿主没有原生对话框工具（Windows 没有纯 argv 的对话框；
  Linux 缺 `zenity`/`kdialog`）。调用方退回手输路径。
- `available=true, path=null` —— 对话框已打开，用户取消。
- `available=true, path="…"` —— 用户选定了路径。

机制与 `pick_folder` 一致：macOS 用 `osascript`（`choose file` /
`choose file name`），Linux 用 `zenity --file-selection [--save --confirm-overwrite]`
再到 `kdialog --getopenfilename` / `--getsavefilename`。对话框始终以**参数向量**
调用（绝不用 shell 字符串）；macOS 上起始目录与建议文件名会被转义进 AppleScript
字符串字面量。

### 2. 共享的前端文件选择器助手

`lib/filePicker.ts` 暴露 `pickOpenFile(start?)` 与
`pickSaveFile(suggestedName, start?)`，各自返回 `{ path, unavailable }`。桌面走
Tauri 的 `open`/`save` 对话框；Web 走新的 daemon 端点；仅当 daemon 报告无原生工具
（或调用出错）时 `unavailable` 才为真，调用方据此显示手输回退。

### 3. 选择全面原生优先；手输仅作最后回退

Web 主密钥卡片默认不再显示路径框。导入打开原生「选文件」对话框，导出打开原生「存
文件」对话框。手输的 `keyPath` 框**仅在**某次选择返回 `unavailable` 后才出现——在
macOS 上永不出现。既有三处「文件夹 + 文本框」（技能导入、Agent `config_dir` ×2）
去掉并排的原始文本框，改为只读显示所选路径 + `FolderPicker` 按钮（其自身的 Web 回退
是应用内浏览器，从不要求打字）。

## 影响

- Web 界面选文件的方式与它已有的选文件夹方式一致；桌面 Tauri 路径不变。手输路径仅
  在没有原生对话框的宿主上作为降级回退保留。
- daemon 新增的 OS 表面很小、有界：对话框只*返回*用户选定的路径——不创建、不打开
  任何东西。信任级别与既有的 `pick-folder` / `browse` 路由相同（环回 + token +
  参数向量调用）。
- ADR-033 §4 的「刻意双路径」就此退役。Web 上选择器对文件夹与文件都已是 daemon
  原生；应用内文件夹浏览器仅作为文件夹的「无原生工具」回退保留。
- macOS 与（装有 `zenity`/`kdialog` 的）Linux 处处都有真对话框；Windows 与精简
  Linux 宿主降级为手输路径——与文件夹选择器已记录的降级方式相同。
