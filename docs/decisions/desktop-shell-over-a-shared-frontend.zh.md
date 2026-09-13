# 桌面壳回归，只负责浏览器做不到的事

> English: [desktop-shell-over-a-shared-frontend.md](./desktop-shell-over-a-shared-frontend.md)

- **状态：** Proposed
- **日期：** 2026-09-12
- **决策者：** Yuxing Wu
- **规格：** [mcp-gateway](../../specs/mcp-gateway/spec.zh.md) FR-024 / FR-028 / FR-029 … FR-032
- **部分推翻：** roadmap 于 2026-09-09 记下的「桌面壳」explicit non-goal
- **相关：** [daemon 把 token 服务在页面里](./daemon-serves-the-token-in-the-page.zh.md)（本 ADR 修订它——它那句「不存在第三种情况」现在有了第三种）、[detect-or-spawn](./daemon-detect-or-spawn.zh.md)、[PyInstaller 分发](./distribution-pyinstaller.zh.md)、[daemon 代理操作系统文件动作](./daemon-proxies-os-file-actions.zh.md)

## 背景

Tauri 壳于 2026-09-09 退役。当时的理由是运维成本，而且这个理由站得住：每次桌面更新都意味着重新构建**加上**重新安装，而构建产物反复和源码漂移——有两次记录在案，一次是在 fetch 之前构建，跑的是旧代码；一次是单独钉住的构建目录，导致 UI 缺陷报告必须先对着 `main` 复核过才能采信。

退役没有称量的，是壳同时也是唯一让 Coffer **能被找到**的东西。三个月的 daemon 直供 Web UI，把缺了它的代价暴露了出来：

- **找不到它。** Coffer 只是几十个标签页里的一个 `127.0.0.1`，没有 Dock 图标，Cmd-Tab 里没有，也没有任何常驻的东西可点。每次访问都从翻标签页或重敲端口开始。
- **不开终端就起不来。** 想看到 UI，得知道 daemon 在不在跑、在哪个端口、以及 `coffer open` 这条命令能同时回答这两件事。对一个正在终端里干活的 CLI 用户，这是合理的要求；对一个只想看看自己 vault 的人，这不合理。
- **它不像个产品。** Coffer 同时是个 portfolio 项目。一个只能从终端命令打开的 localhost 页面，展示得出架构，展示不出东西本身。

这三条都不构成「撤销退役」的理由。它们构成的是「做一个**只**解决这三个问题的壳」的理由——而那是一个比被删掉的那个小得多的壳，因为中间这三个月已经把它大部分工作挪到了更合适的地方：

- 二进制部署搬进了 daemon 自己的 frozen-start 路径（FR-026）。
- 原生选文件夹、用用户的编辑器打开文件、在 Finder 里显示，全都搬到了 daemon 的 HTTP 路由上（[daemon 代理操作系统文件动作](./daemon-proxies-os-file-actions.zh.md)）——而这些在 webview 里原样工作，因为 webview 向 loopback 发 HTTP 请求和浏览器标签页没有区别。

所以壳回来时，两项最大的职责已经有人替它扛了；同时它要面对一个原来那个壳从未有过的约束：**同一份前端构建产物，现在必须同时服务浏览器和原生窗口。**

## 决策

**把 Tauri 壳恢复为现有前端之上的原生宿主，只负责浏览器无法自理的四件事**：一个带 Dock 图标的窗口、一个常驻托盘、启动时的 daemon detect-or-spawn，以及本地页面无从获得的凭据握手。

### 壳承载 UI，不重新实现 UI

`tauri.conf.json` 保留 `frontendDist: ../frontend/dist`。窗口把构建好的 SPA 作为本地 asset 加载，而**不是**加载 `http://127.0.0.1:<port>/`。这正是「原生 app」区别于「加了书签的浏览器窗口」之处：daemon 还没应答，UI 就已经在了，所以一个慢的、不在的或卡住的 daemon，给出的是一张渲染完整、带可操作横幅的页面，而不是一个连接错误。

这也意味着端口对 UI 是不可见的。只有 API 调用带端口，而壳从 `~/.coffer/daemon.json` 里读——和其他所有客户端读的是同一个文件。

### 前端多一个宿主，不是多一条分支

页面是本地 asset，所以没有人往里注入过 token。浏览器那套机制（FR-025）用不上，壳改用一个 IPC 命令提供同样的两个全局变量：

```
浏览器  → daemon 把 window.__COFFER_TOKEN__ 注入 index.html   （FR-025）
Tauri   → 壳 invoke get_daemon_info → setDaemonConnection(...) （FR-030）
```

动三个文件：`lib/tauri.ts` 回来，`lib/auth.ts` 加回 `setDaemonConnection`，`main.tsx` 在 `isTauri()` 时**发起**握手——与首次渲染并行，绝不在它之前。阻塞会推翻上一段：没有 daemon 在跑时这次握手要拉起一个并轮询，于是重启后的一次启动会有大半时间对着空窗口。先渲染意味着立刻看到真正的应用，由横幅解释这段空档，而那些未带凭据发出的请求会在握手落地后被重新拉取。`getCofferBaseUrl` / `getCofferToken` 一行不动——两个宿主收敛到同样的全局变量上，这正是它之所以是第二个**供给者**而不是第二条**路径**的原因。

其余一概不分叉。尤其是 2026-09-09 删掉的 Tauri `dialog` / `opener` 插件分支**继续保持删除**：`filePicker.ts`、`fsActions.ts`、`FileActions.tsx`、`FolderPicker.tsx` 在两个宿主里都走 daemon。把它们还原回来，等于重建那套让前端改不动的 `isTauri()` 分叉，换来的是用户完全感知不到的东西。

有两个能力因为「页面是本地的」而重新变得有意义，两者都以 `isTauri()` 门控：

- **离线横幅上的重启按钮。** 在浏览器里这不可能——daemon 挂了，就没法供出那张承载按钮的页面。在壳里页面本来就在，而壳能拉起 daemon。
- **daemon 版本偏斜检查。** app 和一个 daemon 配对；上一版留下的 daemon 可能还在监听。浏览器没有这种配对关系。

### daemon 默认绑定固定端口

FR-028 把端口做成了可配置项，默认行为是扫描 8000–8009。默认反过来：**daemon 绑 8000，绑不上就拒绝启动**，并指名是哪个进程占着——这套机制 FR-028 已经为它的「已配置端口」路径写好了。

扫描一直是个少数派选择。带 Web UI 的本地服务都是固定一个默认端口并允许修改——Ollama、Syncthing、Grafana、Home Assistant、Tailscale；而会往后扫的那些（Jupyter、Vite）是开发工具，每次启动都把真实 URL 打出来，也没人给它们存书签。漂移的 origin 代价比坏掉的书签更大：浏览器 `localStorage` 是按 origin 隔离的，端口一变，界面语言、侧边栏状态、分页大小、首选编辑器就静默重置，而用户不会把这两件事联系起来。

设置 → 通用里的「网页地址」卡片和 `GET`/`PUT /settings/daemon` 一并删除。一个默认就正确的端口不值得占一块面板；退路放在诊断端口冲突的地方更合适——`coffer daemon port set/clear`，它在没有 daemon 运行时也能用。

### app 是一个自包含的安装包，装了它就等于装了 CLI

`.app` 以 Tauri `externalBin` 的形式打包四个 frozen 二进制——`coffer`、`coffer-daemon`、`coffer-mcp-shim`、`coffer-callback`——并且构建产出 `.dmg`。下载、拖进 Applications、双击，不需要别的；「桌面 app」要值得存在，就必须是这个意思。

旧壳还打包过的 `coffer-hook` 和 `whisper-cli` 不在这个清单里。两者都在这几个月里退役了——SessionStart hook 随最后一批「写入原生配置」的动作一起去掉，语音转写在它搬离本机时去掉——所以这是一个严格小于被删掉那个的包。

壳解析 daemon 走五级链路：`daemon.json` 指出的在跑的 daemon、自己的包内、`~/.coffer/bin/`、`$PATH`、再不行就提示安装 CLI。存活探测排在第一位，而这个位置是正确性而非偏好——第二到第四级回答的都是同一个问题「要 spawn 哪个可执行文件」，第一级回答的是另一个问题「到底要不要 spawn」。顺序反过来，打包版就会在用户已从 CLI 启动的 daemon 旁边再开一个；在固定端口默认之下那个后来者绑不上端口，于是一个本该直接接管的 app 反而报出端口冲突。打包让第二级从「死的」变成寻找可执行文件的常规路径；其余几级留作包内 sidecar 缺失或跑不起来时的退路。

**装了 app 也就装了 CLI**，而壳什么都不用做。daemon 在 frozen start 时会把自己的兄弟二进制——四个全部，包括 `coffer` 本身——部署进 `~/.coffer/bin/`（FR-026），所以 app 第一次启动就把命令行工具留在了磁盘上，用户只需把那个目录加进 `PATH`。这正是 Ollama、Docker Desktop、Tailscale 共用的那套安排：一个可安装的 app，CLI 从它里面链出来，而不是必须先装 CLI。

代价是构建时间。`make desktop` 现在要先为四个二进制跑 PyInstaller 再跑 Tauri——量级在一小时上下——而一个不打包的壳只要几分钟。这正是 2026-09-09 退役时反对的那项运维成本，这次是有意接受的，并且被这样一个事实所限制：只有发布才需要完整构建。

它也继承了 Coffer 在 macOS 上的老问题：二进制未签名，所以浏览器下载的 `.dmg` 带着 `com.apple.quarantine`，macOS 会在双击时以「Coffer 已损坏」拒绝它，只能从系统设置里救回来。发布说明和 README 必须把清除 quarantine 的那一步放在和 CLI 压缩包同等显眼的位置。公证仍是文档记录在案的 non-goal，前提是一个付费 Apple Developer 账号——而它现在成了那个账号所能买到的、价值最高的一件东西。

## 后果

- **两个宿主，一份构建。** `frontend/dist` 同时被 daemon 的静态挂载和 Tauri 包消费。任何 UI 改动同时到达两者；两者不可能互相漂移，因为只有一个产物。
- **退役时担心的失效模式被收窄了，没有消失。** 一个陈旧的 `.app` 仍然可能装着一份陈旧的 `frontend/dist`。但它现在被限制在 UI 这一层——daemon、shim、辅助二进制都不随 app 走——而版本偏斜检查让 daemon 那一半可见。这是实打实的代价，为了「能被找到」而接受。
- **[daemon 把 token 服务在页面里](./daemon-serves-the-token-in-the-page.zh.md) 多了第三种情况。** 它那条「不是由 daemon 供出的浏览器就没有 token……不存在第三种情况」在写下时是对的。壳就是第三种，它通过 IPC 而非文档供给 token。那份 ADR 是被**修订**而非被推翻：注入仍然是**浏览器**取得凭据的方式，让它安全的 `Host` 守卫也原封不动。
- **书签重新可用，浏览器里存的偏好也是。** 两者都来自固定端口，而且都归属于壳并不取代的那个 Web 宿主。
- **端口冲突现在是一次启动失败，而不是一次静默迁移。** 诊断会指名占用者和修复命令，但在用户处理之前 daemon 不会起来。这是刻意的取舍：一个可预测的 origin 比一个自动的 origin 更值钱。
- **发布重新长出第二个产物层，而且几乎是免费的。** FR-022 曾把发布收成单一的 `coffer-cli-<triple>.tar.gz`，现在 `.dmg` 加入它。昂贵的那一半——为四个二进制跑 PyInstaller——是发布任务为 CLI 压缩包本来就要做的事，所以桌面层复用那批产物，只多一次 Tauri 构建。那一小时的代价是**本地** `make desktop` 的代价，不是发布的代价。
- **Rust 重新进入构建，而它的测试不在 `make verify` 里。** `cargo` 仅作为 `make desktop` 和发布的桌面环节的前置条件回归；没有任何验证门禁要长出工具链。代价是 `tray.rs` 的关闭到托盘判定、`daemon.rs` 的限流与端口解析辅助函数——它们当初被写成纯函数正是为了可单测——由一组没有任何门禁会跑的 `cargo test` 覆盖。有工具链的人可以用 `make desktop-test` 跑到它们。接受这一点，是因为壳很小、很少改动，而且改坏了也伤不到 daemon 和 Web 宿主；如果它开始积累逻辑，就该重新评估。

## 备选方案

- **一个加载 `http://127.0.0.1:<port>/` 的薄壳。** 否决。它是成本最低的壳，而且彻底消解了漂移风险；但那样窗口就是一个指向 daemon 的浏览器：daemon 应答之前什么都渲染不出来，重启后换了端口会留下一张死页面直到壳重新导航，而且 Tauri 的 IPC 在未显式配置逐域能力的情况下对远程 origin 不可用。「能被找到」的问题会被解决，「该像个产品」的那个不会。
- **整体 revert PR #317。** 否决。它删掉的东西里大约一半，此后已被在两个宿主里都能工作的 daemon HTTP 路由取代；还原 Tauri `dialog` / `opener` 分支等于为零用户可见收益重建 `isTauri()` 分叉，还原壳的二进制部署则会让两个进程抢着写 `~/.coffer/bin/`。
- **保留 8000–8009 扫描，靠壳兜底。** 否决。它对桌面宿主是可行的（壳从文件里读端口），而它会继续默默惩罚那个壳明确不取代的浏览器宿主——坏掉的书签，和重置的偏好。
- **不打包二进制，把 app 定位成「已装 CLI 之上的可选层」。** 否决。它构建只要几分钟而不是一小时，而且绕开了 Gatekeeper——`curl | sh` 下载的文件不带 quarantine 属性，装完直接能跑，未签名的 `.dmg` 做不到。但一个「你得先会用终端才跑得起来」的 app，根本没有回答壳之所以被恢复的那个理由：够到 Coffer 不应该以「知道 daemon 是什么」为前提。清除 quarantine 是一条写在文档里的命令；必须先装 CLI 则是一个永久的第二个产品。
