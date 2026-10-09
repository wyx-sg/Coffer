// src/components/providers/AddEndpointStep.test.tsx — a vendor fills its addresses; Custom asks for both; a region swaps them.
import { describe, expect } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { MemoryRouter } from "react-router-dom";

import { presetAddresses } from "@/lib/providers/addresses";
import { presetById, type PresetId } from "@/lib/providers/presets";
import { acceptance } from "@/test/acceptance";
import { AddEndpointStep } from "./AddEndpointStep";
import type { EndpointValues } from "./providerSchemas";

function Harness({ id }: { id: PresetId }) {
  const a = presetAddresses(presetById(id));
  const form = useForm<EndpointValues>({
    defaultValues: {
      local: false,
      name: "",
      protocol: "openai",
      baseUrl: "",
      openaiUrl: a.openai,
      anthropicUrl: a.anthropic,
      secret: null,
    },
  });
  return (
    <AddEndpointStep
      form={form}
      presetId={id}
      onPreset={() => undefined}
      localPanel={null}
      showName
      showUrl
      result={null}
      onEdited={() => undefined}
    />
  );
}

function show(id: PresetId) {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <Harness id={id} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const field = (name: RegExp) => screen.getByLabelText(name) as HTMLInputElement;

describe("AddEndpointStep", () => {
  acceptance("provider-switching", "DeepSeek fills both of its addresses in one connection", () => {
    show("deepseek");
    expect(field(/OpenAI-compatible address/).value).toBe("https://api.deepseek.com");
    expect(field(/Anthropic-compatible address/).value).toBe("https://api.deepseek.com/anthropic");
    expect(screen.queryByRole("radiogroup", { name: "Protocol" })).toBeNull();
  });

  acceptance("provider-switching", "Custom asks for the addresses the gateway serves", () => {
    show("custom");
    expect(field(/OpenAI-compatible address/).value).toBe("");
    expect(field(/Anthropic-compatible address/).value).toBe("");
  });

  acceptance("provider-switching", "a vendor shows only the addresses it has", () => {
    show("openai");
    expect(field(/OpenAI-compatible address/).value).toBe("https://api.openai.com/v1");
    expect(screen.queryByLabelText(/Anthropic-compatible address/)).toBeNull();
  });

  acceptance(
    "provider-switching",
    "a vendor with a Mainland China region swaps both addresses",
    () => {
      show("kimi");
      expect(field(/OpenAI-compatible address/).value).toBe("https://api.moonshot.ai/v1");
      const region = within(screen.getByRole("radiogroup", { name: "Region" }));
      fireEvent.click(region.getByRole("radio", { name: "Mainland China" }));
      expect(field(/OpenAI-compatible address/).value).toBe("https://api.moonshot.cn/v1");
      expect(field(/Anthropic-compatible address/).value).toBe("https://api.moonshot.cn/anthropic");
    },
  );
});
