// src/components/providers/AddEndpointStep.test.tsx — a vendor with two wire roots picks the base URL with the wire.
import { describe, expect } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { MemoryRouter } from "react-router-dom";

import { presetById } from "@/lib/providers/presets";
import { acceptance } from "@/test/acceptance";
import { AddEndpointStep } from "./AddEndpointStep";
import type { EndpointValues } from "./providerSchemas";

function Harness() {
  const p = presetById("deepseek");
  const form = useForm<EndpointValues>({
    defaultValues: { local: false, name: "", protocol: "openai", baseUrl: p.baseUrl, secret: null },
  });
  return (
    <AddEndpointStep
      form={form}
      presetId="deepseek"
      onPreset={() => undefined}
      localPanel={null}
      showName
      showUrl
      result={null}
      onEdited={() => undefined}
    />
  );
}

describe("AddEndpointStep", () => {
  acceptance(
    "provider-switching",
    "DeepSeek offers its Anthropic endpoint as a second connection",
    () => {
      const qc = new QueryClient();
      render(
        <QueryClientProvider client={qc}>
          <MemoryRouter>
            <Harness />
          </MemoryRouter>
        </QueryClientProvider>,
      );
      const url = screen.getByLabelText(/Base URL/) as HTMLInputElement;
      expect(url.value).toBe("https://api.deepseek.com");
      const wires = within(screen.getByRole("radiogroup", { name: "Protocol" }));
      fireEvent.click(wires.getByRole("radio", { name: /Anthropic-compatible/ }));
      expect(url.value).toBe("https://api.deepseek.com/anthropic");
      fireEvent.click(wires.getByRole("radio", { name: /OpenAI-compatible/ }));
      expect(url.value).toBe("https://api.deepseek.com");
    },
  );
});
