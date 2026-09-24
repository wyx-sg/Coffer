import { defineConfig } from 'vitepress'
import { withMermaid } from 'vitepress-plugin-mermaid'

const repo = 'https://github.com/wyx-sg/Coffer'

// ---- sidebar sections ----
const start = [
  {
    text: 'Getting started',
    items: [
      { text: 'What is Coffer?', link: '/start/' },
      { text: 'Why Coffer', link: '/start/why-coffer' },
      { text: 'Install', link: '/start/install' },
      { text: 'Quickstart', link: '/start/quickstart' },
      { text: 'Core concepts', link: '/start/concepts' },
    ],
  },
]

const guides = [
  {
    text: 'Agents and tools',
    items: [
      { text: 'Agents', link: '/guides/agents' },
      { text: 'Connect a client', link: '/guides/connect-a-client' },
      { text: 'MCP servers', link: '/guides/mcp-servers' },
      { text: 'Model providers', link: '/guides/providers' },
      { text: 'Credentials', link: '/guides/credentials' },
    ],
  },
  {
    text: 'What agents share',
    items: [
      { text: 'Skills', link: '/guides/skills' },
      { text: 'Knowledge', link: '/guides/knowledge' },
      { text: 'Memory', link: '/guides/memory' },
    ],
  },
  {
    text: 'Talking to agents',
    items: [
      { text: 'Chat', link: '/guides/chat' },
      { text: 'Channels', link: '/guides/channels' },
      { text: 'Telegram', link: '/guides/channels-telegram' },
      { text: 'SeaTalk', link: '/guides/channels-seatalk' },
    ],
  },
  {
    text: 'Apps',
    items: [
      { text: 'Web UI', link: '/guides/web-ui' },
      { text: 'Desktop app', link: '/guides/desktop-app' },
    ],
  },
  {
    text: 'Operating Coffer',
    items: [
      { text: 'Running the daemon', link: '/guides/daemon' },
      { text: 'Vault sync', link: '/guides/vault-sync' },
      { text: 'Activity and audit', link: '/guides/activity' },
      { text: 'Experimental features', link: '/guides/experimental-features' },
      { text: 'Troubleshooting', link: '/guides/troubleshooting' },
      { text: 'FAQ', link: '/guides/faq' },
    ],
  },
]

const architecture = [
  {
    text: 'Foundations',
    items: [
      { text: 'Overview', link: '/architecture/' },
      { text: 'Design principles', link: '/architecture/design-principles' },
      { text: 'Resource framework', link: '/architecture/resource-framework' },
      { text: 'Layering and code layout', link: '/architecture/layering' },
    ],
  },
  {
    text: 'Runtime',
    items: [
      { text: 'Daemon and processes', link: '/architecture/daemon' },
      { text: 'MCP gateway', link: '/architecture/mcp-gateway' },
      { text: 'Chat and turns', link: '/architecture/chat' },
      { text: 'Persistence', link: '/architecture/persistence' },
    ],
  },
  {
    text: 'Subsystems',
    items: [
      { text: 'Knowledge', link: '/architecture/knowledge' },
      { text: 'Memory', link: '/architecture/memory' },
      { text: 'Vault sync', link: '/architecture/vault-sync' },
    ],
  },
  {
    text: 'Cross-cutting',
    items: [
      { text: 'Security model', link: '/architecture/security' },
      { text: 'Observability', link: '/architecture/observability' },
      { text: 'Distribution and releases', link: '/architecture/distribution' },
      { text: 'Decision records', link: '/architecture/decisions' },
    ],
  },
]

const reference = [
  {
    text: 'Reference',
    items: [
      { text: 'CLI', link: '/reference/cli' },
      { text: 'MCP tools', link: '/reference/mcp-tools' },
      { text: 'REST API', link: '/reference/rest-api' },
      { text: 'Configuration', link: '/reference/configuration' },
      { text: 'Files and directories', link: '/reference/filesystem' },
      { text: 'Error codes', link: '/reference/error-codes' },
      { text: 'Glossary', link: '/reference/glossary' },
    ],
  },
]

const contributing = [
  {
    text: 'Contributing',
    items: [
      { text: 'Overview', link: '/contributing/' },
      { text: 'Development setup', link: '/contributing/development' },
      { text: 'Spec-driven workflow', link: '/contributing/spec-workflow' },
      { text: 'Testing', link: '/contributing/testing' },
      { text: 'Frontend', link: '/contributing/frontend' },
      { text: 'Security policy', link: '/contributing/security' },
    ],
  },
]

export default withMermaid(
  defineConfig({
    title: 'Coffer',
    description:
      'Coffer is a local-first vault for AI coding agents: one place on your machine for the MCP servers, skills, knowledge, memory and model providers every agent shares.',
    base: '/Coffer/',
    cleanUrls: true,
    lastUpdated: true,
    lang: 'en',
    head: [['meta', { name: 'theme-color', content: '#c96442' }]],
    markdown: {
      theme: { light: 'github-light', dark: 'github-dark' },
    },
    mermaid: {},
    themeConfig: {
      search: { provider: 'local' },
      outline: { level: [2, 3] },
      socialLinks: [{ icon: 'github', link: repo }],
      editLink: {
        pattern: `${repo}/edit/main/docs-site/:path`,
        text: 'Edit this page on GitHub',
      },
      footer: {
        message: 'Released under the MIT License.',
        copyright: 'Coffer contributors',
      },
      nav: [
        { text: 'Get started', link: '/start/', activeMatch: '^/start/' },
        { text: 'Guides', link: '/guides/agents', activeMatch: '^/guides/' },
        { text: 'Architecture', link: '/architecture/', activeMatch: '^/architecture/' },
        { text: 'Reference', link: '/reference/cli', activeMatch: '^/reference/' },
        { text: 'Contributing', link: '/contributing/', activeMatch: '^/contributing/' },
        {
          text: 'Links',
          items: [
            { text: 'Releases', link: `${repo}/releases` },
            { text: 'Specifications', link: `${repo}/tree/main/openspec/specs` },
            { text: 'Decision records', link: `${repo}/tree/main/docs/decisions` },
          ],
        },
      ],
      sidebar: {
        '/start/': start,
        '/guides/': guides,
        '/architecture/': architecture,
        '/reference/': reference,
        '/contributing/': contributing,
      },
    },
  }),
)
