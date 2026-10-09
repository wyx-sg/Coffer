// frontend/src/components/settings/storage/CallContentRow.test.tsx
import { expect, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { acceptance } from "@/test/acceptance";
import { CallContentRow } from "./CallContentRow";

const state = vi.hoisted(() => ({ enabled: true, mutate: vi.fn() }));
vi.mock("@/lib/hooks/useCallContent", () => ({
  useCallContentSetting: () => ({ isPending: false, data: { enabled: state.enabled } }),
  useSetCallContent: () => ({ isPending: false, isError: false, mutate: state.mutate }),
}));

acceptance("web-ui", "tool call content recording is switched on the Data tab", () => {
  render(<CallContentRow />);
  const toggle = screen.getByRole("switch", { name: "Record tool call content" });
  expect(toggle).toBeChecked();
  fireEvent.click(toggle);
  expect(state.mutate).toHaveBeenCalledWith(false);
});
