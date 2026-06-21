// src/lib/preview/language.test.ts
import { describe, expect, test } from "vitest";
import { languageForFile } from "./language";

describe("languageForFile", () => {
  test("maps common config extensions", () => {
    expect(languageForFile("config.toml")).toBe("toml");
    expect(languageForFile("data.json")).toBe("json");
    expect(languageForFile("compose.yaml")).toBe("yaml");
    expect(languageForFile("compose.yml")).toBe("yaml");
  });

  test("maps code extensions, distinguishing TypeScript", () => {
    expect(languageForFile("a.js")).toBe("javascript");
    expect(languageForFile("a.ts")).toBe("typescript");
    expect(languageForFile("a.tsx")).toBe("typescript");
    expect(languageForFile("hook.py")).toBe("python");
    expect(languageForFile("run.sh")).toBe("shell");
  });

  test("strips directory segments before inspecting the extension", () => {
    expect(languageForFile("/Users/xing/.codex/config.toml")).toBe("toml");
    expect(languageForFile("C:\\Users\\x\\a.json")).toBe("json");
  });

  test("recognizes known dotfiles and bare names", () => {
    expect(languageForFile("Dockerfile")).toBe("dockerfile");
    expect(languageForFile(".env")).toBe("ini");
    expect(languageForFile(".gitignore")).toBe("ini");
  });

  test("falls back to text for unknown or extensionless names", () => {
    expect(languageForFile("README")).toBe("text");
    expect(languageForFile("notes.")).toBe("text");
    expect(languageForFile("mystery.xyz")).toBe("text");
    expect(languageForFile(undefined)).toBe("text");
    expect(languageForFile(null)).toBe("text");
    expect(languageForFile("")).toBe("text");
  });

  test("is case-insensitive on the extension", () => {
    expect(languageForFile("CONFIG.TOML")).toBe("toml");
    expect(languageForFile("Notes.MD")).toBe("markdown");
  });
});
