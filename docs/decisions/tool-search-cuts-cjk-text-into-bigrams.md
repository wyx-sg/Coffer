# Tool Search Cuts CJK Text Into Bigrams

**Status**: Accepted
**Date**: 2026-10-09
**Deciders**: Yuxing Wu
**Related**: [Tool Overload: List a Usage-Ranked Slice, Search the Rest](tool-overload-tier-the-list-search-the-rest.md), [Tool Search Indexes Parameter Text](tool-search-indexes-parameter-text.md), [Eval Capture and Regression Gate](eval-capture-and-regression-gate.md), spec mcp-gateway "Forward tools, resources and prompts"

## Context

`coffer__search_tools` ranks the aggregated catalogue with a BM25-lite scorer
that is lexical, local and model-free ([Tool Overload](tool-overload-tier-the-list-search-the-rest.md)).
Its tokenizer kept only `[a-z0-9]+` runs. Chinese, Japanese and Korean text
was dropped before scoring, so on the owner's 284-tool catalogue the query
查询账号列表 ("list accounts") returned **no results at all**, although the
account tools it wanted are described in Chinese. Teams that write internal
tools in Chinese describe them in Chinese, and agents asked in Chinese often
search in Chinese, so this is the normal case for those users, not an edge.

CJK text has no spaces between words, so a tokenizer must decide where terms
start and end. The constraints: Coffer runs no model and embeds nothing
(the removal of every embedding path is recorded in Tool Overload); the
ranker is a pure domain function the eval can run offline; and the daemon is
a packaged binary where each dependency costs size.

How comparable search engines cut CJK text without a model:

- **Lucene / Elasticsearch / OpenSearch** ship `CJKAnalyzer` and the
  `cjk_bigram` token filter: overlapping two-character terms, a lone CJK
  character kept as a unigram, and unigram output off by default.
- **SQLite FTS5** offers a `trigram` tokenizer for scripts without word
  boundaries, matching any three-character substring.
- **Meilisearch** (via `charabia`) and many Chinese search stacks segment with
  a dictionary (jieba); this gives real words but needs a dictionary of
  several megabytes and still misses domain terms it has never seen.

## Options Considered

### Option A — Overlapping bigrams, lone characters kept (chosen)

After NFKC folding (so full-width ＧｉｔＨｕｂ reads as GitHub), each CJK run
becomes its overlapping character pairs: 查询账号 → 查询, 询账, 账号. A run of
one character stays itself. Latin text tokenizes as before.

- Pros: no dependency and no dictionary; works the same for Chinese, Japanese
  and Korean; a two-character word, the commonest length in Chinese, is always
  one of the terms, so 账号 in a query meets 账号 in a description wherever it
  sits; spurious pairs across word boundaries (询账) are rare across the
  catalogue, so their idf stays low and they add little noise.
- Cons: a pair can match across an unrelated word boundary; a one-character
  query word inside a longer run (按 in 按手机号) is only found as part of a
  pair; more terms per document than a segmenter would produce.
- Measured on the tool-search eval (285 tools, 89 queries, 35 of them in
  Chinese or mixed): recall@5 goes from 0.506 to 0.787 and MRR from 0.384 to
  0.633 together with [parameter text](tool-search-indexes-parameter-text.md);
  Chinese queries hit in 30 of 35 cases, up from 9 (those 9 hit through the
  Latin words in mixed queries).

### Option B — Bigrams plus unigrams

Emit every character as well as every pair (`output_unigrams: true`).

- Pros: a one-character query term matches anywhere.
- Cons: single characters such as 查 or 询 occur in most Chinese descriptions,
  so they add score to the wrong tools. On the same eval recall@5 fell to
  0.742 and MRR to 0.596, and Chinese hits to 28 of 35.
- Loses on the measurement.

### Option C — Dictionary segmentation (jieba)

Segment with a word dictionary and index the words.

- Pros: real word boundaries, fewer spurious terms.
- Cons: a new runtime dependency with a dictionary of several megabytes in
  every packaged daemon; a tool catalogue is full of product and domain terms
  (灰度, 工单, 值班) a general dictionary splits unpredictably; segmentation of
  a short query and of a long description can disagree, and then nothing
  matches, which bigrams cannot do.
- Loses because bigrams reach the same queries with no dependency, and a
  mis-segmentation fails silently.

### Option D — Trigrams (SQLite FTS5 style)

- Pros: fewer spurious matches than bigrams.
- Cons: a two-character word, the commonest length in Chinese, produces no
  trigram, so 账号 alone could never match.
- Loses for that reason.

### Option E — Embeddings or a model that translates the query

- Pros: would also bridge a Chinese query to an English description, which no
  lexical cut can.
- Cons: Coffer runs no model and embeds nothing (Tool Overload, Option
  "Embedding-based search"); the ranker must stay deterministic and offline.
- Out of bounds for this decision. The remaining Chinese misses in the eval
  are exactly these cross-language cases (给同事发一封邮件 against an English
  `send_message`).

## Decision

The tool-search tokenizer folds text with NFKC, splits Latin text as before,
and cuts every CJK run (ideographs, kana, Hangul) into overlapping two-character
terms, keeping a run of one character as itself. No unigrams are added and no
dictionary is used. Query and documents go through the same tokenizer.

## Consequences

- A Chinese, Japanese or Korean query matches tools described in the same
  language. A query in one language still does not match a description in
  another; that stays a known gap of a lexical ranker.
- The tokenizer lives in `backend/coffer/domain/mcp/tool_search.py`; the
  `tool_search` eval now reports recall on CJK queries on its own, and its
  baseline gates recall@5 and MRR in CI.
