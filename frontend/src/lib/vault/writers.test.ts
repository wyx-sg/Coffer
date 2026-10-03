// frontend/src/lib/vault/writers.test.ts — who wrote a vault version, in a word.
import { expect, test } from "vitest";
import type { TFunction } from "i18next";

import { vaultWriterLabel } from "./writers";

const t = ((key: string) => key) as unknown as TFunction;

test("an agent is named by its product, every other writer is You, Coffer or Git", () => {
  expect(vaultWriterLabel(t, "agent:claude_code")).toBe("Claude Code");
  expect(vaultWriterLabel(t, "agent:codex")).toBe("Codex");
  expect(vaultWriterLabel(t, "user")).toBe("vault.writer.user");
  expect(vaultWriterLabel(t, "disk")).toBe("vault.writer.user");
  expect(vaultWriterLabel(t, "daemon")).toBe("vault.writer.daemon");
  expect(vaultWriterLabel(t, "curation")).toBe("vault.writer.daemon");
  // Sync is experimental: its versions read as Git, never as "Sync".
  expect(vaultWriterLabel(t, "sync")).toBe("vault.writer.sync");
  // A writer this build does not know reads as what it most likely is.
  expect(vaultWriterLabel(t, "someone-new")).toBe("vault.writer.user");
});
