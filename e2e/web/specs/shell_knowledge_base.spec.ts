// e2e/web/specs/shell_knowledge_base.spec.ts
//
// Spec 006 — the knowledge-base detail surface end-to-end.
//
// Since the unified 知识 redesign (ADR-030), the standalone KB list page is
// gone — /knowledge-bases redirects to the unified /knowledge surface, which
// has no in-page KB-creation dialog and no per-KB ranked-search panel. The KB
// itself plus a document are provisioned via the REST API (file-picker dialogs
// are not automatable portably), then the still-routed KB DETAIL page
// (/knowledge-bases/:name) drives the unified retrieval bar's SEARCH path
// through the real UI. This is the browser-level companion to the backend
// acceptance suite: it pins frontend↔backend wiring for the keyword search
// path that returns ranked passages.

import { expect } from "@playwright/test";
import { acceptance } from "./_acceptance";
import { beforeEachInjectToken, readDaemonToken } from "./_helpers";

beforeEachInjectToken();

acceptance(
  "006-knowledge-base",
  "keyword search returns ranked passages",
  async ({ page }) => {
    const { token, port } = readDaemonToken();
    const apiBase = `http://127.0.0.1:${port}/api/v1`;
    const kbName = `e2e-kb-${Date.now().toString(36)}`;

    try {
      // 1. Provision the KB via REST. The unified 知识 redesign removed the
      //    standalone list page (and its create dialog); KBs are created through
      //    the API, then curated on the still-routed detail page.
      const create = await fetch(`${apiBase}/knowledge_bases`, {
        method: "POST",
        headers: {
          "X-Coffer-Token": token,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ name: kbName, description: null, config: {} }),
      });
      expect(create.status).toBe(201);

      // 2. Ingest a markdown document via REST (no portable file-picker driving).
      const form = new FormData();
      form.append(
        "file",
        new File(["# Deploys\n\nwe deploy with make release\n"], "deploys.md", {
          type: "text/markdown",
        }),
      );
      const ingest = await fetch(
        `${apiBase}/knowledge_bases/${kbName}/documents`,
        {
          method: "POST",
          headers: { "X-Coffer-Token": token },
          body: form,
        },
      );
      expect(ingest.status).toBe(201);

      // 3. Open the KB detail page (still routed for in-page links). The doc tree
      //    shows the markdown title ("Deploys"), not the source filename.
      await page.goto(`/knowledge-bases/${kbName}`);
      await expect(
        page.getByText("Deploys", { exact: true }).first(),
      ).toBeVisible();

      // 4. Drive the unified retrieval bar's SEARCH (keyword is the default mode):
      //    a keyword search returns ranked passages, each showing the matched
      //    document and a snippet of the surrounding text.
      await page
        .getByPlaceholder("Search this knowledge base…")
        .fill("release");
      await page.getByRole("button", { name: "Search", exact: true }).click();
      await expect(page.getByText(/make release/).first()).toBeVisible();
    } finally {
      // Clean up even on assertion failure so reruns against a reused daemon
      // stay isolated.
      await fetch(`${apiBase}/resources/knowledge_base/${kbName}`, {
        method: "DELETE",
        headers: { "X-Coffer-Token": token },
      });
    }
  },
);
