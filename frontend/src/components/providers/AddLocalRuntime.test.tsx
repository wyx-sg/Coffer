// src/components/providers/AddLocalRuntime.test.tsx — the Add dialog's local path when nothing answers.
//
// Detection found no runtime: the note says so, keeps typing an address as the
// manual path, and offers the detect response's hand-off for setting one up.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider, type UseQueryResult } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { TooltipProvider } from "@/components/ui/tooltip";
import type { DetectLocalOut } from "@/lib/api/providers";
import { acceptance } from "@/test/acceptance";
import { AddLocalRuntime } from "./AddLocalRuntime";

vi.mock("@/lib/api/agentProviders", () => ({
  agentProvidersApi: { list: vi.fn().mockResolvedValue({ agents: [] }) },
}));

const PROMPT = "Please set up a local model runtime on this machine.";

function renderDetect(data: DetectLocalOut) {
  const detect = {
    data,
    error: null,
    isFetching: false,
  } as unknown as UseQueryResult<DetectLocalOut>;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <TooltipProvider>
        <MemoryRouter>
          <AddLocalRuntime
            detect={detect}
            requested
            chosen={0}
            onChoose={() => undefined}
            onDetect={() => undefined}
          />
        </MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>,
  );
}

const writeText = vi.fn().mockResolvedValue(undefined);
beforeEach(() => {
  Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
});
afterEach(() => vi.clearAllMocks());

describe("AddLocalRuntime with nothing found", () => {
  acceptance(
    "provider-switching",
    "nothing found hands setting up a runtime to an agent",
    async () => {
      renderDetect({ found: [], handoff: { prompt: PROMPT } });
      expect(screen.getByText(/Nothing answered on the default ports/)).toHaveTextContent(
        "type the address of a runtime that is already running",
      );
      fireEvent.click(screen.getByRole("button", { name: "Copy prompt" }));
      expect(writeText).toHaveBeenCalledWith(PROMPT);
      expect(screen.getByRole("button", { name: "Detect" })).toBeEnabled();
    },
  );

  test("without a hand-off only the note shows", () => {
    renderDetect({ found: [], handoff: null });
    expect(screen.getByText(/Nothing answered on the default ports/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Copy prompt" })).toBeNull();
  });
});
