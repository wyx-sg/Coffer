// Parse every ```mermaid block in the site with the Mermaid version the site
// ships, and fail when any block does not parse.
//
// The diagrams render in the reader's browser, so `vitepress build` passes even
// when one is broken and the page shows Mermaid's "Syntax error in text" bomb
// instead. `npm run build` runs this first, so the docs-site CI job catches it.
//
// Usage: node scripts/check_mermaid.mjs   (from docs-site/)
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'
import { JSDOM } from 'jsdom'

// Mermaid sanitises labels with DOMPurify, which needs a window to load.
const { window } = new JSDOM('')
globalThis.window = window
globalThis.document = window.document
const { default: mermaid } = await import('mermaid')

const root = fileURLToPath(new URL('..', import.meta.url))

function* markdownFiles(dir) {
  for (const name of readdirSync(dir)) {
    if (name === 'node_modules' || name.startsWith('.')) continue
    const path = join(dir, name)
    if (statSync(path).isDirectory()) yield* markdownFiles(path)
    else if (name.endsWith('.md')) yield path
  }
}

let blocks = 0
const failures = []
for (const file of markdownFiles(root)) {
  const source = readFileSync(file, 'utf8')
  for (const match of source.matchAll(/^```mermaid[ \t]*\n([\s\S]*?)^```/gm)) {
    blocks += 1
    const line = source.slice(0, match.index).split('\n').length
    try {
      await mermaid.parse(match[1])
    } catch (error) {
      failures.push(`${relative(root, file)}:${line}\n  ${String(error.message ?? error).replaceAll('\n', '\n  ')}`)
    }
  }
}

if (failures.length) {
  console.error(`${failures.length} of ${blocks} Mermaid diagrams do not parse:\n`)
  console.error(failures.join('\n\n'))
  process.exit(1)
}
console.log(`All ${blocks} Mermaid diagrams parse.`)
