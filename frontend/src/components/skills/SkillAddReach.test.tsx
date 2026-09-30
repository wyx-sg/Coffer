// frontend/src/components/skills/SkillAddReach.test.tsx
// "Available to" in the Add skill dialog is a draft of the one reach control:
// choosing a state reports it, and the hook the dialog calls writes it onto
// every skill the add created — Off disables, chosen agents set the scope,
// every agent writes nothing (an add already reaches every agent).
import { afterEach, expect, test, vi } from "vitest";
import { fireEvent, render, renderHook, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { PropsWithChildren } from "react";

import { TooltipProvider } from "@/components/ui/tooltip";
import { acceptance } from "@/test/acceptance";
import { useApplySkillReach } from "@/lib/hooks/useSkillCopies";
import { EVERY_AGENT } from "@/lib/skills/reach";
import { SkillAddReach } from "./SkillAddReach";

vi.mock("@/lib/hooks/useAgents", () => ({ useAgents: vi.fn(() => ({ data: [] })) }));
vi.mock("@/lib/api/resources", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/resources")>()),
  resourcesApi: { disable: vi.fn(async () => undefined), enable: vi.fn(async () => undefined) },
}));
vi.mock("@/lib/api/scope", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/scope")>()),
  scopeApi: { put: vi.fn(async () => ({})), get: vi.fn() },
}));

const { resourcesApi } = await import("@/lib/api/resources");
const { scopeApi } = await import("@/lib/api/scope");

function wrapper({ children }: PropsWithChildren) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <TooltipProvider>{children}</TooltipProvider>
    </QueryClientProvider>
  );
}

afterEach(() => vi.clearAllMocks());

test("choosing Disabled reports the draft", () => {
  const onChange = vi.fn();
  render(<SkillAddReach value={EVERY_AGENT} onChange={onChange} />, { wrapper });
  expect(screen.getByText("0 of 0 agents · you can change it any time")).toBeInTheDocument();
  fireEvent.click(within(screen.getByTestId("skill-add-reach")).getByRole("button"));
  fireEvent.click(screen.getByRole("radio", { name: /Disabled/ }));
  expect(onChange).toHaveBeenCalledWith({ mode: "disabled", scope: null });
});

acceptance("web-ui", "a skill is added with the reach chosen in the dialog", async () => {
  const { result } = renderHook(() => useApplySkillReach(), { wrapper });
  await result.current.mutateAsync({ uids: ["a", "b"], mode: "disabled", scope: null });
  expect(vi.mocked(resourcesApi.disable).mock.calls).toEqual([["a"], ["b"]]);
  await result.current.mutateAsync({
    uids: ["c"],
    mode: "restricted",
    scope: { agents: ["ag-cc"] },
  });
  await waitFor(() => expect(scopeApi.put).toHaveBeenCalledWith("c", { agents: ["ag-cc"] }));
  await result.current.mutateAsync({ uids: ["d"], mode: "everywhere", scope: null });
  expect(scopeApi.put).toHaveBeenCalledTimes(1);
});
