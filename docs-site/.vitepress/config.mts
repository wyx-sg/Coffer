import { defineConfig } from 'vitepress'
import { withMermaid } from 'vitepress-plugin-mermaid'
import { readFileSync } from 'node:fs'

let refSidebar: any[] = []
try {
  refSidebar = JSON.parse(
    readFileSync(new URL('./reference-sidebar.json', import.meta.url), 'utf8'),
  )
} catch {}

// ---- sidebar sections ----
const guide = [
  {
    text: 'Guide',
    items: [
      { text: 'Introduction', link: '/guide/introduction' },
      { text: 'Download & install', link: '/guide/install' },
      { text: 'Getting Started', link: '/guide/getting-started' },
      { text: 'Concepts', link: '/guide/concepts' },
    ],
  },
  {
    text: 'Using the vault',
    items: [
      { text: 'Register an MCP server', link: '/guide/register-server' },
      { text: 'Connect a client', link: '/guide/connect-client' },
      { text: 'Agents', link: '/guide/agents' },
      { text: 'Skills', link: '/guide/skills' },
      { text: 'Knowledge', link: '/guide/knowledge' },
      { text: 'Channels', link: '/guide/channels' },
      { text: 'Sync', link: '/guide/sync' },
      { text: 'Credentials', link: '/guide/credentials' },
    ],
  },
  {
    text: 'Apps',
    items: [{ text: 'Web UI', link: '/guide/web-ui' }],
  },
]

const arch = [
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

const contrib = [
  {
    text: 'Contributing',
    items: [
      { text: 'Contributing', link: '/contributing/' },
      { text: 'Security', link: '/contributing/security' },
    ],
  },
]

export default withMermaid(
  defineConfig({
    title: 'Coffer',
    description: 'Local-first AI agent vault — one secure, shared interface for every AI agent on your machine: MCP tools, skills, knowledge, chat, channels, and vault sync.',
    base: '/Coffer/',
    cleanUrls: true,
    lastUpdated: true,
    appearance: false, // light-only: no dark mode (spec ui-shell)
    ignoreDeadLinks: true,
    lang: 'en',
    themeConfig: {
      search: { provider: 'local' },
      socialLinks: [{ icon: 'github', link: 'https://github.com/wyx-sg/Coffer' }],
      nav: [
        { text: 'Guide', link: '/guide/introduction' },
        { text: 'Architecture', link: '/architecture/overview' },
        { text: 'Reference', link: '/reference' },
        { text: 'Contributing', link: '/contributing/' },
      ],
      sidebar: {
        '/guide/': guide,
        '/architecture/': arch,
        '/contributing/': contrib,
        '/reference': refSidebar,
      },
    },
  }),
)
