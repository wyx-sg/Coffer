"""``coffer-hook`` console entrypoint — agent session-lifecycle bridge (Slice 6).

Installed into an agent's hooks config (Claude ``settings.json`` / Codex
``hooks.json``). At SessionStart it pulls the Coffer rules bundle from the local
daemon and prints it as ``additionalContext``; at SessionEnd it signals the
daemon to distill. It must NEVER raise and NEVER block the agent — every failure
path exits 0 silently.
"""
