# 前端 — React / TypeScript / Vite

> English: [frontend.md](./frontend.md)

Coffer 的前端是桌面应用的 Web 界面（`frontend/`）：生产环境跑在 Tauri 壳里，
开发环境跑在 Vite dev server（`make dev`）。本文件是这层界面的工程规范——与
[`stack.md`](./stack.md)（后端）、
[`visual-language.md`](./visual-language.md)（视觉设计）并列。
动 `frontend/src` 之前先读它。

若本文件与代码不一致：以符合下文「canonical（标准）」一列的代码为准，修掉离群者。
若某条规则挡住了你，停下来提出来——不要另起一套并行模式。

## 1. 技术栈

- **React 18 + TypeScript 5**（strict）、**Vite** 构建、**React Router v6**。
- **TanStack Query v5** 管所有服务端状态。不引入 Redux / Zustand / MobX。
- 有 OpenAPI 契约的接口用 **openapi-fetch + openapi-typescript** 生成类型化客户端；
  其余用一个共享的手写 helper（§4）。
- 设计系统用 **shadcn/ui + Radix + Tailwind**（§6）。
- 表单用 **react-hook-form + zod**，文案用 **i18next**，图标用 **lucide-react**。

功能专属的库由第一个需要它的 spec 引入（比如 markdown 渲染器），不预装。

## 2. 目录结构（标准）

只有一套。功能 `X` 严格落在这些位置：

```
src/pages/XPage.tsx              — 列表/索引页；详情页用 XDetailPage.tsx
src/components/x/                 — 功能组件（文件名 PascalCase）
src/lib/hooks/useX.ts            — X 的所有 query + mutation（见 §3）
src/lib/api/x.ts                 — /api/v1/x 的 wire 类型 + 请求函数
src/i18n/locales/{en,zh}.json    — 挂在顶层 "x" 键下
```

- **数据获取写在 hook 文件里，绝不内联进组件。** 页面/组件调 `useX()`，不直接调
  `useQuery`/`useMutation`。（历史债：`src/kinds/knowledge_base` 和
  `src/kinds/memory` 把 query 内联在详情页里——那是要迁移**离开**的模式，不要照抄。）
- **`src/kinds/<name>/` 只用于 kind 注册表的 UI 模块**（资源框架自动渲染的
  `KindUIModule`）。新的普通功能用上面的 `pages` + `components` + `hooks` + `api`
  布局，不要新建 `kinds/<name>/` 模块。
- UI 基础组件放 `src/components/ui/`（shadcn）。跨功能 helper 放 `src/lib/`。

## 3. 状态管理

| 状态类型 | 存放位置 |
| --- | --- |
| 服务端数据（任何来自 daemon 的） | TanStack Query，经 `useX` hook |
| 临时 UI 状态（展开/折叠、草稿输入） | 组件内本地 `useState` |
| 需跨刷新存活的用户偏好 | `localStorage`，经 `src/lib/preferences.ts` / `auth.ts` |
| **可寻址**的应用状态（当前打开哪个会话/资源） | **URL**（路由参数），不是 `useState` |

最后一行很关键：任何用户期望在刷新、深链、后退后仍存在的东西，必须是路由参数
（`/chat/:id`、`/agents/:name`），而非本地状态。「当前选中哪一项」是导航，不是 UI 状态。

没有全局 store。跨组件的服务端数据通过 query 缓存共享（同一 query key → 同一份数据），
不经 Context。唯二的 Context provider 是 `QueryClientProvider` 和 `ToastProvider`。

### Query key

层级数组，第一段 = 功能名词。详情/子资源在父 key 上扩展，这样前缀失效能命中整棵子树：

```ts
["agents"]                       // 列表
["agents", name]                 // 单个 agent
["agents", name, "config-files"] // 该 agent 的子资源
```

- **不要用扁平连字符 key**（`["kb-documents", name]`）——它们无法作为一组失效。
  Memory/KB 现在这么写，新代码不许。
- 从 hook 文件导出 key 构造函数（`conversationKey(id)`、`messagesKey(id)`），
  不要在调用处内联字符串数组。

## 4. API 层

`src/lib/api/` 下每个请求模块都经 `src/lib/auth.ts`（`getCofferBaseUrl`、
`getCofferToken`）解析 base URL + token，并发送 `X-Coffer-Token` +
`X-Coffer-Actor: "ui"`。**actor 永远是 `"ui"`**（`kinds/memory/api.ts` 里的
`"user"` 是已知离群项）。

存在两种请求风格，按「该 spec 是否提供了 OpenAPI 契约」来选：

- **生成客户端**（`getApiClient()`，基于 `src/lib/api/client.ts` + 代码生成的
  `types.ts`）——当接口在 OpenAPI spec 里时优先用，路径/响应全类型安全。
- 否则用**共享手写 helper**。**目标态：唯一一个共享 `call<T>()`**（拼 URL + 处理
  204 + `{error:{code,message}}` → `ApiError`）。今天 `call<T>()` 在 `api/chat.ts`、
  `agents.ts`、`models.ts`、`skills.ts` 里各复制一份——你动到其中一个时，把它提到共享的
  `src/lib/api/call.ts`，让模块 import 它。不要再加第五份拷贝。

所有错误收敛到 `ApiError(code, message)`（`src/lib/api/errors.ts`）。用
`translateApiError(t, error)` 展示——它把 `errors.<CODE>` i18n key 映射出来，
服务端 message 作兜底。绝不直接显示裸错误字符串。

流式（chat SSE）是唯一在 TanStack Query 之外的路径：`src/lib/chat/streamClient.ts`
里一个类型化的 async-generator。wire 事件解析留在那里；在 hook（`useChatTurn`）里
累积成视图状态，不要写进组件。

## 5. Mutation 与缓存失效

默认模式——成功即失效，失败即 toast：

```ts
return useMutation({
  mutationFn: (vars) => xApi.update(vars),
  onSuccess: () => void qc.invalidateQueries({ queryKey: ["x"] }),
  onError: (e) => toast.error(translateApiError(t, e)),
});
```

- **`onError` → toast 是默认**，不是可选。（现有若干 hook 漏了它——那是缺口，不是先例。）
- **乐观 `setQueryData`** 只用在延迟对用户可见、且结构易于就地修改的场景（如重命名、
  切模型）。之后仍要失效，让服务端保持权威。
- **删除**先移除详情 + 子 key（`removeQueries`）再失效列表，避免过期详情页重新拉到 404。
- 批量/表格操作走 `src/lib/hooks/useBulkMutate.ts`（一条汇总 toast + 一次失效爆发），
  绝不逐行 toast。
- `qc.invalidateQueries(...)` 前缀 `void`（即发即忘）。

## 6. 组件与设计系统

- **从 `src/components/ui/` 基础组件搭起**（shadcn：`Button`、`Dialog`、`Select`、
  `Textarea`…）。基础组件已覆盖的控件不要手搓。
- **只用命名导出。** `export function Foo()`。无 default export。
- **文件头注释**：第一行 `// src/path` + 一行用途。
- 条件类名用 **`cn()`**（`src/lib/utils`）。除有文档说明的主题桥接外，不用内联 `style`。
- **只用语义 token**（`text-muted-foreground`、`bg-card`、`border-border`）。
  健康/状态表面用 `status.ok|warn|err` token——**不要**用裸 `green/amber/emerald`
  调色板类。（`statusColors.ts`、`ToolCallCard`、`ApprovalCard` 现在绕过了——动到就修。）
- **只用 type scale**——`text-sm`/`text-xs`/…，绝不 `text-[11px]`。圆角用规定集合
  （卡片 `rounded-lg`、控件 `rounded-md`、chip `rounded-sm`）。见
  [`visual-language.md`](./visual-language.md)。
- **仅亮色。** 不要加 `dark:` 变体——没有暗色 token 集,它们是死样式。
- 文件保持聚焦；组件涨过几百行就是该拆分的信号。一个文件一个组件，测试同目录（§8）。

## 7. TypeScript 与 i18n

- **strict** + `noUnusedLocals/Parameters`。`src` 里 **零 `any`**（非 lint 强制——靠自觉）。
  用 `unknown` + 收窄代替。
- props/对象形状用 `interface`，联合/别名用 `type`。仅类型导入用 `import type`。
- props：在签名里解构一个本地 `interface Props { … }`；不直观的 prop 加 JSDoc。
- **每个用户可见字符串都过 `t(...)`。** 不硬编码文案，不硬编码 aria-label。
- key 是功能命名空间下的嵌套 camelCase 点分路径（`chat.composer.placeholder`）。
  **en 与 zh 严格 key 对齐**——同一次改动里两边都加；`src/i18n/locales.test.ts` 守门。

## 8. 测试

- **Vitest + Testing Library**，`*.test.tsx` 与被测单元同目录。
- 通过组件/hook 测**行为**，不测实现。用真实 `QueryClientProvider` 渲染；只 mock 网络
  边界（`api` 模块或 `streamClient`）。
- 新组件/hook 与其测试同一次提交。验收场景覆盖遵循 [`testing.md`](./testing.md) 的 marker。
- 聚焦检查跑 `cd frontend && npx vitest run <file>`；`make verify` 跑全套 + lint + tsc。

## 9. 收敛清单（已知债 → 目标态）

你在这些附近工作时，往目标态迁移；不要扩大债务：

1. **唯一 `call<T>()`** 放 `src/lib/api/call.ts`；四个手写 API 模块 import 它，不再各持一份。
2. **数据获取全部进 hook 文件**——把 `kinds/knowledge_base`、`kinds/memory` 详情页里
   内联的 `useQuery`/`useMutation` 抽到 `useKnowledgeBase` / `useMemoryStore` hook。
3. **query key 全部层级化**——用 `["memory", …]` / `["kb", …]` 取代扁平的
   `["memory-facts", …]` / `["kb-documents", …]`。
4. **actor 头全部 `"ui"`**——修 `kinds/memory/api.ts`。
5. **每个可见失败的 mutation 都加 `onError` toast`**。
