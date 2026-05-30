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

test("specFileLabel: spec sub-files get uniform type labels, no spec number", () => {
  assert.equal(specFileLabel("spec", "en"), "Spec");
  assert.equal(specFileLabel("data-model", "en"), "Data model");
  assert.equal(specFileLabel("quickstart", "en"), "Quickstart");
  assert.equal(specFileLabel("spec", "zh"), "功能规格");
  assert.equal(specFileLabel("data-model", "zh"), "数据模型");
});

test("specFileLabel: unknown base falls back to titleized name (no number)", () => {
  assert.equal(specFileLabel("design-notes", "en"), "Design Notes");
});

test("classifyFile: English .md goes to the EN reference tree", () => {
  const r = classifyFile("specs/001-mcp-gateway/spec.md");
  assert.deepEqual(r, {
    locale: "en",
    dest: "reference/specs/001-mcp-gateway/spec.md",
  });
});

test("classifyFile: .zh.md goes to the zh tree with .zh stripped", () => {
  const r = classifyFile(
    "docs/decisions/ADR-002-code-layout-layer-first.zh.md",
  );
  assert.deepEqual(r, {
    locale: "zh",
    dest: "zh/reference/adr/ADR-002-code-layout-layer-first.md",
  });
});

test("classifyFile: tasks.md is excluded", () => {
  assert.equal(classifyFile("specs/001-mcp-gateway/tasks.md"), null);
});

test("classifyFile: files outside the synced areas are excluded", () => {
  assert.equal(classifyFile("backend/coffer/domain/resource.py"), null);
  assert.equal(classifyFile("README.md"), null);
});

test("classifyFile: a directory README.md becomes index.md", () => {
  assert.deepEqual(classifyFile("docs/decisions/README.md"), {
    locale: "en",
    dest: "reference/adr/index.md",
  });
  assert.deepEqual(classifyFile("docs/decisions/README.zh.md"), {
    locale: "zh",
    dest: "zh/reference/adr/index.md",
  });
});

test("rewriteLinks: cross-doc .md link → site route (extensionless)", () => {
  const src = "specs/001-mcp-gateway/spec.md";
  const out = rewriteLinks("See [data model](./data-model.md).", src);
  assert.equal(
    out,
    "See [data model](/reference/specs/001-mcp-gateway/data-model).",
  );
});

test("rewriteLinks: link to an ADR from architecture → adr route", () => {
  const src = ".specify/memory/architecture.md";
  const out = rewriteLinks(
    "[ADR-002](../../docs/decisions/ADR-002-code-layout-layer-first.md)",
    src,
  );
  assert.equal(
    out,
    "[ADR-002](/reference/adr/ADR-002-code-layout-layer-first)",
  );
});

test("rewriteLinks: anchors and external links pass through unchanged", () => {
  const src = "specs/001-mcp-gateway/spec.md";
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
  const src = "specs/001-mcp-gateway/spec.md";
  const out = rewriteLinks("[tasks](./tasks.md)", src);
  assert.equal(out, `[tasks](${GH_BLOB}/specs/001-mcp-gateway/tasks.md)`);
});

test("rewriteLinks: directory target → GitHub tree URL (not blob)", () => {
  const src = "specs/001-mcp-gateway/plan.md";
  const out = rewriteLinks("see [ADRs](../../docs/decisions/)", src);
  assert.equal(
    out,
    "see [ADRs](https://github.com/wyx-sg/Coffer/tree/main/docs/decisions)",
  );
});

test("rewriteLinks: .md link with a title preserves the title on the route", () => {
  const src = "specs/001-mcp-gateway/spec.md";
  const out = rewriteLinks(
    'See [data model](./data-model.md "Data Model").',
    src,
  );
  assert.equal(
    out,
    'See [data model](/reference/specs/001-mcp-gateway/data-model "Data Model").',
  );
});

test("rewriteLinks: trailing whitespace before ) does not break .md detection", () => {
  const src = "specs/001-mcp-gateway/spec.md";
  const out = rewriteLinks("See [x](./data-model.md ).", src);
  assert.equal(out, "See [x](/reference/specs/001-mcp-gateway/data-model).");
});

test("rewriteLinks: image to a repo asset → raw URL (not blob, not a route)", () => {
  const GH_RAW = GH_BLOB.replace("/blob/", "/raw/");
  const src = ".specify/memory/architecture.md";
  const out = rewriteLinks("![diagram](../assets/x.png)", src);
  assert.equal(out, `![diagram](${GH_RAW}/.specify/assets/x.png)`);
});

test("rewriteLinks: link escaping the repo root is left unchanged", () => {
  const src = "specs/001-mcp-gateway/spec.md";
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

test("specFolderLabel: numeric prefix with acronym", () => {
  assert.equal(specFolderLabel("001-mcp-gateway"), "001 · MCP Gateway");
});

test("specFolderLabel: two-word non-acronym", () => {
  assert.equal(specFolderLabel("002-ui-shell"), "002 · UI Shell");
});

test("specFolderLabel: three-word with acronym", () => {
  assert.equal(
    specFolderLabel("003-mcp-gateway-desktop"),
    "003 · MCP Gateway Desktop",
  );
});
