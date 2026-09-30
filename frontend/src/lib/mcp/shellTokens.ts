// frontend/src/lib/mcp/shellTokens.ts
//
// POSIX-shell-style word splitting for one pasted command line: single quotes
// (literal), double quotes (with \" \\ \$ \` escapes), backslash escapes
// outside quotes, and `\`-newline continuations joined first. No expansion.

/** The words of `line`, or `null` when a quote is left open. */
export function shellSplit(line: string): string[] | null {
  const text = line.replace(/\\\r?\n/g, " ");
  const words: string[] = [];
  let word = "";
  let inWord = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (c === "'") {
      const end = text.indexOf("'", i + 1);
      if (end < 0) return null;
      word += text.slice(i + 1, end);
      inWord = true;
      i = end;
    } else if (c === '"') {
      let j = i + 1;
      for (; j < text.length && text[j] !== '"'; j++) {
        if (text[j] === "\\" && '"\\$`'.includes(text[j + 1] ?? "")) j++;
        word += text[j];
      }
      if (j >= text.length) return null;
      inWord = true;
      i = j;
    } else if (c === "\\" && i + 1 < text.length) {
      word += text[++i];
      inWord = true;
    } else if (/\s/.test(c)) {
      if (inWord) words.push(word);
      word = "";
      inWord = false;
    } else {
      word += c;
      inWord = true;
    }
  }
  if (inWord) words.push(word);
  return words;
}
