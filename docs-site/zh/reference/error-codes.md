---
title: 错误码
description: Coffer 守护进程返回的每个错误码，及其 HTTP 状态、含义和常见修复方法，另含聊天轮次错误、MCP 错误以及命令行退出码。
---

# 错误码 {#error-codes}

本页列出 Coffer 可能返回的所有错误码：管理 API 的错误码及其 HTTP 状态、聊天轮次可能失败时给出的错误码、MCP 网关返回的 JSON-RPC 错误，以及 `coffer` 命令行和 MCP shim 的退出码。你在响应、日志行或 Web 界面中看到某个错误码时，可以在这里查。

## 错误信封 {#the-error-envelope}

所有管理 API 错误的响应体结构相同，而且每个错误响应都带有一个 `X-Coffer-Trace` 响应头，你可以用它在守护进程日志中搜索：

```json
{
  "error": {
    "code": "SECRET_MISSING",
    "message": "secret not found in the secret store: mcp/jira/token",
    "details": {}
  }
}
```

`details` 通常为空，除非错误带有结构化上下文：`reason`（简短的机器可读原因）、`feature`（用于 `FEATURE_DISABLED`），或特定路由的字段，例如 `doc_type`。

没有列在守护进程状态表中的错误码会回退为 HTTP `500`。下面各表给出的是每个错误码实际发送时的状态。

## 请求与框架错误 {#request-and-framework-errors}

| 错误码 | HTTP | 含义 | 常见修复 |
| --- | --- | --- | --- |
| `UNAUTHENTICATED` | 401 | `X-Coffer-Token` 请求头缺失或错误。 | 从 `~/.coffer/daemon.json` 读取当前令牌；它在每次守护进程启动和 `coffer daemon rotate-token` 时都会变。 |
| `DAEMON_NOT_READY` | 503 | 守护进程还没有生效的令牌；它仍在启动中。 | 稍后重试。 |
| `HOST_NOT_ALLOWED` | 403 | 请求的 `Host` 请求头不是带着守护进程端口的 `127.0.0.1`、`localhost` 或 `[::1]`。用于防御 DNS 重绑定。 | 直接访问 `127.0.0.1:<port>` 或 `localhost:<port>`，不要经过代理或其他主机名。 |
| `ORIGIN_NOT_ALLOWED` | 403 | 请求带有的 `Origin` 不属于 Coffer 自己：守护进程的 Web 源、桌面应用，或显式开启的开发源。用于防御来自其他网站的请求。 | 从守护进程或桌面应用打开界面。要从开发源提供界面，用 `COFFER_DEV_CORS=1` 启动守护进程，或把该源列入 `COFFER_CORS_ORIGINS`。 |
| `BAD_REQUEST` | 400 | 某个路由拒绝了请求（例如无效的 `X-Coffer-Actor` 值，或发到 `/mcp` 的 JSON 格式错误）。 | 阅读 `message`；修正请求。 |
| `CURSOR_INVALID` | 400 | 发给分页列表（审计日志、MCP 调用日志、智能体的对话记录会话、聊天对话）的 `cursor` 无法解码，或者是为另一个列表或另一组筛选条件签发的。 | 去掉 `cursor` 重新读第一页，或发送同一列表、同样筛选条件返回的 `next_cursor`。 |
| `NOT_FOUND` | 404 | 没有这个路由或对象，由路由抛出而非领域错误。 | 检查路径；守护进程在 `/api/v1/openapi.json` 向带令牌的调用方提供实时的路由列表。 |
| `FORBIDDEN` | 403 | 路由拒绝了该操作。 | 阅读 `message`。 |
| `CONFIG_INVALID` | 422 | 请求体或查询参数未通过校验，或资源的配置无效。提交的值不会被回显。 | 对照 `/api/v1/openapi.json`（需带令牌）中该路由的 schema 检查请求体。 |
| `INTERNAL_ERROR` | 500 | 意外的失败。完整的 traceback 在守护进程日志中，对应响应的 trace id。 | 运行 `grep <trace-id> ~/.coffer/logs/daemon.log`，或 `coffer log daemon --errors`。 |
| `HTTP_<status>` | 同名状态 | 一个没有具名错误码的普通 HTTP 错误。 | 阅读 `message`。 |

## 资源与生效范围 {#resources-and-scope}

| 错误码 | HTTP | 含义 | 常见修复 |
| --- | --- | --- | --- |
| `RESOURCE_NOT_FOUND` | 404 | 你给的 uid 或名字没有对应的资源。 | 用该类型的 `list` 命令核对名字（例如 `coffer mcp list`）；名字只在同一类型内唯一。 |
| `RESOURCE_ALREADY_EXISTS` | 409 | 该类型已有同名资源。 | 换个名字，或编辑已有的资源。 |
| `UNKNOWN_KIND` | 400 | 该类型不是本守护进程注册的类型。 | 使用已注册的类型，例如 `mcp_server`、`skill` 或 `agent`。 |
| `GENERIC_CREATE_NOT_ALLOWED` | 409 | 这个类型不能通过通用的 `/resources` 端点创建或更新。 | 使用该类型自己的端点或命令（例如 `coffer agent add`、`coffer provider add`）。 |
| `NAME_IMMUTABLE` | 409 | 该资源的类型在注册后就固定了名字，因为智能体会引用它：MCP 服务器的名字是它工具名的前缀，技能的名字就是它的文件夹。智能体的名字就是它的类型，完全不能改。消息会说明重新注册会重置哪些东西。 | 删除该 MCP 服务器或技能，再用新名字重新注册。 |
| `SCOPE_INVALID` | 422 | 生效范围（激活范围）的内容无效，或该类型没有生效范围。 | 发送智能体允许列表，或在支持的类型上使用它的 `scope` 命令（例如 `coffer skill scope <name> --agents a,b`）。见[生效范围](/zh/architecture/resource-framework#reach)。 |
| `RESOURCE_PROTECTED` | 409 | 该资源由 Coffer 自己管理（例如 Coffer 生成的技能），不能被接管或删除。 | 不用管它；Coffer 会维护它。 |
| `RESOURCE_NOT_TOGGLEABLE` | 409 | 该资源的类型不能启用或禁用：每个知识集和记忆分区都始终提供。 | 如果不再需要提供，就删除该资源。 |
| `UPKEEP_ALREADY_RUNNING` | 409 | 该知识集已有一次整理正在进行。 | 等正在进行的整理完成；`coffer daemon status` 和界面都会显示它。 |
| `UNKNOWN_PRUNABLE_TABLE` | 404 | 保留请求指定的表没有保留策略。 | 用 `coffer config list retention.` 列出有效的表。 |
| `ATTENTION_NOT_IGNORABLE` | 409 | 该键下没有可以忽略的提醒项：要么什么都没列出，要么列出的是故障而不是提示。 | 刷新提醒列表；故障要修好，而不是忽略。 |

## 密钥 {#secrets}

| 错误码 | HTTP | 含义 | 常见修复 |
| --- | --- | --- | --- |
| `SECRET_MISSING` | 400 | 所引用的密钥 ref 下没有存储任何密钥。 | 存入它：`coffer secret set <ref>`，或在资源表单中重新填写。 |
| `SECRET_IN_USE` | 409 | 仍有资源引用该密钥，不能删除。消息会列出这些资源。 | 先解除关联或删除那些资源。 |
| `SECRET_LOCKED` | 503 | 系统钥匙串已锁定或不可用，或者一次钥匙串写入无法验证。 | 解锁钥匙串（登录桌面会话）后重试。 |
| `SECRET_UNREADABLE` | 500 | 某个已存的密钥无法用当前主密钥解密。 | 恢复与之匹配的主密钥，或重新填写该密钥。见[密钥存储](/zh/guides/secret-store)。 |
| `MASTER_KEY_MISSING` | 503 | 存在加密的密钥，但主密钥既不在密钥文件中也不在钥匙串中。在守护进程启动时抛出。 | 恢复 `~/.coffer/master.key`（或用 `coffer sync key import` 导入），或者重新填写你的密钥。 |
| `MASTER_KEY_FILE_INVALID` | 422 | 要导入的主密钥文件不存在或不是有效的主密钥，或者 `.cfk` 备份的指纹与其主密钥不符。 | 导入桌面应用写出的主密钥备份。 |
| `MASTER_KEY_PASSPHRASE_WRONG` | 422 | 导入受口令保护的主密钥备份（`.cfk`）时口令错误或没给口令。 | 输入在另一台 Mac 上导出主密钥时设置的口令。 |
| `MASTER_KEY_PASSPHRASE_TOO_SHORT` | 422 | 请求主密钥备份时给的口令不足八个字符。什么都没写入。 | 选一个更长的口令。 |
| `SECRET_BINDING_PENDING` | 409 | 某个密钥将发往一个没有人批准过的去处或目标。什么都没发送。`details.approval_ids` 列出等待中的审批。 | 在 Coffer 桌面应用中批准，或用 `coffer secret reject <id>` 拒绝。见[密钥 → 审批](/zh/guides/secrets#approvals)。 |
| `SECRET_BINDING_REJECTED` | 409 | 有人对这个目的地和目标拒绝过这个密钥，而且没有东西在等待。什么都没发送。`details.approval_ids` 列出被拒绝的审批。 | 更改去处，或在密钥页面再次询问（`POST /api/v1/secrets/approvals/{id}/ask-again`）。见[密钥 → 审批](/zh/guides/secrets#approvals)。 |
| `APPROVAL_NOT_FOUND` | 404 | 没有这个 id 的审批。 | 用 `coffer secret approvals --all` 列出。 |
| `APPROVAL_NOT_PENDING` | 409 | 该审批已被批准、拒绝或取代。 | 无需操作；新的改动会产生新的审批。 |
| `PRESENCE_GRANT_INVALID` | 403 | 一次查看、主密钥备份或审批没有带有效的在场授权：缺失、过期、已用过、属于别的操作或目标，或者不是桌面应用签发的。 | 在 Coffer 桌面应用中操作，它会执行在场检查并签发授权。 |
| `SECRET_NAME_INVALID` | 422 | 独立密钥的名字不是由 `[A-Za-z0-9_.-]` 组成、最多 64 个字符的单个片段。 | 选一个有效的名字，例如 `orders-db`。 |
| `SECRET_NOT_FOUND` | 404 | `coffer run` 指定的独立密钥不在存储中。只有 `secret/<name>` 的值能这样解析；资源的密钥永远不能。 | 存入它：`coffer secret set secret/<name>`。 |

## MCP 服务器与网关 {#mcp-servers-and-the-gateway}

| 错误码 | HTTP | 含义 | 常见修复 |
| --- | --- | --- | --- |
| `UPSTREAM_UNAVAILABLE` | 503 | 上游 MCP 服务器无法连接、已禁用，或不支持该方法。 | 运行 `coffer mcp test <name>`；检查服务器的命令或 URL 以及它的密钥。 |
| `UPSTREAM_TIMEOUT` | 504 | 上游 MCP 服务器没有及时应答。 | 检查服务器；重试。 |
| `TOOL_DISABLED` | 403 | 该工具、资源或提示词在其服务器上被关闭，或服务器不在调用方智能体的生效范围内，或名字无法识别。 | 用 `coffer mcp cap enable <server> tool:<name>` 启用它，或扩大服务器的生效范围。 |
| `INVALID_PREFIX` | 400 | 名字不是 Coffer 的命名空间形式（`<server>__<tool>`、`coffer://<server>/<uri>`）。 | 完全照 `tools/list` 或 `coffer__search_tools` 返回的名字使用。见 [MCP 工具](/zh/reference/mcp-tools#upstream-names)。 |

## 自定义工具 {#custom-tools}

| 错误码 | HTTP | 含义 | 常见修复 |
| --- | --- | --- | --- |
| `NOT_A_CUSTOM_TOOL_GROUP` | 404 | 该名字属于其他传输方式的 MCP 服务器，而不是自定义工具组。 | 用 `coffer mcp` 管理它，或用 `coffer tool list` 列出工具组。 |
| `CUSTOM_TOOL_NOT_FOUND` | 404 | 该工具组中没有这个名字的工具。 | 用 `coffer tool show <group>` 列出它的工具。 |
| `CUSTOM_TOOL_EXISTS` | 409 | 该工具组中已有同名工具。 | 换个名字，或编辑已有的工具。 |
| `OPENAPI_UNREADABLE` | 422 | OpenAPI 文档无法获取、解析或读取：不是 JSON 或 YAML、不是 OpenAPI 3.x、大于 5 MiB，或者 URL 位于回环、私有或链路本地主机上。 | 修正文档，或把私有主机上的规范作为文件导入。 |
| `NOT_IMPORTED_FROM_OPENAPI` | 409 | 对一个工具全部是手动添加的工具组请求了重新导入。 | 没有可重新导入的内容；请手动添加工具。 |
| `OPENAPI_FILE_NEEDED` | 422 | 该工具组是从文件导入的，重新导入需要再次提供那个文件。 | 提供文件：`coffer tool reimport <group> --file <path>`。 |

## 依赖的命令行工具 {#required-clis}

| 错误码 | HTTP | 含义 | 常见修复 |
| --- | --- | --- | --- |
| `CLI_NOT_KNOWN` | 404 | 没有托管技能需要该命令，也没有以该名字添加的命令行工具。 | 用 `coffer cli list` 列出已知的命令。 |
| `CLI_TOOL_EXISTS` | 409 | 已经添加过同名的命令行工具。 | 用 `coffer cli edit` 修改它，或先移除。 |
| `CLI_TOOL_INVALID` | 400 | 命令名、最低版本或登录检查不合法。 | 使用普通的命令名或绝对路径；字段见 `message`。 |
| `CLI_TOOL_NOT_DECLARED` | 404 | 该命令行工具不是手动添加的，因此不能在这里编辑或移除。 | 技能需要的命令要在技能里修改，不在这里。 |

## 智能体与智能体工作目录 {#agents-and-agent-workspaces}

| 错误码 | HTTP | 含义 | 常见修复 |
| --- | --- | --- | --- |
| `AGENT_TYPE_REGISTERED` | 409 | 这个类型的智能体已经注册过。一台机器上每种类型只有一个智能体，并以类型命名。消息会给出已有智能体的 uid。 | 使用已有的智能体。要让它指向另一个目录，运行 `coffer agent edit <name> --config-dir <dir>`。 |
| `AGENT_CONFIG_DIR_REGISTERED` | 409 | 已有智能体注册到这个配置目录。 | 使用已有的智能体，或换一个配置目录。 |
| `AGENT_CONFIG_DIR_MISSING` | 409 | 该智能体的配置目录在本机上不存在。在应用同步过来的智能体时抛出。 | 在本机上安装该智能体，或在这里忽略它。 |
| `PRIVILEGED_PATH` | 422 | 该路径是 Coffer 拒绝管理的系统位置。 | 选择你主目录下的路径。 |
| `SKILL_DIR_NOT_WRITABLE` | 422 | 智能体的技能目录不存在、不是目录或不可写。`details.reason` 说明是哪一种。 | 创建该目录或修正它的权限。 |
| `CONFIG_FILE_NOT_ALLOWED` | 404 | 该配置文件键不是 Coffer 为此类智能体编辑的键。 | 使用智能体详情页列出的键（例如 `settings` 或 `instructions`）；`coffer path agent <agent> config` 会列出这些文件。 |
| `CONFIG_FILE_FORMAT_INVALID` | 422 | 新内容是格式错误的 JSON 或 TOML。磁盘上的文件未改动。 | 修正语法后再保存。 |
| `CONFIG_FILE_STALE` | 409 | 你读取之后，配置文件在磁盘上被改过。 | 重新加载文件，再重新做你的修改。 |
| `AGENT_CONFIG_PARSE_ERROR` | 422 | 磁盘上的某个智能体配置文件无法解析。 | 在编辑器中修复该文件。 |
| `SHIM_NOT_FOUND` | 422 | 在 `PATH` 上和打包位置都找不到 `coffer-mcp-shim` 二进制。 | 重新安装 Coffer，让 `~/.coffer/bin` 中有 shim。见[安装](/zh/start/install)。 |
| `MCP_INSTALL_UNSUPPORTED` | 422 | 这个类型的智能体没有地方安装 Coffer 的 MCP 条目。 | 手动连接客户端；见[连接客户端](/zh/guides/connect-a-client)。 |
| `MCP_ENTRY_NOT_FOUND` | 404 | 智能体的配置文件中没有这个名字的 MCP 条目。 | 刷新智能体的 MCP 列表。 |
| `MCP_ENTRY_PROTECTED` | 422 | 该条目是 Coffer 自己的网关条目。 | 用安装和卸载操作，不要直接编辑它。 |
| `MCP_ENTRY_SOURCE_AMBIGUOUS` | 422 | 该条目存在于多个配置文件中。 | 指明来源文件。 |
| `ADOPT_SECRET_UNRESOLVED` | 422 | 纳入托管一个 MCP 条目时，发现了没有密钥映射的、疑似密钥的环境变量键。 | 纳入托管时把列出的每个键映射到一个密钥 ref。 |
| `ADOPT_SECRET_REF_EXISTS` | 409 | 纳入托管一个 MCP 条目时，把某个密钥键映射到了已有值的 ref，或映射到独立密钥 `secret/<name>`。纳入托管只创建 ref。什么都没写入。 | 把该键映射到一个新的 ref；如果没有任何东西使用已有的密钥，也可以先删除它。 |
| `PLUGIN_NOT_FOUND` | 404 | 没有已安装的插件使用这个标识符。 | 刷新插件列表。 |
| `PLUGIN_TOGGLE_UNSUPPORTED` | 422 | 这个类型智能体的插件不能通过 Coffer 启用或禁用。 | 使用智能体自己的工具。 |
| `PLUGIN_UNINSTALL_UNSUPPORTED` | 422 | 这个类型智能体的插件必须用智能体自己的工具卸载。 | 使用智能体自己的工具。 |
| `PLUGIN_UNINSTALL_FAILED` | 422 | 智能体自己的卸载命令失败了。 | 阅读 `message`；自己运行卸载。 |
| `FS_PATH_NOT_BROWSABLE` | 400 | 文件夹选择器的路径不存在、不是目录或不可读。 | 选另一个文件夹。 |
| `FS_PATH_NOT_OPENABLE` | 400 | 要打开或显示的目标不是绝对路径、不存在，或启动失败。 | 检查路径和首选编辑器设置。 |

## 技能 {#skills}

| 错误码 | HTTP | 含义 | 常见修复 |
| --- | --- | --- | --- |
| `SKILL_INVALID` | 422 | 该技能文件夹不是有效的技能（例如缺少 `SKILL.md` 或其格式错误）。 | 修好文件夹后重新导入。 |
| `SKILL_FILE_STALE` | 409 | 你读取之后，某个技能文件在磁盘上被改过。 | 重新加载，再重新做你的修改。 |
| `UNMANAGED_SKILL_NOT_FOUND` | 404 | 在智能体自己的技能文件夹中找不到这个名字的技能。 | 刷新智能体的技能列表。 |
| `UNMANAGED_SKILL_INVALID` | 422 | 智能体自己的某个技能因为文件夹无效而无法纳入托管。 | 修好它的 `SKILL.md`，再纳入托管。 |
| `SKILL_STAGING_NOT_FOUND` | 404 | 该 id 下没有暂存内容：导入或更新预览已被确认、取消或已过期（暂存只保留一小时，重启后不保留）。 | 重新暂存来源。 |
| `SKILL_ORPHAN_NOT_FOUND` | 404 | 技能存储中没有该名称、且不在你的技能库中的文件夹。 | 刷新技能页面。 |
| `SKILL_COPY_NOT_OURS` | 409 | 删除技能时发现某个智能体的副本不是 Coffer 的链接，所以整个删除被拒绝，什么都没改。`details` 给出该文件夹和智能体。 | 先从主副本恢复那个副本，或自己删除该文件夹。 |
| `SKILL_COPY_NOT_DIFFERING` | 409 | 请求比较或处理的智能体副本并不是挡在 Coffer 链接位置上的文件夹。 | 无需比较：该智能体已经是链接，或那里什么都没有。 |
| `SKILL_NOT_FROM_GIT` | 409 | 该技能不是从 Git 仓库添加的，因此没有可以更新的来源。 | 用 `--force` 从它的仓库重新添加以替换它。 |
| `SKILL_SOURCE_UNREACHABLE` | 502 | git 无法拉取技能的仓库、解析它的 ref 或找到它的文件夹。消息是 git 自己的，已去掉任何凭据；如果缺少 git，`details.handoff` 是给你的智能体的提示词。 | 检查仓库地址、ref 以及你对它的访问权限。 |
| `SKILL_UPDATE_CONFLICT` | 409 | 自固定提交以来技能文件夹被编辑过，接受更新会丢弃这些编辑。 | 保留你的编辑，或接受更新并丢弃它们。 |
| `SKILL_UPDATE_NOT_PENDING` | 409 | “我已合并”给出的提交不是该技能正在等待的更新。 | 重新打开更新，并基于它提供的提交合并。 |

## 知识 {#knowledge}

| 错误码 | HTTP | 含义 | 常见修复 |
| --- | --- | --- | --- |
| `KNOWLEDGE_COLLECTION_NOT_FOUND` | 404 | 调用方看不到这个名字的知识集。 | 用 `coffer knowledge list` 列出知识集。 |
| `KNOWLEDGE_COLLECTION_EXISTS` | 409 | 已存在同名知识集。 | 换一个名字。 |
| `KNOWLEDGE_FILE_NOT_FOUND` | 404 | 该路径下没有文档。 | 浏览知识集的目录，`coffer path knowledge <collection>` 会给出它。 |
| `KNOWLEDGE_FILE_CONFLICT` | 409 | 你读取之后，文档在磁盘上被改过，所以你的保存被拒绝，文件保持原样。`details` 带有 `saved: false` 以及文档的当前内容（`current_body`、`current_fingerprint`）。 | 与当前文本对比后，用新的 fingerprint 再次保存。 |
| `KNOWLEDGE_PATH_UNSAFE` | 400 | 路径跳出了知识根目录、指向隐藏条目，或无法指代一篇文档。 | 使用指向知识集内某篇 Markdown 文档的相对路径。 |
| `KNOWLEDGE_UPLOAD_TOO_LARGE` | 413 | 上传超过了消息中给出的大小上限。 | 拆分文档或上传更小的文件。 |
| `INGEST_REJECTED` | 400 | 上传的内容无法转换。`details.reason` 为 `unsupported_type`、`scanned_pdf`（没有文本层的 PDF）或 `empty_conversion`；`details.doc_type` 给出类型。 | 转成支持的格式；对扫描的 PDF 做 OCR。 |
| `KNOWLEDGE_CURATION_HELD` | 409 | 立即整理被拒绝，因为同步轮次正在等你处理（冲突或确认）。 | 先在同步里处理，再重新点击立即整理。 |
| `KNOWLEDGE_HISTORY_UNAVAILABLE` | 503 | 本机不记录知识历史，通常是因为没装 git。写入仍然可用。 | 安装 git；历史从下一次写入开始记录。 |
| `KNOWLEDGE_VERSION_NOT_FOUND` | 404 | 知识历史中没有这个 id 的版本，或该文档没有这个版本。 | 用 `coffer knowledge history <path>` 或 `coffer knowledge changes` 列出版本。 |
| `KNOWLEDGE_NOT_A_PASS` | 400 | 只有一轮整理可以撤销，而这个版本是其他类型的改动。 | 用 `coffer knowledge restore` 恢复文档的早期版本。 |
| `KNOWLEDGE_UNDO_CONFLICT` | 409 | 之后的改动动过这轮整理涉及的某篇文档（消息中给出），所以撤销被拒绝，什么都没写。 | 改为编辑或恢复那篇文档。 |
| `KNOWLEDGE_NOT_A_DELETE` | 400 | 你要恢复的改动没有删除任何文档或知识集。 | 改为恢复该文档的早期版本。 |
| `KNOWLEDGE_RESTORE_CONFLICT` | 409 | 放回被删除的文档会覆盖该路径上现在的文件。`details` 给出版本和文档；什么都没写。 | 先移走或重命名该路径上的文件，再恢复。 |
| `KNOWLEDGE_ERROR` | 400 | 知识层的其他拒绝。 | 阅读 `message`。 |
| `ENGINE_UNAVAILABLE` | 503 | 操作所需的某个二进制或转换器（ripgrep，或文档转换后端）不可用。 | 重新安装 Coffer；打包附带的二进制中包含它们。 |
| `GREP_PATTERN_INVALID` | 400 | ripgrep 拒绝了某个模式。 | 修正模式。 |

## 记忆 {#memory}

| 错误码 | HTTP | 含义 | 常见修复 |
| --- | --- | --- | --- |
| `MEMORY_NOTE_NOT_FOUND` | 404 | 该分区中没有这个 slug 的笔记。 | 在分区页面上列出笔记。 |
| `MEMORY_RAW_ENTRY_NOT_FOUND` | 404 | 该分区中没有这个 id 的原始条目。 | 刷新；该条目可能已被提炼并移除。 |
| `MEMORY_UNSAFE_PATH` | 400 | 某段路径是隐藏的、全是点，或因其他原因不安全。 | 使用分区内的路径。 |
| `MEMORY_UNREADABLE` | 422 | 某个智能体的原生记忆文件无法解析。 | 修复消息中指出的文件。 |
| `MEMORY_DELIVERY_UNSUPPORTED` | 422 | 这个类型的智能体没有 Coffer 可以安装的记忆 Hook。 | 无；该智能体用自己的文件工具从记忆根目录（`coffer path memory`）读取记忆笔记。 |
| `MEMORY_DELIVERY_CONFIG_INVALID` | 422 | 智能体的设置或 Hook 文件不是 Coffer 能编辑的 JSON 对象。 | 修复该文件，然后重新安装投递。 |
| `MEMORY_TRIGGER_INVALID` | 422 | 某个触发器无法使用：未知的类型、无法编译的模式、没有 `--command` 的 `block` 触发器或没有 `--error` 的 `context` 触发器，或笔记没有写成 `<partition>/<slug>`。什么都没写入。 | 修正消息中指出的字段，再重新添加触发器。 |
| `MEMORY_TRIGGER_NOT_FOUND` | 404 | 没有这个 id 的触发器。 | 用 `coffer memory trigger list` 列出触发器。 |

## 聊天与消息渠道 {#chat-and-channels}

| 错误码 | HTTP | 含义 | 常见修复 |
| --- | --- | --- | --- |
| `CONVERSATION_NOT_FOUND` | 404 | 没有这个 id 的对话。 | 刷新对话列表。 |
| `UNKNOWN_AGENT` | 400 | 对话所用的智能体没有注册智能体提供方。 | 从 `GET /api/v1/agent-providers` 中选择一个智能体。 |
| `AGENT_CONFIG_REJECTED` | 400 | 智能体拒绝了对话的配置，例如未知的模型，或者该类型没有 Coffer 管理的已启用智能体。`details.reason` 是一个简短的标记，如 `model_not_found` 或 `agent_not_managed`。 | 选择该智能体提供的模型，或在「智能体」页面添加或启用该智能体。 |
| `MESSAGE_NOT_FOUND` | 404 | 重发时指定的用户消息不属于该对话。 | 刷新对话；重试那里显示的消息。 |
| `ATTACHMENT_EXPIRED` | 410 | 再次发送（重试）的消息带有一个已被 30 天媒体清理删除的文件；什么都没发送。 | 重新附上文件，发送一条新消息。 |
| `ATTACHMENT_NOT_FOUND` | 422 | 消息引用了一个没有存储过的附件：从未上传，或其文件已被清理。什么都没发送。 | 重新上传该文件。 |
| `ATTACHMENT_TOO_LARGE` | 413 | 网页输入框上传的文件超过了消息中给出的单文件上限。 | 附上更小的文件。 |
| `ATTACHMENT_TYPE_UNSUPPORTED` | 415 | 没有智能体能在一轮对话中使用这种类型的文件（视频、压缩包、可执行文件和其他二进制文件）。 | 附上图片、文档、音频或文本文件。 |
| `CHANNEL_NOT_PAIRED` | 409 | 该消息渠道没有可发送的已配对聊天。 | 配对它：`coffer channel pair <name>`。见[消息渠道](/zh/guides/channels)。 |
| `CHANNEL_PERSON_NOT_FOUND` | 404 | 该消息渠道上没有与所指名字匹配的已配对的人。 | 用 `coffer channel show <name>` 列出已配对的人，再用其中一个的 id。 |
| `CHANNEL_NOT_RUNNING` | 409 | 该消息渠道的适配器没有运行（已禁用或仍在启动）。 | 启用该渠道并等待它连上。 |
| `CHANNEL_SEND_FAILED` | 502 | 消息平台拒绝了发送或发送失败。 | 阅读 `message`；检查机器人的令牌和权限。 |

## 模型提供商 {#model-providers}

| 错误码 | HTTP | 含义 | 常见修复 |
| --- | --- | --- | --- |
| `PROVIDER_SECRET_SOURCE_INVALID` | 422 | 新建连接必须恰好提供密钥值或密钥 ref 中的一个。 | 传 `--secret` 或 `--secret-ref`，不要两个都传。 |
| `PROVIDER_PROTOCOL_LOCKED_WHILE_ACTIVE` | 409 | 有智能体运行在该连接上时，不能更改其协议格式。 | 对运行在它上面的每个智能体运行 `coffer provider builtin <agent_type>`，编辑后再重新切换。 |
| `PROVIDER_DOES_NOT_REACH_AGENT` | 409 | 不能把智能体切到它不生效的连接上：连接或智能体被停用，或连接的作用范围没有指明该智能体。 | 开启该连接，或把该智能体加入它的作用范围，然后再切换。 |
| `PROVIDER_INTERNAL_ONLY` | 409 | `ollama` 连接只供 Coffer 内部引擎使用，不能为智能体开启。 | 改为把它作为内部引擎的默认连接。 |
| `PROVIDER_INTERNAL_DEFAULT_TAKEN` | 409 | 已有另一个连接是内部引擎的默认连接。 | 用 `coffer config set engine.provider <name>` 转移这个标记。 |
| `PROVIDER_TRANSCRIBE_DEFAULT_TAKEN` | 409 | 已有另一个连接是语音转文字的默认连接。 | 用 `coffer config set transcribe.provider <name>` 转移这个标记。 |

## 保险库 {#the-vault}

| 错误码 | HTTP | 含义 | 常见修复 |
| --- | --- | --- | --- |
| `VAULT_FILE_STALE` | 409 | 你读取之后，文件在磁盘上被改过（你在编辑器中的编辑、另一次保存），所以写入被拒绝，而不是覆盖它。 | 重新加载，然后用新的 fingerprint 再次保存。 |
| `VAULT_FILE_INVALID` | 422 | 这次写入会让某个保险库文件无法通过校验。什么都没写入。 | 修正消息中指出的问题。 |
| `VAULT_PATH_INVALID` | 400 | 该路径不是可以读取历史的保险库文件或文件夹，或位于 `secret/` 下。 | 使用相对于保险库的路径，例如 `skills/pdf/`。 |
| `VAULT_VERSION_NOT_FOUND` | 404 | 该版本不在此文件的历史中。 | 从 `coffer vault history` 中选一个。 |
| `VAULT_GIT_FAILED` | 500 | 对保险库仓库的某个 git 操作失败。 | 阅读消息和守护进程日志。 |

## 保险库同步 {#vault-sync}

| 错误码 | HTTP | 含义 | 常见修复 |
| --- | --- | --- | --- |
| `SYNC_NO_REMOTE` | 409 | 没有配置同步远端。 | `coffer sync remote set <url>`。见[保险库同步](/zh/guides/vault-sync)。 |
| `SYNC_NO_PLAINTEXT_FOUND` | 409 | 请求了仍然推送，但上一轮并没有因明文密钥停下。 | 没有需要跳过的内容；运行 `coffer sync now`。见[保险库同步](/zh/guides/vault-sync#when-a-round-finds-a-plaintext-secret)。 |
| `SYNC_REMOTE_INVALID` | 422 | URL 或分支会被 git 当作选项解析，或者不是 git 接受的名字。 | 修正 URL 或分支。 |
| `SYNC_REMOTE_FAILED` | 502 | 针对远端的某个 git 操作失败。消息已脱敏。 | 检查网络访问、远端 URL 和令牌的权限。 |
| `SYNC_NOTHING_STOPPED` | 409 | 你回答了一个冲突、暂停或加入选择，但没有任何同步轮次在等这个回答。 | 无需操作。 |
| `SYNC_CONFLICT_MARKERS_LEFT` | 422 | 手动合并的副本中仍有冲突标记；消息会给出所在行。 | 删除它们，保存，然后把文件标记为已解决。 |
| `SYNC_SECRET_NOT_EDITABLE` | 422 | 停下的一轮中的加密密钥被在编辑器中打开，或被答复为“编辑”。 | 保留本机的版本，或采用另一台的。 |
| `SYNC_ROUND_NOT_FOUND` | 404 | 没有这个 id 的同步轮次。 | 从 `coffer sync history` 中选一个。 |
| `SYNC_NOTHING_TO_ROLL_BACK` | 409 | 该轮次没有应用任何东西，或者它本身就是一次回滚。 | 无需操作。 |
| `SYNC_MACHINE_NOT_FOUND` | 404 | 没有这个 id 的机器共享此保险库。 | 用 `coffer sync machine list` 列出机器。 |
| `SYNC_MACHINE_NAME_INVALID` | 422 | 机器名为空或过长。 | 换一个名字。 |
| `SYNC_CANNOT_RETIRE_SELF` | 422 | 你试图退役当前所在的机器。 | 从另一台机器退役它，或在这里清除同步远端。 |

## 守护进程 {#the-daemon}

| 错误码 | HTTP | 含义 | 常见修复 |
| --- | --- | --- | --- |
| `PORT_OUT_OF_RANGE` | 422 | 端口不在 1024-65535 之间，守护进程永远无法绑定它。`details` 给出该端口和范围。 | 选一个范围内的端口。 |
| `PORT_IN_USE` | 409 | 另一个程序占用了该端口。Coffer 能识别时，`details.holder` 给出它的名称和 pid。 | 停掉那个程序，或换一个端口。 |

## 实验功能 {#experimental-features}

| 错误码 | HTTP | 含义 | 常见修复 |
| --- | --- | --- | --- |
| `FEATURE_DISABLED` | 404 | 该路由或资源属于一个在本机上已关闭的实验功能。`details.feature` 给出功能名。 | `coffer config set feature.<feature> on`。见[实验功能](/zh/guides/experimental-features)。 |
| `FEATURE_UNKNOWN` | 404 | 该键不是实验功能。键只有 `knowledge`、`memory`、`sync` 和 `models`。 | 用 `coffer config list feature.` 列出键。 |
| `FEATURE_PINNED` | 409 | `COFFER_FEATURES` 在守护进程的生命周期内固定了该功能。 | 修改 `COFFER_FEATURES` 并重启守护进程。 |

## 启动错误 {#startup-errors}

这些错误在守护进程启动、开始处理请求之前抛出。它们出现在 `~/.coffer/logs/daemon.log` 和 `coffer daemon start` 的输出中。

| 错误码 | HTTP | 含义 | 常见修复 |
| --- | --- | --- | --- |
| `DB_SCHEMA_TOO_NEW` | 409 | `~/.coffer/runs.db` 被更新或不同的 Coffer 构建迁移过。万一出现在响应中，就使用这个状态码。 | 升级 Coffer，或恢复数据库迁移前的备份。见[文件与目录](/zh/reference/filesystem)。 |
| `VAULT_MIGRATION_REQUIRED` | 409 | 该 home 仍把状态保存在 `coffer.db` 中，来自保险库布局之前的 Coffer。 | 停止守护进程并运行 `coffer migrate`。见[升级现有的 Coffer](/zh/guides/upgrading)。 |
| `VAULT_MIGRATION_ON_HOLD` | 409 | `coffer migrate --rollback` 已把 home 恢复原状，并留下了暂停标记。 | 运行之前的构建，或先运行 `coffer migrate --resume` 再运行 `coffer migrate`。 |
| `VAULT_MIGRATION_REFUSED` | 409 | `coffer migrate` 不会处理当前状态的 home，例如一次中途停下的升级。 | 按消息操作；升级做到一半时，先运行 `coffer migrate --rollback`。 |
| `GIT_MISSING` | 500 | 保险库需要 `git`，但没有找到。需要 git 的路由也会返回它。 | 按适合这台机器的方式安装 git；错误的 `details.handoff` 是给你的智能体的提示词。 |

`MASTER_KEY_MISSING` 也可能让启动失败；见[密钥](#secrets)。低于 2.40 的 `git` 也会让守护进程停下，但没有错误码：日志会给出找到的版本，并附上一段可以交给你的智能体、让它升级 git 的提示词。

## 聊天轮次错误 {#chat-turn-errors}

失败的聊天轮次以对话事件流上的 `turn_error` 事件结束，而不是 HTTP 错误。它的 `code` 取以下之一：

| 错误码 | 含义 |
| --- | --- |
| `stream_ended` | 智能体在轮次结束前停止了响应：它的进程退出了或连接断开了。 |
| `turn_timeout` | 智能体在空闲窗口内没有产生任何事件，所以轮次被取消、智能体进程被停止。已产生的部分回复会保留。窗口由 `COFFER_TURN_IDLE_TIMEOUT_SECONDS` 设置（[配置](/zh/reference/configuration)）。 |
| `daemon_stopped` | Coffer 在轮次完成前停止了。 |
| `empty_prompt` | 没有可发送的用户消息。 |
| `sdk_connect_error`、`sdk_stream_error`、`sdk_error` | Claude Code 无法启动、它的流失败了，或它报告了错误。消息会说明是哪种。 |
| `codex_connect_error`、`codex_stream_error`、`codex_error` | Codex 的同类错误。 |
| `INTERNAL_ERROR` | Coffer 内部的意外失败，包括排队的轮次无法启动。 |

## MCP 网关错误 {#mcp-gateway-errors}

经由 `/mcp` 的调用以 JSON-RPC 错误应答，而不是上面的错误信封。

| JSON-RPC 错误码 | 含义 |
| --- | --- |
| `-32600` | 无效请求：请求体不是 JSON-RPC 对象，或没有 `method`。 |
| `-32000` | `TOOL_DISABLED`：该能力被关闭、不在智能体的生效范围内，或无法识别。 |
| `-32603` | 其他任何失败。Coffer 的错误会带上它的消息；其他错误一律报告为 `internal error: <ExceptionClass>`，以免泄漏任何上游内容。 |

失败的内置工具则会返回一个带 `isError: true` 的带内结果；见[MCP 工具](/zh/reference/mcp-tools#how-built-in-tools-answer)。

## 命令行退出码 {#cli-exit-codes}

每个 `coffer` 命令都以下列退出码之一退出。守护进程返回的 HTTP 错误按状态映射。

| 退出码 | 名称 | 何时 |
| --- | --- | --- |
| `0` | OK | 成功。 |
| `1` | Generic | 其他任何失败，包括 `FEATURE_DISABLED`（会打印开启该功能的命令）。 |
| `2` | Invalid usage | 参数或选项组合有误。 |
| `3` | Daemon unreachable | 守护进程无法启动或不再应答；命令行会建议查看 `~/.coffer/logs/daemon.log`。 |
| `4` | Not found | 守护进程返回了 `404`。 |
| `5` | Conflict | 守护进程返回了 `409`。 |
| `6` | Invalid input | 守护进程返回了 `400` 或 `422`。 |
| `7` | Upstream test failed | `coffer mcp test` 无法初始化上游服务器。 |
| `8` | Secret issue | 错误码为 `SECRET_MISSING` 或 `SECRET_LOCKED`。 |
| `9` | Waiting for approval | 改动已保存，但其中的某个密钥正在 Coffer 桌面应用中等待审批（`SECRET_BINDING_PENDING`，或一个指明待审批的 `202`）。命令打印了 `waiting for approval in the Coffer app` 以及审批的 id。在应用中批准，或加 `--wait` 重新运行。见[密钥 → 审批](/zh/guides/secrets#approvals)。 |

出错时传 `--verbose`（`coffer -v …`）可以打印完整的 traceback 和 HTTP 上下文。

## MCP shim 退出码 {#mcp-shim-exit-codes}

`coffer-mcp-shim` 是智能体启动的 stdio 桥。

| 退出码 | 何时 |
| --- | --- |
| `0` | 正常退出：智能体关闭了 stdin，或 shim 收到了 `SIGTERM`。 |
| `1` | 未捕获的致命错误。 |
| `3` | 守护进程无法连接，也无法启动。 |

## 相关内容 {#related}

- [故障排查](/zh/guides/troubleshooting)
- [可观测性](/zh/architecture/observability) — trace id、守护进程日志和 `coffer log`
