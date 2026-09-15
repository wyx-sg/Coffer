# Coffer UI 视觉语言

> English: [visual-language.md](./visual-language.md)
>
> 给所有动 `frontend/` 的 agent 看的配套参考。token 的事实来源是 [`frontend/tailwind.config.js`](../frontend/tailwind.config.js)；本文件记录约定。

## 事实来源

`frontend/tailwind.config.js` 是 spacing、color、radius、typography、容器宽度等所有 token 的唯一事实来源。不要新设一套并行的 CSS 变量，也不要写 ad-hoc 内联样式值；要扩展就改 Tailwind 配置，再复用其中的 token。

## 配色

所有语义色都是 HSL 变量 (`hsl(var(--name))`)，按主题解析。重设计阶段只有浅色。

语义 token（在 `tailwind.config.js` 的 `theme.extend.colors` 中定义）：

- `background` / `foreground` — 页面底色。
- `card` / `card-foreground` — 卡片底面与其上文字。
- `popover` / `popover-foreground` — 下拉与对话框。
- `primary` / `primary-foreground` — 主行动 ("Add MCP server"、"Save")。
- `secondary` / `secondary-foreground` — 次行动、未激活 tab。
- `muted` / `muted-foreground` — 禁用 / 占位文字。
- `accent` / `accent-foreground` — hover 与选中态。
- `destructive` / `destructive-foreground` — 删除 / 移除。
- `border`、`input`、`ring` — 表面边、输入边、聚焦环。
- `status.ok` / `status.warn` / `status.err` — 健康胶囊（resource 列表、daemon-offline banner 用）。组件只经 `frontend/src/lib/statusColors.ts` 取用。
- `highlight` / `highlight-active` — 搜索或选择正指向的那一行 / 那一项，以及当前激活的那一个；「你正在看的就是这个」只用这两个 token。

选语义名，不选底层色相。需要新色时优先加一个新的语义 token，不要在组件里写死 hex / hsl。

## 排版

`fontFamily.sans` 是默认 UI 字体（系统栈 + Inter / Roboto 兜底）。`fontFamily.serif` 留给长文 (Source Serif)。`fontFamily.mono` 留给代码、命令片段与标识符 (`SFMono-Regular` / `Menlo` 兜底)。

用 Tailwind 内置的字号刻度 (`text-sm`、`text-base`、`text-lg`、`text-xl`、`text-2xl`)，不要在组件里写像素值。同一界面内的标题按刻度逐级递进；不跳级。

## 间距

继续使用 Tailwind 默认的 4 px 刻度 (`p-4`、`gap-6`、`space-y-3` ……)。`container` 工具类居中内容，外边距 `2rem`，`2xl` 断点设在 1400 px。`maxWidth.content` (72 rem) 限制工作台页面宽度；`maxWidth.prose` (60 ch) 限制长文段宽。

## 圆角

`borderRadius.lg` / `md` / `sm` / `xl` 都派生自 `--radius`，调一个根变量即可整体重设。卡片用 `rounded-lg`，按钮 / 输入用 `rounded-md`，行内 chip 用 `rounded-sm`。

## 组合规则

- 从 `frontend/src/components/ui/` 里的 shadcn 基础件搭界面，不要为每个页面发明新的包装。
- 空 / 加载 / 错误态是一等公民——绝不允许界面在数据加载时没有内容。`components/EmptyState.tsx`
  是共享的空态基础件（icon、标题、描述、行动）——所有列表 / 未找到 / 零结果界面都用它。加载态用
  `components/ui/skeleton.tsx` 保住界面的真实形状：`DataTable` 拿到 `isLoading` 就在已挂载的表头下
  渲染骨架行，详情页渲染一个 `Skeleton` 标题，而不是一片空白或一张「加载中…」卡片。
- 非致命的提醒（能用但不寻常的配置、没有指向任何 agent 的 reach）用 `Alert` 的 `warning` 变体——
  卡片底色上的 status-warn 边框与图标——不是 destructive alert，也不是 toast。
- 状态类显示（daemon offline、capability disabled、工具调用健康度）走 `status.*` token，不要用裸
  `green/amber/emerald` 调色板类。字号用内置 scale（`text-sm`/`text-xs`/…），绝不用逐组件的 `text-[Npx]`。
- 侧边栏始终存在。`md` 及以上展开为带文字的导航栏并可折叠；`md` 以下就是只有图标的窄栏，
  窄视口保留导航，而不是把它藏进抽屉。

## 不确定时

如果还没有合适的 token，就在引入它的同一份 PR 里扩展 Tailwind 配置，并在 PR 描述里说明这次新增。别把 magic number 内联到组件里。
