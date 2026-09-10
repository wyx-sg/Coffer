"""General-purpose LLM adapters.

These are not agent adapters — they call a plain chat model on behalf of a
Coffer operation (knowledge merge, organize, agentic reorg) rather than
driving a coding agent's session. They lived under ``infrastructure.chat``
only because the chat page was the first thing to need a chat model; the
consumers that outlived it are knowledge-layer operations.
"""
