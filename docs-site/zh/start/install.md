---
title: 安装
description: 通过一行安装脚本、macOS 桌面应用、发布压缩包或源码安装 Coffer，然后验证、启动、升级或卸载。
---

# 安装 {#install}

本页介绍安装 Coffer 的所有受支持方式、每种方式会在磁盘上放什么，以及如何验证、升级和卸载。如果你只想尽快用起来，可以[让你的智能体来安装](#let-your-agent-install-it)，或者运行一行安装脚本，然后接着看[快速上手](/zh/start/quickstart)。

::: warning 还没有打过标签的发布版本
一行安装脚本、桌面 `.dmg` 和发布压缩包都从打过标签的 GitHub 发布版本下载。在第一个 `v*` 标签发布之前，这些下载都会返回 404。目前请[从源码安装](#from-source)。
:::

## 让你的智能体来安装 {#let-your-agent-install-it}

如果你已经在用某个编程智能体（Claude Code、Codex，或任何能在你机器上运行命令的智能体），把下面这段提示词粘贴给它：

```text
Install Coffer on this machine by following
https://wyx-sg.github.io/Coffer/start/install — pick the install path that fits
this machine (a release build if one is published for this OS and architecture,
otherwise from source). Ask me before running anything with sudo or editing my
shell profile. When it is installed, check it with `coffer daemon status`.
Then, for each coding agent installed here (claude-code, codex), run
`coffer agent add <type>` and `coffer agent connect <type>`, telling me which
config files connect will change before you run it. Do not handle any
credentials: if a step needs a login, tell me what to do instead.
```

智能体会读这个页面，选出适合你机器的安装方式并检查结果；凡是要动 Coffer 自身目录以外的东西，都会先问你。Coffer 从不让智能体处理凭据，所以任何登录都由你自己完成。本页其余部分就是智能体要遵循的步骤，也是你手动安装时要遵循的步骤。

## 选择安装方式 {#choose-an-install-path}

| 方式 | 适合 | 你会得到 |
| --- | --- | --- |
| [一行安装脚本](#one-line-installer) | 在 Mac 上用终端的人 | `~/.coffer/bin` 里的 `coffer`、`coffer-daemon`、`coffer-mcp-shim` |
| [桌面应用](#desktop-app) | 喜欢窗口和菜单栏图标的人 | `Coffer.app`，首次打开后还有同样的三个二进制 |
| [发布压缩包](#release-archive) | 手动安装，或没有图形界面的机器 | 同样的三个二进制，解压到你选的位置 |
| [从源码](#from-source) | 贡献者、Linux 用户，以及想跟进 `main` 的人 | 一套 Python 安装，`PATH` 上有 `coffer` 和 `coffer-mcp-shim` |

预编译二进制只面向 **Apple 芯片（arm64）的 macOS**。Intel Mac、Linux 和 Windows 没有发布构建，在这些机器上请从源码安装（Python 3.12 或更高版本）。

每种方式装的都是完整的 Coffer。Web 界面由守护进程自己提供，所以装了 CLI 也就有了界面（`coffer open`），装了桌面应用也就有了 CLI。

## 一行安装脚本 {#one-line-installer}

```sh
curl -fsSL --proto '=https' --tlsv1.2 https://wyx-sg.github.io/Coffer/install.sh | sh
```

这个脚本会：

1. 检查你是否在 macOS arm64 上。其他操作系统或架构会报错退出，并提示你从源码安装。
2. 从 GitHub Releases 下载 `coffer-cli-aarch64-apple-darwin.tar.gz` 和该版本的 `SHA256SUMS`，然后校验压缩包的校验和。校验和不匹配，脚本就会停止。
3. 把 `coffer`、`coffer-daemon` 和 `coffer-mcp-shim` 装进安装目录。每个二进制先复制成旁边的一个临时名字，加上可执行权限，再重命名覆盖公开名字。所以当这个名字是指向某个版本目录的符号链接时（一旦从别处启动的守护进程，比如桌面应用，把它的构建部署到那里，就会是这样），被替换的是链接本身，上一个版本的二进制原样保留，可用于回滚。
4. 如果该目录还不在你的 `PATH` 上，就往你的 shell 配置文件追加一行。配置文件取决于你的 shell：zsh 是 `~/.zshrc`（或 `$ZDOTDIR/.zshrc`），macOS 上的 bash 是 `~/.bash_profile`，fish 是 `~/.config/fish/config.fish`（以 `fish_add_path` 的形式），其他 shell 是 `~/.profile`。再次运行脚本不会重复添加这一行。

打开一个新 shell，或者 `source` 脚本提到的配置文件，让 `coffer` 出现在 `PATH` 上。脚本最后会建议你运行两条连接 Claude Code 的命令：

```sh
coffer agent add claude-code
coffer agent connect claude-code
```

它们做了什么，见[快速上手](/zh/start/quickstart)。

### 安装脚本选项 {#installer-options}

为 `sh` 进程设置这些环境变量：

| 变量 | 默认值 | 作用 |
| --- | --- | --- |
| `COFFER_INSTALL_DIR` | `~/.coffer/bin` | 三个二进制复制到哪里。 |
| `COFFER_VERSION` | 最新发布版本 | 安装指定的标签，比如 `v<version>`。不带开头 `v` 的版本号也可以。 |
| `COFFER_NO_MODIFY_PATH` | 未设置 | 设为 `1` 则不改动你的 shell 配置文件，脚本会改为打印需要添加的那一行。 |

```sh
curl -fsSL --proto '=https' --tlsv1.2 https://wyx-sg.github.io/Coffer/install.sh \
  | COFFER_VERSION=v<version> COFFER_NO_MODIFY_PATH=1 sh
```

用 `curl` 安装的二进制不会被加上隔离标记，所以 macOS Gatekeeper 不会拦它。

## 桌面应用 {#desktop-app}

1. 从 [Releases](https://github.com/wyx-sg/Coffer/releases/latest) 下载 `.dmg`。经过签名和公证的正式版名为 `Coffer-aarch64-apple-darwin.dmg`；没有代码签名的构建会在名字里注明，即 `Coffer-unsigned-aarch64-apple-darwin.dmg`。
2. 打开 `.dmg`，把 **Coffer** 拖到**应用程序**。
3. 仅限未签名的构建：对于从浏览器下载的副本，macOS 会拒绝打开并提示 "Coffer is damaged and can't be opened"。应用并没有损坏。清除隔离标记后再打开即可：

   ```sh
   xattr -dr com.apple.quarantine /Applications/Coffer.app
   ```

4. 打开 Coffer。应用会找到正在运行的守护进程，或启动它内置的那个，并在原生窗口里显示界面。关闭窗口后，菜单栏图标会留着。

应用内置了和发布压缩包相同的三个二进制。它的守护进程第一次启动时，会把它们复制到 `~/.coffer/bin`。如果还想用 CLI，把这个目录加到你的 `PATH`：

```sh
export PATH="$HOME/.coffer/bin:$PATH"   # add to your shell profile
```

菜单栏、更新、重启和离线横幅见[桌面应用](/zh/guides/desktop-app)。

## 发布压缩包 {#release-archive}

每个发布版本都会发布 `coffer-cli-aarch64-apple-darwin.tar.gz`，以及一个覆盖该版本所有文件的 `SHA256SUMS` 文件。

```sh
shasum -a 256 -c SHA256SUMS --ignore-missing   # verify what you downloaded
mkdir -p ~/.coffer/bin
tar -xzf coffer-cli-aarch64-apple-darwin.tar.gz -C ~/.coffer/bin
export PATH="$HOME/.coffer/bin:$PATH"          # add to your shell profile
```

三个二进制要放在同一个目录里。`coffer` 和 `coffer-mcp-shim` 需要启动守护进程时，会在自己旁边找 `coffer-daemon`。如果你是用浏览器下载的压缩包，用 `xattr -dr com.apple.quarantine ~/.coffer/bin` 清除隔离标记。

## 从源码 {#from-source}

你需要 Python 3.12 或更高版本，以及 git。构建 Web 界面需要 Node.js，另外推荐安装 [ripgrep](https://github.com/BurntSushi/ripgrep)（`rg`）。知识整理用 `rg` 挑选候选文档；没有它时会退回到较慢的内置搜索。

```sh
git clone https://github.com/wyx-sg/Coffer.git
cd Coffer
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ./backend
```

`pip install` 会在 venv 的 `PATH` 上放两个命令行脚本：`coffer` 和 `coffer-mcp-shim`。源码安装没有单独的 `coffer-daemon` 二进制，CLI 和 shim 会用同一个 Python 环境启动守护进程。

先构建一次 Web 界面，让守护进程有东西可以提供。不构建的话，API 和 MCP 端点照样能用，只是 `coffer open` 没有页面可打开。

```sh
cd frontend && npm install && npm run build && cd ..
```

::: tip 贡献者环境
`make install` 会创建 `.venv`，安装带开发依赖的后端，并安装前端的 npm 依赖。然后 `make dev` 会在 8000 端口运行守护进程，在 5173 端口运行带热重载的 Vite 开发服务器。见[开发环境搭建](/zh/contributing/development)。
:::

### 从源码构建冻结二进制和应用 {#frozen-binaries-and-the-app-from-source}

| 命令 | 产出 |
| --- | --- |
| `make bundle-binaries` | 用 PyInstaller 冻结到 `dist/` 的 `coffer`、`coffer-daemon` 和 `coffer-mcp-shim`，布局与发布压缩包相同 |
| `make desktop` | `Coffer.app` 和一个未签名的 `.dmg`。需要 Rust 工具链和 Node.js，由于要先跑 PyInstaller，大约需要 50 分钟。 |

## 各文件装在哪里 {#what-gets-installed-where}

| 路径 | 是什么 |
| --- | --- |
| `~/.coffer/bin/coffer`、`coffer-daemon`、`coffer-mcp-shim` | 公开名字。发布构建中它们是指向某个版本目录的符号链接。 |
| `~/.coffer/bin/<version>/` | 每个已部署的构建一个目录。当前版本和上一个版本都会保留，所以把链接指回旧目录就能回滚。 |
| `~/.coffer/vault/` | 保险库：一个 git 仓库，存放资源文件、技能、知识、记忆触发器和加密后的密钥。 |
| `~/.coffer/local/` | 只对本机成立的设置：智能体、生效范围、保留策略、同步远端。 |
| `~/.coffer/runs.db` | 历史数据库：审计日志、调用记录、对话、同步轮次、用量。 |
| `~/.coffer/runs.db.pre-<revision>` | 每次 schema 迁移前做的副本。保留最新的三份。 |
| `~/.coffer/master.key` | 密钥的主密钥（权限 `0600`），除非你把它移到了钥匙串。 |
| `~/.coffer/daemon.json` | 运行时发现文件：PID、端口和 API 令牌（权限 `0600`）。启动时写入，退出时删除。 |
| `~/.coffer/daemon-config.json` | 守护进程启动前读取的设置：固定端口、机器名、各实验功能开关。 |
| `~/.coffer/content/`、`~/.coffer/derived/` | 媒体文件和聊天工作目录；以及 Coffer 可重建的状态，比如记忆树。 |
| `~/.coffer/logs/daemon.log` | 守护进程日志，由守护进程、它的子进程和桌面应用共用。 |

发布构建的守护进程会自己管理 `~/.coffer/bin`。每次启动时，它都会检查自己的构建是否已经部署在那里。如果没有，就把三个二进制复制到 `~/.coffer/bin/<version>/`，并以一次原子操作把公开符号链接切换过去。源码安装从不这样做。[文件与目录](/zh/reference/filesystem)参考列出了每一个路径。

## 验证安装 {#verify-the-install}

```sh
coffer daemon start
coffer daemon status
```

```text
status:  ready
version: 0.2.0
port:    8000
pid:     48213
```

你的版本号和 PID 会不一样。然后打开界面：

```sh
coffer open
```

`coffer open` 读取 `~/.coffer/daemon.json`，在浏览器里打开 `http://127.0.0.1:8000/`。它加载的页面已经带上了 API 令牌，所以不用任何额外步骤就处于登录状态。加上 `--no-browser` 则只打印 URL。

## 启动并保持守护进程运行 {#start-and-keep-the-daemon-running}

你很少需要自己启动守护进程：

- 任何需要守护进程的 `coffer` 命令，在守护进程没运行时都会启动它。
- 智能体开始会话时，`coffer-mcp-shim` 也会这样做。
- 桌面应用在启动时会启动它。

守护进程一旦启动，就会一直运行，直到你停止它或者另一个守护进程取代它。如果想让 macOS 在登录时启动它、崩溃后自动重启，就安装登录服务：

```sh
coffer daemon service install    # coffer daemon service status | uninstall
```

守护进程绑定 `127.0.0.1:8000`。如果有别的程序已经占用了这个端口，守护进程会拒绝启动，并说出占用端口的程序。你可以用 `coffer config set daemon.port <port>` 换端口，用 `coffer config unset daemon.port` 改回去。见[运行守护进程](/zh/guides/daemon)。

## 升级 {#upgrade}

::: code-group

```sh [Installer]
curl -fsSL --proto '=https' --tlsv1.2 https://wyx-sg.github.io/Coffer/install.sh | sh
coffer daemon restart
```

```sh [Source]
git pull
source .venv/bin/activate && pip install -e ./backend
(cd frontend && npm install && npm run build)
coffer daemon restart
```

:::

在浏览器里，**设置 › 关于**会把这次升级做成一段给智能体的提示词，并写明当前运行的版本和这份副本的安装方式。

对于桌面应用：退出 Coffer，用 `coffer daemon stop` 停掉守护进程，用新版本替换 `Coffer.app`，再清除一次它的隔离标记。下次启动时会运行新的守护进程，由它部署新的二进制。

重启很重要，因为已经在运行的守护进程会继续跑旧版本。当 CLI 或 shim 发现守护进程的版本和自己不同时，会在 stderr 上打印一行警告，写明守护进程的可执行文件。新构建在执行 schema 迁移之前，会先保存 `runs.db.pre-<revision>`。如果你的 Coffer 还把状态存在 `coffer.db` 里，升级需要你自己运行一次性的步骤：见[升级已有的 Coffer](/zh/guides/upgrading)。

## 卸载 {#uninstall}

1. 把每个智能体和 Coffer 断开连接（这会从它的配置中删掉 Coffer 的条目），再从 Coffer 中移除该智能体。移除智能体时，Coffer 投递给它的技能链接也会一并删除：

   ```sh
   coffer agent disconnect claude-code
   coffer agent rm claude-code
   ```

2. 停止守护进程；如果装过登录服务，也把它移除：

   ```sh
   coffer daemon service uninstall
   coffer daemon stop
   ```

3. 删除二进制：`rm -r ~/.coffer/bin`。从你的 shell 配置文件里删掉 `# Added by Coffer installer` 这一行及其后的 `PATH` 行。对于桌面应用，把 `Coffer.app` 从**应用程序**移到废纸篓。
4. 如有需要，删除保险库本身。

::: danger 删除 ~/.coffer 不可恢复
`~/.coffer` 里有你的数据库、知识集、技能库和密钥的主密钥。删除它会销毁所有已保存的密钥，以及只存在于那里的所有文档。如果以后可能还要用，先把它复制到别处。
:::

## 实验功能 {#experimental-features}

每个构建都带有同样的能力。其中四项属于实验功能——知识、记忆、同步和模型提供商——无论稳定版还是源码构建，一开始都是关闭的。在设置 → 功能中，或用 `coffer config set feature.<key> on` 开启。见[实验功能](/zh/guides/experimental-features)。

## 下一步 {#next-steps}

- [快速上手](/zh/start/quickstart)：连接 Claude Code，注册你的第一个 MCP 服务器。
- [运行守护进程](/zh/guides/daemon)
- [分发与发布](/zh/architecture/distribution)
- [故障排查](/zh/guides/troubleshooting)
