"""Infrastructure adapters for the agent-chat surface.

Concrete SQLAlchemy repos for conversations and messages, and the adapters that
drive Claude Code and Codex through their own SDKs. The LangGraph/LangChain
adapters that once sat here moved to :mod:`coffer.infrastructure.llm`, now their
only home — importlinter Contract 9a forbids this package importing those SDKs
at all.
"""
