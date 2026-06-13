// frontend/src/components/settings/ProviderModelField.test.tsx
import type { PropsWithChildren } from "react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { ProviderModelField } from "./ProviderModelField";

const listMutate = vi.fn();
const testChatMutate = vi.fn();

vi.mock("@/lib/hooks/useModelIntrospection", () => ({
  useListProviderModels: () => ({ mutate: listMutate, isPending: false, data: undefined }),
  useTestConnection: () => ({ mutate: testChatMutate, isPending: false, data: undefined }),
  useTestEmbedding: () => ({ mutate: vi.fn(), isPending: false, data: undefined }),
}));

function wrap({ children }: PropsWithChildren) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

afterEach(() => vi.clearAllMocks());

describe("ProviderModelField", () => {
  test("fetch passes provider/base_url/credential_ref", async () => {
    render(
      <ProviderModelField
        provider="openai"
        baseUrl="https://api.openai.com/v1"
        credentialRef="OPENAI_KEY"
        model=""
        onModelChange={() => {}}
        kind="chat"
      />,
      { wrapper: wrap },
    );
    fireEvent.click(screen.getByRole("button", { name: /fetch models/i }));
    await waitFor(() => expect(listMutate).toHaveBeenCalled());
    expect(listMutate.mock.calls[0][0]).toMatchObject({
      provider: "openai",
      base_url: "https://api.openai.com/v1",
      credential_ref: "OPENAI_KEY",
    });
  });

  test("test connection sends the entered model", async () => {
    render(
      <ProviderModelField
        provider="openai"
        baseUrl={null}
        credentialRef="OPENAI_KEY"
        model="gpt-4o"
        onModelChange={() => {}}
        kind="chat"
      />,
      { wrapper: wrap },
    );
    fireEvent.click(screen.getByRole("button", { name: /test connection/i }));
    await waitFor(() => expect(testChatMutate).toHaveBeenCalled());
    expect(testChatMutate.mock.calls[0][0]).toMatchObject({ provider: "openai", model: "gpt-4o" });
  });

  test("typing a model id calls onModelChange (manual fallback)", () => {
    const onChange = vi.fn();
    render(
      <ProviderModelField
        provider="ollama"
        baseUrl={null}
        credentialRef={null}
        model=""
        onModelChange={onChange}
        kind="chat"
      />,
      { wrapper: wrap },
    );
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "llama3" } });
    expect(onChange).toHaveBeenCalledWith("llama3");
  });
});
