// src/components/custom-tools/GroupBanners.test.tsx — what a group says about itself: the header's state pill, the
// banner under it (failing calls with a hand-off, Off with Turn on, a missing secret, a secret waiting for
// approval with one button) and the list row's subtitle.
import { beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { TooltipProvider } from "@/components/ui/tooltip";
import type { CustomToolGroup } from "@/lib/api/customTools";
import { openApprovalsSheet } from "@/lib/hooks/useApprovals";
import { GroupBanners } from "./GroupBanners";
import { GroupHeader } from "./GroupHeader";
import { GroupRow } from "./GroupRow";
import { makeGroup } from "./testFixtures";

vi.mock("@/lib/api/secret", () => ({
  secretsApi: {
    list: vi.fn(async () => ({
      refs: [
        {
          ref: "secret/a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1",
          label: "Grafana token",
          present: false,
          cited_by: [],
          mentioned_by_skills: [],
          bindings: [],
        },
      ],
    })),
  },
}));
vi.mock("@/lib/api/resources", () => ({
  resourcesApi: { enable: vi.fn(async () => undefined), disable: vi.fn() },
}));
vi.mock("@/lib/api/scope", () => ({ scopeApi: { get: vi.fn(), put: vi.fn() } }));
vi.mock("@/lib/hooks/useAgents", () => ({
  useAgents: vi.fn(() => ({ data: [{ uid: "ag-cc", name: "claude-code", type: "claude_code" }] })),
}));
vi.mock("@/lib/hooks/useApprovals", () => ({ openApprovalsSheet: vi.fn() }));
const { resourcesApi } = await import("@/lib/api/resources");

function mount(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <TooltipProvider>
        <MemoryRouter>{ui}</MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>,
  );
}

const banners = (g: CustomToolGroup) =>
  mount(<GroupBanners group={g} onChooseAnother={() => {}} />);

beforeEach(() => vi.clearAllMocks());

describe("group banners", () => {
  test("failing calls say so, link to the group's calls and hand off to an agent", () => {
    banners(
      makeGroup({
        name: "status-page",
        health: "failing",
        health_reason: "last_call_failed",
        handoff: { prompt: "Find out why the calls of status-page fail" },
      }),
    );
    expect(
      screen.getByText("Calls to status-page.internal.example are failing"),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View calls" })).toHaveAttribute(
      "href",
      "/activity?tab=mcp&q=status-page",
    );
    expect(screen.getByRole("button", { name: /Hand off to|Copy prompt/ })).toBeInTheDocument();
  });

  test("an Off group says no agent can use it and turns on from the banner", async () => {
    banners(makeGroup({ name: "pagerduty", enabled: false, health: "off" }));
    expect(screen.getByText("Off — no agent can use it")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Turn on" }));
    await waitFor(() => expect(resourcesApi.enable).toHaveBeenCalledWith("uid-pagerduty"));
  });

  test("a missing secret has Add secret and Choose another, no hand-off", async () => {
    const onChoose = vi.fn();
    mount(
      <GroupBanners
        group={makeGroup({
          name: "grafana",
          health: "attention",
          secret_state: "missing",
          headers: [
            {
              name: "Authorization",
              value: null,
              secret: "a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1",
              secret_state: "missing",
            },
          ],
        })}
        onChooseAnother={onChoose}
      />,
    );
    expect(await screen.findByText("Secret Grafana token isn't in Secrets")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add secret" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Choose another" }));
    expect(onChoose).toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: /Hand off to|Copy prompt/ })).toBeNull();
  });

  test("a secret waiting for approval has one button, Open approvals", async () => {
    banners(
      makeGroup({
        name: "grafana",
        health: "attention",
        secret_state: "pending_approval",
        pending_secrets: ["a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1"],
        headers: [
          {
            name: "Authorization",
            value: null,
            secret: "a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1",
            secret_state: "pending_approval",
          },
        ],
      }),
    );
    expect(await screen.findByText("Grafana token waits for approval")).toBeInTheDocument();
    expect(screen.getAllByRole("button")).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "Open approvals" }));
    expect(openApprovalsSheet).toHaveBeenCalled();
  });

  test("a healthy group has no banner", () => {
    const { container } = banners(makeGroup());
    expect(container).toBeEmptyDOMElement();
  });
});

describe("group header and row", () => {
  test("the header pill names the secret problem and Reach · Edit group · ⋯ stay fixed", () => {
    mount(
      <GroupHeader
        group={makeGroup({ health: "attention", secret_state: "pending_approval" })}
        onEdit={() => {}}
        onDelete={() => {}}
      />,
    );
    expect(screen.getByText("Waiting for approval")).toBeInTheDocument();
    expect(screen.getByTestId("scope-control")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Edit group" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /More actions for billing/ })).toBeInTheDocument();
  });

  test("a group waiting for approval says so in the list, without the secret's name", () => {
    mount(
      <ul>
        <GroupRow
          group={makeGroup({ health: "attention", secret_state: "pending_approval" })}
          selected={false}
          onOpen={() => {}}
          checked={false}
          onCheckedChange={() => {}}
        />
      </ul>,
    );
    expect(screen.getByText("Waiting for approval")).toHaveClass("text-warning");
  });

  test("an Off row leaves the reach column empty", () => {
    mount(
      <ul>
        <GroupRow
          group={makeGroup({ enabled: false, health: "off" })}
          selected={false}
          onOpen={() => {}}
          checked={false}
          onCheckedChange={() => {}}
        />
      </ul>,
    );
    expect(screen.queryByText("All agents")).toBeNull();
    expect(screen.queryByText("Off")).toBeNull();
  });
});
