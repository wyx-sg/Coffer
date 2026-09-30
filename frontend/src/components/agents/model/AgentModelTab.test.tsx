// src/components/agents/model/AgentModelTab.test.tsx
//
// The agent's Model tab: provider cards, the model picker (fixed list, text
// models only), Effort from the catalogue, Model per tier, test → confirm, and
// the stale-file refusal. Only the network boundary (`call`) is faked; every
// hook and the query cache are real. Connection uids are `u-`-prefixed and
// differ from names, so a request that carried a name would fail loudly.
import type { PropsWithChildren } from "react";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { acceptance } from "@/test/acceptance";
import { ApiError } from "@/lib/api/errors";
import type { AgentOut } from "@/lib/api/agents";
import type { AgentModel } from "@/lib/api/agentModels";
import type { Provider, ProviderModel } from "@/lib/api/providers";
import { AgentModelTab } from "./AgentModelTab";

const call = vi.fn();
vi.mock("@/lib/api/call", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/call")>();
  return { ...actual, call: (...args: unknown[]) => call(...args) };
});

const CLAUDE: AgentOut = {
  uid: "a-claude",
  name: "claude-code",
  type: "claude_code",
  config_dir: "/home/me/.claude",
  display_name: "Claude Code",
  model: null,
  effort: null,
  tier_models: null,
  wire_api: null,
  version: null,
  state: "installed_active",
  created_at: "",
  updated_at: "",
};
const CODEX: AgentOut = { ...CLAUDE, uid: "a-codex", type: "codex", config_dir: "/home/me/.codex" };

const text = (...ids: string[]): ProviderModel[] => ids.map((id) => ({ id, modality: "text" }));

function conn(name: string, over: Partial<Provider> = {}): Provider {
  return {
    uid: `u-${name}`,
    name,
    protocol: "anthropic",
    base_url: "https://api.example.com",
    secret_ref: "ref",
    is_active: false,
    title: null,
    internal_default: false,
    transcribe_default: false,
    fallback: true,
    models: [],
    enabled: true,
    description: null,
    local_runtime: null,
    compatible_agents: ["claude_code"],
    created_at: "",
    updated_at: "",
    ...over,
  };
}

interface Net {
  providers?: Provider[];
  catalogue?: AgentModel[];
  listed?: ProviderModel[];
  testOk?: boolean;
  activate?: () => unknown;
  route?: unknown;
}

function serve(net: Net) {
  call.mockImplementation(async (path: string, opts?: { method?: string }) => {
    const method = opts?.method ?? "GET";
    if (path === "/providers") return { providers: net.providers ?? [] };
    if (path.startsWith("/agent-providers/")) return { models: net.catalogue ?? [] };
    if (path === "/models/list-models") return { models: net.listed ?? [], message: "" };
    if (path === "/models/test-connection")
      return net.testOk === false
        ? { ok: false, message: "invalid key" }
        : { ok: true, message: "Reached api.example.com in 420 ms" };
    if (method === "PATCH") return CLAUDE;
    if (path.endsWith("/activate")) return net.activate ? net.activate() : {};
    if (path.startsWith("/providers/use-builtin/")) return {};
    if (path.startsWith("/proxy/routes/")) return net.route ?? { primary: null, fallbacks: [] };
    if (path.endsWith("/hint")) return { agent_uid: "a", last4: "3f2a" };
    if (path.endsWith("/rotate")) return { agent_uid: "a", rotated: true };
    if (path === "/proxy/status") return { port: 8001 };
    throw new Error(`unexpected ${method} ${path}`);
  });
}

function renderTab(agent: AgentOut = CLAUDE) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const Wrapper = ({ children }: PropsWithChildren) => (
    <MemoryRouter>
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    </MemoryRouter>
  );
  return render(<AgentModelTab agent={agent} />, { wrapper: Wrapper });
}

const calls = (pred: (path: string, method: string) => boolean) =>
  call.mock.calls.filter(([p, o]) =>
    pred(p as string, (o as { method?: string })?.method ?? "GET"),
  );

/** Open a Select by its label and read its options, then close it again. */
async function options(name: RegExp, expectOne?: string): Promise<string[]> {
  fireEvent.keyDown(screen.getByRole("combobox", { name }), { key: "ArrowDown" });
  if (expectOne) await screen.findByRole("option", { name: expectOne });
  const out = screen.queryAllByRole("option").map((o) => o.textContent ?? "");
  fireEvent.keyDown(document.activeElement ?? document.body, { key: "Escape" });
  return out;
}

const card = (name: RegExp) => screen.findByRole("radio", { name });
const confirmBtn = () => screen.getByRole("button", { name: /confirm switch/i });

beforeEach(() => {
  call.mockReset();
});

describe("AgentModelTab", () => {
  acceptance("provider-switching", "the Model tab says which provider is tried next", async () => {
    serve({
      providers: [conn("official", { is_active: true })],
      listed: text("claude-opus-4-8"),
      route: {
        agent_uid: CLAUDE.uid,
        model: "claude-opus-4-8",
        primary: { connection_uid: "u-official", name: "official", local: false },
        fallbacks: [{ connection_uid: "u-gw", name: "Company gateway", local: false }],
      },
    });
    renderTab({ ...CLAUDE, model: "claude-opus-4-8" });
    expect(
      await screen.findByText(
        "If official fails: Company gateway — it also offers claude-opus-4-8",
      ),
    ).toBeInTheDocument();
    expect(await screen.findByText(/••••3f2a/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /rotate/i }));
    await waitFor(() =>
      expect(calls((p, m) => p.endsWith("/rotate") && m === "POST")).toHaveLength(1),
    );
  });

  test("no fallback, and nothing at all on the built-in login", async () => {
    serve({
      providers: [conn("official", { is_active: true })],
      route: {
        agent_uid: CLAUDE.uid,
        model: null,
        primary: { connection_uid: "u-official", name: "official", local: false },
        fallbacks: [],
      },
    });
    const view = renderTab();
    expect(await screen.findByText("If official fails: No fallback")).toBeInTheDocument();
    view.unmount();
    serve({ providers: [] });
    renderTab();
    await screen.findByText("No other compatible provider yet");
    expect(screen.queryByText(/Proxy token/)).toBeNull();
  });

  acceptance(
    "provider-switching",
    "the agent's model picker offers a fixed list without free-form entry",
    async () => {
      serve({
        providers: [conn("official", { is_active: true })],
        listed: text("claude-opus-4-8", "claude-haiku-4-5"),
      });
      renderTab({ ...CLAUDE, model: "claude-opus-4-8" });
      await screen.findByRole("combobox", { name: /^model$/i });
      const opts = await options(/^model$/i, "claude-haiku-4-5");
      // The connection's INTROSPECTED models; an id is chosen, never typed.
      expect(opts).toEqual(["claude-opus-4-8", "claude-haiku-4-5"]);
      expect(opts.some((o) => /custom/i.test(o))).toBe(false);
      expect(screen.queryByRole("textbox")).toBeNull();
    },
  );

  acceptance(
    "provider-switching",
    "a non-text curated model never reaches a chat model picker",
    async () => {
      serve({
        providers: [
          conn("agnes", {
            is_active: true,
            models: [
              { id: "agnes-2.0", modality: "text" },
              { id: "agnes-embed-3", modality: "embedding" },
            ],
          }),
        ],
      });
      renderTab({ ...CLAUDE, model: "agnes-2.0", tier_models: { opus: "agnes-2.0" } });
      await screen.findByRole("combobox", { name: /^model$/i });
      // Every chat slot — the Model and each tier — offers the text id only,
      // and a curated connection is never probed.
      expect(await options(/^model$/i, "agnes-2.0")).toEqual(["agnes-2.0"]);
      expect(await options(/^opus$/i, "agnes-2.0")).toEqual(["agnes-2.0"]);
      expect(calls((p) => p === "/models/list-models")).toHaveLength(0);
    },
  );

  test("built-in login with no other connection: add one, nothing to apply", async () => {
    serve({
      catalogue: [
        {
          id: "claude-opus-5-5",
          label: "Opus 5.5",
          description: "",
          efforts: [],
          default_effort: null,
        },
      ],
    });
    renderTab();
    expect(await screen.findByText("No other compatible provider yet")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /add provider/i })).toHaveAttribute(
      "href",
      "/model-providers",
    );
    expect(screen.getByRole("radio", { name: /built-in login/i })).toHaveAttribute(
      "aria-checked",
      "true",
    );
    expect(screen.getByText("Current")).toBeInTheDocument();
    // The default is shown, not offered; no tiers on the built-in login.
    expect(await screen.findByText("claude-opus-5-5 · Claude Code’s default")).toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: /^model$/i })).toBeNull();
    expect(screen.queryByText("Model per tier")).toBeNull();
    expect(screen.getByText("Nothing to apply")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /confirm switch/i })).toBeNull();
  });

  test("a disabled or unrouted connection is not offered", async () => {
    serve({
      providers: [
        conn("live"),
        conn("switched-off", { enabled: false }),
        conn("gpt", { compatible_agents: ["codex"] }),
      ],
    });
    renderTab();
    await card(/live/);
    expect(screen.queryByRole("radio", { name: /switched-off/ })).toBeNull();
    expect(screen.queryByRole("radio", { name: /gpt/ })).toBeNull();
    expect(screen.getByText(/api\.example\.com · key in Coffer’s vault/)).toBeInTheDocument();
  });

  // Scenario (revise-web-ui-ia, provider-switching): "a Claude-id gateway matches each tier by name"
  test("picking a connection stages a model and the tier suggestion; test, then confirm", async () => {
    serve({
      providers: [
        conn("gateway", {
          models: text("claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5", "claude-fable-1"),
        }),
      ],
    });
    renderTab();
    fireEvent.click(await card(/gateway/));
    // A pick is a draft: nothing written, confirm waits for a test.
    expect(calls((_p, m) => m === "PATCH")).toHaveLength(0);
    expect(confirmBtn()).toBeDisabled();
    expect(screen.getByRole("combobox", { name: /^haiku$/i })).toHaveTextContent("claude-haiku-5");
    expect(screen.getByRole("combobox", { name: /^fable$/i })).toHaveTextContent("claude-fable-1");
    // The review names the file and the tier pins before anything is written.
    const review = screen.getByRole("region", { name: /review the switch/i });
    expect(within(review).getByText("~/.claude/settings.json")).toBeInTheDocument();
    expect(
      within(review).getByText(/"env.ANTHROPIC_DEFAULT_SONNET_MODEL": "claude-sonnet-5-5"/),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /test connection/i }));
    expect(await screen.findByText(/Reached api.example.com/)).toBeInTheDocument();
    await waitFor(() => expect(confirmBtn()).toBeEnabled());
    fireEvent.click(confirmBtn());
    await waitFor(() =>
      expect(calls((p) => p === "/providers/u-gateway/activate")).toHaveLength(1),
    );
    const [, patch] = calls((_p, m) => m === "PATCH")[0] as [string, { body: unknown }];
    expect(patch.body).toEqual({
      model: "claude-opus-5-5",
      effort: null,
      tier_models: {
        opus: "claude-opus-5-5",
        sonnet: "claude-sonnet-5-5",
        haiku: "claude-haiku-5",
        fable: "claude-fable-1",
      },
    });
  });

  // Scenario (revise-web-ui-ia, provider-switching): "a non-Claude connection pins every tier to the model"
  test("a non-Claude connection pins every tier to the model, with no Fable row", async () => {
    serve({ providers: [conn("kimi", { models: text("kimi-k3", "kimi-k3-mini") })] });
    renderTab();
    fireEvent.click(await card(/kimi/));
    for (const tier of [/^opus$/i, /^sonnet$/i, /^haiku$/i])
      expect(screen.getByRole("combobox", { name: tier })).toHaveTextContent("kimi-k3");
    expect(screen.queryByRole("combobox", { name: /^fable$/i })).toBeNull();
  });

  test("a failed test keeps confirm disabled and shows the message", async () => {
    serve({ providers: [conn("agnes", { models: text("agnes-2.0") })], testOk: false });
    renderTab();
    fireEvent.click(await card(/agnes/));
    fireEvent.click(screen.getByRole("button", { name: /test connection/i }));
    expect(await screen.findByText("invalid key")).toBeInTheDocument();
    expect(confirmBtn()).toBeDisabled();
  });

  // Scenario (revise-web-ui-ia, provider-switching): "the model tab shows only provider, model, effort and the tiers"
  test("Codex: Effort offers the catalogue's levels, and there is no tier section", async () => {
    serve({
      providers: [
        conn("openai", {
          is_active: true,
          protocol: "openai",
          compatible_agents: ["codex"],
          models: text("gpt-5"),
        }),
      ],
      catalogue: [
        {
          id: "gpt-5",
          label: "GPT-5",
          description: "",
          efforts: ["low", "medium", "high"],
          default_effort: "medium",
        },
      ],
    });
    renderTab({ ...CODEX, model: "gpt-5" });
    const effort = await screen.findByRole("radiogroup", { name: "Effort" });
    expect(
      within(effort)
        .getAllByRole("radio")
        .map((r) => r.textContent),
    ).toEqual(["Model default", "Low", "Medium", "High"]);
    expect(screen.queryByText("Model per tier")).toBeNull();
    expect(screen.queryByRole("spinbutton")).toBeNull();
  });

  test("a model that reports no levels hides Effort", async () => {
    serve({ providers: [conn("official", { is_active: true, models: text("m1") })] });
    renderTab({ ...CLAUDE, model: "m1" });
    expect(
      await screen.findByText("Effort is hidden: this model reports no levels."),
    ).toBeInTheDocument();
    expect(screen.queryByRole("radiogroup", { name: "Effort" })).toBeNull();
  });

  test("switching to the built-in login confirms without a test", async () => {
    serve({ providers: [conn("official", { is_active: true, models: text("m1") })] });
    renderTab({ ...CLAUDE, model: "m1" });
    await card(/official/);
    fireEvent.click(await card(/built-in login/i));
    const review = screen.getByRole("region", { name: /review the switch/i });
    expect(within(review).getByText("apiKeyHelper")).toBeInTheDocument();
    fireEvent.click(confirmBtn());
    await waitFor(() =>
      expect(calls((p) => p === "/providers/use-builtin/claude_code")).toHaveLength(1),
    );
    expect(calls((_p, m) => m === "PATCH")).toHaveLength(0);
  });

  test("a stale settings.json refuses the switch and Reload keeps the draft", async () => {
    serve({
      providers: [conn("agnes", { models: text("agnes-2.0") })],
      activate: () => {
        throw new ApiError("CONFIG_FILE_STALE", "changed on disk");
      },
    });
    renderTab();
    fireEvent.click(await card(/agnes/));
    fireEvent.click(screen.getByRole("button", { name: /test connection/i }));
    await waitFor(() => expect(confirmBtn()).toBeEnabled());
    fireEvent.click(confirmBtn());
    expect(
      await screen.findByText("Switch refused — settings.json changed on disk"),
    ).toBeInTheDocument();
    const before = calls((p) => p === "/providers").length;
    fireEvent.click(screen.getByRole("button", { name: /reload preview/i }));
    await waitFor(() => expect(calls((p) => p === "/providers").length).toBeGreaterThan(before));
    expect(screen.queryByText(/Switch refused/)).toBeNull();
    expect(screen.getByRole("radio", { name: /agnes/ })).toHaveAttribute("aria-checked", "true");
  });
});
