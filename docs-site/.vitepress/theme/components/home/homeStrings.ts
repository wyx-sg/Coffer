export type Lang = "en" | "zh";

export const PROMPT =
  "Install Coffer on this machine by following https://wyx-sg.github.io/Coffer/start/install — pick the install path that fits this machine (a release build if one is published for this OS and architecture, otherwise from source). Ask me before running anything with sudo or editing my shell profile. When it is installed, check it with `coffer daemon status`. Then tell me to open Coffer's Agents page and press Connect on each coding agent installed here (Claude Code, Codex); the dialog shows which config files it will change. Do not handle any credentials: if a step needs a login, tell me what to do instead.";

export const SHELL_CMD =
  "curl -fsSL --proto '=https' --tlsv1.2 https://wyx-sg.github.io/Coffer/install.sh | sh";

export const RELEASES = "https://github.com/wyx-sg/Coffer/releases/latest";
export const GITHUB = "https://github.com/wyx-sg/Coffer";

export const STR = {
  en: {
    h1: "One setup for all your AI coding agents.",
    lead: "Everything your AI coding agents share — MCP servers, tools, skills, model providers, knowledge — set up once on your Mac. Claude Code and Codex both use it, and it stays in files you own.",
    start: "Get started",
    install: "Install",
    tabDesktop: "Desktop app",
    tabAgent: "Ask your agent",
    tabShell: "Shell",
    download: "Download for Mac",
    dlMeta: "Apple silicon · .dmg",
    dlNote: "Open it and drag Coffer to Applications. The app includes the CLI.",
    other: "Other ways to install",
    copyPrompt: "Copy prompt",
    copyCmd: "Copy",
    copied: "Copied",
    note: "Prebuilt for macOS on Apple silicon. On other machines, install from source.",
    shot: "The Coffer app open on Overview",
    exp: "Experimental",
    allGuides: "All guides",
    groups: [
      {
        label: "What every agent shares",
        items: [
          ["plug", "MCP servers and tools", "Register a server or turn any HTTP API into tools. Every agent reaches them through one endpoint.", "MCP servers", "/guides/mcp-servers", false],
          ["layers", "Skills", "Import a skill library once. Coffer links it into each agent you choose.", "Skills", "/guides/skills", false],
          ["swap", "Model providers", "Store a provider once, switch agents to it, and see what each one uses.", "Model providers", "/guides/providers", true],
          ["book", "Knowledge", "Plain Markdown collections every agent reads and adds to.", "Knowledge", "/guides/knowledge", true],
        ],
      },
      {
        label: "Working with your agents",
        items: [
          ["chat", "Conversations", "Drive Claude Code or Codex from the browser, with the folder and model you pick.", "Conversations", "/guides/chat", false],
          ["send", "Channels", "Message your agents from Telegram or SeaTalk, in chats, groups and threads.", "Channels", "/guides/channels", false],
          ["memory", "Memory", "What one agent learns about a repository, the others know too.", "Memory", "/guides/memory", true],
          ["sync", "Vault sync", "Keep the same vault on every Mac through a git remote you own.", "Vault sync", "/guides/vault-sync", true],
        ],
      },
    ],
    how: "How it works",
    howLead: "One daemon on your Mac sits between your agents and the files they share.",
    arch: "Architecture overview",
    you: "You manage it from",
    youItems: ["Desktop app", "Web UI", "CLI", "Telegram / SeaTalk"],
    agents: { title: "Your agents", sub: "One entry in each config", rows: [["CC", "Claude Code", ""], ["CX", "Codex", ""], ["", "Any MCP client", "by hand"]] },
    coffer: { title: "Coffer", sub: "One daemon on 127.0.0.1", rows: [["plug", "MCP gateway", "/mcp"], ["swap", "Model proxy", "providers"], ["layers", "Delivery", "skills, config"]], foot: "Nothing listens beyond loopback." },
    vault: { title: "Vault", sub: "~/.coffer", rows: [["folder", "skills/", ""], ["folder", "knowledge/", ""], ["folder", "memory/", "read-only"], ["folder", "coffer.db", ""], ["folder", "secrets", "encrypted"]], foot: "Plain files in a git repository." },
    remote: { title: "Git remote", sub: "Optional", note: "Each Mac keeps a full copy." },
    arrows: ["MCP", "reads, writes", "pull, push"],
    diagramLabel: "You manage Coffer from the app, the web UI, the CLI or a chat channel. Agents reach Coffer over MCP; Coffer reads and writes the vault, which can sync with a git remote.",
    takeaways: [
      ["The agent’s files stay in charge.", "Coffer writes only the entries it manages and keeps a", ".bak", "of each file it changes."],
      ["Reach decides who gets what.", "Each server and skill reaches every agent, a chosen few, or none.", "", ""],
      ["No hosted service.", "There is no account. Cloud services appear only as the providers and servers you choose.", "", ""],
    ],
    pathH: "New to Coffer? Read these five pages in order.",
    path: [
      ["What is Coffer?", "The problem, what it manages, what it is not.", "/start/"],
      ["Core concepts", "Daemon, vault, resource, reach: the words the docs use.", "/start/concepts"],
      ["Quickstart", "Connect an agent and share a server. About 15 minutes.", "/start/quickstart"],
      ["Architecture overview", "Every moving part, and the four data flows.", "/architecture/"],
      ["Principles", "The invariants every change is held to.", "/architecture/principles"],
    ],
    after: ["After that, go to the ", "Guides", " for a task, or the ", "Reference", " for a command."],
  },
  zh: {
    h1: "一次配置，所有 AI 编程智能体共用。",
    lead: "AI 编程智能体共用的一切——MCP 服务器、工具、技能、模型提供商、知识——在你的 Mac 上只配一次。Claude Code 和 Codex 都能用，全部留在你自己的文件里。",
    start: "开始使用",
    install: "安装",
    tabDesktop: "桌面 app",
    tabAgent: "交给智能体",
    tabShell: "Shell",
    download: "下载 Mac 版",
    dlMeta: "Apple 芯片 · .dmg",
    dlNote: "打开后把 Coffer 拖进「应用程序」。app 自带命令行工具。",
    other: "其他安装方式",
    copyPrompt: "复制提示词",
    copyCmd: "复制",
    copied: "已复制",
    note: "预编译版本支持 Apple 芯片的 macOS；其他机器请从源码安装。",
    shot: "打开概览页的 Coffer app",
    exp: "实验性",
    allGuides: "全部指南",
    groups: [
      {
        label: "所有智能体共用",
        items: [
          ["plug", "MCP 服务器与工具", "注册服务器，或把任何 HTTP API 变成工具。每个智能体都通过同一个端点使用。", "MCP 服务器", "/guides/mcp-servers", false],
          ["layers", "技能", "技能库只导入一次，Coffer 链接进你选的每个智能体。", "技能", "/guides/skills", false],
          ["swap", "模型提供商", "提供商只存一次，切换智能体过去，并查看各自的用量。", "模型提供商", "/guides/providers", true],
          ["book", "知识", "普通 Markdown 文集，每个智能体都能读、能补充。", "知识", "/guides/knowledge", true],
        ],
      },
      {
        label: "和智能体一起工作",
        items: [
          ["chat", "对话", "在浏览器里驱动 Claude Code 或 Codex，文件夹和模型由你选。", "对话", "/guides/chat", false],
          ["send", "渠道", "在 Telegram 或 SeaTalk 里给智能体发消息，私聊、群聊和话题都行。", "渠道", "/guides/channels", false],
          ["memory", "记忆", "一个智能体在某个仓库学到的，其他智能体也知道。", "记忆", "/guides/memory", true],
          ["sync", "保险库同步", "通过你自己的 git 远端，在每台 Mac 上保持同一个保险库。", "保险库同步", "/guides/vault-sync", true],
        ],
      },
    ],
    how: "工作原理",
    howLead: "一个守护进程运行在你的 Mac 上，站在智能体和它们共享的文件之间。",
    arch: "架构总览",
    you: "你从这里管理它",
    youItems: ["桌面 app", "Web UI", "CLI", "Telegram / SeaTalk"],
    agents: { title: "你的智能体", sub: "每个配置里一条入口", rows: [["CC", "Claude Code", ""], ["CX", "Codex", ""], ["", "任何 MCP 客户端", "手动"]] },
    coffer: { title: "Coffer", sub: "一个守护进程，127.0.0.1", rows: [["plug", "MCP 网关", "/mcp"], ["swap", "模型代理", "提供商"], ["layers", "投递", "技能、配置"]], foot: "只监听本机回环地址。" },
    vault: { title: "保险库", sub: "~/.coffer", rows: [["folder", "skills/", ""], ["folder", "knowledge/", ""], ["folder", "memory/", "只读"], ["folder", "coffer.db", ""], ["folder", "secrets", "已加密"]], foot: "git 仓库里的普通文件。" },
    remote: { title: "Git 远端", sub: "可选", note: "每台 Mac 都有完整副本。" },
    arrows: ["MCP", "读写", "拉取、推送"],
    diagramLabel: "你从 app、Web UI、CLI 或聊天渠道管理 Coffer。智能体通过 MCP 访问 Coffer；Coffer 读写保险库，保险库可以与 git 远端同步。",
    takeaways: [
      ["智能体自己的文件说了算。", "Coffer 只写它管理的条目，改动的每个文件都留一份", ".bak", "。"],
      ["Reach 决定谁拿到什么。", "每个服务器和技能可以给所有智能体、选定的几个，或一个都不给。", "", ""],
      ["没有托管服务。", "没有账号。云服务只会以你选的提供商和服务器出现。", "", ""],
    ],
    pathH: "第一次用 Coffer？按顺序读这五页。",
    path: [
      ["什么是 Coffer？", "它解决什么问题、管什么、不是什么。", "/start/"],
      ["核心概念", "守护进程、保险库、资源、reach：文档通用的词。", "/start/concepts"],
      ["快速上手", "连接一个智能体并共享一个服务器，约 15 分钟。", "/start/quickstart"],
      ["架构总览", "所有组件和四条数据流。", "/architecture/"],
      ["原则", "每次改动都要遵守的不变量。", "/architecture/principles"],
    ],
    after: ["读完之后，做具体任务看", "指南", "，查命令看", "参考", "。"],
  },
} as const;

export const ICONS: Record<string, string> = {
  plug: '<path d="M9 3v5M15 3v5M6 8h12v3a6 6 0 0 1-12 0zM12 17v4"/>',
  layers: '<path d="m12 3 9 5-9 5-9-5 9-5z"/><path d="m3 13 9 5 9-5"/>',
  swap: '<path d="M4 8h13l-3-3M20 16H7l3 3"/>',
  folder: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
  book: '<path d="M4 5.5A1.5 1.5 0 0 1 5.5 4H19v14H5.5A1.5 1.5 0 0 0 4 19.5z"/><path d="M4 19.5A1.5 1.5 0 0 0 5.5 21H19v-3"/>',
  chat: '<path d="M5 5h14a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1h-8l-4 3v-3H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1z"/>',
  send: '<path d="M21 3 10 14M21 3l-7 18-4-7-7-4z"/>',
  memory: '<path d="M12 3a6 6 0 0 0-6 6c0 2.2 1.2 3.6 2 4.5V17h8v-3.5c.8-.9 2-2.3 2-4.5a6 6 0 0 0-6-6zM9 21h6"/>',
  sync: '<path d="M20 11a8 8 0 0 0-14.5-4.5L4 8M4 4v4h4M4 13a8 8 0 0 0 14.5 4.5L20 16M20 20v-4h-4"/>',
  branch: '<circle cx="6" cy="6" r="2"/><circle cx="6" cy="18" r="2"/><circle cx="18" cy="8" r="2"/><path d="M6 8v8M18 10c0 4-4 4-10 7"/>',
  arrow: '<path d="M5 12h14M13 6l6 6-6 6"/>',
  chev: '<path d="m9 6 6 6-6 6"/>',
  copy: '<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V6a2 2 0 0 1 2-2h8"/>',
  check: '<path d="m5 12 5 5 9-10"/>',
  download: '<path d="M12 4v11M7 10l5 5 5-5M5 20h14"/>',
};
