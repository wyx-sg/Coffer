// frontend/src/components/skills/SkillBulkDelete.test.tsx — deleting a selection (canvas 4.3.39).
//
// One call answers per skill. All deleted is a toast and the selection clears;
// when one is refused because an agent's copy is no longer Coffer's link the
// dialog stays open on "Deleted 1 of 2", names who went and which folder
// blocked the other, and its primary button becomes "Delete pdf, keep Codex's
// folder", which sends only the refused skill again with the keep option.
import { afterEach, expect, test, vi } from "vitest";
import { acceptance } from "@/test/acceptance";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { ToastProvider } from "@/components/ui/toast";
import "@/i18n";
import type { SkillBulkDeleteResult } from "@/lib/api/skills";
import { makeAgent, makeSkill } from "@/test/skillsPageKit";
import { SkillBulkDelete } from "./SkillBulkDelete";

vi.mock("@/lib/api/skills", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/skills")>()),
  skillsApi: { bulkDelete: vi.fn() },
}));
vi.mock("@/lib/hooks/useAgents", () => ({
  useAgents: () => ({ data: [makeAgent({ uid: "ag-cx", name: "codex", display_name: "Codex" })] }),
}));
const { skillsApi } = await import("@/lib/api/skills");
const bulk = vi.mocked(skillsApi.bulkDelete);

const PDF = makeSkill({ uid: "sk-pdf", name: "pdf" });
const NOTES = makeSkill({ uid: "sk-rn", name: "release-notes" });

const ok = (s: { uid: string; name: string }): SkillBulkDeleteResult => ({
  uid: s.uid,
  name: s.name,
  deleted: true,
  kept_copies: [],
  error_code: null,
  error_message: null,
  error_details: null,
});
const refused: SkillBulkDeleteResult = {
  uid: "sk-pdf",
  name: "pdf",
  deleted: false,
  kept_copies: [],
  error_code: "SKILL_COPY_NOT_OURS",
  error_message: "not ours",
  error_details: { path: "/Users/me/.codex/skills/pdf", agent_name: "codex" },
};

function mount(onDone = vi.fn()) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <SkillBulkDelete skills={[PDF, NOTES]} onDone={onDone} label="Delete" />
      </ToastProvider>
    </QueryClientProvider>,
  );
  fireEvent.click(screen.getByRole("button", { name: "Delete" }));
  return { onDone };
}

afterEach(() => vi.clearAllMocks());

test("deleting all of them closes the dialog and clears the selection", async () => {
  bulk.mockResolvedValue({ results: [ok(PDF), ok(NOTES)] });
  const { onDone } = mount();
  const dialog = await screen.findByRole("dialog", { name: "Delete 2 skills?" });
  fireEvent.click(within(dialog).getByRole("button", { name: "Delete 2 skills" }));
  await waitFor(() => expect(onDone).toHaveBeenCalled());
  expect(bulk).toHaveBeenCalledWith(["sk-pdf", "sk-rn"]);
  expect(screen.queryByRole("dialog")).toBeNull();
});

acceptance("web-ui", "a bulk delete offers to keep the folder that stopped one skill", async () => {
  bulk.mockResolvedValueOnce({ results: [refused, ok(NOTES)] });
  bulk.mockResolvedValueOnce({ results: [ok(PDF)] });
  const { onDone } = mount();
  const dialog = await screen.findByRole("dialog", { name: "Delete 2 skills?" });
  fireEvent.click(within(dialog).getByRole("button", { name: "Delete 2 skills" }));

  expect(await within(dialog).findByText("Deleted 1 of 2")).toBeInTheDocument();
  expect(dialog).toHaveTextContent("release-notes is deleted. pdf isn’t:");
  expect(dialog).toHaveTextContent("~/.codex/skills/pdf");
  expect(dialog).toHaveTextContent("is a regular folder now, not Coffer’s link");
  expect(onDone).not.toHaveBeenCalled();

  fireEvent.click(within(dialog).getByRole("button", { name: "Delete pdf, keep Codex’s folder" }));
  await waitFor(() => expect(bulk).toHaveBeenLastCalledWith(["sk-pdf"], true));
  await waitFor(() => expect(onDone).toHaveBeenCalled());
});
