// frontend/src/lib/mcp/commandLine.ts
//
// Whether a pasted line is a command at all. Conservative on purpose: a
// sentence from a README must not become a stdio server named after its
// first word, so a line is a command only when its first word looks like a
// program AND the line does not read like prose.

/** Launchers MCP READMEs use; always programs. */
const KNOWN_PROGRAMS = new Set([
  ...["npx", "uvx", "bunx", "pnpm", "yarn", "npm", "bun", "deno", "node", "uv"],
  ...["python", "python3", "pipx", "docker", "podman", "java", "go", "cargo", "dotnet"],
  ...["ruby", "php", "claude", "codex"],
]);

/** Lower-case English words a README sentence starts with and no MCP
 *  launcher is called. */
const STOPWORDS = new Set([
  ...["a", "an", "the", "this", "that", "these", "it", "its", "you", "your", "we", "our"],
  ...["to", "and", "or", "if", "then", "for", "in", "on", "with", "from", "by", "of", "as"],
  ...["see", "note", "please", "install", "run", "use", "add", "open", "first", "next"],
  ...["make", "click", "copy", "paste", "set", "configure", "follow", "is", "are", "can"],
]);

/** An env assignment `KEY=value` (leading a command, or after -e / --env). */
export const ASSIGNMENT_RE = /^[A-Za-z_][A-Za-z0-9_]*=/;

/** Whether `word` could name a program: a known launcher, a path, a file
 *  with an extension, or a single lower-case word. */
export function looksLikeProgram(word: string): boolean {
  if (KNOWN_PROGRAMS.has(word)) return true;
  if (/^[a-z][a-z0-9+.-]*:\/\//i.test(word)) return false; // a URL of another scheme
  if (STOPWORDS.has(word)) return false;
  if (/[\\/]/.test(word)) return true;
  if (/^[\w-]+\.[A-Za-z0-9]+$/.test(word)) return true;
  return /^[a-z][a-z0-9_-]*$/.test(word);
}

/** The line with its quoted segments removed, so punctuation inside an
 *  argument (`--tags "a, b"`) does not count as prose. */
function unquoted(line: string): string {
  return line.replace(/'[^']*'|"(?:\\.|[^"\\])*"/g, "x");
}

const PLAIN_WORD = /^[A-Za-z][a-z]*$/;
const COMMANDISH = /^-|[\\/.@=:]/;

/** Whether `line` (split into `words`) reads like a sentence rather than a
 *  command. A line led by a known launcher is judged by its punctuation only:
 *  `claude mcp add github` is all plain words and still a command. */
export function looksLikeProse(line: string, words: string[]): boolean {
  const bare = unquoted(line).trim();
  if (/[.?!:;,]$/.test(bare)) return true;
  if (/[,;] |[.?!] +[A-Z]/.test(bare)) return true;
  if (KNOWN_PROGRAMS.has(words.find((w) => !ASSIGNMENT_RE.test(w)) ?? "")) return false;
  if (words.length >= 4 && words.every((w) => PLAIN_WORD.test(w))) return true;
  return words.length > 12 && !words.some((w) => COMMANDISH.test(w));
}
