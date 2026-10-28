# A Channel Reply Names Its Files, and the Files Follow It

**Status**: Accepted
**Date**: 2026-10-28
**Deciders**: Yuxing Wu
**Related**: [A Long Channel Reply Is Rewritten Short by the Agent](long-channel-reply-is-rewritten-short.md), [Channel Attachments](channel-attachments.md), spec channels "Send files back only through an explicit sentinel"

## Context

An agent hands the user a file with a `MEDIA:/absolute/path | caption` line.
Coffer used to upload each file as soon as the reply was finished, before the
reply itself, and on SeaTalk follow each file with a text message holding its
caption. A SeaTalk group reply with two CSV files on 2026-10-28 arrived as five
messages: file, caption, file, caption, then the reply card. The owner asked
whether the files and their captions could go with the card.

What SeaTalk allows (its Open Platform docs, read 2026-09-11 and recorded in
`seatalk_parse.py`): an interactive card holds only `title`, `description`,
`button`, `button_group` and `image` elements, so a card cannot carry a file;
a `file` message has a filename and content and no caption field. A file is
always its own message.

How comparable chat bots pair files with text (their public API docs, 2026-10):

- **Telegram Bot API**: `sendDocument` / `sendPhoto` take a caption, and
  `sendMediaGroup` sends up to ten files as one album.
- **Slack**: a file upload can carry an `initial_comment`, so text and file are
  one message.
- **Feishu / Lark**: like SeaTalk, a card has no file element; bots send the
  card and the files as separate messages.
- **OpenClaw's SeaTalk plugin**: sends text, image and file replies as separate
  messages; nothing combines them.

## Options Considered

### Option A — The reply goes first and names the files; the files follow it bare (chosen)

The `MEDIA:` lines are taken out of the reply, which goes out first. Where a
file message cannot carry a caption, the reply ends with one line per file,
`📎 name — caption`. The files are uploaded after it, with no text message of
their own. Two files: three messages instead of five.

- ✅ The fewest messages SeaTalk allows, and the conclusion is read first.
- ✅ Same order as the files Coffer itself attaches (a table turned into CSV).
- ⚠️ The reply names a file before it has been uploaded; one that then fails is
  said in a short follow-up line.

### Option B — Files first, the reply last and naming them

- ✅ By the time the reply (and its @mention) arrives, every file is there.
- ❌ The reader finishes the conclusion and has to scroll up to find the files.

### Option C — A button per file on the reply card; a tap sends the file

- ✅ Nothing lands in the chat until someone wants it; in a group the file could
  go privately to whoever tapped.
- ❌ Coffer would have to keep every file for days, a card holds at most nine
  buttons with 🗑 and 📄 already among them, and the tap still produces a
  separate file message. Considered and set aside by the owner.

### Option D — Drop the card and reply in plain text

- ❌ Group replies are cards because SeaTalk can rewrite a card but delete
  nothing; without cards a group reply could no longer be withdrawn. It also
  does not reduce the file messages.

## Decision

Option A, for every transport. A transport declares `media_captions` when its
file message carries a caption (Telegram); there the caption stays on the file
and the reply is not extended. On one without (SeaTalk), the reply lists the
files when at least one has a caption; files without any caption are just sent.

## Consequences

- `deliver_media` is split into `take_media` (strip the lines, before the reply)
  and `send_media_files` (upload, after it). SeaTalk's `send_media` no longer
  sends a caption message.
- An upload that fails after the reply went out is reported as
  `⚠️ Couldn't send 'name'.` rather than leaving the `MEDIA:` line in the text.
