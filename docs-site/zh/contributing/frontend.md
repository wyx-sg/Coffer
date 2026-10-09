---
title: 前端
description: Coffer React Web 界面的约定：技术栈、目录布局、生成的 API 客户端、TanStack Query 的 key 和 hook、设计系统、i18n、共享页面模式和测试。
---

# 前端 {#frontend}

本页概括 `frontend/` 的约定。它是一个 React 应用，由守护进程作为 Web 界面提供，也由桌面壳承载。改动 `frontend/src` 之前请先读这一页。具有约束力的规则在 [`.agents/frontend.md`](https://github.com/wyx-sg/Coffer/blob/main/.agents/frontend.md)（工程）和 [`.agents/visual-language.md`](https://github.com/wyx-sg/Coffer/blob/main/.agents/visual-language.md)（视觉设计）里。如果某条规则挡住了你，请在 pull request 里提出来，而不是另起一套平行的模式。

## 技术栈 {#stack}

| 关注点 | 选择 |
| --- | --- |
| 界面 | React 18 和 TypeScript 5（strict、`noUnusedLocals`、`noUnusedParameters`），用 Vite 构建 |
| 路由 | React Router v6，路由在 `src/router.tsx` |
| 服务端状态 | TanStack Query v5。没有 Redux、Zustand 或其他全局 store |
| API 类型 | openapi-typescript，从每项能力的 OpenAPI 契约生成，而契约又从后端模型生成 |
| 组件 | 基于 Radix 原语的 shadcn/ui，用 Tailwind 做样式 |
| 表单 | react-hook-form 和 zod |
| 文案 | i18next，带英文和中文文案目录 |
| 图标 | lucide-react |
| 测试 | Vitest 和 Testing Library（jsdom） |

某个功能专用的库，随第一个需要它的改动一起引入。不会「以防万一」预先安装任何东西。

同一份构建产物运行在三种宿主里：由守护进程在自己的地址上提供、开发时由 Vite 提供、由[桌面壳](/zh/guides/desktop-app)作为本地资源加载。`src/lib/auth.ts` 屏蔽了你所处的宿主：每个宿主都通过同样的两个全局变量提供 API base URL 和令牌。令牌从不持久化，因为守护进程每次启动都会生成一个新的。

## 目录布局 {#folder-layout}

一个功能 `X` 恰好分布在这些地方：

```text
src/pages/XPage.tsx               list page; XDetailPage.tsx for the detail page
src/components/x/                 feature components, dialogs, tables
src/lib/hooks/useX.ts             every query and mutation for X
src/lib/api/x.ts                  request functions and wire types for /api/v1/x
src/lib/api/queryKeys.ts          every query key builder, for all features
src/lib/x/                        pure helpers the feature owns
src/i18n/locales/{en,zh}.json     copy under the top-level "x" key
```

- 组件从不直接调用 `useQuery` 或 `useMutation`，而是调用 `src/lib/hooks/` 里的某个 hook。[`useSkills.ts`](https://github.com/wyx-sg/Coffer/blob/main/frontend/src/lib/hooks/useSkills.ts) 是一个紧凑的例子。
- 各资源类型遵循同样的布局。没有按类型划分的注册表。
- 导入只向下指：`pages` 到 `components` 再到 `lib`。`src/lib/**` 不得导入 `src/components/**` 或 `src/pages/**`，`src/components/**` 不得导入 `src/pages/**`，由 ESLint 强制。两层都要用的类型或纯函数（状态色调、触达模式、保存编排）放在 `lib/`。唯一的例外是 `useToast`，它是变更 hook 要调用的界面原语 hook。多个测试套件共用的测试工具放在 `src/test/`。
- 共享原语放在 `src/components/ui/`，共享的界面组件（`PageHeader`、`DataTable`、`EmptyState`）放在 `src/components/`。复用已有的跨功能工具：`lib/agents/display.ts`。
- 路由在 `router.tsx` 里用 `lazyPage()` 做代码分割。列表页立即加载。详情页，以及任何引入编辑器或 markdown 处理流水线的页面，在第一次访问时加载。
- 出于历史原因保留了一个命名例外：MCP 服务器列表是 `pages/ResourcesPage.tsx`，路由为 `mcp-servers`。
- 实验功能的页面包在 `FeatureGate` 里。当该功能在本机被关闭时，它渲染“未找到”页面，因为关闭的功能看起来就像不存在：它的侧边栏和命令面板入口通过同一份注册表被略去，没有提示，也没有“开启”按钮。见[实验功能](/zh/guides/experimental-features)。

文件大小门禁在这里同样适用：页面 ≤ 200 行，组件 ≤ 250 行，hook 或工具函数 ≤ 300 行。

## API 层 {#the-api-layer}

每个请求都从同一个模块 `src/lib/api/client.ts` 发出。它通过 `src/lib/auth.ts` 解析 base URL 和令牌，并发送 `X-Coffer-Token` 和 `X-Coffer-Actor: ui`。`src` 里没有其他地方调用 `fetch`，唯一的例外是聊天事件流。

- **生成的类型。** 每项能力的契约都从后端模型生成，`npm run codegen`（或 `make frontend-codegen`；`make contracts` 会运行两步）对每一份契约运行 openapi-typescript，写出 `src/lib/api/generated/<capability>.ts`。永远不要手动编辑 `generated/`。`npm run lint` 以 `codegen:check` 开头，所以只重新生成了契约却没重新生成类型，CI 会失败。
- **类型化客户端**（`src/lib/api/client.ts` 中的 `getApiClient()`，基于 openapi-fetch）知道每项能力的路径，所以经由它的调用会检查路径、参数、请求体和响应。
- **请求函数** 位于 `src/lib/api/x.ts`，调用类型化客户端，并用 `unwrap`（2xx 响应体）、`unwrapOptional`（响应体或 `204`）或 `unwrapVoid`（无响应体）处理结果，把 `{ error: { code, message, details } }` 变成 `ApiError`。没有其他传输方式，也没有第二个辅助函数；hook 和组件都不直接调用 `getApiClient()` 或 `fetch`。
- **没有手写的传输类型。** `src/lib/api/x.ts` 中的传输类型是生成 schema 的别名，比如 `components["schemas"]["ProviderOut"]`。当契约与后端实际发送的内容不符时，修复后端模型并重新生成，永远不要改 TypeScript。`codegen:check` 会拒绝这些模块以及 `src/lib/hooks/` 下导出的 interface，或拼写出对象形状的 type，也拒绝 `unwrap*` 调用上的对象字面量类型参数。从不跨越传输层的类型要带一个 `@ui-only` 标签说明这一点；该标签是唯一的豁免。

错误统一收敛到 `ApiError(code, message)`。用 `translateApiError(t, error)` 显示它们，它会在文案目录里查找 `errors.<CODE>`，找不到就退回到服务端的消息。永远不要显示原始错误字符串。

## Query key 与 hook {#query-keys-and-hooks}

每个 key 都来自 [`src/lib/api/queryKeys.ts`](https://github.com/wyx-sg/Coffer/blob/main/frontend/src/lib/api/queryKeys.ts) 中的某个构建函数。key 是分层数组，第一段是功能名词。详情的 key 在列表 key 的基础上延伸，所以按前缀失效会清掉整棵子树：

```ts
export const agentsKey = ["agents"] as const;
export const agentKey = (uid: string) => ["agents", uid] as const;
export const agentConfigFilesKey = (uid: string) => ["agents", uid, "config-files"] as const;
```

- 在其他任何地方写字面量 `queryKey: ["…"]` 都是 ESLint 错误。
- 用资源的 UID 做 key，永远不用名字，这样重命名不会让缓存失联。
- 避免扁平的连字符 key（`["knowledge-documents", path]`），它们无法作为一组失效。

mutation 成功时让缓存失效，出错时弹出 toast：

```ts
export function useRemoveSkill() {
  const qc = useQueryClient();
  const onError = useSkillToastError();          // toast.error(translateApiError(t, e))
  return useMutation({
    mutationFn: (uid: string) => skillsApi.remove(uid),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: skillsKey });
    },
    onError,
  });
}
```

- `onError` toast 是默认做法。只有当组件在行内渲染错误时才去掉它，并用注释说明。
- 只在延迟肉眼可见、而且补丁很简单（比如重命名）的地方使用乐观的 `setQueryData`。之后仍然要失效一次。
- 删除操作会移除详情和子资源的查询，然后让列表失效，这样过期的详情视图就不会重新请求到一个 404。
- 表格批量操作走 `useBulkMutate`：一条汇总 toast，一次集中失效。

### 状态放在哪里 {#where-state-lives}

| 状态 | 位置 |
| --- | --- |
| 来自守护进程的任何东西 | TanStack Query，经由一个 `useX` hook |
| 临时 UI 状态（展开、折叠、输入草稿） | 组件里的 `useState` |
| 刷新后仍要保留的偏好 | `localStorage`，读写都用 try/catch 保护，存储被禁用时回退到默认值（页大小和编辑器见 `src/lib/preferences.ts`） |
| 打开的是哪一项 | 路由参数：`/channels/:uid`、`/agents/:type` |
| 选中的是哪个详情 tab | 路径的最后一段：`/<kind>/<id>/<tab>`，默认 tab 对应不带该段的路径（`src/lib/detailTabs.ts`） |
| 选中的是哪个文件 | 通过 `useSearchParams` 读取的查询参数（`?file=`） |

凡是用户期望在刷新、深链接或后退按钮之后依然保留的东西，都应该放在 URL 里。

## 设计系统 {#design-system}

用 `src/components/ui/` 中的 shadcn 原语搭建界面：`Button`、`Dialog`、`Select`、`Tabs`、`Tooltip`、`Skeleton`、`ConfirmDialog` 等。不要手搓已有原语覆盖的控件。用 `Tooltip` 而不是原生 `title=`，用 `Skeleton` 而不是自定义的闪烁块。行操作都是明确的按钮。唯一的菜单是 `Menu`（`src/components/ui/menu.tsx`），即智能体行和智能体页头上的「⋯」：建立在 `Popover` 原语上的一小列命令，支持方向键导航，破坏性的项用 danger 角色显示。

token 来自 [`frontend/tailwind.config.js`](https://github.com/wyx-sg/Coffer/blob/main/frontend/tailwind.config.js)，建立在其上的视觉词汇来自 [`.agents/visual-language.md`](https://github.com/wyx-sg/Coffer/blob/main/.agents/visual-language.md)：

- **颜色：只用语义角色。** 使用 Foundations 角色：`surface`（以及 `sidebar`、`raised`、`sunken`、`selected`、`hover`、`footer`）、`border` / `border-subtle`、`text` / `text-muted` / `text-subtle`、`accent`（以及 `soft`、`text`、`foreground`），还有状态角色 `success`、`warning`、`danger` 和 `neutral`，每个都带一个 `-soft` 填充色。shadcn 的名字（`background`、`card`、`primary`、`destructive` 等）作为指向某个角色的别名保留。健康状态颜色只通过 `src/lib/statusColors.ts` 获得，它把一种色调（`ok`、`warn`、`error`、`muted`）映射到状态角色上。`src` 中不会出现 `green-500` 这类原始调色板 class。
- **字号：配置里的刻度。** 使用 `text-2xs`（11 px）到 `text-xl`，`display` 只用于品牌，永远不要用 `text-[11px]`。应用以 13 px 为基准，层级靠字重（`font-book`、`font-label`、`font-bold`、`font-heavy`）和颜色体现。`font-sans` 用于界面，`font-mono` 用于代码和标识符。
- **间距：** Tailwind 默认的 4 px 刻度。`max-w-content`（72 rem）限制工作台页面的宽度，`max-w-prose`（60 ch）限制正文的宽度。
- **圆角：** 随表面增大的固定档位：最小的标记用 `rounded-xs`（4 px），所有控件用 `rounded-md`（7 px），浮在页面上方的东西用 `rounded-2xl`（12 px）。
- **浅色和深色。** 每个颜色 token 在 `src/index.css` 里都有浅色值和深色值。`src/lib/theme.ts` 把查看者的选择（跟随系统、浅色或深色）解析到 `<html data-theme>` 上，深色集合重新指向这些变量，所以不要加 `dark:` 变体。
- 条件 class 用 `cn()`，所有时间戳都用 `src/lib/utils` 中的 `formatDateTime`。

缺少某个 token 时，在同一个 pull request 里把它加到 Tailwind 配置中，并在描述里说明。不要内联魔法数字。

## 页面模式 {#page-patterns}

| 模式 | 用法 |
| --- | --- |
| `PageHeader` | 列表页和详情页共用的唯一页头：标题旁放 `badges`，右侧放 `actions`，标题下一行 `subtitle`。它没有返回按钮：页面从不带「← 列表」链接，标题栏的后退和前进箭头是唯一的历史控件。详情页操作保持固定顺序：生效范围、测试或刷新、编辑、删除 |
| `DataTable` | 唯一的列表表格。传入 `isLoading`，让表头在骨架行上方保持挂载；传入 `emptyAction` 作为行动号召。每张表格上生效范围列的表头都是 `resources.cols.reach` |
| 生效范围 | 处处是三种模式：**关闭**、**所有智能体**、**指定智能体**。控件在你修改时就保存，触发按钮显示徽标，从不显示“N / M 个智能体”。列表上没有生效范围筛选：行上显示徽标，列表按状态分组 |
| 密钥 | 只来自 Coffer。`SecretField` 选一个已存的密钥，或接受一个粘贴的值并随表单存到密钥页面；请求头或环境变量的行（`KeyValueSecretRows`）是明文，字段末尾有 🔑 选择器。没有密钥/明文切换、没有替换按钮、没有“已存储”徽标 |
| 交接 | 一个拆分按钮，**交给 &lt;Agent&gt; ▾**（`AgentHandoff`）：按钮在首选终端里启动默认的交接智能体并把提示词作为第一条消息，▾ 菜单里是另一个智能体和**复制提示词**。提示词始终来自守护进程。Coffer 自己能做的事（重试、测试、重新检查）从不使用它 |
| 抽屉 | 640 宽（带侧栏的编辑器，比如自定义工具抽屉，为 1040），从标题栏下方开始 |
| 提示（toast） | 一个标题，可选再带第二行（`description`），说明保留了什么或添加了什么 |
| `EmptyState` | 每一个空列表、未找到页面和零结果搜索：图标、标题、描述、操作 |
| `Skeleton` | 加载状态保持界面的真实形状。永远不要显示空白屏幕或 "Loading…" 卡片 |
| `ConfirmDialog` | 每一次不可逆操作的确认，永远不要用 `window.confirm`；可以恢复的删除（知识文档或知识集）不弹它，而是弹一条带**撤销**的提示。mutation 运行期间它接收 `pending`，只在 `onSuccess` 中关闭，所以删除失败时对话框会带着错误保持打开，错误标题由 `errorTitle` 给出（「无法删除 sentry」）；`confirmLabel` 始终是静止时的文案，进行中的文案是 `pendingLabel` |
| `Alert`（`warning` 变体） | 非致命的提醒，比如一个不寻常但能工作的配置。不是 toast，也不是破坏性警告 |
| 改动即保存 | 设置、生效范围和模型提供商在控件改动时立即写入，写入失败就在控件下方说明；没有保存按钮，也没有未保存守卫，因为 Web 界面没有文档编辑器：文件以只读方式显示，带在编辑器中打开和在访达中显示。对话框的取消是 ghost 按钮 |
| tab 放进 URL | 详情页把 tab 放在路径里，`/<kind>/<id>/<tab>` |
| 标题优先于名字 | 带标题的类型（提供商、消息渠道）的资源，设置了 `title` 时显示它，否则显示 `name`。智能体、MCP 服务器、技能、知识集和记忆分区没有标题，始终显示名字：MCP 服务器和技能的名字一旦注册就固定不变（`409 NAME_IMMUTABLE`），智能体的名字就是它的类型，所以它们的编辑表单既不提供重命名，也不提供标题 |

代码风格：只用具名导出，每个文件一个组件。每个文件第一行是一条注明路径和用途的注释，比如 `// src/components/EmptyState.tsx — …`。props 声明为局部的 `interface Props`。仅类型的导入用 `import type`。`src` 里没有 `any`，用 `unknown` 再收窄。

## 国际化 {#internationalisation}

界面通过 `src/i18n/locales/en.json` 和 `zh.json` 提供英文和简体中文。英文是回退语言。这是一项产品功能。文档站和 README 也是双语的；仓库里的其他文档都只有英文（见[参与贡献](/zh/contributing/#docs-site-in-two-languages)）。

- 每一个面向用户的字符串都经过 `t(...)`，包括 `aria-label`。
- key 是功能顶层 key 下嵌套的 camelCase 路径，比如 `handoff.promptCopied`。
- 在同一个改动里把每个 key 同时加到**两份**文案目录。`src/i18n/locales.test.ts` 会让任何只存在于一份目录中的 key 失败。
- 后端错误码和审计事件类型也需要条目：每个错误对应一个 `errors.<CODE>`。当你新增一个 `CofferError` 子类或 `AuditEventType` 时，重新生成对等测试读取的 fixture：

  ```sh
  PYTHONPATH=backend .venv/bin/python scripts/dump_i18n_backend_keys.py
  ```

  `make lint` 会以 `--check` 运行同一个脚本，所以新加的错误码如果没有 fixture 条目（也就没有翻译），CI 会失败。

## 测试 {#testing}

- 把 `*.test.tsx` 放在它覆盖的模块旁边，新组件或新 hook 要在同一个提交里带上它的测试。
- 通过组件或 hook 测试行为，而不是测试其实现。用真实的 `QueryClientProvider` 渲染，只 mock 网络边界：`src/lib/api/*` 模块，或者 `streamClient`。
- 用 `@/test/acceptance` 中的 `acceptance(spec, scenario, fn)` 标记场景覆盖。见[测试](/zh/contributing/testing#acceptance-markers)。
- Radix `Tabs` 在 `mousedown` 上切换，而不是 `click`。在测试中对 tab 触发器使用 `fireEvent.mouseDown`，否则 tab 不会切换，后面的断言可能会因为错误的原因通过。
- 用 `cd frontend && npx vitest run src/path/File.test.tsx` 运行单个文件。`make verify-unit` 运行整个套件，`make lint` 额外加上 ESLint、`tsc` 和 knip。和 CI 一样使用 Node 20。

浏览器层面的流程属于 `e2e/web/specs/` 下的 Playwright `web` 项目。见[端到端测试](/zh/contributing/testing#end-to-end-tests-with-playwright)。

## 相关 {#related}

- [Web 界面指南](/zh/guides/web-ui)
- [测试](/zh/contributing/testing)
- [开发环境搭建](/zh/contributing/development#wire-contracts-and-frontend-codegen)
- [`web-ui` 规格](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/web-ui/spec.md)
