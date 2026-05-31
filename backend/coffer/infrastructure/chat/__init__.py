"""Chat infrastructure — SQLite persistence + concrete agent runtimes.

The LangGraph / LangChain engine and the external-agent subprocess driver are
confined to this package (engine isolation, enforced by importlinter); the
application layer talks to them only through the ports in
``coffer.application.chat.ports``.
"""
