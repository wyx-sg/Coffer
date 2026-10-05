// src/lib/mcp/rebindMcpSecret.test.ts — rebinding changes one secret_refs entry and keeps the rest of the config.
import { expect, test, vi } from "vitest";

import { resourcesApi } from "@/lib/api/resources";
import { rebindMcpSecret } from "./rebindMcpSecret";

test("only the named env var's ref changes", async () => {
  const update = vi.spyOn(resourcesApi, "update").mockResolvedValue(undefined);
  await rebindMcpSecret(
    {
      uid: "u1",
      config: {
        transport: { type: "stdio", command: "npx", secret_refs: { A: "secret/a", B: "secret/b" } },
        spawn_timeout_seconds: 5,
      },
    },
    "A",
    "secret/c",
  );
  expect(update).toHaveBeenCalledWith("u1", {
    config: {
      transport: { type: "stdio", command: "npx", secret_refs: { A: "secret/c", B: "secret/b" } },
      spawn_timeout_seconds: 5,
    },
  });
});
