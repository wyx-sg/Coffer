import { test } from "node:test";
import assert from "node:assert/strict";
import {
  classifyFile,
  rewriteLinks,
  extractTitle,
  specFolderLabel,
  specFileLabel,
  GH_BLOB,
} from "./sync-reference.mjs";

test("specFileLabel: spec sub-files get uniform type labels", () => {
  assert.equal(specFileLabel("spec"), "Spec");
  assert.equal(specFileLabel("data-model"), "Data model");
  assert.equal(specFileLabel("quickstart"), "Quickstart");
});

test("specFileLabel: unknown base falls back to titleized name", () => {
  assert.equal(specFileLabel("design-notes"), "Design Notes");
});

test("classifyFile: a spec .md goes to the reference tree", () => {
  const r = classifyFile("specs/mcp-gateway/spec.md");
  assert.deepEqual(r, { dest: "reference/specs/mcp-gateway/spec.md" });
});

test("classifyFile: an ADR goes to the adr area", () => {
  const r = classifyFile("docs/decisions/code-layout-layer-first.md");
  assert.deepEqual(r, { dest: "reference/adr/code-layout-layer-first.md" });
});

test("classifyFile: tasks.md is excluded", () => {
  assert.equal(classifyFile("specs/mcp-gateway/tasks.md"), null);
});

test("classifyFile: files outside the synced areas are excluded", () => {
  assert.equal(classifyFile("backend/coffer/domain/resource.py"), null);
  assert.equal(classifyFile("README.md"), null);
});

test("classifyFile: a directory README.md becomes index.md", () => {
  assert.deepEqual(classifyFile("docs/decisions/README.md"), {
    dest: "reference/adr/index.md",
  });
});

test("rewriteLinks: cross-doc .md link → site route (extensionless)", () => {
  const src = "specs/mcp-gateway/spec.md";
  const out = rewriteLinks("See [data model](./data-model.md).", src);
  assert.equal(
    out,
    "See [data model](/reference/specs/mcp-gateway/data-model).",
  );
});

test("rewriteLinks: link to an ADR from architecture → adr route", () => {
  const src = ".specify/memory/architecture.md";
  const out = rewriteLinks(
    "[Layer-First Code Layout](../../docs/decisions/code-layout-layer-first.md)",
    src,
  );
  assert.equal(
    out,
    "[Layer-First Code Layout](/reference/adr/code-layout-layer-first)",
  );
});

test("rewriteLinks: anchors and external links pass through unchanged", () => {
  const src = "specs/mcp-gateway/spec.md";
  const input =
    "[x](#section) and [y](https://example.com) and [z](mailto:a@b.c)";
  assert.equal(rewriteLinks(input, src), input);
});

test("rewriteLinks: non-synced repo path → GitHub blob URL", () => {
  const src = ".specify/memory/architecture.md";
  const out = rewriteLinks("[code](../../backend/pyproject.toml)", src);
  assert.equal(out, `[code](${GH_BLOB}/backend/pyproject.toml)`);
});

test("rewriteLinks: excluded tasks.md target → GitHub blob URL", () => {
  const src = "specs/mcp-gateway/spec.md";
  const out = rewriteLinks("[tasks](./tasks.md)", src);
  assert.equal(out, `[tasks](${GH_BLOB}/specs/mcp-gateway/tasks.md)`);
});

test("rewriteLinks: directory target → GitHub tree URL (not blob)", () => {
  const src = "specs/mcp-gateway/plan.md";
  const out = rewriteLinks("see [ADRs](../../docs/decisions/)", src);
  assert.equal(
    out,
    "see [ADRs](https://github.com/wyx-sg/Coffer/tree/main/docs/decisions)",
  );
});

test("rewriteLinks: .md link with a title preserves the title on the route", () => {
  const src = "specs/mcp-gateway/spec.md";
  const out = rewriteLinks(
    'See [data model](./data-model.md "Data Model").',
    src,
  );
  assert.equal(
    out,
    'See [data model](/reference/specs/mcp-gateway/data-model "Data Model").',
  );
});

test("rewriteLinks: trailing whitespace before ) does not break .md detection", () => {
  const src = "specs/mcp-gateway/spec.md";
  const out = rewriteLinks("See [x](./data-model.md ).", src);
  assert.equal(out, "See [x](/reference/specs/mcp-gateway/data-model).");
});

test("rewriteLinks: image to a repo asset → raw URL (not blob, not a route)", () => {
  const GH_RAW = GH_BLOB.replace("/blob/", "/raw/");
  const src = ".specify/memory/architecture.md";
  const out = rewriteLinks("![diagram](../assets/x.png)", src);
  assert.equal(out, `![diagram](${GH_RAW}/.specify/assets/x.png)`);
});

test("rewriteLinks: link escaping the repo root is left unchanged", () => {
  const src = "specs/mcp-gateway/spec.md";
  const input = "[x](../../../../outside.md)";
  assert.equal(rewriteLinks(input, src), input);
});

test("extractTitle: plain heading", () => {
  assert.equal(extractTitle("# Hello\n\nbody"), "Hello");
});

test("extractTitle: heading after YAML frontmatter", () => {
  assert.equal(extractTitle("---\nx: 1\n---\n# Real Title\n"), "Real Title");
});

test("extractTitle: no heading returns null", () => {
  assert.equal(extractTitle("no heading"), null);
});

test("specFolderLabel: acronyms keep their casing", () => {
  assert.equal(specFolderLabel("mcp-gateway"), "MCP Gateway");
});

test("specFolderLabel: two-word non-acronym", () => {
  assert.equal(specFolderLabel("ui-shell"), "UI Shell");
});

test("specFolderLabel: three or more words", () => {
  assert.equal(specFolderLabel("provider-switching-rules"), "Provider Switching Rules");
});

test("specFolderLabel: two-word spec folder", () => {
  assert.equal(specFolderLabel("vault-sync"), "Vault Sync");
});
