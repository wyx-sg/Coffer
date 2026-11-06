## Delete the unused conversation instead of editing it

Editing the old conversation's agent config would skip the provider's
`init_conversation`, which validates the directory and model and resolves the
defaults. Creating the new conversation first and then deleting the empty one
keeps that validation and leaves one row. A conversation with no agent session id
has no turn, no agent-side session and nothing in the chat history worth keeping;
`/resume` already skips a conversation that was deleted elsewhere.
