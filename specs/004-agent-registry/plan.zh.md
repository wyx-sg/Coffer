# 实施计划：004 —— Agent Registry

> English: [plan.md](./plan.md)

**Feature Branch**: `feature/004-agent-registry`
**Date**: 2026-05-22
**Spec**: [./spec.md](./spec.md)
**Status**: Draft

## 摘要

向 Coffer 加入 `agent` 这一 Resource kind：本地安装 AI agent 的 registry。v1 支持两个类型——**Claude Code**（`claude_code`）与 **OpenAI Codex**（`codex`）——每个都同时覆盖该产品的 CLI 与 app/IDE 形态，二者共享一个配置目录。发现（discovery）是只读的：扫描把已安装但未注册的 agent 报告为候选项，由用户确认要添加哪些——不自动注册任何内容（包括启动时）。用户也可手工添加、编辑、移除 agent。

在 registry 之上，本功能新增两项能力：

1. **配置文件查看 + 编辑** —— 每个 agent 类型暴露一份精选的自有配置文件 allowlist（Claude Code：`settings.json`、`settings.local.json`、`~/.claude.json`、`CLAUDE.md`；Codex：`config.toml`、`AGENTS.md`）。用户以原始文本读取并保存它们；保存会按格式校验、原子写入并保留 `.bak`。同一套原子写入 + `.bak` 机制也支撑 Coffer-MCP 的安装/卸载。
2. **一键安装 Coffer-MCP** —— 把一个 `coffer` stdio MCP-server 条目（指向 `coffer-mcp-shim`）写入/移除到 agent 的 MCP 配置，带状态查询与幂等性。

该 kind 暴露一个 `on_delete` 钩子，由 the 005-skill-manager spec 接入用于 skill binding 的级联清理。同时交付 REST 路由、CLI 子命令与桌面 Agents 页面。

本 spec 是 spec 001 中引入的 kind-agnostic Resource 框架的第二个消费者，用以验证该框架的可复用性。

## 技术上下文

| 维度             | 取值                                                                                                                                                                            |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **语言 / 版本**  | Python 3.12+，TypeScript 5.x                                                                                                                                                    |
| **新运行时依赖** | `tomlkit`（MIT）—— 为 Codex `config.toml` 的 MCP 安装做格式保留的 TOML 编辑。                                                                                                   |
| **存储**         | SQLite，位于 `~/.coffer/coffer.db`。无新增表——agent 是通用 `resources` 表中的行（head 迁移保持在 0004）。配置文件与 MCP 安装状态不持久化——磁盘上的 agent 配置文件即为事实来源。 |
| **测试**         | 4 层（unit / integration / contract / e2e）；acceptance 标记绑定到 scenario。                                                                                                   |
| **目标平台**     | macOS arm64+x64、Windows x64、Linux x64+arm64                                                                                                                                   |
| **性能目标**     | 冷启动发现扫描 ≤ 200 ms。CRUD 单次操作 ≤ 50 ms。                                                                                                                                |
| **约束**         | local-first，仅 127.0.0.1；保留分层架构；不引入新的凭据存储。                                                                                                                   |
| **规模**         | 每个用户 ≤ 8 个已注册 agent。                                                                                                                                                   |

## Constitution 检查

| 条款                             | 合规 | 说明                                                                                 |
| -------------------------------- | ---- | ------------------------------------------------------------------------------------ |
| I. Local-First（NON-NEGOTIABLE） | ✅   | 纯本地 registry；无网络调用。                                                        |
| II. Spec-as-Truth                | ✅   | 本计划实现 `spec.md`；spec 先于代码提交。                                            |
| III. Open-Source-Readiness       | ✅   | 新增一个依赖 `tomlkit`——MIT、开源；按治理要求在 PR 描述中说明。                      |
| 语言                             | ✅   | 仅 Python + TypeScript。                                                             |
| 架构：分层                       | ✅   | 新代码遵循 `surfaces → application → domain → infrastructure`；domain 不依赖 infra。 |
| 持久化：控制面用 SQLite          | ✅   | Registry 在 SQLite 中。                                                              |
| 凭据                             | ✅   | 无。                                                                                 |
| 网络默认                         | ✅   | 仅 loopback HTTP。发现（discovery）只读本地文件系统。                                |

## 项目结构

### 文档

```
specs/004-agent-registry/
  spec.md
  plan.md              (本文件)
  data-model.md
  contracts/api.openapi.yaml
  quickstart.md
```

### 新增后端模块

```
backend/coffer/domain/agent/
  __init__.py
  types.py             # AgentType StrEnum (claude_code, codex) + default_config_dir + 检测标记
  config.py            # AgentConfig (Pydantic)
  config_files.py      # ConfigFileFormat, ConfigFileSpec, config_files_for(), validate_content, spec_for
  mcp_install.py       # apply_install / apply_uninstall / is_installed（纯文本变换，TOML 用 tomlkit）

backend/coffer/application/agent/
  __init__.py
  service.py             # AgentService (register [name 可选] / update / remove)
  auto_detect.py         # AutoDetectService.discover() -> list[AgentCandidate]（只读扫描，返回候选项，无抑制列表，不在启动时运行）
  config_file_service.py # AgentConfigFileService (list/read) + ConfigFileStorePort
  mcp_service.py         # AgentMcpService (status/install/uninstall) + ShimResolver
  kind.py                # make_agent_kind(on_delete_hook) -> Kind

backend/coffer/application/fs/
  __init__.py
  browse_service.py      # BrowseService.browse(path) -> 直接子目录（只读文件夹浏览）

backend/coffer/infrastructure/agent/
  __init__.py
  config_file_store.py    # ConfigFileStore：read_text / stat；write_text_atomic (+ .bak) 用于配置文件保存与 Coffer-MCP 安装

backend/coffer/surfaces/http/agent_routes.py         # GET/POST /agents, GET/PATCH/DELETE /agents/{name}, GET /agents/candidates
backend/coffer/surfaces/http/agent_config_routes.py  # GET /agents/{name}/config-files[/{key}], GET/POST/DELETE /agents/{name}/mcp-install
backend/coffer/surfaces/http/fs_routes.py            # GET /fs/browse（支撑 Web 文件夹选择器的只读文件夹浏览器）
backend/coffer/surfaces/cli/agent_cmd.py             # coffer agent {add, list, edit, rm, detect, config ls|cat, mcp status|install|uninstall}
```

### 新增前端模块

```
frontend/src/pages/AgentsPage.tsx                 # 现有列表页
frontend/src/components/agents/
  AgentAddForm.tsx / AgentEditForm.tsx / AgentTable.tsx   # 现有
  FolderPicker.tsx         # config-dir 文件夹选择器（桌面用 OS 原生对话框；Web 用 GET /fs/browse 文件夹浏览器）
  AgentConfigPanel.tsx     # 单 agent 的配置文件列表 + 编辑器（文件列表 + 可编辑内容视图，带保存、查找/替换、格式标签）
  AgentMcpInstall.tsx      # 一键安装/卸载开关 + 状态徽标
frontend/src/lib/api/agents.ts                     # 扩展配置文件 + MCP 安装调用
frontend/src/lib/hooks/useAgents.ts                # 新增 useAgentConfigFiles / useAgentConfigFile / useAgentMcpInstall
frontend/src/i18n/locales/{en,zh}.json             # agents.config.* / agents.mcp.* 字符串
```

agent 详情页（`/agents/:name`）是一个简单的 **Overview + Config files** 详情页：
一个 Overview tab 汇总 agent 已注册的配置，一个 Config files tab 在可编辑查看器中
呈现其已知配置文件，带保存控件与一个编辑器内查找/替换便利功能。

## 阶段

### Phase 0 —— Research（已在对话中关闭）

- 备选方案：在 Resource 框架之外另设独立 `agents` 表 → 否决（丧失 audit/CRUD/UI 统一性；agent-as-peer 也没有未来扩展空间）。
- 备选方案：把 agent 合入 the 005-skill-manager spec → 重新评估后否决（按 spec 体量切分更清晰；一份 PR 同时交付两者）。
- 发现（discovery）启发式：已知标记目录（即该类型的 `default_config_dir`）存在即把该类型作为候选项呈现。后续 spec 可能加入「PATH 上有命令」类型的检测。

> 基础 registry（类型/config/service/发现（discovery），REST/CLI/桌面 CRUD）已在本分支
> 交付。以下阶段覆盖 v2 增量：收窄到两个类型、配置文件查看 + 编辑、一键安装
> Coffer-MCP。

### Phase 1 —— 类型收窄 + contracts

- 从 `AgentType`（enum、`_DISPLAY`、`_default_config_dir`）移除 `claude_desktop` 与 `cursor`；把 `codex_cli` 重命名为 `codex`（显示名「OpenAI Codex」）。更新 OpenAPI enum、data-model、quickstart、前端类型下拉框，以及所有引用被移除/重命名类型的测试。
- 向后端运行时依赖加入 `tomlkit`。

### Phase 2 —— 配置文件 domain + 后端（TDD）

1. Domain：`agent/config_files.py` —— `ConfigFileFormat`、`ConfigFileSpec`、`config_files_for`、`spec_for`、`validate_content`；allowlist 基于 agent 的 `config_dir` 解析。新错误 `ConfigFileNotAllowed`、`ConfigFileFormatInvalid`。新 audit 事件 `agent_config_file_written`。先写单元测试。
2. Infrastructure：`config_file_store.py` —— 读取、stat；原子写入 + `.bak` 用于配置文件保存与 Coffer-MCP 安装。用临时目录写集成测试。
3. Application：`AgentConfigFileService`（`list/read`）over `ConfigFileStorePort`。集成测试：list/read/缺失/未知 key。
4. Surfaces：`agent_config_routes.py`（HTTP GET）、`coffer agent config ls|cat`（CLI）、composition 接线。Contract + CLI 测试。

### Phase 3 —— Coffer-MCP 安装（TDD）

1. Domain：`agent/mcp_install.py` —— 对 `json`（`~/.claude.json`）与 `toml`（`config.toml`，经 `tomlkit`）的 `apply_install`/`apply_uninstall`/`is_installed`。两种格式的纯文本单元测试，含幂等性。
2. Application：`AgentMcpService`（`status/install/uninstall`）+ shim 路径解析器（`COFFER_MCP_SHIM_PATH` → `shutil.which` → 解释器脚本目录 → 打包回退 → `ShimNotFound`）。新 audit 事件 `agent_mcp_installed`/`agent_mcp_uninstalled`。集成测试含重复安装、未安装时卸载、shim 缺失。
3. Surfaces：HTTP GET/POST/DELETE `…/mcp-install`、`coffer agent mcp status|install|uninstall`。Contract + CLI 测试。

### Phase 4 —— 前端

- `AgentConfigPanel` —— 列出配置文件、在可编辑内容视图里打开某个文件，带保存控件、内联校验错误与一个编辑器内查找/替换（带格式标签）。`AgentMcpInstall` —— 状态徽标 + 安装/卸载开关。
- agent 详情页是一个简单的 Overview + Config files 详情页。
- `FolderPicker` —— 无需输入路径即可选择自定义 `config_dir`：打包桌面应用用 OS 原生目录对话框，Web 用 daemon 支撑的 `GET /fs/browse` 文件夹浏览器。add/edit 表单把 agent 名称设为可选（省略时由服务端按类型派生默认名）。
- 用 TanStack Query + openapi-fetch 接 hooks；英文 + 简体中文 i18n 字符串（`agents.config.*`、`agents.mcp.*`）。
- e2e（`e2e/web/specs/shell_agents.spec.ts`）：查看一个配置文件；安装 Coffer MCP 并观察状态翻转。

### Phase 5 —— Acceptance + verify

- `spec.md` 中每一个 acceptance scenario 至少被一个带 `@pytest.mark.acceptance(spec="004-agent-registry", scenario="…")` 的测试覆盖。
- `make verify`（e2e 用 `make verify-all`）在 macOS + Linux 上绿。

## 风险 / 未知

- **GUI / venv 的 PATH** —— 桌面或 venv 启动的 daemon 不继承 shell `PATH`（且其 `sys.executable` 可能是指向基础解释器的符号链接），因此裸 `coffer-mcp-shim` 命令可能解析不到。缓解：安装时解析为绝对路径（`shutil.which` → 解释器的 `sysconfig` 脚本目录 → 打包的 `dist/` 回退），全部落空则显式失败。
- **`~/.claude.json` 重序列化** —— 安装 MCP 条目会用 stdlib `json`（`indent=2`）重序列化整个 JSON 文件，产生较大 diff。可接受且可经 `.bak` 恢复；已记录。
- **TOML 格式** —— Codex `config.toml` 的编辑用 `tomlkit` 以保留用户的注释/排版，而非整体重序列化。

## 延期至后续 spec 的开放项

- agent **类型**扩展超出 v1 的两种（Claude Desktop 聊天应用、Cursor、Gemini CLI、GitHub Copilot）—— 每个增加一个 enum 值、扫描器与配置文件 allowlist。
- **结构化 MCP-server 管理**（`~/.claude.json` 内，超出一键 Coffer 条目之外）—— 专门的后续 surface，而非原始文件编辑。
- agent **健康检查**（注册路径上的安装是否仍存在）—— 单独 spec。
- agent **作为 MCP peer**（把另一个 agent 通过 Coffer MCP 网关暴露为可调用工具）—— 探索性。
