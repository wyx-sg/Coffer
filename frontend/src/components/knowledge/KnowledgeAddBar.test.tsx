// frontend/src/components/knowledge/KnowledgeAddBar.test.tsx
import { describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { KnowledgeAddBar } from "./KnowledgeAddBar";
import type { KnowledgeBaseOut } from "@/kinds/knowledge_base/api";

const KBS = [{ name: "kb1" }, { name: "kb2" }] as KnowledgeBaseOut[];

describe("KnowledgeAddBar", () => {
  test("a pasted text becomes a note (add-by-shape: text → note)", () => {
    const onAddNote = vi.fn();
    render(
      <KnowledgeAddBar
        kbs={KBS}
        canAddNote
        isAddingNote={false}
        isUploading={false}
        onAddNote={onAddNote}
        onUploadFile={() => {}}
      />,
    );
    fireEvent.change(screen.getByPlaceholderText(/paste a link or write a note/i), {
      target: { value: "https://example.com" },
    });
    fireEvent.click(screen.getByRole("button", { name: /add note/i }));
    expect(onAddNote).toHaveBeenCalledWith("https://example.com");
  });

  test("a chosen file becomes a document upload (shape: file → document)", () => {
    const onUploadFile = vi.fn();
    const { container } = render(
      <KnowledgeAddBar
        kbs={KBS}
        canAddNote
        isAddingNote={false}
        isUploading={false}
        onAddNote={() => {}}
        onUploadFile={onUploadFile}
      />,
    );
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(["x"], "spec.pdf", { type: "application/pdf" });
    fireEvent.change(input, { target: { files: [file] } });
    expect(onUploadFile).toHaveBeenCalledWith("kb1", file);
  });

  test("disables the note input when the scope has no memory store", () => {
    render(
      <KnowledgeAddBar
        kbs={KBS}
        canAddNote={false}
        isAddingNote={false}
        isUploading={false}
        onAddNote={() => {}}
        onUploadFile={() => {}}
      />,
    );
    expect(screen.getByPlaceholderText(/notes are unavailable/i)).toBeDisabled();
  });

  test("disables file upload when there are no knowledge bases", () => {
    render(
      <KnowledgeAddBar
        kbs={[]}
        canAddNote
        isAddingNote={false}
        isUploading={false}
        onAddNote={() => {}}
        onUploadFile={() => {}}
      />,
    );
    expect(screen.getByRole("button", { name: /upload file/i })).toBeDisabled();
    expect(screen.getByText(/create a knowledge base to upload/i)).toBeInTheDocument();
  });
});
