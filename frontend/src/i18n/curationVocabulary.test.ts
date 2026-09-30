// src/i18n/curationVocabulary.test.ts — the web UI calls curation Curate, never merge.
//
// Spec knowledge "Present a collection as one tree in the web UI": every
// label, button and help line about curation says Curate / Curation (整理),
// and inbox entries are items. The CLI half is
// backend/tests/integration/surfaces/cli/test_knowledge_curation_vocabulary.py.
import { expect } from "vitest";

import { acceptance } from "@/test/acceptance";

import en from "./locales/en.json";
import zh from "./locales/zh.json";

function strings(obj: unknown, prefix = ""): [string, string][] {
  if (typeof obj === "string") return [[prefix, obj]];
  if (obj === null || typeof obj !== "object") return [];
  return Object.entries(obj as Record<string, unknown>).flatMap(([k, v]) =>
    strings(v, prefix ? `${prefix}.${k}` : k),
  );
}

/** Every string about curation: the Knowledge page's own, and any elsewhere
 *  whose key or text names curation. */
function aboutCuration(locale: Record<string, unknown>, word: RegExp): [string, string][] {
  return strings(locale).filter(
    ([key, text]) => key.startsWith("knowledge.") || /curat/i.test(key) || word.test(text),
  );
}

acceptance("knowledge", "curation is called curate, never merge", () => {
  const enLines = aboutCuration(en, /curat/i);
  const zhLines = aboutCuration(zh, /整理/);
  expect(enLines.length).toBeGreaterThan(20);
  expect(zhLines.length).toBeGreaterThan(20);

  expect(enLines.filter(([, text]) => /merg/i.test(text))).toEqual([]);
  expect(zhLines.filter(([, text]) => /合并|融合|merg/i.test(text))).toEqual([]);
  // Inbox entries are items, never the spec's "material".
  expect(enLines.filter(([, text]) => /material/i.test(text))).toEqual([]);
  expect(zhLines.filter(([, text]) => /素材|材料/.test(text))).toEqual([]);

  expect(en.knowledge.curate.now).toBe("Curate now");
  expect(zh.knowledge.curate.now).toBe("立即整理");
  expect(en.knowledge.automatic.title).toMatch(/curation/i);
  expect(zh.knowledge.automatic.title).toMatch(/整理/);
  expect(en.knowledge.inbox.waitingCount_other).toMatch(/items waiting/);
});
