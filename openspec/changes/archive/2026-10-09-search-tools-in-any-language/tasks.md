## 1. Ranker

- [x] 1.1 Tokenize CJK runs into overlapping bigrams after NFKC folding
- [x] 1.2 Add the input schema's parameter text as a third field at weight 0.5
- [x] 1.3 Feed `schema_text(inputSchema)` from the gateway's search corpus

## 2. Eval

- [x] 2.1 Replace the tool-search datasets with a realistic mixed-language catalogue and query set
- [x] 2.2 Score recall@5 and MRR, report CJK-query recall, gate MRR, record the new baseline

## 3. Docs

- [x] 3.1 ADRs for CJK bigrams and parameter text; update Tool Overload
- [x] 3.2 MCP gateway architecture page, English and Chinese
