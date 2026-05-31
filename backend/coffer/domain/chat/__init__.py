"""Chat subsystem — conversations + messages held against an agent target.

Chat is an orchestrator that sits on top of the agent kinds (it may reference
both ``agent`` and ``builtin_agent`` resources), not a peer kind. Domain holds
the pure value objects (conversations, messages, runtime events); the
``AgentRuntime`` port lives in the application layer and concrete runtimes in
infrastructure.
"""
