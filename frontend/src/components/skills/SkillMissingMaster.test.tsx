// frontend/src/components/skills/SkillMissingMaster.test.tsx
// A skill whose master folder is gone offers Restore from the vault's
// history: the newest version that still had files, put back as a folder
// restore (a new version); with no such version, Restore can't be chosen.
import { expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { SkillMissingMaster } from "@/components/skills/SkillMissingMaster";
import "@/i18n";
import { makeSkill } from "@/test/skillsPageKit";

vi.mock("@/lib/api/vault", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/vault")>()),
  vaultApi: { history: vi.fn(), diff: vi.fn(), restore: vi.fn(async () => ({})) },
}));
const { vaultApi } = await import("@/lib/api/vault");

function mount() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <SkillMissingMaster skill={makeSkill({ name: "hello" })} onDeleted={() => {}} />
    </QueryClientProvider>,
  );
}

const base = {
  time: "2026-09-30T08:00:00Z",
  writer: "disk",
  display_writer: "disk",
  actor: null,
  machine: null,
  summary: "Edited on disk",
  operation: "edit",
  restored_from: null,
  removed: false,
};

test("restore puts back the newest version that still had files", async () => {
  vi.mocked(vaultApi.history).mockResolvedValue({
    path: "skills/hello/",
    next_cursor: null,
    versions: [
      {
        ...base,
        version: "d".repeat(40),
        paths: [{ path: "skills/hello/SKILL.md", status: "removed", added: 0, removed: 3 }],
      },
      {
        ...base,
        version: "c".repeat(40),
        paths: [{ path: "skills/hello/SKILL.md", status: "modified", added: 1, removed: 1 }],
      },
    ],
  });
  mount();
  const restore = await screen.findByRole("radio", { name: /Restore it from History/ });
  await waitFor(() => expect(restore).not.toBeDisabled());
  fireEvent.click(restore);
  fireEvent.click(screen.getByRole("button", { name: /Restore/ }));
  await waitFor(() =>
    expect(vaultApi.restore).toHaveBeenCalledWith({
      path: "skills/hello/",
      version: "c".repeat(40),
      expected_fingerprint: null,
    }),
  );
});
