// frontend/src/components/memory/memoryTestData.ts — wire fixtures shared by the memory page tests.
//
// Test-only data (imported by `*.test.tsx` files, never by the app): a
// partition set, one partition's memories, a retired memory, deliveries and
// the delivered text, in the generated wire shapes.
import type {
  DeliveredOut,
  DeliveryOverviewOut,
  MemoryFileTreeOut,
  NoteListOut,
  NoteOut,
  PartitionOut,
  RetiredListOut,
} from "@/lib/api/memoryTypes";

export const GLOBAL: PartitionOut = {
  uid: "mp-4410",
  name: "global",
  repository_path: "",
  repository_key: "",
  note_count: 12,
  unresolvable: false,
  distilled_at: "2026-09-30T09:00:00Z",
  sample: "Prefers Chinese replies; docs and commits in English",
  sources: ["claude-code", "codex"],
  waiting_entries: 0,
  waiting_agents: [],
  updated_at: "2026-09-30T09:00:00Z",
};

export const COFFER: PartitionOut = {
  uid: "mp-be27",
  name: "coffer",
  repository_path: "/Users/dev/work/coffer",
  repository_key: "remote:github.com/wyx-sg/coffer",
  note_count: 2,
  unresolvable: false,
  distilled_at: "2026-09-30T08:00:00Z",
  sample: "Use Node 20 for frontend vitest",
  sources: ["claude-code", "codex"],
  waiting_entries: 0,
  waiting_agents: [],
  updated_at: "2026-09-30T09:00:00Z",
};

/** A partition whose repository has been deleted from disk. */
export const GONE: PartitionOut = {
  uid: "mp-0d5c",
  name: "old-prototype",
  repository_path: "/Users/dev/work/old-prototype",
  repository_key: "path:/Users/dev/work/old-prototype",
  note_count: 6,
  unresolvable: true,
  distilled_at: "2026-09-20T08:00:00Z",
  sample: "Mock settlement server listens on 4010",
  sources: ["claude-code"],
  waiting_entries: 0,
  waiting_agents: [],
  updated_at: "2026-09-30T09:00:00Z",
};

const NOTE_BASE = {
  partition: "coffer",
  type: "lesson",
  search_terms: [],
  created_at: "2026-09-20T10:00:00Z",
  updated_at: "2026-09-26T10:00:00Z",
  agents: ["claude-code"],
};

export const NOTES: NoteListOut = {
  notes: [
    {
      ...NOTE_BASE,
      key: "coffer/use-node-20",
      slug: "use-node-20",
      title: "Use Node 20 for frontend vitest",
      description: "22 and 24 exit 1 even when every test passes.",
      file_path: "/Users/dev/.coffer/memory/partitions/coffer/notes/use-node-20.md",
    },
    {
      ...NOTE_BASE,
      key: "coffer/daemon-port",
      slug: "daemon-port",
      title: "Daemon port is fixed at 8000",
      description: "Read from daemon-config.json before the DB opens.",
      file_path: "/Users/dev/.coffer/memory/partitions/coffer/notes/daemon-port.md",
    },
  ],
};

export const NATIVE_PATH = "/Users/dev/.claude/projects/-Users-dev-work-coffer/memory/node.md";

export const NODE_NOTE: NoteOut = {
  ...NOTES.notes[0],
  body: "Run the frontend tests on **Node 20**, the version CI uses.",
  fingerprint: "fp-node-1",
  origins: [
    {
      agent: "codex",
      native_path: "/Users/dev/.codex/memories/coffer.md",
      anchor: "a1",
      captured_at: "2026-09-26T09:00:00Z",
      source_written_at: "2026-09-26T08:00:00Z",
    },
    {
      agent: "claude-code",
      native_path: NATIVE_PATH,
      anchor: "",
      captured_at: "2026-09-25T09:00:00Z",
      source_written_at: "2026-09-25T08:00:00Z",
    },
  ],
};

export const PORT_NOTE: NoteOut = {
  ...NOTES.notes[1],
  body: "The shim pins the port per session.",
  fingerprint: "fp-port-1",
  origins: [
    {
      agent: "claude-code",
      native_path: NATIVE_PATH,
      anchor: "",
      captured_at: "2026-09-25T09:00:00Z",
      source_written_at: "2026-09-25T08:00:00Z",
    },
  ],
};

export const RETIRED: RetiredListOut = {
  retired: [
    {
      slug: "use-node-18",
      title: "Use Node 18 for vitest",
      reason: "Superseded: CI moved to Node 20.",
      replaced_by: "use-node-20",
      retired_at: "2026-09-26T10:00:00Z",
    },
  ],
};

export const FILES: MemoryFileTreeOut = {
  root: {
    name: "coffer",
    path: "",
    abs_path: "/Users/dev/.coffer/derived/memory/coffer",
    folder_abs_path: "/Users/dev/.coffer/derived/memory",
    type: "dir",
    size: null,
    truncated: false,
    children: [
      {
        name: "notes",
        path: "notes",
        abs_path: "/Users/dev/.coffer/derived/memory/coffer/notes",
        folder_abs_path: "/Users/dev/.coffer/derived/memory/coffer",
        type: "dir",
        size: null,
        truncated: false,
        children: [
          {
            name: "use-node-20.md",
            path: "notes/use-node-20.md",
            abs_path: "/Users/dev/.coffer/derived/memory/coffer/notes/use-node-20.md",
            folder_abs_path: "/Users/dev/.coffer/derived/memory/coffer/notes",
            type: "file",
            size: 200,
            truncated: false,
            children: [],
          },
        ],
      },
    ],
  },
};

export const DELIVERIES: DeliveryOverviewOut = {
  window_days: 7,
  agents: [
    {
      agent_uid: "ag-codex",
      agent_name: "Codex",
      agent_type: "codex",
      deliveries: 0,
      by_moment: {},
      last_delivered_at: null,
      notes_read: null,
      notes_read_status: "unavailable",
    },
    {
      agent_uid: "ag-cc",
      agent_name: "Claude Code",
      agent_type: "claude_code",
      deliveries: 12,
      by_moment: { session_start: 12 },
      last_delivered_at: "2026-09-30T08:00:00Z",
      notes_read: 5,
      notes_read_status: "available",
    },
  ],
};

export const DELIVERED: DeliveredOut = {
  partition: "coffer",
  agents: [
    {
      agent_uid: "ag-codex",
      agent_name: "Codex",
      agent_type: "codex",
      event: "SessionStart",
      text: "# coffer (codex)\n- Use Node 20 for frontend vitest",
    },
    {
      agent_uid: "ag-cc",
      agent_name: "Claude Code",
      agent_type: "claude_code",
      event: "SessionStart",
      text: "# coffer (claude)\n- Use Node 20 for frontend vitest",
    },
  ],
};
