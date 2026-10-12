// frontend/src/test/channelKit.tsx
// Shared fixtures for the Channels page suites: channel rows and statuses
// shaped like the wire, and a renderer that mounts the page at an address the
// way router.tsx routes it (all three channel addresses render the same
// page) and reports where the router ended up. Each suite mocks the network
// boundary itself (vi.mock is hoisted per file).
import { render } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryRouter, RouterProvider } from "react-router-dom";

import { TooltipProvider } from "@/components/ui/tooltip";
import type { ChannelPrompts, ChannelSettings, ChannelStatus } from "@/lib/api/channels";
import type { ResourceOut } from "@/lib/api/resources";
import { ChannelsPage } from "@/pages/ChannelsPage";

/** The agent channels drive — a uid, like every cross-resource reference. */
export const AGENT = { uid: "u-6c1d0b83", name: "claude-code", display_name: "Claude Code" };

export function makeChannel(
  over: Partial<ResourceOut> & { config?: Record<string, unknown> } = {},
) {
  return {
    uid: "u-c0be4512",
    kind: "channel",
    name: "team-bot",
    description: null,
    scope: null,
    enabled: true,
    toggleable: true,
    secrets_readable_by_local_processes: false,
    ...over,
    config: {
      channel_type: "seatalk",
      app_id: "8231",
      app_secret_ref: "channel/0f/app-secret",
      default_agent: AGENT.uid,
      ...(over.config ?? {}),
    },
  } as unknown as ResourceOut;
}

/** What the daemon's typed reading of a channel's config looks like: the stored
 *  keys, with the defaults the daemon fills in for the rest. */
export function makeSettings(channel: ResourceOut): ChannelSettings {
  return {
    default_agent: null,
    default_agent_config: null,
    require_mention: true,
    ignore_other_mentions: false,
    wait_after_text_seconds: 1.5,
    wait_after_forward_seconds: 5,
    show_steps: true,
    new_conversation_after_idle_hours: 24,
    directories: [],
    direct_reply_style: "",
    group_reply_style: "",
    direct_reply_style_base: "",
    group_reply_style_base: "",
    ...channel.config,
  } as unknown as ChannelSettings;
}

/** Coffer's default reply style, as the tests' daemon reports it. */
export const DEFAULT_STYLE = "The first line is the outcome; then at most about 15 lines.";

/** What the daemon reports for the System prompt section. */
export function makePrompts(over: { directChanged?: boolean } = {}): ChannelPrompts {
  const note = (kind: string) =>
    `You are replying in a Telegram ${kind} chat (the team-bot channel). To send a file, put MEDIA:/path on its own line.`;
  return {
    direct: {
      channel_note: note("direct"),
      default_style: DEFAULT_STYLE,
      default_changed: over.directChanged ?? false,
    },
    group: { channel_note: note("group"), default_style: DEFAULT_STYLE, default_changed: false },
  };
}

export function makeStatus(channel: ResourceOut, over: Partial<ChannelStatus> = {}): ChannelStatus {
  const seatalk = channel.config.channel_type === "seatalk";
  return {
    uid: channel.uid,
    name: channel.name,
    channel_type: seatalk ? "seatalk" : "telegram",
    enabled: channel.enabled,
    running: true,
    starting: false,
    pending_pairing: false,
    workspace_directory: "/home/me/.coffer/content/workspace",
    commands: [
      {
        name: "new",
        args: "[agent]",
        description: "Start a fresh conversation (keeps model and directory)",
        description_zh: "开始新对话并保留模型和目录",
      },
      {
        name: "stop",
        args: "",
        description: "Interrupt the running turn",
        description_zh: "中断正在运行的回合",
      },
      {
        name: "model",
        args: "[name]",
        description: "Pick a model",
        description_zh: "选择模型",
      },
    ],
    people: [
      {
        sender_id: "alex",
        display_name: "Alex Chen",
        chat_id: "c-1",
        paired_at: "2026-09-12T08:00:00Z",
        active_conversation_id: null,
      },
    ],
    inbound: seatalk ? { websocket_state: "connected", websocket_error: null } : null,
    diagnostics: [],
    secret_approval: null,
    handoff: null,
    settings: makeSettings(channel),
    prompts: makePrompts(),
    ...over,
  };
}

let router: ReturnType<typeof createMemoryRouter> | null = null;

/** Where the router is now — path and query. */
export const where = {
  get url(): string {
    const loc = router?.state.location;
    return loc ? loc.pathname + loc.search : "";
  },
};

/** Mount the Channels page at `url`, routed as router.tsx routes it. */
export function renderChannelsPage(url = "/channels") {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  router = createMemoryRouter(
    [
      { path: "/channels", element: <ChannelsPage /> },
      { path: "/channels/:uid", element: <ChannelsPage /> },
      { path: "/channels/:uid/:tab", element: <ChannelsPage /> },
      { path: "/conversations", element: <div>conversations page</div> },
    ],
    { initialEntries: [url] },
  );
  return render(
    <QueryClientProvider client={qc}>
      <TooltipProvider>
        <RouterProvider router={router} />
      </TooltipProvider>
    </QueryClientProvider>,
  );
}
