// src/components/status/StatusWord.test.tsx — every status is a dot beside its word; only problems colour the word.
import { describe, expect, test } from "vitest";
import { render, screen } from "@testing-library/react";

import { acceptance } from "@/test/acceptance";
import { StatusPill } from "./StatusPill";
import { StatusWord } from "./StatusWord";

function dotOf(el: HTMLElement): HTMLElement {
  const dot = el.querySelector<HTMLElement>("[data-tone]");
  if (!dot) throw new Error("no dot");
  return dot;
}

describe("StatusWord", () => {
  acceptance("web-ui", "a status is a dot beside its word", () => {
    render(
      <>
        <StatusWord tone="ok">Running</StatusWord>
        <StatusWord tone="warn">Degraded</StatusWord>
        <StatusWord tone="err">Failing</StatusWord>
        <StatusWord tone="off">Disabled</StatusWord>
      </>,
    );
    const running = screen.getByText("Running");
    const degraded = screen.getByText("Degraded");
    const failing = screen.getByText("Failing");
    const disabled = screen.getByText("Disabled");

    // Each word has its dot, and the dot carries the status colour.
    expect(dotOf(running)).toHaveClass("bg-success");
    expect(dotOf(degraded)).toHaveClass("bg-warning");
    expect(dotOf(failing)).toHaveClass("bg-danger");
    expect(dotOf(disabled)).toHaveClass("bg-neutral");

    // Healthy is quiet; problems take their status colour.
    expect(running).toHaveClass("text-text-muted");
    expect(degraded).toHaveClass("text-warning");
    expect(failing).toHaveClass("text-danger");
    expect(disabled).toHaveClass("text-text-muted");
  });
});

describe("StatusPill", () => {
  test("fills with the tone's soft colour and keeps the dot", () => {
    render(
      <>
        <StatusPill tone="err">Failing</StatusPill>
        <StatusPill tone="off">Held</StatusPill>
      </>,
    );
    const failing = screen.getByText("Failing");
    expect(failing).toHaveClass("bg-danger-soft", "text-danger");
    expect(dotOf(failing)).toHaveClass("bg-danger");
    expect(screen.getByText("Held")).toHaveClass("bg-neutral-soft", "text-text-muted");
  });
});
