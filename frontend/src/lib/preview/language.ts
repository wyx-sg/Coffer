// src/lib/preview/language.ts
// Maps a file name (or known basename) to a PreviewLanguage id used by
// <CodeView> for syntax highlighting. Pure and dependency-free so it can be
// unit-tested without pulling in CodeMirror; the id is resolved to an actual
// CodeMirror extension by languageExtension() in codemirrorLang.ts. "text"
// means no highlighting.
export type PreviewLanguage =
  | "json"
  | "yaml"
  | "toml"
  | "markdown"
  | "javascript"
  | "typescript"
  | "python"
  | "shell"
  | "css"
  | "html"
  | "xml"
  | "ini"
  | "dockerfile"
  | "text";

const BY_EXT: Record<string, PreviewLanguage> = {
  json: "json",
  jsonc: "json",
  yaml: "yaml",
  yml: "yaml",
  toml: "toml",
  md: "markdown",
  mdx: "markdown",
  markdown: "markdown",
  js: "javascript",
  jsx: "javascript",
  mjs: "javascript",
  cjs: "javascript",
  ts: "typescript",
  tsx: "typescript",
  mts: "typescript",
  cts: "typescript",
  py: "python",
  pyi: "python",
  sh: "shell",
  bash: "shell",
  zsh: "shell",
  fish: "shell",
  css: "css",
  scss: "css",
  less: "css",
  html: "html",
  htm: "html",
  xml: "xml",
  svg: "xml",
  ini: "ini",
  cfg: "ini",
  conf: "ini",
  properties: "ini",
  env: "ini",
};

const BY_NAME: Record<string, PreviewLanguage> = {
  dockerfile: "dockerfile",
  ".env": "ini",
  ".gitignore": "ini",
  ".npmrc": "ini",
};

/** Resolve a file's preview language from its name; "text" when unknown. */
export function languageForFile(filename?: string | null): PreviewLanguage {
  if (!filename) return "text";
  const base = filename.split(/[\\/]/).pop() ?? filename;
  const lower = base.toLowerCase();
  if (lower in BY_NAME) return BY_NAME[lower];
  const dot = lower.lastIndexOf(".");
  if (dot <= 0 || dot === lower.length - 1) return "text";
  return BY_EXT[lower.slice(dot + 1)] ?? "text";
}
