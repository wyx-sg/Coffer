// src/components/preview/codemirrorLang.ts
// Resolves a PreviewLanguage id to a CodeMirror language extension. Kept apart
// from the pure languageForFile() map so that map stays CodeMirror-free and
// unit-testable. Languages without a dedicated @codemirror/lang-* package use
// StreamLanguage over @codemirror/legacy-modes (toml, python, shell, …).
import type { Extension } from "@codemirror/state";
import { StreamLanguage } from "@codemirror/language";
import { json } from "@codemirror/lang-json";
import { yaml } from "@codemirror/lang-yaml";
import { javascript } from "@codemirror/lang-javascript";
import { toml } from "@codemirror/legacy-modes/mode/toml";
import { python } from "@codemirror/legacy-modes/mode/python";
import { shell } from "@codemirror/legacy-modes/mode/shell";
import { properties } from "@codemirror/legacy-modes/mode/properties";
import { css } from "@codemirror/legacy-modes/mode/css";
import { xml } from "@codemirror/legacy-modes/mode/xml";
import { dockerFile } from "@codemirror/legacy-modes/mode/dockerfile";

import type { PreviewLanguage } from "@/lib/preview/language";

/** CodeMirror extension for a language id, or null for plain/rendered text. */
export function languageExtension(lang: PreviewLanguage): Extension | null {
  switch (lang) {
    case "json":
      return json();
    case "yaml":
      return yaml();
    case "javascript":
      return javascript({ jsx: true });
    case "typescript":
      return javascript({ jsx: true, typescript: true });
    case "toml":
      return StreamLanguage.define(toml);
    case "python":
      return StreamLanguage.define(python);
    case "shell":
      return StreamLanguage.define(shell);
    case "ini":
      return StreamLanguage.define(properties);
    case "css":
      return StreamLanguage.define(css);
    case "html":
    case "xml":
      return StreamLanguage.define(xml);
    case "dockerfile":
      return StreamLanguage.define(dockerFile);
    // markdown is rendered (not shown raw in CodeView); "text" has no grammar.
    case "markdown":
    case "text":
      return null;
  }
}
