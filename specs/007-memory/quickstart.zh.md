# Quickstart —— Memory Manager

> English: [quickstart.md](./quickstart.md)

## CLI

```bash
# 用本地 Ollama 作为 LLM provider 创建一个 memory store。
coffer memory create coding-prefs \
    --description "What the agent has learned about the user's coding style" \
    --llm-provider ollama \
    --llm-model llama3.1

# 或者先不配 LLM（读路径可用；add_memory 会一直返回 503，
# 直到你新建一个带真实 provider 的 store —— provider 创建后不可变）。
coffer memory create coding-prefs --llm-provider none

# 或者用 OpenAI。
coffer keychain set openai-key sk-...                       # 一次性存好 key
coffer memory create coding-prefs \
    --llm-provider openai \
    --llm-model gpt-4o-mini \
    --llm-credential-ref openai-key

# 写入 memory（CLI / 由用户）。
coffer memory add coding-prefs "Uses tabs over spaces."
coffer memory add coding-prefs "Branch names follow feat/<short-name>."

# 列出、搜索。
coffer memory list coding-prefs
coffer memory list coding-prefs --json
coffer memory search coding-prefs "indentation style"
coffer memory search coding-prefs "indentation" --top-k 3 --json

# 编辑、删除、清空。
coffer memory edit coding-prefs <id> "Uses tabs over spaces (4-tab indent)."
coffer memory delete coding-prefs <id>
coffer memory clear coding-prefs --yes

# Per-store 度量。
coffer memory describe coding-prefs
```

每个读命令都支持 `--json`。

## 桌面端

1. 侧栏 → **Resources** → **Add** → **Memory Store**。
2. 在表单里选 LLM provider。Ollama 作为推荐的本地默认；选 OpenAI 会提示输入 keychain ref。
3. 打开 store。memory 列表是主视图，顶部带搜索框。
4. 点一条 memory 展开 / 编辑 / 就地删除。
5. 顶栏显示数量与磁盘占用；kebab 菜单提供「Clear all」。

## 经由 MCP 客户端

四个内置工具出现在工具清单：

- `coffer__list_memory_stores`
- `coffer__add_memory(store, text)`
- `coffer__search_memory(store, query, top_k=5)`
- `coffer__delete_memory(store, memory_id)`

agent 在会话中可以写 memory（「用户告诉我他喜欢 X」），下次会话再召回。

## LLM provider 配置

`add_memory` 需要一个 LLM（mem0 用它做事实抽取）。三选一：

- **Ollama**（推荐做本地优先方案）：安装 Ollama，跑 `ollama pull llama3.1`，然后用 `--llm-provider ollama --llm-model llama3.1` 创建 store。
- **OpenAI**（云）：用 `coffer keychain set <ref> <key>` 把 key 存好，然后用 `--llm-provider openai --llm-credential-ref <ref> --llm-model gpt-4o-mini` 创建 store。

`llm_provider` 在 store 创建后**不可变**（连同 `llm_model`、`llm_endpoint`、`llm_credential_ref`、`embedding_model`）。要换 provider，请新建一个 store。读路径（`list`、`get`、`search`）不需要 LLM，因此 `--llm-provider none` 的 store 仍然支持这些路径；只有 `add_memory` 在这种 store 下返回 503。

## 文件落在哪里

```
~/.coffer/
├── coffer.db                  # SQLite —— 控制面（resources、memory_records、audit、...）
└── memory/
    └── coding-prefs/
        ├── chroma/            # mem0 的向量后端
        └── ...                # mem0 内部文件
```

## 限制

- memory 文本：1–8192 字符（按 store 可调，上限 32 768）。
- 每个 store 的 memory 条数：~10 000 软上限。
- 搜索 top_k：1–20（默认 5）。
