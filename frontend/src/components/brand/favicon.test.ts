// src/components/brand/favicon.test.ts — the tab icon is the Stroke C mark at 16px, and turns light on dark tabs.
import { describe, expect, test } from "vitest";

import favicon from "../../../public/favicon.svg?raw";
import { cofferMarkStroke } from "./cofferMarkStroke";

describe("favicon", () => {
  test("draws the Coffer mark with the 16px stroke and a dark-scheme ink", () => {
    const doc = new DOMParser().parseFromString(favicon, "image/svg+xml");
    const path = doc.querySelector("path");
    expect(path?.getAttribute("d")).toMatch(/^M20 8\.5V7/);
    expect(path?.getAttribute("stroke-width")).toBe(String(cofferMarkStroke(16)));
    expect(doc.querySelector("circle")?.getAttribute("r")).toBe("1.9");
    expect(favicon).toContain("prefers-color-scheme: dark");
  });
});
