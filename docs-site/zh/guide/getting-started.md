# 快速上手

> **本页面介绍从源码安装 / 开发者路径。** 如需预构建的一行命令安装或桌面应用，请参阅
> [下载与安装](/zh/guide/install)。

从源码安装 Coffer 并接入第一个 MCP 客户端。守护进程运行后，你机器上的所有 MCP 客户端
都可以通过 shim 接入，无需额外配置。

## 从源码安装

```bash
git clone https://github.com/wyx-sg/Coffer.git
cd Coffer
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ./backend[dev]
make verify          # sanity-check the install
```

`pip install` 会把 CLI（`coffer`）与 stdio shim（`coffer-mcp-shim`）作为 console-script 入口
装到 `PATH` 上 —— 无需单独部署。

- **`coffer`** —— 用于注册和查看 MCP 服务器的管理 CLI。
- **`coffer-mcp-shim`** —— MCP 客户端用来和守护进程通信的 stdio 桥接程序。

`make verify` 会运行完整的检查套件（lint、类型检查、单元测试、集成测试、契约检查与
acceptance 审计），确认安装状态正常。

::: tip 守护进程自动启动 —— 不需要手动启动
守护进程在你首次运行任何 `coffer` 管理命令或 MCP 客户端通过 shim 连接时会自动拉起。
`coffer daemon start` 可用于显式控制，但**不是**必要的安装步骤。
:::

[注册第一个服务器 →](/zh/guide/register-server)
