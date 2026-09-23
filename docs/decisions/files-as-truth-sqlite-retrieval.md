# Retrieval Stack — Markdown Files as Truth, Not a Vendored Engine

**Status**: Superseded by [Knowledge Is Plain Files](knowledge-is-plain-files.md) — kept only for the one constraint the live design inherits, below.
**Date**: 2026-06-09
**Deciders**: Yuxing Wu
**Related**: spec [knowledge](../../openspec/specs/knowledge/spec.md), [Layer-First Code Layout](code-layout-layer-first.md), [One Shared Knowledge Store](agent-native-shared-memory.md)

## Why this ADR is still here

Everything it designed is gone — the FTS5 keyword index, the sqlite-vec vector
index, their reciprocal-rank fusion, the configurable OpenAI-compatible
embedder, the pluggable `MarkdownConverter`. The knowledge layer is now a
directory of markdown files an agent greps; read
[Knowledge Is Plain Files](knowledge-is-plain-files.md) for today's answer.

What survives is one constraint, enforced in code: `backend/pyproject.toml`'s
import contract **"Dropped engines banned everywhere"** forbids `coffer.domain`,
`coffer.application`, `coffer.infrastructure` and `coffer.surfaces` from
importing `llama_index`, `mem0`, `chromadb`, `sentence_transformers`,
`sqlite_vec` or `fastembed`. That contract has no explanation anywhere but here.

## Why those engines were tried, and why they stay banned

The first knowledge layer bought **LlamaIndex** for document retrieval, **mem0**
for memory, and **chroma** as mem0's vector store: three heavy moving parts plus
glue for what is conceptually "retrieve over markdown". Each was dropped for a
reason that has not expired.

- **LlamaIndex persists a derived index and insists on owning it** — structurally
  incompatible with files being the sole truth, because the index can diverge
  from the markdown and then nothing is authoritative to back up or rebuild
  from. The one thing wanted from it, embedding adapters, was a thin client.
- **mem0 requires an LLM call at write time** — friction when the consumer is
  already an LLM that can write a clean fact itself — and it dual-wrote fact
  text to chroma *and* SQLite, which is the dual-source-of-truth bug itself.
- **chroma** was a second embedded datastore, hence a second truth for vectors,
  earning nothing once vectors are rebuildable from files.
- **sqlite_vec, sentence_transformers and fastembed** were this ADR's own
  replacements, and went out with embeddings on 2026-09-14: Coffer embeds
  nothing, so there is no vector store and nothing to embed for.

The ban is not dependency hygiene. Every one of these libraries wants to own a
derived store, so re-admitting any of them re-admits the divergence that
files-as-truth exists to prevent — which is why an import of one is treated as a
mistake rather than a design choice, and why the contract is repo-wide rather
than a rule in the knowledge layer alone.
