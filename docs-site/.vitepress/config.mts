import { defineConfig } from 'vitepress'
import { withMermaid } from 'vitepress-plugin-mermaid'
import { readFileSync } from 'node:fs'

let refSidebar: { en: any[]; zh: any[] } = { en: [], zh: [] }
try {
  refSidebar = JSON.parse(
    readFileSync(new URL('./reference-sidebar.json', import.meta.url), 'utf8'),
  )
} catch {}

// ---- EN sidebar sections ----
const guideEn = [
  {
    text: 'Guide',
    items: [
      { text: 'Introduction', link: '/guide/introduction' },
      { text: 'Download & install', link: '/guide/install' },
      { text: 'Getting Started', link: '/guide/getting-started' },
      { text: 'Register an MCP server', link: '/guide/register-server' },
      { text: 'Connect a client', link: '/guide/connect-client' },
      { text: 'Web UI', link: '/guide/web-ui' },
      { text: 'Desktop app', link: '/guide/desktop' },
      { text: 'Concepts', link: '/guide/concepts' },
    ],
  },
]

const archEn = [
  {
    text: 'Architecture',
    items: [
      { text: 'Principles', link: '/architecture/principles' },
      { text: 'System overview', link: '/architecture/overview' },
      { text: 'Daemon & processes', link: '/architecture/processes' },
      { text: 'Resource framework', link: '/architecture/resource-framework' },
      { text: 'Layering & boundaries', link: '/architecture/layering' },
      { text: 'Surfaces', link: '/architecture/surfaces' },
      { text: 'Request lifecycle', link: '/architecture/request-lifecycle' },
      { text: 'Persistence', link: '/architecture/persistence' },
      { text: 'Security', link: '/architecture/security' },
      { text: 'Audit & accountability', link: '/architecture/audit' },
      { text: 'Observability', link: '/architecture/observability' },
      { text: 'Distribution', link: '/architecture/distribution' },
    ],
  },
]

const contribEn = [
  {
    text: 'Contributing',
    items: [
      { text: 'Contributing', link: '/contributing/' },
      { text: 'Security', link: '/contributing/security' },
    ],
  },
]

// ---- ZH sidebar sections ----
const guideZh = [
  {
    text: '指南',
    items: [
      { text: '介绍', link: '/zh/guide/introduction' },
      { text: '下载与安装', link: '/zh/guide/install' },
      { text: '快速开始', link: '/zh/guide/getting-started' },
      { text: '注册 MCP server', link: '/zh/guide/register-server' },
      { text: '接入客户端', link: '/zh/guide/connect-client' },
      { text: 'Web UI', link: '/zh/guide/web-ui' },
      { text: '桌面应用', link: '/zh/guide/desktop' },
      { text: '核心概念', link: '/zh/guide/concepts' },
    ],
  },
]

const archZh = [
  {
    text: '架构',
    items: [
      { text: '设计原则', link: '/zh/architecture/principles' },
      { text: '系统总览', link: '/zh/architecture/overview' },
      { text: '守护进程与进程模型', link: '/zh/architecture/processes' },
      { text: 'Resource 框架', link: '/zh/architecture/resource-framework' },
      { text: '分层与边界', link: '/zh/architecture/layering' },
      { text: 'Surfaces', link: '/zh/architecture/surfaces' },
      { text: '请求全链路', link: '/zh/architecture/request-lifecycle' },
      { text: '持久化', link: '/zh/architecture/persistence' },
      { text: '安全', link: '/zh/architecture/security' },
      { text: '审计与问责', link: '/zh/architecture/audit' },
      { text: '可观测性', link: '/zh/architecture/observability' },
      { text: '分发', link: '/zh/architecture/distribution' },
    ],
  },
]

const contribZh = [
  {
    text: '参与贡献',
    items: [
      { text: '贡献指南', link: '/zh/contributing/' },
      { text: '安全', link: '/zh/contributing/security' },
    ],
  },
]

export default withMermaid(
  defineConfig({
    title: 'Coffer',
    description: 'Local-first AI agent vault — manage all your MCP servers from one place.',
    base: '/Coffer/',
    cleanUrls: true,
    lastUpdated: true,
    appearance: false, // light-only: no dark mode (DESIGN.md §9, spec 002)
    ignoreDeadLinks: true,
    srcExclude: ['**/DESIGN.md', '**/IMPLEMENTATION-PLAN.md'],
    themeConfig: {
      search: { provider: 'local' },
      socialLinks: [{ icon: 'github', link: 'https://github.com/wyx-sg/Coffer' }],
    },
    locales: {
      root: {
        label: 'English',
        lang: 'en',
        themeConfig: {
          nav: [
            { text: 'Guide', link: '/guide/introduction' },
            { text: 'Architecture', link: '/architecture/overview' },
            { text: 'Reference', link: '/reference' },
            { text: 'Contributing', link: '/contributing/' },
          ],
          sidebar: {
            '/guide/': guideEn,
            '/architecture/': archEn,
            '/contributing/': contribEn,
            '/reference': refSidebar.en,
          },
        },
      },
      zh: {
        label: '中文',
        lang: 'zh-Hans',
        link: '/zh/',
        themeConfig: {
          nav: [
            { text: '指南', link: '/zh/guide/introduction' },
            { text: '架构', link: '/zh/architecture/overview' },
            { text: '参考', link: '/zh/reference' },
            { text: '参与贡献', link: '/zh/contributing/' },
          ],
          sidebar: {
            '/zh/guide/': guideZh,
            '/zh/architecture/': archZh,
            '/zh/contributing/': contribZh,
            '/zh/reference': refSidebar.zh,
          },
        },
      },
    },
  }),
)
