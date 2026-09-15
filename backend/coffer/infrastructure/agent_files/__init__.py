"""On-disk file formats written by the managed agents themselves — Claude
Code's session transcripts today — that more than one kind reads.

The agent kind (``infrastructure.agent.native_memory_store``) and the memory
kind (``infrastructure.memory.readers.claude_code``) both recover a project's
real working directory from the same transcript files, so neither kind owns
the parser: it lives here, where either may import it without one kind
reaching into the other. Read-only throughout. Add a format here only when a
second kind needs it; a format one kind alone reads belongs to that kind.
"""
