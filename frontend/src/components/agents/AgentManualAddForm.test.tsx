// frontend/src/components/agents/AgentManualAddForm.test.tsx
// The manual add form's config directory is picked, never typed: Browse asks
// the daemon for the host's native directory dialog, and the folder it returns
// is what the registration carries.
import { afterEach, describe, expect, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { PropsWithChildren, ReactNode } from "react";

import { AgentManualAddForm } from "./AgentManualAddForm";
import { fsApi } from "@/lib/api/fs";
import { acceptance } from "@/test/acceptance";

vi.mock("@/lib/api/fs", () => ({ fsApi: { browse: vi.fn(), pickFolder: vi.fn() } }));

function renderForm(ui: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return render(ui, { wrapper: Wrapper });
}

afterEach(() => vi.clearAllMocks());

describe("AgentManualAddForm", () => {
  acceptance(
    "agent-registry",
    "pick a custom config directory with the native dialog",
    async () => {
      vi.mocked(fsApi.pickFolder).mockResolvedValue({ available: true, path: "/work/agent-home" });
      const onSubmit = vi.fn().mockResolvedValue(undefined);
      const { container } = renderForm(
        <AgentManualAddForm open onToggle={() => {}} formId="manual" onSubmit={onSubmit} />,
      );

      fireEvent.click(screen.getByRole("button", { name: /browse/i }));
      await waitFor(() => expect(screen.getByDisplayValue("/work/agent-home")).toBeInTheDocument());
      expect(fsApi.browse).not.toHaveBeenCalled();

      fireEvent.submit(container.querySelector("form#manual") as HTMLFormElement);
      await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
      expect(onSubmit.mock.calls[0][0].config_dir).toBe("/work/agent-home");
    },
  );
});
