"""`builtin_agent` kind — Coffer's own LLM agent (spec 008-builtin-agent-chat).

Distinct from the external `agent` kind (004), which only manages config for
third-party coding agents. A built-in agent is a real LLM loop Coffer runs
itself (engine LangGraph, behind the `AgentRuntime` port). This package holds
only the pure config value object; the runtime lives in infrastructure.
"""
