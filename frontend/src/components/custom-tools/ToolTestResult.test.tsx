// src/components/custom-tools/ToolTestResult.test.tsx — each way a test run can end reads as the canvas
// boards do: an answer, the API's error, a rejected secret, a timeout, no connection, a response cut short.
import { describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import type { CustomToolTestOut } from "@/lib/api/customTools";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ToolTestResult } from "./ToolTestResult";

vi.mock("@/lib/api/secret", () => ({
  secretsApi: {
    list: vi.fn(async () => ({
      refs: [
        {
          ref: "secret/deploy-token",
          present: true,
          locked: false,
          cited_by: [],
          mentioned_by_skills: [],
          bindings: [],
        },
      ],
    })),
  },
}));

const URL = "https://deploy.internal.example/v1/services/web/health?env=staging";

function result(patch: Partial<CustomToolTestOut>): CustomToolTestOut {
  return {
    ok: true,
    duration_ms: 180,
    url: URL,
    status: 200,
    status_line: "HTTP 200 OK",
    body: '{"healthy":true}',
    truncated: false,
    content_type: "application/json",
    error: null,
    failure: null,
    handoff: null,
    ...patch,
  };
}

const show = (r: CustomToolTestOut, onChangeTimeout?: () => void) =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <TooltipProvider>
        <MemoryRouter>
          <ToolTestResult
            result={r}
            method="GET"
            group="deploy-api"
            secret="deploy-token"
            timeoutSeconds={30}
            onChangeTimeout={onChangeTimeout}
          />
        </MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>,
  );
const block = () => screen.getByTestId("custom-tool-test-result");
const viewer = () => screen.queryByTestId("custom-tool-response");
const handoff = () => screen.queryByRole("button", { name: /Ask an agent|Copy prompt/ });

describe("ToolTestResult", () => {
  test("an answer is a neutral block with the URL; the response is in the viewer outside it", () => {
    show(result({}));
    expect(screen.getByText("200 OK · 180 ms · 16 B JSON")).toBeInTheDocument();
    expect(block()).toHaveClass("bg-surface-sunken");
    expect(block()).not.toHaveClass("bg-danger-soft");
    expect(screen.getByText(URL)).toBeInTheDocument();
    expect(viewer()).toBeInTheDocument();
    expect(block().contains(viewer())).toBe(false);
    expect(screen.getByText("Response · application/json")).toBeInTheDocument();
  });

  test("an error answer is a danger block with no hand-off; the response stays in the viewer", () => {
    show(
      result({
        ok: false,
        status: 404,
        status_line: "HTTP 404 Not Found",
        body: '{"error":"unknown_service"}',
      }),
    );
    expect(block()).toHaveClass("bg-danger-soft");
    expect(screen.getByText(/404 Not Found · 180 ms/)).toBeInTheDocument();
    expect(screen.getByText(/The API answered with an error; its response is below/)).toBeInTheDocument();
    expect(handoff()).toBeNull();
    expect(block().contains(viewer())).toBe(false);
  });

  test("a rejected secret keeps the hint and opens the secret's Change value, with no hand-off", async () => {
    show(result({ ok: false, status: 401, status_line: "HTTP 401 Unauthorized", body: "" }));
    expect(screen.getByText(/The API rejected deploy-token/)).toBeInTheDocument();
    expect(screen.getByText(/every tool in deploy-api uses the same secret/)).toBeInTheDocument();
    expect(handoff()).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Change value" }));
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
  });

  test("a timeout offers Change timeout and a hand-off", () => {
    const onChange = vi.fn();
    show(
      result({
        ok: false,
        status: null,
        status_line: null,
        body: "",
        failure: "timeout",
        handoff: { prompt: "Find out why the request timed out" },
      }),
      onChange,
    );
    expect(screen.getByText("No response — timed out after 30 s")).toBeInTheDocument();
    expect(screen.getByText(/Coffer stopped waiting after deploy-api's 30 s timeout/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Change timeout" }));
    expect(onChange).toHaveBeenCalled();
    expect(handoff()).toBeInTheDocument();
    expect(viewer()).toBeNull();
  });

  test("no connection names the host and hands off, without Change timeout", () => {
    show(
      result({
        ok: false,
        status: null,
        status_line: null,
        body: "",
        failure: "connect",
        error: "connection refused",
        handoff: { prompt: "Find out why it could not connect" },
      }),
    );
    expect(screen.getByText("Couldn't connect to deploy.internal.example")).toBeInTheDocument();
    expect(screen.getByText(/from this Mac \(connection refused\)/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Change timeout" })).toBeNull();
    expect(handoff()).toBeInTheDocument();
  });

  test("a response cut short is noted at the top of the viewer, not in the block", () => {
    show(result({ truncated: true }));
    expect(screen.getByText("200 OK · 180 ms · 16 B JSON, cut short")).toBeInTheDocument();
    const note = screen.getByText("Cut short at 1 MB.");
    expect(viewer()?.contains(note)).toBe(true);
    expect(screen.getByText(/Agents get the same first 1 MB/)).toBeInTheDocument();
  });
});
