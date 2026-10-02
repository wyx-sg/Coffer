// frontend/src/components/skills/SkillDeliveryEdit.test.tsx
// Editing delivery from a skill's Delivery tab (spec skill-manager "Decide
// which agents a skill is for"): each agent — delivered or not — has a switch
// that writes the skill's scope, shows pending, toasts, and keeps the header's
// reach button in step; a switched-off agent cannot be switched on.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";

import type { AgentOut } from "@/lib/api/agents";
import type { SkillOut } from "@/lib/api/skills";
import { makeAgent, makeSkill, renderSkillsPage } from "@/test/skillsPageKit";

const h = vi.hoisted(() => ({
  skills: [] as SkillOut[],
  agents: [] as AgentOut[],
  agentResources: [] as { uid: string; enabled: boolean }[],
  release: null as null | (() => void),
  fail: false,
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

vi.mock("@/components/ui/toast", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/components/ui/toast")>()),
  useToast: () => ({ toast: h.toast, dismiss: vi.fn() }),
}));

vi.mock("@/lib/api/skills", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/skills")>()),
  skillsApi: {
    list: vi.fn(async () => ({ items: h.skills })),
    filesTree: vi.fn(),
    fileContent: vi.fn(),
    verify: vi.fn(async () => ({ entries: [] })),
  },
}));
vi.mock("@/lib/api/agents", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/agents")>()),
  agentsApi: { list: vi.fn(async () => ({ items: h.agents })) },
}));
vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  getApiClient: () => ({
    GET: async () => ({
      data: { resources: h.agentResources.map((r) => ({ ...r, kind: "agent", scope: null })) },
      error: undefined,
    }),
  }),
}));
vi.mock("@/lib/api/scope", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/scope")>()),
  scopeApi: {
    put: vi.fn(async (_uid: string, scope: { agents: string[] | null } | null) => {
      if (h.release) await new Promise<void>((r) => (h.release = r));
      if (h.fail) throw new Error("boom");
      h.skills = h.skills.map((s) => ({ ...s, scope }));
      return {};
    }),
  },
}));

const { scopeApi } = await import("@/lib/api/scope");

const CC = makeAgent();
const CODEX = makeAgent({ uid: "ag-cx", name: "codex", display_name: "Codex", type: "codex" });

beforeEach(() => {
  h.skills = [makeSkill({ scope: { agents: [CC.uid] } })];
  h.agents = [CC, CODEX];
  h.agentResources = [
    { uid: CC.uid, enabled: true },
    { uid: CODEX.uid, enabled: true },
  ];
  h.release = null;
  h.fail = false;
});
afterEach(() => vi.clearAllMocks());

const row = (name: string) => screen.findByTestId(`skill-delivery-${name}`);
const headerText = () => document.querySelector("header")?.textContent ?? "";

describe("the delivery tab's switches", () => {
  test("every agent has a switch, on for the delivered and off for the rest", async () => {
    renderSkillsPage("/skills/hello/delivery");
    const cc = within(await row("claude-code")).getByRole("switch");
    const cx = within(await row("codex")).getByRole("switch");
    expect(cc).toBeChecked();
    expect(cx).not.toBeChecked();
  });

  test("turning an agent on writes the scope, toasts, and the header follows", async () => {
    renderSkillsPage("/skills/hello/delivery");
    const before = headerText();
    fireEvent.click(within(await row("codex")).getByRole("switch"));
    await waitFor(() =>
      expect(scopeApi.put).toHaveBeenCalledWith("sk-11aa", { agents: [CC.uid, CODEX.uid] }),
    );
    await waitFor(() => expect(h.toast.success).toHaveBeenCalledWith("Delivered to Codex"));
    await waitFor(() =>
      expect(within(screen.getByTestId("skill-delivery-codex")).getByRole("switch")).toBeChecked(),
    );
    await waitFor(() => expect(headerText()).not.toBe(before));
  });

  test("turning an agent off writes the scope without it", async () => {
    renderSkillsPage("/skills/hello/delivery");
    fireEvent.click(within(await row("claude-code")).getByRole("switch"));
    await waitFor(() => expect(scopeApi.put).toHaveBeenCalledWith("sk-11aa", { agents: [] }));
    await waitFor(() => expect(h.toast.success).toHaveBeenCalledWith("Removed from Claude Code"));
  });

  test("a change in flight dims the row and says what is happening", async () => {
    h.release = () => {};
    renderSkillsPage("/skills/hello/delivery");
    fireEvent.click(within(await row("codex")).getByRole("switch"));
    const pending = await screen.findByTestId("skill-delivery-codex");
    await waitFor(() => expect(pending).toHaveTextContent("Delivering…"));
    expect(pending).toHaveAttribute("aria-busy", "true");
    expect(within(pending).queryByRole("switch")).toBeNull();
    h.release?.();
    await waitFor(() =>
      expect(screen.getByTestId("skill-delivery-codex")).not.toHaveAttribute("aria-busy"),
    );
  });

  test("a refused change leaves the row as it was", async () => {
    h.fail = true;
    renderSkillsPage("/skills/hello/delivery");
    fireEvent.click(within(await row("codex")).getByRole("switch"));
    await waitFor(() =>
      expect(screen.getByTestId("skill-delivery-codex")).not.toHaveAttribute("aria-busy"),
    );
    expect(
      within(screen.getByTestId("skill-delivery-codex")).getByRole("switch"),
    ).not.toBeChecked();
    expect(h.toast.success).not.toHaveBeenCalled();
  });

  test("an agent that is switched off keeps its switch off and says why", async () => {
    h.agentResources = [
      { uid: CC.uid, enabled: true },
      { uid: CODEX.uid, enabled: false },
    ];
    renderSkillsPage("/skills/hello/delivery");
    const codex = await row("codex");
    await waitFor(() => expect(within(codex).getByRole("switch")).toBeDisabled());
    expect(codex).toHaveTextContent("The agent is off.");
  });

  test("Deliver to all writes the every-agent scope", async () => {
    renderSkillsPage("/skills/hello/delivery");
    fireEvent.click(await screen.findByRole("button", { name: "Deliver to all" }));
    await waitFor(() => expect(scopeApi.put).toHaveBeenCalledWith("sk-11aa", null));
  });
});
