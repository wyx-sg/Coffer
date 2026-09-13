// frontend/src/components/knowledge/KnowledgeUploadButton.test.tsx
//
// Upload into the collection (and folder) in view (spec knowledge FR-061).
// `useUploadKnowledgeFile` runs as a REAL react-query mutation against the
// mocked wire layer (`@/kinds/knowledge/api`), so a successful call really
// does invalidate `["knowledge"]` — the mechanism a mounted tree query relies
// on to refresh itself with no manual reload.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";

import { KnowledgeUploadButton } from "./KnowledgeUploadButton";
import { ToastProvider } from "@/components/ui/toast";
import { ApiError } from "@/lib/api/errors";
import { knowledgeKey } from "@/kinds/knowledge/useKnowledge";

vi.mock("@/kinds/knowledge/api", () => ({
  uploadFile: vi.fn(),
}));

const { uploadFile } = await import("@/kinds/knowledge/api");
const uploadFileMock = vi.mocked(uploadFile);

afterEach(() => vi.clearAllMocks());

/** Mounts a query under `["knowledge"]` so an invalidation is observable as a refetch. */
function TreeSentinel({ onFetch }: { onFetch: () => void }) {
  useQuery({
    queryKey: knowledgeKey,
    queryFn: () => {
      onFetch();
      return Promise.resolve({ ok: true });
    },
  });
  return null;
}

function renderButton(onFetch: () => void = () => {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <TreeSentinel onFetch={onFetch} />
        <KnowledgeUploadButton collection="shopee" directory={null} />
      </ToastProvider>
    </QueryClientProvider>,
  );
}

function chooseFile(name: string, type: string) {
  const input = document.querySelector('input[type="file"]') as HTMLInputElement;
  const file = new File(["hello"], name, { type });
  fireEvent.change(input, { target: { files: [file] } });
}

describe("KnowledgeUploadButton", () => {
  test("a successful upload refreshes the knowledge tree", async () => {
    uploadFileMock.mockResolvedValue({
      path: "shopee/notes.md",
      title: "Notes",
      description: "converted notes",
      converter: "markitdown",
      raw_path: "/Users/dev/.coffer/knowledge/shopee/.raw/notes.pdf",
    });
    const onFetch = vi.fn();
    renderButton(onFetch);

    // The sentinel query fetches once on mount.
    await waitFor(() => expect(onFetch).toHaveBeenCalledTimes(1));

    chooseFile("notes.pdf", "application/pdf");

    await waitFor(() =>
      expect(uploadFileMock).toHaveBeenCalledWith(
        expect.objectContaining({ collection: "shopee", directory: null }),
      ),
    );
    // Success invalidates ["knowledge"], so the sentinel refetches — the
    // mechanism the tree relies on to show the new file with no manual reload.
    await waitFor(() => expect(onFetch).toHaveBeenCalledTimes(2));
    expect(await screen.findByText(/Notes/)).toBeInTheDocument();
  });

  test("an unsupported file type is named, never a raw error code", async () => {
    uploadFileMock.mockRejectedValue(
      new ApiError("INGEST_REJECTED", "unsupported document type: '.xyz'", {
        reason: "unsupported_type",
        doc_type: ".xyz",
      }),
    );
    renderButton();

    chooseFile("weird.xyz", "application/octet-stream");

    const toast = await screen.findByText(/file type isn.t supported/i);
    expect(toast).toBeInTheDocument();
    expect(screen.queryByText("INGEST_REJECTED")).toBeNull();
  });

  test("a too-large file says so, never a raw error code", async () => {
    uploadFileMock.mockRejectedValue(
      new ApiError(
        "KNOWLEDGE_UPLOAD_TOO_LARGE",
        "upload of 30000000 bytes exceeds the 20971520 byte limit",
      ),
    );
    renderButton();

    chooseFile("huge.pdf", "application/pdf");

    expect(await screen.findByText(/too large/i)).toBeInTheDocument();
    expect(screen.queryByText("KNOWLEDGE_UPLOAD_TOO_LARGE")).toBeNull();
  });
});
