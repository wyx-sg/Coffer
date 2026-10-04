import { readFileSync, readdirSync } from 'node:fs'
import { defineConfig, type DefaultTheme } from 'vitepress'
import type MarkdownIt from 'markdown-it'
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

// The CLI reference is an index page plus one generated page per command
// group (docs-site/scripts/gen_cli_reference.py). The group pages are listed
// under the index's sidebar entry straight from the directory, so a group the
// generator adds or removes needs no sidebar edit.
const CLI_INDEX = '/reference/cli'
const cliFiles: string[] = readdirSync(new URL('../reference/cli/', import.meta.url))
  .filter((file) => file.endsWith('.md'))
  .map((file) => file.slice(0, -'.md'.length))
// In the order `coffer --help` lists them, which the generated index's table
// follows; a page the table does not link goes last.
const cliOrder = [
  ...readFileSync(new URL('../reference/cli.md', import.meta.url), 'utf8').matchAll(
    /\]\(\/reference\/cli\/([\w-]+)\)/g,
  ),
].map((m) => m[1])
const rank = (name: string) => (cliOrder.includes(name) ? cliOrder.indexOf(name) : cliOrder.length)
const cliGroups = [...cliFiles].sort((a, b) => rank(a) - rank(b) || a.localeCompare(b))

function sidebarItem(lang: Lang, item: SourceItem): DefaultTheme.SidebarItem {
  const link = `${prefix(lang)}${item.link}`
  if (item.link !== CLI_INDEX) return { text: item.text[lang], link }
  return {
    text: item.text[lang],
    link,
    collapsed: true,
    items: cliGroups.map((name) => ({ text: `coffer ${name}`, link: `${link}/${name}` })),
  }
}

function sidebar(lang: Lang): DefaultTheme.SidebarMulti {
  const out: DefaultTheme.SidebarMulti = {}
  for (const [section, groups] of Object.entries(sections)) {
    out[`${prefix(lang)}/${section}/`] = groups.map((group) => ({
      text: group.text[lang],
      items: group.items.map((item) => sidebarItem(lang, item)),
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
    links: 'More',
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
    links: '更多',
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
    { text: t.guides, link: `${p}/guides/`, activeMatch: `^${p}/guides/` },
    { text: t.architecture, link: `${p}/architecture/`, activeMatch: `^${p}/architecture/` },
    { text: t.reference, link: `${p}/reference/`, activeMatch: `^${p}/reference/` },
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

// `::: steps` wraps a run of `###` headings into numbered steps: each heading
// and what follows it until the next heading becomes one <div class="vp-step">.
function stepsPlugin(md: MarkdownIt) {
  md.block.ruler.before(
    'fence',
    'coffer_steps',
    (state, startLine, endLine, silent) => {
      const line = (n: number) => state.src.slice(state.bMarks[n] + state.tShift[n], state.eMarks[n])
      if (state.sCount[startLine] - state.blkIndent >= 4) return false
      // Any fence of three or more colons works, so a step can hold a
      // shorter `:::` container; only a fence of the same length closes it.
      const opener = /^(:{3,})\s*steps\s*$/.exec(line(startLine))
      if (!opener) return false
      if (silent) return true
      const marker = opener[1].length
      let depth = 1
      let end = startLine + 1
      for (; end < endLine; end++) {
        const fence = /^(:{3,})\s*(\S?)/.exec(line(end))
        if (!fence || fence[1].length !== marker) continue
        if (!fence[2]) {
          if (--depth === 0) break
        } else depth++
      }
      const open = state.push('steps_open', 'div', 1)
      open.block = true
      open.attrs = [['class', 'vp-steps']]
      open.map = [startLine, end]
      const first = state.tokens.length
      const oldParent = state.parentType
      const oldMax = state.lineMax
      state.parentType = 'container' as typeof state.parentType
      state.lineMax = end
      state.md.block.tokenize(state, startLine + 1, end)
      state.parentType = oldParent
      state.lineMax = oldMax
      // group the inner tokens by top-level h3
      const inner = state.tokens.splice(first)
      const level = state.level
      let inStep = false
      const closeStep = () => {
        if (!inStep) return
        const c = new state.Token('step_close', 'div', -1)
        c.block = true
        state.tokens.push(c)
        inStep = false
      }
      for (const tok of inner) {
        if (tok.type === 'heading_open' && tok.tag === 'h3' && tok.level === level) {
          closeStep()
          const o = new state.Token('step_open', 'div', 1)
          o.block = true
          o.attrs = [['class', 'vp-step']]
          state.tokens.push(o)
          inStep = true
        }
        state.tokens.push(tok)
      }
      closeStep()
      const close = state.push('steps_close', 'div', -1)
      close.block = true
      state.line = end + 1
      return true
    },
    { alt: ['paragraph', 'reference', 'blockquote', 'list'] },
  )
}

// Tables get a rounded, bordered wrapper that scrolls sideways when wide.
function tableWrap(md: MarkdownIt) {
  const render = (tokens: any[], idx: number, options: any, _env: any, self: any) =>
    self.renderToken(tokens, idx, options)
  const open = md.renderer.rules.table_open ?? render
  const close = md.renderer.rules.table_close ?? render
  md.renderer.rules.table_open = (...a) => '<div class="vp-table">' + open(...a)
  md.renderer.rules.table_close = (...a) => close(...a) + '</div>'
}

// The Vault C mark, inlined so the site needs no extra asset.
const mark = (stroke: string, accent: string) =>
  'data:image/svg+xml,' +
  encodeURIComponent(
    `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"><path d="M20 8.5V7a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v10a4 4 0 0 0 4 4h8a4 4 0 0 0 4-4v-1.5" fill="none" stroke-linecap="round" stroke-linejoin="round" stroke="${stroke}" stroke-width="1.75"/><circle cx="12" cy="12" r="1.9" fill="none" stroke="${accent}" stroke-width="1.75"/></svg>`,
  )

// Code colours from the canvas: plain text, a shell command bold, options and
// keys in the link colour, strings green, comments subtle.
function codeTheme(name: string, c: { bg: string; fg: string; flag: string; string: string; subtle: string }) {
  return {
    name,
    type: name.endsWith('dark') ? 'dark' : 'light',
    colors: { 'editor.background': c.bg, 'editor.foreground': c.fg },
    tokenColors: [
      { settings: { foreground: c.fg } },
      { scope: ['comment', 'punctuation.definition.comment'], settings: { foreground: c.subtle } },
      { scope: ['string', 'punctuation.definition.string'], settings: { foreground: c.string } },
      {
        scope: ['constant.other.option', 'variable.parameter', 'support.type.property-name', 'entity.name.tag', 'keyword.other.definition'],
        settings: { foreground: c.flag },
      },
      // a shell command reads as one bold line: its name and bare arguments
      {
        scope: ['entity.name.command', 'entity.name.function.call', 'support.function.builtin', 'string.unquoted.argument'],
        settings: { foreground: c.fg, fontStyle: 'bold' },
      },
      { scope: ['string.unquoted.argument constant.other.option'], settings: { foreground: c.flag, fontStyle: 'bold' } },
    ],
  }
}
const codeLight = codeTheme('coffer-light', { bg: '#F6F7F9', fg: '#16181D', flag: '#3342C4', string: '#177A4F', subtle: '#6B717D' })
const codeDark = codeTheme('coffer-dark', { bg: '#16171B', fg: '#E4E5EA', flag: '#A3ABFF', string: '#4CB782', subtle: '#868A97' })

const editPattern = `${repo}/edit/main/docs-site/:path`

export default withMermaid(
  defineConfig({
    title: 'Coffer',
    base: '/Coffer/',
    cleanUrls: true,
    lastUpdated: true,
    head: [['meta', { name: 'theme-color', content: '#4353d8' }]],
    markdown: {
      theme: { light: codeLight as any, dark: codeDark as any },
      config: (md) => {
        md.use(stepsPlugin)
        md.use(tableWrap)
      },
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
          lastUpdated: { text: 'Last updated', formatOptions: { dateStyle: 'long' } },
          docFooter: { prev: 'Previous', next: 'Next' },
          footer: {
            message: 'Released under the MIT License.',
            copyright: 'Copyright © Coffer contributors',
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
          lastUpdated: { text: '最后更新于', formatOptions: { dateStyle: 'long' } },
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
            copyright: '版权所有 © Coffer 贡献者',
          },
        },
      },
    },
    themeConfig: {
      logo: { light: mark('#16181D', '#4353D8'), dark: mark('#E4E5EA', '#5A66E6'), alt: 'Coffer' },
      search: {
        provider: 'local',
        options: {
          // each hit shows the start of its section under the title, clamped
          // to two lines in styles/widgets.css
          detailedView: true,
          translations: {
            modal: { footer: { selectText: 'to open', navigateText: 'to navigate', closeText: 'to close' } },
          },
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
      outline: { level: [2, 3], label: 'On this page' },
      socialLinks: [{ icon: 'github', link: repo }],
    },
  }),
)
