// src/components/providers/ProviderMark.test.tsx — each provider gets its official mark, or the neutral glyph.
import { describe, expect, test } from "vitest";
import { render } from "@testing-library/react";

import type { Provider } from "@/lib/api/providers";
import { ProviderMark } from "./ProviderMark";

type MarkInput = Pick<Provider, "base_url" | "protocol" | "local_runtime">;

const markOf = (p: Partial<MarkInput>) => {
  const provider: MarkInput = {
    base_url: "https://gw.example/v1",
    protocol: "openai",
    local_runtime: null,
    ...p,
  };
  const { container } = render(<ProviderMark provider={provider} />);
  const tile = container.querySelector("[data-provider-mark]") as HTMLElement;
  return { kind: tile.dataset.providerMark, images: tile.querySelectorAll("img") };
};

describe("ProviderMark", () => {
  test("vendors with an official mark get it, by endpoint", () => {
    expect(markOf({ base_url: "https://api.anthropic.com", protocol: "anthropic" }).kind).toBe(
      "anthropic",
    );
    expect(markOf({ base_url: "https://api.openai.com/v1" }).kind).toBe("openai");
    expect(markOf({ base_url: "https://eu.api.openai.com/v1" }).kind).toBe("openai");
  });

  test("a local runtime is drawn from what detection recorded", () => {
    const local = (runtime: "ollama" | "vllm" | "llama_server" | "lmstudio") =>
      markOf({ base_url: "http://127.0.0.1:9000", local_runtime: { runtime } }).kind;
    expect(local("ollama")).toBe("ollama");
    expect(local("vllm")).toBe("vllm");
    expect(local("llama_server")).toBe("llama-cpp");
    expect(local("lmstudio")).toBe("lmstudio");
    expect(markOf({ base_url: "http://localhost:11434", protocol: "ollama" }).kind).toBe("ollama");
  });

  test("OpenRouter has its own mark; the OpenAI Blossom comes with its word", () => {
    expect(markOf({ base_url: "https://openrouter.ai/api/v1" }).kind).toBe("openrouter");
    const { container } = render(
      <ProviderMark
        provider={{
          base_url: "https://api.openai.com/v1",
          protocol: "openai",
          local_runtime: null,
        }}
      />,
    );
    expect(container).toHaveTextContent("OpenAI");
    const row = render(
      <ProviderMark
        provider={{
          base_url: "https://api.openai.com/v1",
          protocol: "openai",
          local_runtime: null,
        }}
        withWord={false}
      />,
    );
    expect(row.container).not.toHaveTextContent("OpenAI");
  });

  test("every preset vendor has its mark, in either region; a gateway gets the neutral glyph", () => {
    expect(markOf({ base_url: "https://api.deepseek.com" }).kind).toBe("deepseek");
    expect(markOf({ base_url: "https://api.deepseek.com/anthropic" }).kind).toBe("deepseek");
    expect(markOf({ base_url: "https://api.moonshot.cn/v1" }).kind).toBe("kimi");
    expect(
      markOf({ base_url: "https://dashscope-intl.aliyuncs.com/compatible-mode/v1" }).kind,
    ).toBe("qwen");
    expect(markOf({}).kind).toBe("glyph");
  });

  test("a mark with a dark-theme file carries both, one per theme", () => {
    expect(markOf({ base_url: "https://api.anthropic.com" }).images).toHaveLength(2);
    expect(markOf({ base_url: "https://openrouter.ai/api/v1" }).images).toHaveLength(2);
    // The neutral glyph is drawn, not a file.
    expect(markOf({}).images).toHaveLength(0);
    // Ollama has one file; its tile, not the mark, changes on the dark theme.
    expect(markOf({ protocol: "ollama" }).images).toHaveLength(1);
  });
});
