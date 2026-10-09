## Where the prompt is chosen

Chat composes the system context and must not import the channel kind, so the
prompt crosses the existing seam: `ChannelNote`, the domain value the channel
kind's `ChannelNoteReader` builds per turn, gains `owner_prompt`. The reader
already reads the channel's stored config and locates the conversation's chat,
so it picks the prompt there — `direct_system_prompt` for a `direct` chat,
`group_system_prompt` for a `group` one. A thread carries its chat's kind, so a
direct-chat thread reads the direct prompt and a group thread (including the
thread a group's main-chat message roots) the group prompt. When the
conversation's chat cannot be located the kind is unknown and no prompt is
guessed; the note then says less, as it already does.

`channel_system_context` appends it after the built-in text, behind the heading
line `Instructions from the channel's owner:`. Being part of the channel note,
it lands before the memory digest and the model note in the composed context.

## When a change takes effect

The reader reads the resource row on every turn rather than the binding the
adapter started with, so no restart is involved. Both providers build a fresh
adapter per turn and compose the system context for it:

- **Claude Code** gets the context as the `append` of its `claude_code` preset
  system prompt on every run, including a `--resume`d one. The system prompt is
  not part of the stored session, so the resumed run uses the new text.
- **Codex** gets it as `developerInstructions` on `thread/resume` as well as
  `thread/start`, the same path the per-turn model note already relies on.

So an edited prompt applies from the next turn of an existing conversation.

## Limits

4,000 characters per prompt: enough for a page of conventions, small next to
the context it rides with on every turn. The value is trimmed (surrounding
whitespace carries nothing, and a whitespace-only prompt is no prompt); text
inside is kept as written. The cap is checked by the config model, so the REST
route, the CLI and a hand-edited vault file all meet the same rule.

## Why a dialog, not save-as-you-type

Every other channel setting saves as it changes. A prompt is prose written in
one go, and a half-typed instruction saved mid-sentence would steer a turn that
happens to start meanwhile. The section therefore follows the detail-page
convention of an Edit button and a dialog with Save and Cancel.
