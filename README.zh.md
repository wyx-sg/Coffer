# Coffer

<p align="center">
  <a href="./README.md">English</a> · <b>简体中文</b>
</p>

<p align="center">
  <a href="https://wyx-sg.github.io/Coffer/"><img alt="文档" src="https://img.shields.io/badge/%E6%96%87%E6%A1%A3-coffer-C96442"></a>
  <a href="./LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-blue"></a>
  <img alt="Python ≥3.12" src="https://img.shields.io/badge/python-%E2%89%A53.12-3776AB?logo=python&logoColor=white">
  <img alt="Claude Code 兼容" src="https://img.shields.io/badge/Claude%20Code-%E5%85%BC%E5%AE%B9-C96442">
  <img alt="平台" src="https://img.shields.io/badge/%E5%B9%B3%E5%8F%B0-macOS-555">
</p>

> 本地优先 (local-first) 的 AI agent 保险库。一个地方统一管理你的 AI agent 所触及的一切。

Coffer 是一个守护进程 (daemon) + CLI + 桌面应用，它为你机器上的每个 AI agent 提供一个安全、共享的统一接口。所有状态都保存在你自己的机器上 —— 没有云账号，没有厂商锁定。Coffer 管理的每一类东西都是一种 **resource kind**：

- **MCP 服务器** —— 把上游 (upstream) MCP 服务器聚合起来，再通过一个统一、带命名空间的接口重新暴露给各类 MCP 客户端（Claude Code、Codex）。配置一次，所有客户端看到的工具完全一致。
- **Agents** —— 检测并注册你本地的 AI 编码 agent、在应用内编辑它们的配置文件，并一键把 Coffer 自己的 MCP 服务器安装到任意 agent 中。
- **Skills** —— 维护一个 agent skill 包的主库，把它们投递到一个或多个 agent 的 skill 目录，并做漂移 (drift) 校正。
- **知识库 (Knowledge base)** —— 放入任意格式的文档（自动转换为 markdown），让 agent 通过 grep / 关键词 / 向量检索取用。
- **Memory** —— 一个跨 agent（Claude / Codex）共享的、agent-native 的唯一权威 memory 存储，可经 MCP 读写。
- **Channels** —— 从 Telegram 或 SeaTalk 与内置 agent 聊天、回应审批提示，并在手机上接收通知。

在多台机器上用 Coffer？**多机同步**通过一个你自己掌控的 git 仓库让一个仓库在多机间保持一致 —— 知识、记忆、资源，以及仅密文的凭证都会同步；加密密钥绝不离开你的机器。

内置的 **chat** 平台与 Web/桌面 UI 把它们串起来：与 Coffer agent 对话、浏览并管理每一种 kind，并实时观察 invocation。

📖 **文档站点：** https://wyx-sg.github.io/Coffer/

## 下载与安装

> **尚无打 tag 的 release。** 下面的预构建二进制、一行安装脚本和桌面 DMG 会随 Coffer
> 的首个 tagged release 一起发布，目前尚未提供 —— 在那之前这些链接会 404。现在请先
> **[从源码安装](#从源码安装开发者)**（见下文），这是当前可用的安装方式。

### 一行命令安装（macOS）—— _随首个 release 提供_

```sh
curl -fsSL --proto '=https' --tlsv1.2 https://wyx-sg.github.io/Coffer/install.sh | sh
```

安装三个二进制文件 —— `coffer`（管理 CLI）、`coffer-daemon`、`coffer-mcp-shim` —— 到
`~/.coffer/bin`。**守护进程首次使用时自动启动，无需手动执行启动命令。** 环境变量覆盖：
`COFFER_INSTALL_DIR`、`COFFER_VERSION`、`COFFER_NO_MODIFY_PATH`。

### 桌面应用（大多数用户）—— _随首个 release 提供_

从 [Releases](https://github.com/wyx-sg/Coffer/releases/latest) 下载安装包：

| 平台                  | 文件                                    |
| --------------------- | --------------------------------------- |
| macOS Apple silicon   | `Coffer_<version>_aarch64-unsigned.dmg` |

Coffer 目前只发布 macOS（Apple Silicon）版本。`-unsigned` 后缀表示该 DMG
尚未公证（见下文）。请用 release 的 `SHA256SUMS` 文件校验下载。

> **macOS（未签名）：** 构建未签名（公证待完成），首次打开时 macOS 可能提示 Coffer「已损坏」
> （并非真的损坏——此时右键「打开」无效）。清除隔离标记：
> `xattr -dr com.apple.quarantine /Applications/Coffer.app` —— 如果仍无法打开，重新进行 ad-hoc
> 签名：`codesign --force --deep --sign - /Applications/Coffer.app`

### 从源码安装（开发者）

请参阅下方的[从源码安装（开发者）](#从源码安装开发者)。

---

## 从源码安装（开发者）

```bash
git clone https://github.com/wyx-sg/Coffer.git
cd Coffer
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ./backend[dev]
make verify          # sanity-check the install
```

`pip install` 会把 CLI（`coffer`）与 stdio shim（`coffer-mcp-shim`）作为 console-script 入口装到
`PATH` 上 —— 无需单独部署。守护进程会在你首次运行任何 `coffer` 命令或连接 MCP 客户端时**自动启动** ——
`coffer daemon start` 可用于显式控制，但并非必要的安装步骤。

---

## 快速上手

注册你的第一个 MCP 服务器 —— 以 `@modelcontextprotocol/server-filesystem` 为例：

```bash
coffer mcp add filesystem \
  --stdio "npx -y @modelcontextprotocol/server-filesystem /tmp"

coffer mcp list                   # → filesystem  | stdio | enabled
coffer mcp tool list filesystem   # → read_file, write_file, list_directory, …
```

然后把你的 MCP 客户端指向 shim —— 见下方 **接入 MCP 客户端**。

### Agents

**agent** 是一个已注册的本地 AI 编码 agent（支持的类型：`claude_code`、`codex`）。
Coffer 可以自动检测已安装的 agent（它会列出候选项并请你确认 —— 不会自动注册任何东西）、
在应用内编辑每个 agent 精选 (curated) 的配置文件（带格式校验、原子写入并生成 `.bak` 备份，
以及一个会滚动到匹配处的编辑器内查找/替换），并一键把 Coffer 自己的 MCP 服务器安装到 agent 或从中卸载。
桌面/Web UI 提供一个 **Agents** 页面（列表 + 详情）、一个检测对话框、配置文件编辑器，以及 MCP 安装开关。

```bash
coffer agent detect               # 发现已安装的 agent（注册前需确认）
coffer agent add claude_code      # 注册一个（--name 可选；默认 claude-code）
coffer agent config edit <name> <key>  # 在 $EDITOR 中编辑某个精选配置文件
coffer agent mcp install <name>   # 把 Coffer 的 MCP 服务器安装到该 agent
```

---

## 接入 MCP 客户端

把 `coffer-mcp-shim` 配成 stdio MCP 服务器的启动命令即可。shim 会自动发现守护进程（必要时自动拉起），无需手工配置端口或 token。

### Claude Code

```bash
claude mcp add coffer coffer-mcp-shim
```

### Codex

`~/.codex/config.toml`：

```toml
[mcp_servers.coffer]
command = "coffer-mcp-shim"
```

改完配置后重启客户端。工具名带命名空间，形如 `<server-name>__<tool-name>`（例如 `filesystem__read_file`）。

---

## 项目结构

```
backend/              Python daemon + CLI + shim
  coffer/
    domain/           pure types + business rules (no I/O)
    application/      services + orchestration
    infrastructure/   DB, MCP transports, encrypted credential store, daemon discovery
    surfaces/         HTTP (FastAPI) + CLI (Typer) + stdio shim
specs/                Speckit specs (one per feature)
docs/decisions/       Architectural Decision Records (ADRs)
agents/               Workflow, SDD, stack, and testing guides
```

架构深入解读：[.specify/memory/architecture.md](.specify/memory/architecture.md)。
ADRs：[docs/decisions/](docs/decisions/)。

---

## 开发者常用命令

| 命令           | 作用                                                                 |
| -------------- | -------------------------------------------------------------------- |
| `make verify`  | 全量检查：lint、类型、单元、集成、契约 (contract) 与 acceptance 审计 |
| `make install` | 把后端依赖装进项目 venv                                              |

---

## 参与贡献

- **Conventional Commits**（必须遵守）—— 见 [agents/workflow.md](agents/workflow.md)
- **Spec-driven development**（规格驱动开发）—— 每个功能从 `specs/<id>/` 下的 spec 开始 —— 见 [agents/sdd.md](agents/sdd.md)
- **架构契约** —— 6 条 importlinter 契约必须保持绿色（定义在 [backend/pyproject.toml](backend/pyproject.toml)）
- **凭据 (credentials)** —— secret 只以 Fernet 密文形式经 `coffer.infrastructure.credentials` 存于 `credentials` 表；明文绝不落到 DB、日志或审计

---

## 许可证

MIT —— 见 [LICENSE](LICENSE)。
