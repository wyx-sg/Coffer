# Coffer UI 视觉语言

> English: [visual-language.md](./visual-language.md)
>
> 给所有动 `frontend/` 的 agent 看的配套参考。token 的事实来源是 [`frontend/tailwind.config.js`](../../frontend/tailwind.config.js)；本文件记录约定。

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
- `status.ok` / `status.warn` / `status.err` — 健康胶囊（resource 列表、daemon-offline banner 用）。

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
- 空 / 加载 / 错误态是一等公民——绝不允许界面在数据加载时没有内容。每个界面自带空/加载/错误处理
  （如 `components/chat/ChatEmptyState.tsx`）；目前还没有共享的 `EmptyState` 基础件——当第二个功能
  需要同样形状时再抽一个出来。
- 状态类显示（daemon offline、capability disabled、工具调用健康度）走 `status.*` token，不要用裸
  `green/amber/emerald` 调色板类。字号用内置 scale（`text-sm`/`text-xs`/…），绝不用逐组件的 `text-[Npx]`。

## 不确定时

如果还没有合适的 token，就在引入它的同一份 PR 里扩展 Tailwind 配置，并在 PR 描述里说明这次新增。别把 magic number 内联到组件里。
