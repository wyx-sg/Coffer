// The unsaved-changes guard (board 1.1.12): one dialog for every way out of a
// document editor that holds edits. The editor here is a stand-in that only
// registers; the real editors reach the same guard through useFileDraft.
import { describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createMemoryRouter, Link, RouterProvider, useLocation } from "react-router-dom";

import { UnsavedGuardProvider } from "./UnsavedGuard";
import { ApiError } from "@/lib/api/errors";
import { useUnsavedGuard } from "@/lib/hooks/useUnsavedGuard";
import { acceptance } from "@/test/acceptance";
import "@/i18n";

function Editor({ dirty, save }: { dirty: boolean; save: () => Promise<unknown> }) {
  useUnsavedGuard({ dirty, file: "SKILL.md", owner: "sentry-issue-triage", save });
  return <p>editing</p>;
}

function Where() {
  const loc = useLocation();
  return <output data-testid="where">{loc.pathname + loc.search}</output>;
}

function renderApp(opts: { dirty?: boolean; save?: () => Promise<unknown> } = {}) {
  const save = opts.save ?? vi.fn(() => Promise.resolve());
  const router = createMemoryRouter(
    [
      {
        path: "*",
        element: (
          <UnsavedGuardProvider>
            <Editor dirty={opts.dirty ?? true} save={save} />
            <Link to="/skills/other">other skill</Link>
            <Link to="/settings/general">settings</Link>
            <Where />
          </UnsavedGuardProvider>
        ),
      },
    ],
    { initialEntries: ["/skills/sentry-issue-triage"] },
  );
  render(<RouterProvider router={router} />);
  return { save };
}

const where = () => screen.getByTestId("where").textContent;

describe("unsaved-changes guard", () => {
  acceptance("web-ui", "a dirty editor stops leaving and asks first", () => {
    renderApp();
    fireEvent.click(screen.getByRole("link", { name: "other skill" }));
    const dialog = screen.getByRole("dialog", { name: "Leave without saving?" });
    expect(dialog).toHaveTextContent(
      "You edited SKILL.md in sentry-issue-triage. If you leave now, those edits are lost.",
    );
    expect(where()).toBe("/skills/sentry-issue-triage");
    fireEvent.click(within(dialog).getByRole("button", { name: "Keep editing" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(where()).toBe("/skills/sentry-issue-triage");
  });

  acceptance("web-ui", "Discard changes leaves without saving", async () => {
    const { save } = renderApp();
    fireEvent.click(screen.getByRole("link", { name: "other skill" }));
    fireEvent.click(screen.getByRole("button", { name: "Discard changes" }));
    await waitFor(() => expect(where()).toBe("/skills/other"));
    expect(save).not.toHaveBeenCalled();
  });

  acceptance("web-ui", "Save and leave saves, then goes on", async () => {
    const { save } = renderApp();
    fireEvent.click(screen.getByRole("link", { name: "other skill" }));
    fireEvent.click(screen.getByRole("button", { name: "Save and leave" }));
    await waitFor(() => expect(where()).toBe("/skills/other"));
    expect(save).toHaveBeenCalledOnce();
  });

  acceptance("web-ui", "a refused save keeps the guard open and says why", async () => {
    renderApp({
      save: () => Promise.reject(new ApiError("SKILL_FILE_STALE", "changed on disk")),
    });
    fireEvent.click(screen.getByRole("link", { name: "other skill" }));
    fireEvent.click(screen.getByRole("button", { name: "Save and leave" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Couldn’t save SKILL.md");
    expect(where()).toBe("/skills/sentry-issue-triage");
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  acceptance("web-ui", "a clean editor and the Settings modal are never stopped", async () => {
    renderApp({ dirty: false });
    fireEvent.click(screen.getByRole("link", { name: "other skill" }));
    await waitFor(() => expect(where()).toBe("/skills/other"));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  test("opening Settings over a dirty editor is not leaving", async () => {
    renderApp();
    fireEvent.click(screen.getByRole("link", { name: "settings" }));
    await waitFor(() => expect(where()).toBe("/settings/general"));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  acceptance(
    "web-ui",
    "closing or reloading the window with unsaved edits asks the browser",
    () => {
      const fire = () => {
        const e = new Event("beforeunload", { cancelable: true });
        window.dispatchEvent(e);
        return e.defaultPrevented;
      };
      const { unmount } = render(
        <RouterProvider
          router={createMemoryRouter([
            {
              path: "*",
              element: (
                <UnsavedGuardProvider>
                  <Editor dirty save={() => Promise.resolve()} />
                </UnsavedGuardProvider>
              ),
            },
          ])}
        />,
      );
      expect(fire()).toBe(true);
      unmount();
      expect(fire()).toBe(false);
    },
  );
});
