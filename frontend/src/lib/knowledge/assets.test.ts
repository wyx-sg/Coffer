import { describe, expect, it } from "vitest";

import { isImagePath, resolveAsset } from "@/lib/knowledge/assets";

describe("resolveAsset", () => {
  it("resolves a source's picture against its folder", () => {
    expect(resolveAsset("docs/sources/deck.md", "../assets/deck-1a2b/image-1.png")).toBe(
      "docs/assets/deck-1a2b/image-1.png",
    );
    expect(resolveAsset("docs/pages/a.md", "pic%20one.png")).toBe("docs/pages/pic one.png");
  });

  it("leaves a link off the page, or out of the collection, alone", () => {
    expect(resolveAsset("docs/sources/deck.md", "https://x.dev/a.png")).toBeNull();
    expect(resolveAsset("docs/sources/deck.md", "data:image/png;base64,AA")).toBeNull();
    expect(resolveAsset("docs/sources/deck.md", "../../other/a.png")).toBeNull();
    expect(resolveAsset("docs/sources/deck.md", undefined)).toBeNull();
  });

  it("knows a picture by its name", () => {
    expect(isImagePath("docs/assets/x/image-1.JPG")).toBe(true);
    expect(isImagePath("docs/sources/deck.md")).toBe(false);
  });
});
