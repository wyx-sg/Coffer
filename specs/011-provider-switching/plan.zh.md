# 实现计划：011——Provider Switching

> English: [plan.md](./plan.md)

**Branch**: `feature/G9-provider-switching`
**Date**: 2026-06-21
**Spec**: [./spec.md](./spec.md)
**Status**: Draft

## 概述

为 Coffer 添加 `provider` Resource kind：一个共享的 LLM provider profile 注册表，每条 profile 投影到匹配 agent 的原生配置文件（anthropic/Claude Code → `~/.claude/settings.json`；openai/Codex → `~/.codex/config.toml`）。凭证经 Fernet 加密；原始密钥绝不进入原生配置文件。本 PR 交付 REST 路由、CLI 子命令、最简前端 DataTable 页，以及 sync / 审计接入。

## 技术背景

| 维度 | 值 |
|---|---|
| **语言 / 版本** | Python 3.12+，TypeScript 5.x |
| **新运行时依赖** | 无；`tomlkit` 已在后端（MCP TOML 路径）；`EncryptedCredentialStore` 已在代码库中 |
| **存储** | 共享 `resources` 表（`kind='provider'`）；无需新迁移 |
| **测试** | 4 层；acceptance 标记与规范场景对应 |
| **目标平台** | macOS arm64+x64（主要）；Windows / Linux（现有 CI） |
| **性能目标** | 激活（投影到磁盘）≤ 200 ms |
| **约束** | Local-first；凭证隔离（决策 B）；域层纯函数（无 I/O） |

## 章程检查

| 条款 | 合规 | 说明 |
|---|---|---|
| I. Local-First | ✅ | provider profile 和凭证本地存储；sync 使用用户控制的 git |
| II. Spec-as-Truth | ✅ | 规范在代码前提交 |
| III. Open-Source-Readiness | ✅ | 无新闭源依赖 |
| 语言 | ✅ | Python + TypeScript |
| 架构：分层 | ✅ | 纯投影函数返回文本（域层）；文件写入在 `_project`（服务层）；域层无 I/O |
| 持久化 | ✅ | 控制平面在 SQLite `resources` 表（复用）；原始密钥在 Fernet vault |
| 凭证 | ✅ | 原始密钥只在 vault；`ProviderConfig` 只持有 `credential_ref` |
| 网络默认 | ✅ | 仅 loopback HTTP API |

## 项目结构

### 文档

```
specs/011-provider-switching/
  spec.md / spec.zh.md
  data-model.md / data-model.zh.md
  plan.md / plan.zh.md             （本文件）
  quickstart.md / quickstart.zh.md
  research.md / research.zh.md
  contracts/api.openapi.yaml
docs/decisions/ADR-032-provider-switching.md
docs/decisions/ADR-032-provider-switching.zh.md
```

### 新增后端模块

```
backend/coffer/domain/provider/
  __init__.py
  config.py        # WireFormat、WireApi 枚举 + ProviderConfig（Pydantic v2）
  projection.py    # apply_anthropic_settings / apply_codex_provider 纯函数
                   # + ProjectionTarget + target_for() + 常量

backend/coffer/application/provider/
  __init__.py
  service.py       # ProviderService（CRUD + activate + resolve_active_key + _project）
                   # + ActivateResult
  kind.py          # make_provider_kind(...) -> Kind

backend/coffer/surfaces/http/provider_routes.py
backend/coffer/surfaces/http/provider_schemas.py
backend/coffer/surfaces/http/provider_wiring.py
backend/coffer/surfaces/cli/provider_cmd.py
```

### 修改的后端模块

```
backend/coffer/domain/audit.py           # 添加 PROVIDER_SWITCHED 到 AuditEventType
backend/coffer/surfaces/http/wiring.py  # 添加 wire_provider_kind(...)
backend/coffer/surfaces/http/app.py     # 在 composition root 注册 provider Kind
```

### 新增前端模块

```
frontend/src/lib/api/providers.ts                 # 手写客户端 + TS 类型
frontend/src/lib/hooks/useProviders.ts            # React Query hooks（list / create / delete / activate）
frontend/src/pages/settings/ProvidersPage.tsx     # 设置 → 供应商列表页
frontend/src/components/settings/ProviderForm.tsx # 创建档案表单（添加对话框使用）
frontend/src/pages/settings/SettingsLayout.tsx    # 添加供应商导航标签
frontend/src/router.tsx                           # /settings/providers 路由
frontend/src/i18n/locales/{en,zh}.json            # 添加 provider 字符串
```

---

## 任务

任务按不相交的文件区域分组。每个任务列出涉及的文件和覆盖的 acceptance 场景（标记时需与规范场景标题完全一致）。

---

### 任务 1——域层：WireFormat、WireApi、ProviderConfig、投影函数

**涉及文件：**
- `backend/coffer/domain/provider/__init__.py`（新建）
- `backend/coffer/domain/provider/config.py`（新建）
- `backend/coffer/domain/provider/projection.py`（新建）

**构建内容：**
1. `WireFormat` 和 `WireApi` 字符串枚举放在 `config.py`（无独立 `wire.py`）。
2. `ProviderConfig` Pydantic v2 模型放在 `config.py`（所有字段；不含 secret）。添加 `model_validator` 确保 `fast_model` 仅对 `wire_format == "anthropic"` 有意义（警告，不报错——对 openai 忽略）。确保 `model_dump(mode="json")` 为 JSON 稳定输出。
3. `projection.py` 中的纯投影函数，返回原生配置文本：
   `apply_anthropic_settings(config, existing_text) -> str` 和
   `apply_codex_provider(config, profile_name, existing_text) -> str`。
   还有：`ProjectionTarget`、`target_for(wire)`、常量
   `CODEX_PROVIDER_ID`、`CODEX_ENV_KEY`、`ANTHROPIC_API_KEY_HELPER`。
   不存在 `ProjectionPatch` 数据类；不存在 `build_patch()` 函数。

**覆盖的 acceptance 场景：**（单元测试，无 I/O，不加 acceptance 标记）

**依赖任务：** 无；纯域，可最先启动。

---

### 任务 2——应用层：ProviderService + kind factory

**涉及文件：**
- `backend/coffer/application/provider/__init__.py`（新建）
- `backend/coffer/application/provider/service.py`（新建）
- `backend/coffer/application/provider/kind.py`（新建）

**构建内容：**

`ProviderService`（无独立 `ProviderRepo`；provider profile 是由 `ResourceService` 管理的普通 resource 行）：
- `create`：校验凭证来源（只能一个）；若提供 `secret_value` 则通过 `EncryptedCredentialStore.set` 存储；注册 Resource。
- `update`：部分 patch；若提供 `secret_value` 则轮换 vault 条目。
- `delete`：`find_credential_citations`；若自有则删除 vault 条目；删除 Resource。
- `activate`：顺序 clear（通过 `ResourceService.update_config`）然后 set 实现单活跃不变量；对匹配的 agent 调用 `_project`；发出 `PROVIDER_SWITCHED`；返回 `ActivateResult`。
- `resolve_active_key(wire: WireFormat) -> str`：按 wire format 找到活跃 profile；`EncryptedCredentialStore.get(ref)`；返回明文（调用方打印到 stdout；不得记录）。不支持按名称解析。
- `_project(profile_name, config, agent_config_dir)`：内联私有方法；调用 `apply_anthropic_settings` 或 `apply_codex_provider` 然后通过 `ConfigFileStore.write_text_atomic` 写入。无独立 `ProviderProjector` 类。

`make_provider_kind()` factory：返回 `Kind`，内含 schema、CRUD hooks 接入 `ProviderService`、`config_schema` 通过 `ProviderConfig` 校验。

参考：`backend/coffer/application/knowledge_base/kind.py`。

**覆盖的 acceptance 场景：**
- `activating a profile deactivates the previous active profile of the same wire format`
- `create an anthropic provider profile with an inline secret`
- `create a profile that reuses an existing credential ref`
- `reject a profile with an unknown wire format`
- `reject a profile that supplies neither a secret nor a credential ref`
- `update a provider profile`
- `delete a provider profile cleans up its owned credential`
- `activate a profile whose wire matches no registered agent records active but projects nothing`
- `a provider switch is recorded in the audit log`
- `resolve the active provider key for the apiKeyHelper`

**依赖任务：** 任务 1（需要 `WireFormat`、`ProviderConfig`、投影函数）

---

### 任务 3——审计 + sync 接入（composition root）

**涉及文件：**
- `backend/coffer/domain/audit.py`（修改：添加 `PROVIDER_SWITCHED`）
- `backend/coffer/surfaces/http/wiring.py`（修改：添加 `wire_provider_kind`）
- `backend/coffer/surfaces/http/app.py`（修改：注册 provider kind）

**构建内容：**
1. 在 `AuditEventType` 中添加 `PROVIDER_SWITCHED = "provider_switched"`。
2. 在 `wiring.py` 中添加 `wire_provider_kind(app, resource_svc, audit, sm, agent_registry) -> None`：构建 `ProviderService`，调用 `make_provider_kind()`，注册到 `app.state.kinds["provider"]`。镜像 `wire_kb_kind`。
3. 在 `app.py` 的适当位置调用 `wire_provider_kind(...)`。

无需新迁移；无 SCHEMA_VERSION bump。

**覆盖的 acceptance 场景：**
- `a provider profile round-trips through sync export and import`

**依赖任务：** 任务 2

---

### 任务 4——HTTP 路由

**涉及文件：**
- `backend/coffer/surfaces/http/provider_routes.py`（新建）
- `backend/coffer/surfaces/http/provider_schemas.py`（新建）
- `backend/coffer/surfaces/http/provider_wiring.py`（新建）

**构建内容：**
FastAPI router，包含：
- `GET  /providers` → `list_providers`（响应：`ProviderListOut` = `{ "providers": [...] }`）
- `POST /providers` → `create_provider`（body：`ProviderCreateRequest`）
- `GET  /providers/{name}` → `get_provider`
- `PATCH /providers/{name}` → `update_provider`（body：`ProviderPatchRequest`；`wire_format` 和 `credential_ref` 不可变）
- `DELETE /providers/{name}` → `delete_provider`
- `POST /providers/{name}/activate` → `activate_provider`（返回 `ActivateOut`）

响应模型 `ProviderOut` 绝不含 secret；映射 `ProviderConfig` 去掉 secret 再加 `name`、`created_at`、`updated_at`。

`ProviderListOut`：`{ "providers": list[ProviderOut] }`。

`ProviderCreateRequest`：`{name, wire_format, base_url, model, fast_model?, wire_api?, credential_ref?, secret_value?}`。服务层强制执行唯一凭证来源。

`ActivateOut`：`{activated: str, projected: list[str], skipped: list[str]}`。

在 `app.py`（或 wiring）中挂载到 `/api/v1/providers`。

**覆盖的 acceptance 场景：**
- `list provider profiles`
- （其他场景也经由路由执行）

**依赖任务：** 任务 2、3

---

### 任务 5——CLI

**涉及文件：**
- `backend/coffer/surfaces/cli/provider_cmd.py`（新建）

**构建内容：**
Typer（或 Click）子命令组 `provider`，包含：
- `list [--json]`
- `add <name> --wire <fmt> --base-url <url> --model <m> [--fast-model <m>] [--wire-api <api>] [--credential-ref <ref>] [--secret <value>]`（若未提供 `--secret` 且无 `--credential-ref` 则提示输入）
- `show <name> [--json]`
- `edit <name> [字段标志] [--secret <value>]`
- `remove <name>`
- `switch <name>`
- `key --wire <fmt>` → 将原始密钥打印到 stdout；按该 wire 的活跃 profile 解析；不支持按名称形式；不得将值泄露到日志

将 `provider_cmd` 接入主 Coffer CLI 组（通常是 `backend/coffer/surfaces/cli/main.py`）。

**覆盖的 acceptance 场景：**
- `the command line covers create, list, and switch`
- `resolve the active provider key for the apiKeyHelper`

**依赖任务：** 任务 2

---

### 任务 6——前端：API 客户端、hooks 和页面

**涉及文件：**
- `frontend/src/lib/api/providers.ts`（新建）
- `frontend/src/lib/hooks/useProviders.ts`（新建）
- `frontend/src/pages/settings/ProvidersPage.tsx`（新建）
- `frontend/src/components/settings/ProviderForm.tsx`（新建）
- `frontend/src/i18n/locales/en.json`（追加 provider 字符串）
- `frontend/src/i18n/locales/zh.json`（追加 provider 字符串）
- `frontend/src/pages/settings/SettingsLayout.tsx` + `router.tsx`（添加 Providers 标签/路由）

**构建内容：**
- `providers.ts`：手写 `ProviderOut`、`ProviderCreateRequest` 等类型；`listProviders()`、`createProvider()`、`updateProvider()`、`deleteProvider()`、`activateProvider()` fetch 封装。
- `useProviders.ts`：封装上述接口的 React Query hooks；可被 `vi.mock`。
- `ProvidersPage.tsx`：DataTable，列：name / wire_format / base_url / model / active；行操作：Switch、Delete；顶部操作：Add（create）。桌面页不含内联编辑——编辑通过 CLI/API 实现。
- `ProviderForm.tsx`：仅用于创建的受控表单。
- 测试：`vi.mock` hooks；断言表格渲染 profile 并调用 activate mutation。

**覆盖的 acceptance 场景：**
- `the Providers page lists profiles and can switch the active one`

**依赖任务：** 任务 4（需要 API 形状）

---

### 任务 7——测试

**涉及文件：**
- `backend/tests/unit/domain/provider/`（新建）：测试纯投影函数（`apply_anthropic_settings` / `apply_codex_provider`）与 `ProviderConfig` 校验
- `ProviderService` 由下面的集成测试覆盖（HTTP / CLI / sync），不单独写 unit 套件——它涉及 DB + vault + 文件系统 I/O
- 集成测试：`backend/tests/integration/surfaces/http/test_provider_routes.py`、`surfaces/cli/test_provider_cmd.py`、`sync/test_provider_sync.py`
- acceptance 标记直接打在上述集成测试上（无独立的 scenarios 文件）
- `frontend/src/pages/settings/ProvidersPage.test.tsx`（新建）：页面 acceptance 测试

**构建内容：**

单元：
- `apply_anthropic_settings` 和 `apply_codex_provider` 两种 wire；断言精确的键设置和键删除。
- `ProviderConfig` 校验：缺少必填字段；两者都有 / 都没有凭证来源；未知 `wire_format`。
- 单活跃不变量：两条 anthropic profile；激活 B → A 变为非活跃（通过 mock `ResourceService` 的服务层测试）。

集成（真实临时文件 + DB）：
- 以 `secret_value` 创建 → `credential_ref` 存储，vault 有条目。
- 激活 anthropic → `settings.json` 含托管键，保留其他键。
- 激活 openai → `config.toml` 含托管键，保留其他键。
- 激活后 `.bak` 文件存在。
- 审计日志中出现 `provider_switched`（小写）。
- Sync export → import → profile 还原，YAML 中无 secret。
- 删除 → 自有 vault 条目消失。

Acceptance 标记（`@pytest.mark.acceptance(spec="011-provider-switching", scenario="<title>")`）：
规范中所有 17 个场景标题（逐字节一致）。

TS acceptance（`acceptance("011-provider-switching", "the Providers page lists profiles and can switch the active one", ...)`）：
在 `ProvidersPage` 测试中。

**覆盖的 acceptance 场景：** spec.md 中列出的全部 17 个。

**依赖任务：** 任务 1–6

---

## 风险

- **tomlkit 合并顺序**：合并时必须保留 TOML 注释和顺序。使用 tomlkit 的类字典 API，不使用字符串替换。通过往返测试验证：加载 → 合并 → 再次加载 → 非 Coffer 键仍存在。
- **settings.json 与 Claude Code 的竞争写入**：Claude Code 可能并发写入 `settings.json`。`write_text_atomic`（写入 `.tmp`，`os.replace`）可缓解但不能完全消除。记录为已知限制。
- **Codex 环境变量缺口**：`COFFER_PROVIDER_KEY` 不会自动为 Codex 设置。Quickstart 记录手动 export 方法。自动注入与 hot-switch 一同延期。

## 延期到未来规范的事项

- Provider drift-verify（spec 4.9）：检查原生配置是否与活跃 profile 一致。
- Hot-switch：对正在运行的 Claude Code / Codex 进程的会话内热重载。
- 将 `COFFER_PROVIDER_KEY` 自动注入 Coffer 启动的 Codex 进程。
- 显式停用 / 原生配置还原。
