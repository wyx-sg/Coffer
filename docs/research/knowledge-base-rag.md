# Competitive Research — Local-First Knowledge Base / RAG for Agents

> English: this file · 中文版: [knowledge-base-rag.zh.md](./knowledge-base-rag.zh.md)
>
> Internal competitive-research report for Coffer's knowledge base (spec 006,
> ADR-012). **Date:** 2026-06-16. **Method:** deep-research harness (this run
> also read Coffer's own KB code to verify the comparison).
>
> **✓ Coverage gap filled.** The first pass went deep on txtai, Open WebUI
> Knowledge, RAGFlow, Cognee, and two SQLite-FTS5+sqlite-vec peers; a targeted
> follow-up then covered the five tools it had missed — **AnythingLLM, Onyx
> (Danswer), Khoj, Morphik, LlamaIndex** — folded in as §5 below.

## 1. Landscape at a glance

Local-first RAG splits by **where the source of truth lives** and **how heavy the
ingestion pipeline is**:

| Class                                  | Truth lives in                                  | Examples                                    |
| -------------------------------------- | ----------------------------------------------- | ------------------------------------------- |
| **Files-as-truth + rebuildable index** | Original/markdown files; DB is throwaway        | **Coffer**, obsidian-hybrid-search, AIngram |
| **DB-as-truth**                        | A parsed corpus / vector store is authoritative | RAGFlow, Cognee, txtai                      |
| **App-managed collections**            | The app's workspace owns the docs               | Open WebUI Knowledge, AnythingLLM, Onyx     |

### The players (first pass)

- **txtai** (`neuml/txtai`, OSS) — an all-in-one local-first embeddings DB
  (sparse + dense + graph + SQL); retrieval via BM25 / hybrid / SQL / graph
  (openCypher); default embedding `all-MiniLM-L6-v2` (HF Hub or local); agents
  reach it via REST / **MCP** / Python. [confirmed 3-0]
- **Open WebUI Knowledge** — **5 content-extraction engines** (Tika, Docling,
  Azure Document Intelligence, Mistral OCR, custom); hybrid retrieval = BM25 +
  vector + **cross-encoder reranking**; native tools `query_knowledge_files` /
  `grep_knowledge_files` / `view_file` / `kb_exec`; hash-based refs. [confirmed]
- **RAGFlow** (`infiniflow/ragflow`, OSS) — the deepest ingestion: default
  **DeepDoc vision OCR + table-structure + doc-layout** recognition (PDF/DOCX/
  XLS/PPT → chunks with positions, tables→natural language, figure captions),
  plus pluggable parsers (Naive/MinerU/Docling/OpenDataLoader/VLM, four marked
  _Experimental_). Hybrid retrieval (keyword threshold 0.2, vector weight 0.3).
  **Crucially: the embedding model is LOCKED per-dataset once chunked.** [confirmed 3-0]
- **Cognee** (`topoteretes/cognee`, Apache-2.0) — a **writable** vector +
  knowledge-graph memory (MCP `remember`/`recall`/`forget`); more memory than KB.
- **SQLite-FTS5 + sqlite-vec peers that mirror Coffer's exact stack** —
  **obsidian-hybrid-search** (files authoritative, rebuildable; BM25 weighted
  title 10× / aliases 5× / content 1× + vector + fuzzy fused via **RRF**; MCP
  `search`/`read`/`reindex`/`status`) and **AIngram** (one SQLite file is truth;
  FTS5 + sqlite-vec + graph fused via RRF; local `nomic-embed` ONNX 768-d, **no
  external embedding API**). [confirmed 3-0] FTS5 `bm25()` rank is **negative**;
  sqlite-vec does KNN but **not** embeddings; both peers use **weighted RRF that
  Coffer lacks.**

## 2. Capability comparison (first pass)

| Capability          | txtai         | Open WebUI         | RAGFlow                | obsidian/AIngram | **Coffer KB**                                                   |
| ------------------- | ------------- | ------------------ | ---------------------- | ---------------- | --------------------------------------------------------------- |
| Source of truth     | embeddings DB | app collection     | parsed DB              | **files**        | **`docs/<id>.md` files + `raw/`**                               |
| Rebuildable index   | partial       | —                  | re-chunk needed        | ✅               | **✅ `coffer reindex`**                                         |
| Ingestion / OCR     | basic         | 5 engines incl OCR | DeepDoc vision OCR     | markdown only    | **MarkItDown only**                                             |
| Keyword (BM25)      | ✅            | ✅                 | ✅                     | ✅ FTS5          | **✅ FTS5 bm25()**                                              |
| Vector              | ✅            | ✅                 | ✅                     | ✅ sqlite-vec    | **✅ sqlite-vec (opt-in)**                                      |
| Hybrid fusion (RRF) | ✅            | ✅                 | ✅                     | **✅ RRF**       | **❌ modes are separate**                                       |
| Reranking           | —             | ✅ cross-encoder   | ✅                     | —                | **❌**                                                          |
| Embedding swap      | easy          | easy               | **locked per dataset** | re-embed         | **✅ trivial via reindex**                                      |
| Agent access        | REST/MCP/Py   | native tools       | REST                   | MCP              | **read-only MCP tools (list/search/grep/read) + agentic `ask`** |
| Writable by agent   | yes           | yes                | yes                    | no               | **no (read-only)**                                              |

## 3. How Coffer compares

**Where Coffer is competitive or ahead.**

1. **Files-as-truth + trivially rebuildable index is a genuine edge.** RAGFlow,
   Cognee, and txtai make a parsed DB authoritative; RAGFlow even **locks the
   embedding model once chunked.** Coffer's `docs/<id>.md` + `raw/` truth with a
   throwaway SQLite index makes swapping the embedding model or rebuilding the
   index trivial (`coffer reindex`) — a durability and flexibility win.
2. **Read-only + agent-via-MCP is the right safety posture** for a vault. Coffer
   exposes granular read-only MCP tools (list / keyword-or-vector search / grep /
   read) and layers an agentic `ask` (ADR-024) on top; the agent never writes the
   KB. (Cognee, by contrast, is writable.)
3. **The SQLite-FTS5+sqlite-vec peers validate the whole architecture** —
   independent projects converged on Coffer's exact substrate.

**Where Coffer lags — concrete borrows.**

1. **No hybrid fusion (RRF).** Coffer runs grep / keyword / vector as _separate_
   modes; every serious peer (Open WebUI, RAGFlow, obsidian-hybrid-search,
   AIngram — and, below, LlamaIndex + Onyx) fuses keyword + vector via
   **Reciprocal Rank Fusion**. Highest-value, lowest-cost borrow.
2. **No reranking.** Open WebUI and RAGFlow (and, below, Khoj/Onyx/AnythingLLM)
   add a cross-encoder reranker after retrieval; Coffer has none.
3. **Shallow ingestion.** Coffer is MarkItDown-only; RAGFlow's DeepDoc, Open
   WebUI's 5 engines, and (below) Morphik/LlamaParse do real OCR / layout
   extraction. Coffer's `MarkdownConverter` port already exists — make engines
   pluggable behind it.
4. **Single embedding client.** A local-ONNX option would remove the
   OpenAI-compatible-API dependency for fully-offline use.

## 4. Key takeaways for Coffer

1. **Add RRF hybrid fusion** — the single clearest gap; LlamaIndex's
   `QueryFusionRetriever(mode="reciprocal_rerank")` is a concrete reference.
2. **Add a pluggable reranker** (cross-encoder) — Khoj/Onyx ship one by default.
3. **Make ingestion/OCR pluggable behind the existing `MarkdownConverter` port**
   (DeepDoc/Docling/Mistral-OCR/ColPali-class engines).
4. **Offer a local-embedding option** (ONNX) — _all ten_ surveyed peers have one;
   it is the strongest, most universal signal.
5. **Keep files-as-truth + reindex** — a real advantage over the
   DB-as-truth/locked-embedding competitors; lead with it.

## 5. Follow-up — five more local RAG systems (coverage fill)

A targeted follow-up covered the five mainstream tools the first pass missed. All
five are **actively maintained in 2026**, and **all five offer a true local
embedding option**.

| Tool               | Hybrid RRF fusion                             | Reranker                 | Deep OCR / visual parse      | Local embedding        | MCP access         | License                        |
| ------------------ | --------------------------------------------- | ------------------------ | ---------------------------- | ---------------------- | ------------------ | ------------------------------ |
| **LlamaIndex**     | ✅ `QueryFusionRetriever` (reciprocal_rerank) | ✅                       | LlamaParse (cloud-gated)     | ✅                     | via integrations   | OSS                            |
| **Onyx** (Danswer) | ✅ BM25+vector                                | ✅ optional              | ❌ connector text extraction | ✅ local embed server  | not evidenced      | OSS                            |
| **Khoj**           | bi-encoder → rerank                           | ✅ default cross-encoder | ❌                           | ✅ default `gte-small` | —                  | OSS                            |
| **Morphik** Core   | —                                             | —                        | ✅ **ColPali (OCR-free)**    | ✅                     | ✅ **morphik-mcp** | **BSL 1.1** (source-available) |
| **AnythingLLM**    | —                                             | ✅ (LanceDB only)        | ❌                           | ✅ ONNX/all-MiniLM     | —                  | OSS                            |

- **LlamaIndex** is the concrete RRF reference:
  `QueryFusionRetriever(mode="reciprocal_rerank")` fuses BM25 + vector — exactly
  the fusion Coffer lacks. **LlamaParse** adds layout-aware multimodal markdown
  (cloud/enterprise-gated). [confirmed]
- **Khoj** ships two-stage retrieve-then-rerank by default (bi-encoder
  `thenlper/gte-small` → cross-encoder `mixedbread-ai/mxbai-rerank-xsmall-v1`,
  swappable; fully local when self-hosted) — a clean local reranker template.
  [confirmed 3-0]
- **Onyx** runs fully local / airgap-capable with hybrid BM25+vector + optional
  reranker + a local embedding server + 40 connectors (incremental sync, default
  30-min refresh). [confirmed 3-0]
- **Morphik** Core is the standout for two Coffer-relevant things: OCR-free deep
  **visual** parsing (ColPali page-image embeddings over PDFs/images/video) and a
  **first-class MCP server (`morphik-mcp`)** — the closest analogue to Coffer's
  agent-read-only-via-MCP KB. _Caveat:_ **BSL 1.1**, not OSI-OSS (relicenses
  Apache-2.0 ~4 yrs post-release; free commercial under $2K/mo gross revenue).
  [confirmed 3-0]
- **AnythingLLM** has a reranker but only coupled to LanceDB; native ONNX
  (all-MiniLM) + GGUF local embeddings.

**This confirms and sharpens the four borrows:** (a) **RRF fusion** now has a
concrete reference (LlamaIndex); (b) **reranking** is shipped-by-default in
Khoj/Onyx — a local cross-encoder is the template; (c) **deep/visual parsing**
(Morphik ColPali, LlamaParse) is the high end of the pluggable-OCR borrow;
(d) a **local embedding option** is universal across all surveyed systems — the
strongest signal Coffer should add one. **Morphik's `morphik-mcp` also validates
Coffer's agent-read-only-via-MCP KB design.**

## 6. Sources

First pass:

- github.com/neuml/txtai · neuml.github.io/txtai/api/mcp
- docs.openwebui.com/features/workspace/knowledge · deepwiki.com/open-webui (content-extraction engines)
- github.com/infiniflow/ragflow/blob/main/deepdoc/README.md · ragflow.io/docs/select_pdf_parser · …/configure_knowledge_base
- github.com/topoteretes/cognee
- github.com/flowing-abyss/obsidian-hybrid-search · github.com/bozbuilds/AIngram
- alexgarcia.xyz/blog/2024/sqlite-vec-hybrid-search · sqlite.org/fts5.html

Follow-up:

- github.com/morphik-org/morphik-core · github.com/morphik-org/morphik-mcp · arxiv.org/abs/2407.01449 (ColPali)
- docs.onyx.app (connectors, search_configs, self_hosted data processing) · github.com/onyx-dot-app/onyx · blog.vespa.ai/why-danswer-users-vespa
- github.com/khoj-ai/khoj (embeddings.py, text_search.py, SearchModelConfig)
- LlamaIndex docs — QueryFusionRetriever (reciprocal_rerank), LlamaParse
- github.com/Mintplex-Labs/anything-llm

Coffer code verified: backend/coffer/application/knowledge_base/service.py · builtin_tools.py

## Verification update (2026-06-19)

> Re-verification pass against this report. The central local claim and four of
> five web claims hold; one competitor row (Onyx MCP) is corrected; the
> AnythingLLM coverage bullet checks out.

### ✅ Confirmed

- **Coffer KB has no hybrid/RRF fusion — modes are strictly separate.**
  `RetrievalMode = Literal["grep","keyword","vector"]`
  (`repo:backend/coffer/domain/knowledge/retrieval.py:11`); `search()` dispatches
  exactly one mode per call, with a vector→keyword _fallback_ (not a fusion) and
  no reciprocal-rank or bm25+vec score combination anywhere
  (`repo:backend/coffer/application/knowledge/retrieval.py:109-169`;
  `repo:backend/coffer/application/knowledge_base/service.py:274-300`). FTS5
  bm25 and sqlite-vec KNN exist as separate engines, never combined.
- **LlamaIndex `QueryFusionRetriever(mode="reciprocal_rerank")`** still documents
  fusing BM25 + vector retrievers via RRF.
  https://docs.llamaindex.ai/en/stable/examples/retrievers/reciprocal_rerank_fusion/
- **RAGFlow per-dataset embedding lock + thresholds** — embedding model cannot
  change once a dataset has chunks (delete chunks to switch); similarity
  threshold default 0.2, vector weight default 0.3.
  https://ragflow.io/docs/configure_knowledge_base
- **Morphik license** — `morphik-core` LICENSE is BSL 1.1; Additional Use Grant
  permits production use while gross revenue from that use is < US$2000/month;
  Change License Apache-2.0; Change Date June 18 2029 (~4 yrs).
  https://raw.githubusercontent.com/morphik-org/morphik-core/main/LICENSE
- **Khoj default models** — bi-encoder `thenlper/gte-small` → cross-encoder
  `mixedbread-ai/mxbai-rerank-xsmall-v1`, set in
  https://raw.githubusercontent.com/khoj-ai/khoj/master/src/khoj/processor/embeddings.py

### ✏️ Corrected

- **Onyx MCP access:** old → §5 table marks Onyx MCP access "not evidenced".
  Corrected → Onyx officially supports MCP both as a **client** (agents invoke
  tools) and as a **server** (connect Claude/Cursor to the Onyx knowledge base);
  the row understates current state. https://docs.onyx.app/admins/actions/mcp
- **RAGFlow lock — refinement (not a contradiction):** as of RAGFlow 0.22.1 an
  opt-in compatibility check can permit switching the embedding model on a
  data-containing dataset when re-encoded sample cosine similarity ≥ 0.9. The
  per-dataset lock is the _default_ behavior, now with a newer guarded escape
  hatch. https://ragflow.io/docs/configure_knowledge_base

### ➕ Coverage added

- **AnythingLLM** — reranker is coupled to **LanceDB only**
  (`NativeEmbeddingReranker`, default cross-encoder
  `Xenova/ms-marco-MiniLM-L-6-v2`), with an open feature request to extend
  reranking to other vector DBs (Pinecone/Weaviate/FAISS); native/local
  embedding = ONNX `all-MiniLM-L6-v2` (Xenova quantized, 384-d), the bundled CPU
  embedder in the desktop app — matching the §5 bullet.
  https://deepwiki.com/Mintplex-Labs/anything-llm/6.4-similarity-search-and-reranking
  · https://github.com/Mintplex-Labs/anything-llm/issues/3941
