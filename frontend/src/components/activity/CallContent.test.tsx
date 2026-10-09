// frontend/src/components/activity/CallContent.test.tsx
import { describe, expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { acceptance } from "@/test/acceptance";
import { ToastProvider } from "@/components/ui/toast";
import { CallContent } from "./CallContent";

const detail = vi.hoisted(() => ({ byId: {} as Record<number, unknown> }));
vi.mock("@/lib/hooks/useCallContent", () => ({
  useCallDetail: (id: number) => ({ isPending: false, error: null, data: detail.byId[id] }),
}));

const part = (text: string, truncated = false, bytes = text.length) => ({ text, truncated, bytes });

function show(id: number) {
  render(
    <MemoryRouter>
      <ToastProvider>
        <CallContent id={id} />
      </ToastProvider>
    </MemoryRouter>,
  );
}

describe("CallContent", () => {
  acceptance("web-ui", "a call's drawer shows its arguments and result", () => {
    detail.byId[1] = {
      content: {
        arguments: part('{"query":"coffer"}'),
        result: part('{"items":[1,2', true, 40 * 1024),
        error: null,
        request: null,
        response: null,
      },
    };
    detail.byId[2] = { content: null };

    show(1);
    expect(screen.getByText("Arguments")).toBeInTheDocument();
    expect(screen.getByText("Result")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Copy Arguments" })).toBeInTheDocument();
    expect(screen.getByText("Cut at 16 KB — the call carried 40 KB.")).toBeInTheDocument();
    expect(screen.queryByText("Request")).not.toBeInTheDocument();
  });

  test("a call recorded with recording off says so and links to the setting", () => {
    detail.byId[2] = { content: null };
    show(2);
    expect(screen.getByText(/Content was not recorded for this call/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Record tool call content" })).toHaveAttribute(
      "href",
      "/settings/data",
    );
  });
});
