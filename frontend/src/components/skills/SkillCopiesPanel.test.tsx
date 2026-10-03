// frontend/src/components/skills/SkillCopiesPanel.test.tsx
// "Check copies" (canvas 4.3.25–4.3.28): the findings in two groups — Needs you
// and Fixed by Coffer — one row each with the one button that answers it, and
// the 1060 two-way choice behind Review… on a folder in the way: Replace it with
// Coffer's link / Adopt this folder, What will happen under the cards, the diff of
// the side you are not keeping on the right, the primary naming the write, a
// refusal kept in the dialog with the primary turned Retry.
import { beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { ApiError } from "@/lib/api/errors";
import type { SkillDriftEntry } from "@/lib/api/skills";
import { makeAgent, makeSkill } from "@/test/skillsPageKit";
import { SkillCopiesPanel } from "./SkillCopiesPanel";

vi.mock("@/lib/api/skills", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/skills")>()),
  skillsApi: {
    list: vi.fn(),
    verify: vi.fn(),
    repair: vi.fn(),
    compareCopy: vi.fn(),
    resolveCopy: vi.fn(),
  },
}));
const CODEX = makeAgent({ uid: "ag-cx", name: "codex", display_name: "Codex", type: "codex" });
const CLAUDE = makeAgent();
vi.mock("@/lib/hooks/useAgents", () => ({
  useAgents: vi.fn(() => ({ data: [CODEX, CLAUDE] })),
}));
const { skillsApi } = await import("@/lib/api/skills");
const api = vi.mocked(skillsApi);

const entry = (over: Partial<SkillDriftEntry>): SkillDriftEntry => ({
  skill_name: "frontend-design",
  agent_name: "codex",
  kind: "replaced_with_regular",
  target_path: "/Users/me/.codex/skills/frontend-design",
  handoff: { prompt: "Compare it." },
  ...over,
});

const FINDINGS = [
  entry({ skill_name: "release-notes", agent_name: "", kind: "missing_master", handoff: null }),
  entry({}),
  entry({ skill_name: "lint-rules", agent_name: "", kind: "orphan_master", handoff: null }),
];

function renderPanel(onClose = vi.fn()) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <SkillCopiesPanel onClose={onClose} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { onClose };
}

async function check() {
  fireEvent.click(screen.getByRole("button", { name: "Check again" }));
  return screen.findAllByTestId("skill-copy-finding");
}

describe("SkillCopiesPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.list.mockResolvedValue({
      items: [
        makeSkill({
          uid: "sk-fd",
          name: "frontend-design",
          bindings: [
            {
              agent_uid: CODEX.uid,
              agent_name: "codex",
              last_linked_at: null,
              last_link_path: null,
              link_mode: null,
            },
            {
              agent_uid: CLAUDE.uid,
              agent_name: "claude-code",
              last_linked_at: null,
              last_link_path: null,
              link_mode: null,
            },
          ],
        }),
      ],
    } as never);
    api.verify.mockResolvedValue({ entries: FINDINGS });
  });

  test("a header, then Needs you with one button per finding", async () => {
    renderPanel();
    expect(screen.getByRole("heading", { name: "Check copies" })).toBeInTheDocument();
    expect(
      screen.getByText(/Every agent’s copy of every skill, compared with the library/),
    ).toBeInTheDocument();
    const rows = await check();
    expect(rows).toHaveLength(3);
    const group = screen.getByRole("region", { name: "Needs you" });
    expect(group).toHaveTextContent("3");
    expect(within(rows[0]).getByRole("button", { name: "Open skill" })).toBeInTheDocument();
    expect(within(rows[1]).getByRole("button", { name: "Review…" })).toBeInTheDocument();
    expect(within(rows[2]).getByRole("button", { name: "Open" })).toBeInTheDocument();
    // No status column, no hand-off beside a choice only the person can make.
    expect(screen.queryByText("Left alone · needs you")).not.toBeInTheDocument();
    expect(within(rows[1]).queryByRole("button", { name: "Copy prompt" })).not.toBeInTheDocument();
    expect(rows[0]).toHaveTextContent("Master missing");
    expect(rows[2]).toHaveTextContent("Not in your library");
  });

  test("Open skill and Open leave the panel for the skill and the folder's pane", async () => {
    const { onClose } = renderPanel();
    const rows = await check();
    fireEvent.click(within(rows[0]).getByRole("button", { name: "Open skill" }));
    expect(onClose).toHaveBeenCalled();
  });

  test("Repair moves a put-back link to Fixed by Coffer", async () => {
    const missing = entry({ kind: "missing_link", handoff: null });
    api.verify.mockResolvedValue({ entries: [missing, entry({})] });
    api.repair.mockResolvedValue({
      remediated: [missing],
      remaining: { entries: [entry({})] },
    } as never);
    renderPanel();
    await check();
    fireEvent.click(screen.getByRole("button", { name: "Repair" }));
    expect(await screen.findByRole("region", { name: "Fixed by Coffer" })).toHaveTextContent(
      "Link put back",
    );
    expect(screen.getByRole("region", { name: "Needs you" })).toBeInTheDocument();
  });

  test("Review… opens the two-way choice with What will happen and the diff of the side not kept", async () => {
    api.compareCopy.mockResolvedValue({
      agent_name: "codex",
      agent_uid: CODEX.uid,
      kind: "replaced_with_regular",
      modified_at: null,
      path: "/Users/me/.codex/skills/frontend-design",
      skill_uid: "sk-fd",
      changes: [
        {
          path: "SKILL.md",
          status: "modified",
          diff: "@@ -1,2 +1,2 @@\n keep\n-master line\n+folder line\n",
          binary: false,
          additions: 1,
          deletions: 1,
          truncated: false,
        },
      ],
    } as never);
    renderPanel();
    const rows = await check();
    fireEvent.click(within(rows[1]).getByRole("button", { name: "Review…" }));
    const dialog = await screen.findByRole("dialog", {
      name: /a folder is in the way in Codex/,
    });
    expect(dialog).toHaveTextContent("frontend-design: a folder is in the way in Codex");
    expect(dialog).toHaveTextContent(
      "~/.codex/skills/frontend-design is a real folder, not Coffer’s link. Coffer left it alone at start.",
    );
    expect(within(dialog).getAllByRole("radio")).toHaveLength(2);
    expect(
      within(dialog).getByRole("radio", { name: /Replace it with Coffer’s link/ }),
    ).toHaveAttribute("aria-checked", "true");
    expect(within(dialog).getByText("What will happen")).toBeInTheDocument();
    expect(
      within(dialog).getByText(/Nothing changes; it already gets the master\./),
    ).toBeInTheDocument();
    // Keeping the master: the folder's text → the master — the master line is the added one.
    const diff = await within(dialog).findByRole("region", { name: /Changes to .*SKILL\.md/ });
    expect(diff.querySelector('[data-line="add"]')).toHaveTextContent("master line");
    expect(
      within(dialog).getByText(/the folder’s? → the master|Codex’s folder → the master/),
    ).toBeTruthy();
    expect(within(dialog).getByText("Nothing is written until you choose.")).toBeInTheDocument();
    expect(
      within(dialog).getByRole("button", { name: "Replace with Coffer’s link" }),
    ).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Cancel" })).toBeInTheDocument();
  });

  test("choosing Adopt flips the diff and the primary; confirming sends the choice", async () => {
    api.compareCopy.mockResolvedValue({
      agent_name: "codex",
      agent_uid: CODEX.uid,
      kind: "replaced_with_regular",
      modified_at: null,
      path: "/Users/me/.codex/skills/frontend-design",
      skill_uid: "sk-fd",
      changes: [],
    } as never);
    api.resolveCopy.mockResolvedValue(makeSkill() as never);
    renderPanel();
    const rows = await check();
    fireEvent.click(within(rows[1]).getByRole("button", { name: "Review…" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("radio", { name: /Adopt this folder/ }));
    expect(
      within(dialog).getByText("Makes its files the master, so Claude Code gets them too."),
    ).toBeInTheDocument();
    expect(within(dialog).getByText(/Today’s master is kept in History/)).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "Adopt this folder" }));
    await waitFor(() => expect(api.resolveCopy).toHaveBeenCalledWith("sk-fd", CODEX.uid, "agent"));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  test("a refusal stays in the dialog and the primary becomes Retry", async () => {
    api.compareCopy.mockResolvedValue({
      agent_name: "codex",
      agent_uid: CODEX.uid,
      kind: "replaced_with_regular",
      modified_at: null,
      path: "/Users/me/.codex/skills/frontend-design",
      skill_uid: "sk-fd",
      changes: [],
    } as never);
    api.resolveCopy.mockRejectedValue(new ApiError("SKILL_COPY_NOT_OURS", "not ours"));
    renderPanel();
    const rows = await check();
    fireEvent.click(within(rows[1]).getByRole("button", { name: "Review…" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Replace with Coffer’s link" }));
    expect(await within(dialog).findByRole("button", { name: "Retry" })).toBeInTheDocument();
    expect(within(dialog).getByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });
});
