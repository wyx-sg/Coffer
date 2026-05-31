# Quickstart — Memory Manager

## CLI

```bash
# Create a memory store with local Ollama as the LLM provider.
coffer memory create coding-prefs \
    --description "What the agent has learned about the user's coding style" \
    --llm-provider ollama \
    --llm-model llama3.1

# Or create with no LLM (read paths work; add_memory returns 503 until you
# create a new store with a real provider — provider is immutable post-create).
coffer memory create coding-prefs --llm-provider none

# Or create with OpenAI.
coffer keychain set openai-key sk-...                       # store key once
coffer memory create coding-prefs \
    --llm-provider openai \
    --llm-model gpt-4o-mini \
    --llm-credential-ref openai-key

# Add memories (CLI / by user).
coffer memory add coding-prefs "Uses tabs over spaces."
coffer memory add coding-prefs "Branch names follow feat/<short-name>."

# List, search.
coffer memory list coding-prefs
coffer memory list coding-prefs --json
coffer memory search coding-prefs "indentation style"
coffer memory search coding-prefs "indentation" --top-k 3 --json

# Edit, delete, clear.
coffer memory edit coding-prefs <id> "Uses tabs over spaces (4-tab indent)."
coffer memory delete coding-prefs <id>
coffer memory clear coding-prefs --yes

# Per-store metrics.
coffer memory describe coding-prefs
```

`--json` works on every read command.

## Desktop

1. Sidebar → **Resources** → **Add** → **Memory Store**.
2. Pick the LLM provider in the form. Ollama is offered as the recommended local default; OpenAI prompts for a keychain reference.
3. Open the store. The memory list is the main view, with a search box at the top.
4. Click a memory to expand / edit / delete in place.
5. The header shows count and on-disk size; a kebab-menu offers "Clear all".

## Through an MCP client

Four built-in tools appear:

- `coffer__list_memory_stores`
- `coffer__add_memory(store, text)`
- `coffer__search_memory(store, query, top_k=5)`
- `coffer__delete_memory(store, memory_id)`

The agent can write memories during a session ("the user told me they prefer X") and retrieve them on later sessions.

## LLM provider setup

`add_memory` requires an LLM (mem0 uses it for fact extraction). Choose one:

- **Ollama** (recommended for local-first): install Ollama, run `ollama pull llama3.1`, then create your store with `--llm-provider ollama --llm-model llama3.1`.
- **OpenAI** (cloud): store the API key with `coffer keychain set <ref> <key>`, then create the store with `--llm-provider openai --llm-credential-ref <ref> --llm-model gpt-4o-mini`.

The `llm_provider` choice is **immutable** after the store is created (alongside `llm_model`, `llm_endpoint`, `llm_credential_ref`, and `embedding_model`). To switch providers, create a new store. Reads (`list`, `get`, `search`) do not require an LLM, so a `--llm-provider none` store still supports those paths; only `add_memory` returns 503 against such a store.

## Where files live

```
~/.coffer/
├── coffer.db                  # SQLite — control plane (resources, memory_records, audit, ...)
└── memory/
    └── coding-prefs/
        ├── chroma/            # mem0's vector backend
        └── ...                # mem0 internal files
```

## Limits

- Memory text: 1–8192 chars (configurable per store up to 32 768).
- Memories per store: ~10 000 soft cap.
- Search top_k: 1–20 (default 5).
