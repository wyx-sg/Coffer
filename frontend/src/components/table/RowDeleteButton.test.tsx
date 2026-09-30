// frontend/src/components/table/RowDeleteButton.test.tsx — every list row's delete is the shared, labelled table action.
import { expect, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";

import { acceptance } from "@/test/acceptance";
import { RowDeleteButton } from "./RowDeleteButton";

// Every table's row delete is this one component (.agents/frontend.md §6), so
// the requirement is held here, on a row that carries it.
acceptance("web-ui", "a row action shows its label beside its icon", () => {
  render(
    <table>
      <tbody>
        <tr>
          <td>files</td>
          <td>
            <RowDeleteButton ariaLabel="Delete: files" onDelete={vi.fn()} />
          </td>
        </tr>
      </tbody>
    </table>,
  );
  const row = screen.getByRole("row");
  const del = within(row).getByRole("button", { name: /delete/i });
  expect(del).toHaveTextContent(/^delete$/i); // visible text, not only an aria-label
  expect(del.querySelector("svg")).not.toBeNull(); // and its icon
});
