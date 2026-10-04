// src/components/agents/model/ChangeModelDialog.test.tsx — Change model: form → Review changes → Apply, and the stale refusal (boards 2.1.16, 2.1.62, 2.1.18).
import type { PropsWithChildren } from "react";
import { beforeEach, describe, expect, test } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import type { AgentOut } from "@/lib/api/agents";
import { ApiError } from "@/lib/api/errors";
import type { Provider } from "@/lib/api/providers";
import { acceptance } from "@/test/acceptance";
import { fakeApi } from "@/test/fakeApi";

import { ChangeModelDialog } from "./ChangeModelDialog";

const call = fakeApi();

const AGENT: AgentOut = {
  uid: "u-cc",
  name: "claude-code",
  type: "claude_code",
  config_dir: "/Users/me/.claude",
  display_name: "Claude Code",
  model: "m1",
  tier_models: { opus: "m1", sonnet: "m1", haiku: "m1" },
  version: null,
  install_handoff: null,
  connection_uid: "u-gw",
  state: "installed_active",
  created_at: "",
  updated_at: "",
};
const PROVIDER = {
  uid: "u-gw",
  name: "gw",
  title: null,
  protocol: "anthropic",
  base_url: "https://gw.example",
  secret_ref: "ref",
  enabled: true,
  internal_default: false,
  transcribe_default: false,
  description: null,
  local_runtime: null,
  compatible_agents: ["claude_code"],
  models: [
    { id: "m1", modality: "text" },
    { id: "m2", modality: "text" },
  ],
  created_at: "",
  updated_at: "",
} as unknown as Provider;

const PREVIEW = {
  agent_uid: "u-cc",
  agent_name: "claude-code",
  connection_name: "gw",
  files: [
    {
      path: "/Users/me/.claude/settings.json",
      op: "modify",
      added: 1,
      removed: 0,
      fingerprint: "fp1",
      diff: [
        { kind: "hunk", text: "@@ -1,1 +1,2 @@" },
        { kind: "add", text: '"model": "m2"', new_no: 2 },
      ],
    },
  ],
};

let applyError: ApiError | null;
let testResult: { ok: boolean; message: string };

beforeEach(() => {
  call.mockReset();
  applyError = null;
  testResult = { ok: true, message: "ok" };
  call.mockImplementation(async (path: string, opts) => {
    if (path === "/providers") return { providers: [PROVIDER] };
    if (path.startsWith("/agent-providers/")) return { models: [], default_model: null };
    if (path === "/models/test-connection") return testResult;
    if (path === "/providers/model-switch/preview") return PREVIEW;
    if (path === "/providers/model-switch/apply") {
      if (applyError) throw applyError;
      return PREVIEW;
    }
    throw new Error(`unexpected ${opts.method} ${path}`);
  });
});

function renderDialog(agent: AgentOut = AGENT) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
  render(<ChangeModelDialog agent={agent} open onOpenChange={() => {}} />, { wrapper: Wrapper });
}

async function reviewChange() {
  const model = await screen.findByRole("combobox", { name: "Default model" });
  fireEvent.keyDown(model, { key: "ArrowDown" });
  fireEvent.click(await screen.findByRole("option", { name: "m2" }));
  await waitFor(() => expect(screen.getByRole("button", { name: "Review changes" })).toBeEnabled());
  fireEvent.click(screen.getByRole("button", { name: "Review changes" }));
  expect((await screen.findAllByText("~/.claude/settings.json")).length).toBeGreaterThan(0);
}

describe("ChangeModelDialog", () => {
  test("Review changes is off until something changes, then previews and applies", async () => {
    renderDialog();
    expect(await screen.findByText("Change Claude Code’s model")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Review changes" })).toBeDisabled();
    await reviewChange();
    const preview = call.mock.calls.find(([p]) => p === "/providers/model-switch/preview");
    expect((preview?.[1] as { body: unknown }).body).toMatchObject({
      agent_type: "claude_code",
      connection_uid: "u-gw",
      model: "m2",
    });
    fireEvent.click(await screen.findByRole("button", { name: "Apply 1 change" }));
    await waitFor(() =>
      expect(call.mock.calls.some(([p]) => p === "/providers/model-switch/apply")).toBe(true),
    );
    const apply = call.mock.calls.find(([p]) => p === "/providers/model-switch/apply");
    expect((apply?.[1] as { body: { seen: unknown } }).body.seen).toEqual({
      "/Users/me/.claude/settings.json": "fp1",
    });
  });

  acceptance(
    "provider-switching",
    "applying refuses a file that changed after the preview",
    async () => {
      applyError = Object.assign(new ApiError("CONFIG_FILE_STALE", "stale"), { status: 409 });
      renderDialog();
      await reviewChange();
      fireEvent.click(await screen.findByRole("button", { name: "Apply 1 change" }));
      expect(await screen.findByText("settings.json changed on disk")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Reload preview" })).toBeInTheDocument();
    },
  );

  acceptance(
    "provider-switching",
    "the Change model dialog shows only provider, model and tiers",
    async () => {
      // Claude Code on a non-Claude connection: provider, model and the tiers.
      renderDialog();
      const dialog = await screen.findByRole("dialog");
      await within(dialog).findByText("Default model");
      for (const label of ["Provider", "Default model", "Model per tier"]) {
        expect(within(dialog).getByText(label)).toBeInTheDocument();
      }
      expect(
        within(dialog).queryByText(/output limit|subagent|fallback|thinking|fast/i),
      ).toBeNull();
    },
  );

  test("Codex shows provider and model, no tiers", async () => {
    const codexProvider = {
      ...PROVIDER,
      protocol: "openai",
      compatible_agents: ["codex"],
    } as unknown as Provider;
    call.mockImplementation(async (path: string, opts) => {
      if (path === "/providers") return { providers: [codexProvider] };
      if (path.startsWith("/agent-providers/")) return { models: [], default_model: null };
      throw new Error(`unexpected ${opts.method} ${path}`);
    });
    renderDialog({ ...AGENT, uid: "u-cx", type: "codex", config_dir: "/Users/me/.codex" });
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByText("Provider")).toBeInTheDocument();
    expect(within(dialog).getByText("Default model")).toBeInTheDocument();
    expect(within(dialog).queryByText("Model per tier")).toBeNull();
  });

  acceptance("provider-switching", "the built-in login asks for a provider only", async () => {
    renderDialog();
    const dialog = await screen.findByRole("dialog");
    const trigger = await within(dialog).findByRole("combobox", { name: /provider/i });
    fireEvent.keyDown(trigger, { key: "ArrowDown" });
    fireEvent.click(await screen.findByRole("option", { name: /built-in login/i }));
    await waitFor(() => expect(within(dialog).queryByText("Default model")).toBeNull());
    expect(within(dialog).queryByText("Model per tier")).toBeNull();
    expect(within(dialog).getByText(/picks its model itself/)).toBeInTheDocument();
  });

  acceptance(
    "provider-switching",
    "a model change is tested before it can be reviewed",
    async () => {
      renderDialog();
      const model = await screen.findByRole("combobox", { name: "Default model" });
      fireEvent.keyDown(model, { key: "ArrowDown" });
      fireEvent.click(await screen.findByRole("option", { name: "m2" }));
      const review = screen.getByRole("button", { name: "Review changes" });
      expect(review).toBeDisabled();
      expect(await screen.findByText("Testing connection…")).toBeInTheDocument();
      expect(await screen.findByText(/Connection OK · \d+ ms/)).toBeInTheDocument();
      expect(review).toBeEnabled();
      const probe = call.mock.calls.find(([p]) => p === "/models/test-connection");
      expect((probe?.[1] as { body: unknown }).body).toMatchObject({
        provider: "anthropic",
        model: "m2",
        base_url: "https://gw.example",
        secret_ref: "ref",
      });
    },
  );

  acceptance(
    "provider-switching",
    "a failed connection test keeps Review changes off and offers Retry",
    async () => {
      testResult = { ok: false, message: "401 unauthorized" };
      renderDialog();
      const model = await screen.findByRole("combobox", { name: "Default model" });
      fireEvent.keyDown(model, { key: "ArrowDown" });
      fireEvent.click(await screen.findByRole("option", { name: "m2" }));
      expect(await screen.findByText("Connection failed: 401 unauthorized")).toBeInTheDocument();
      const review = screen.getByRole("button", { name: "Review changes" });
      expect(review).toBeDisabled();
      expect(screen.getByText(/Fix the connection or pick another model/)).toBeInTheDocument();
      testResult = { ok: true, message: "ok" };
      fireEvent.click(screen.getByRole("button", { name: "Retry" }));
      expect(await screen.findByText(/Connection OK/)).toBeInTheDocument();
      expect(review).toBeEnabled();
    },
  );

  acceptance("provider-switching", "the built-in login needs no connection test", async () => {
    renderDialog();
    const dialog = await screen.findByRole("dialog");
    const trigger = await within(dialog).findByRole("combobox", { name: /provider/i });
    fireEvent.keyDown(trigger, { key: "ArrowDown" });
    fireEvent.click(await screen.findByRole("option", { name: /built-in login/i }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Review changes" })).toBeEnabled(),
    );
    expect(call.mock.calls.filter(([p]) => p === "/models/test-connection")).toHaveLength(0);
    expect(within(dialog).queryByText(/Connection OK|Testing connection/)).toBeNull();
  });
});
