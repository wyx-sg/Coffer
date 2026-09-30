import { defineConfig, type DefaultTheme } from 'vitepress'
import { withMermaid } from 'vitepress-plugin-mermaid'
import sidebarSource from './sidebar.json' with { type: 'json' }

const repo = 'https://github.com/wyx-sg/Coffer'

// The site ships in two locales: English at the root and Simplified Chinese
// under /zh/, page for page. Both sidebars come from one file, sidebar.json,
// where every entry carries its English and Chinese label side by side, so the
// two can never list different pages. scripts/check_docs_locales.py (in
// `make lint`) checks that each entry's page exists in both trees.
type Lang = 'en' | 'zh'
type Label = Record<Lang, string>
type SourceItem = { text: Label; link: string }
type SourceGroup = { text: Label; items: SourceItem[] }
type Section = 'start' | 'guides' | 'architecture' | 'reference' | 'contributing'

const sections = sidebarSource as Record<Section, SourceGroup[]>

function prefix(lang: Lang): string {
  return lang === 'en' ? '' : `/${lang}`
}

function sidebar(lang: Lang): DefaultTheme.SidebarMulti {
  const out: DefaultTheme.SidebarMulti = {}
  for (const [section, groups] of Object.entries(sections)) {
    out[`${prefix(lang)}/${section}/`] = groups.map((group) => ({
      text: group.text[lang],
      items: group.items.map((item) => ({
        text: item.text[lang],
        link: `${prefix(lang)}${item.link}`,
      })),
    }))
  }
  return out
}

const navLabels: Record<Lang, Record<string, string>> = {
  en: {
    start: 'Get started',
    guides: 'Guides',
    architecture: 'Architecture',
    reference: 'Reference',
    contributing: 'Contributing',
    links: 'Links',
    releases: 'Releases',
    specs: 'Specifications',
    decisions: 'Decision records',
  },
  zh: {
    start: '入门',
    guides: '指南',
    architecture: '架构',
    reference: '参考',
    contributing: '参与贡献',
    links: '链接',
    releases: '版本发布',
    specs: '规格说明',
    decisions: '决策记录',
  },
}

function nav(lang: Lang): DefaultTheme.NavItem[] {
  const p = prefix(lang)
  const t = navLabels[lang]
  return [
    { text: t.start, link: `${p}/start/`, activeMatch: `^${p}/start/` },
    { text: t.guides, link: `${p}/guides/agents`, activeMatch: `^${p}/guides/` },
    { text: t.architecture, link: `${p}/architecture/`, activeMatch: `^${p}/architecture/` },
    { text: t.reference, link: `${p}/reference/cli`, activeMatch: `^${p}/reference/` },
    { text: t.contributing, link: `${p}/contributing/`, activeMatch: `^${p}/contributing/` },
    {
      text: t.links,
      items: [
        { text: t.releases, link: `${repo}/releases` },
        { text: t.specs, link: `${repo}/tree/main/openspec/specs` },
        { text: t.decisions, link: `${repo}/tree/main/docs/decisions` },
      ],
    },
  ]
}

const editPattern = `${repo}/edit/main/docs-site/:path`

export default withMermaid(
  defineConfig({
    title: 'Coffer',
    base: '/Coffer/',
    cleanUrls: true,
    lastUpdated: true,
    head: [['meta', { name: 'theme-color', content: '#c96442' }]],
    markdown: {
      theme: { light: 'github-light', dark: 'github-dark' },
    },
    mermaid: {},
    locales: {
      root: {
        label: 'English',
        lang: 'en',
        description:
          'Coffer is a local-first vault for AI coding agents: one place on your machine for the MCP servers, skills, knowledge, memory and model providers every agent shares.',
        themeConfig: {
          nav: nav('en'),
          sidebar: sidebar('en'),
          editLink: { pattern: editPattern, text: 'Edit this page on GitHub' },
          footer: {
            message: 'Released under the MIT License.',
            copyright: 'Coffer contributors',
          },
        },
      },
      zh: {
        label: '简体中文',
        lang: 'zh-CN',
        link: '/zh/',
        description:
          'Coffer 是给 AI 编程智能体用的本地保险库：MCP 服务器、技能、知识、记忆和模型提供商在你的机器上集中一处，所有智能体共用。',
        themeConfig: {
          nav: nav('zh'),
          sidebar: sidebar('zh'),
          editLink: { pattern: editPattern, text: '在 GitHub 上编辑此页' },
          lastUpdated: { text: '最后更新于' },
          outline: { level: [2, 3], label: '本页内容' },
          docFooter: { prev: '上一页', next: '下一页' },
          darkModeSwitchLabel: '外观',
          lightModeSwitchTitle: '切换到浅色模式',
          darkModeSwitchTitle: '切换到深色模式',
          sidebarMenuLabel: '菜单',
          returnToTopLabel: '回到顶部',
          langMenuLabel: '切换语言',
          skipToContentLabel: '跳到正文',
          notFound: {
            title: '页面不存在',
            quote: '这个地址下什么也没有。',
            linkText: '回到首页',
          },
          footer: {
            message: '基于 MIT 许可证发布。',
            copyright: 'Coffer 贡献者',
          },
        },
      },
    },
    themeConfig: {
      search: {
        provider: 'local',
        options: {
          // MiniSearch splits on spaces and punctuation, which leaves a Chinese
          // sentence as one token. Split CJK runs into words as well, for the
          // index and the query alike. VitePress serialises this function into
          // the page, so it must not reference anything outside itself.
          miniSearch: {
            options: {
              tokenize: (text: string) =>
                text
                  .split(/[\n\r\p{Z}\p{P}]+/u)
                  .flatMap((part) =>
                    /[㐀-鿿]/.test(part)
                      ? Array.from(new Intl.Segmenter('zh', { granularity: 'word' }).segment(part))
                          .filter((s) => s.isWordLike)
                          .map((s) => s.segment)
                      : [part],
                  )
                  .filter((t) => t.length > 0),
            },
          },
          locales: {
            zh: {
              translations: {
                button: { buttonText: '搜索文档', buttonAriaLabel: '搜索文档' },
                modal: {
                  displayDetails: '显示详细列表',
                  resetButtonTitle: '清除查询',
                  backButtonTitle: '关闭搜索',
                  noResultsText: '没有找到结果',
                  footer: {
                    selectText: '选择',
                    selectKeyAriaLabel: '回车',
                    navigateText: '切换',
                    navigateUpKeyAriaLabel: '上箭头',
                    navigateDownKeyAriaLabel: '下箭头',
                    closeText: '关闭',
                    closeKeyAriaLabel: 'Esc',
                  },
                },
              },
            },
          },
        },
      },
      outline: { level: [2, 3] },
      socialLinks: [{ icon: 'github', link: repo }],
    },
  }),
)
