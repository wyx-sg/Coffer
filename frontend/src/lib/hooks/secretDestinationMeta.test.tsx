// frontend/src/lib/hooks/secretDestinationMeta.test.tsx
//
// A save that can send a stored secret somewhere new opts in to the inline
// approval with `meta.secretDestination`; these cases pin which uid each one
// names (the destination the backend's secret boundary records).
import { describe, expect, test } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { PropsWithChildren } from "react";

import { useCreateProvider, useRebindProviderKey, useUpdateProvider } from "./useProviders";
import { useSaveSyncRemote } from "./useSync";
import { useUpdateCustomToolGroup } from "./useCustomTools";
import { useUpdateChannel } from "./useChannels";
import type { SecretDestinationOf } from "@/lib/inlineApproval";

function destinationOf(mutation: unknown): SecretDestinationOf {
  const { options } = mutation as {
    options: { meta?: { secretDestination?: SecretDestinationOf } };
  };
  return options.meta!.secretDestination!;
}

// `useMutation` hands back the observer's result, not its options, so read the
// options off the mutation cache after a mutate call is not needed: the hook's
// options are reachable through the cache once mutated. Run one failing mutate.
async function metaOf<T extends { mutateAsync: (v: never) => Promise<unknown> }>(
  hook: () => T,
): Promise<SecretDestinationOf> {
  const qc = new QueryClient();
  const wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  const { result } = renderHook(hook, { wrapper });
  await act(async () => {
    await result.current.mutateAsync(undefined as never).catch(() => undefined);
  });
  return destinationOf(qc.getMutationCache().getAll()[0]);
}

describe("secretDestination meta", () => {
  test("provider create names the created provider's uid", async () => {
    const of = await metaOf(useCreateProvider);
    expect(of({ uid: "p-1", name: "x" }, {})).toBe("p-1");
  });

  test("provider update and rebind name the provider in the variables", async () => {
    expect(
      (await metaOf(useUpdateProvider))(undefined, {
        uid: "p-2",
        patch: { base_url: "https://a" },
      }),
    ).toBe("p-2");
    expect(
      (await metaOf(useRebindProviderKey))(undefined, { uid: "p-3", secretRef: "secret/x" }),
    ).toBe("p-3");
  });

  test("sync remote save is the literal remote", async () => {
    expect((await metaOf(useSaveSyncRemote))({}, {})).toBe("remote");
  });

  test("custom tool group update names the group's resource uid from the response", async () => {
    const of = await metaOf(() => useUpdateCustomToolGroup("billing"));
    expect(of({ uid: "r-9", name: "billing" }, {})).toBe("r-9");
  });

  test("channel update names the channel written", async () => {
    const of = await metaOf(useUpdateChannel);
    expect(of({ uid: "c-4", name: "tg" }, {})).toBe("c-4");
  });
});
