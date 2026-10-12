// frontend/src/components/knowledge/KnowledgePictures.test.tsx
//
// An upload's pictures and its original on the Knowledge page (ADR
// knowledge-sources-keep-their-images-and-originals-stay-on-this-mac): a
// source shows its pictures inline, a picture opened from the tree shows the
// picture, and an open source offers its original on the Mac that uploaded it
// or says where it is on any other.
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, vi } from "vitest";

import { COLLECTION, RELEASE, UID, file } from "@/components/knowledge/knowledgeTestData";
import { acceptance } from "@/test/acceptance";
import { answerFromFixtures, renderKnowledge } from "@/test/knowledgeHarness";

vi.mock("@/lib/api/knowledge", () => ({
  listCollections: vi.fn(),
  createCollection: vi.fn(),
  getTree: vi.fn(),
  getFile: vi.fn(),
  getAsset: vi.fn(),
  deleteFile: vi.fn(),
  uploadFile: vi.fn(),
  listChanges: vi.fn(),
  restoreDeleted: vi.fn(),
  describeCollection: vi.fn(),
  getCheck: vi.fn(),
  getCollectionFiles: vi.fn(),
  undoChange: vi.fn(),
}));
vi.mock("@/lib/hooks/useDaemonEvents", () => ({ useDaemonEvents: () => undefined }));
vi.mock("@/lib/api/agentProviders", () => ({
  agentProvidersApi: { list: vi.fn().mockResolvedValue({ agents: [] }) },
}));
vi.mock("@/lib/api/fs", () => ({
  fsApi: {
    listTerminals: vi.fn().mockResolvedValue([]),
    listEditors: vi.fn().mockResolvedValue([]),
    openTerminal: vi.fn(),
    open: vi.fn().mockResolvedValue(undefined),
  },
}));

const api = vi.mocked(await import("@/lib/api/knowledge"));
const fs = vi.mocked((await import("@/lib/api/fs")).fsApi);

const PICTURE = "data:image/png;base64,iVBORw0KGgo=";
const ASSET = `${COLLECTION.name}/assets/deck-1a2b3c4d/image-1.png`;
const DECK = file(`${COLLECTION.name}/sources/deck.md`, {
  kind: "source",
  title: "Deck",
  page_type: "",
  body: "The flow:\n\n![Login flow](../assets/deck-1a2b3c4d/image-1.png)\n",
  original: "deck.pptx",
  original_path: "/Users/dev/.coffer/local/knowledge-originals/abc.pptx",
});
const ELSEWHERE = { ...RELEASE, original: "release.pdf", original_path: null };
const IMAGE = file(ASSET, { kind: "file", title: "image-1.png", page_type: "", body: "" });

beforeEach(() => {
  answerFromFixtures();
  const fixture = api.getFile.getMockImplementation()!;
  const extra: Record<string, typeof DECK> = {
    [DECK.path]: DECK,
    [ELSEWHERE.path]: ELSEWHERE,
    [IMAGE.path]: IMAGE,
  };
  api.getFile.mockImplementation(async (path: string) => extra[path] ?? fixture(path));
  api.getAsset.mockImplementation(async (path: string) => (path === ASSET ? PICTURE : null));
});
afterEach(() => {
  vi.clearAllMocks();
  cleanup();
});

const open = (path: string) =>
  renderKnowledge(`/knowledge/${UID}?file=${encodeURIComponent(path)}`);

describe("an upload's pictures and original", () => {
  acceptance("knowledge", "a source shows its pictures inline", async () => {
    open(DECK.path);
    const picture = await screen.findByRole("img", { name: "Login flow" });
    expect(picture).toHaveAttribute("src", PICTURE);
    expect(api.getAsset).toHaveBeenCalledWith(ASSET);
  });

  acceptance("knowledge", "a picture opened from the tree shows the picture", async () => {
    open(IMAGE.path);
    const pane = await screen.findByTestId("knowledge-picture");
    expect(await within(pane).findByRole("img")).toHaveAttribute("src", PICTURE);
  });

  acceptance(
    "knowledge",
    "an open source offers its original on the Mac that uploaded it",
    async () => {
      open(DECK.path);
      const line = await screen.findByTestId("file-line");
      expect(line).toHaveTextContent("Original");
      fireEvent.click(within(line).getByRole("button", { name: "deck.pptx" }));
      await waitFor(() => expect(fs.open).toHaveBeenCalledWith(DECK.original_path));
    },
  );

  acceptance("knowledge", "on another Mac a source says where its original is", async () => {
    open(ELSEWHERE.path);
    const line = await screen.findByTestId("file-line");
    expect(within(line).getByTestId("original-elsewhere")).toHaveTextContent(
      "Original release.pdf is on the Mac it was uploaded from",
    );
    expect(within(line).queryByRole("button")).toBeNull();
  });
});
