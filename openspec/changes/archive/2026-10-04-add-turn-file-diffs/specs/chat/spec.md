## ADDED Requirements

### Requirement: Record what each reply changed in each file
For every assistant reply, the daemon MUST record a unified diff per file the
reply wrote: for Claude Code, the file's content before the reply's first write to
that path compared with its content when the reply ends; for Codex, the diffs its
file-change items carry. Each file MUST keep its added and removed line counts; a
file over 1 MB or not text keeps only its counts and says why its diff is omitted;
a file whose content ends unchanged is not recorded. The records MUST be readable
per reply — the file list, and one file's diff — and MUST be deleted with the
reply.

#### Scenario: a reply's edits to one file become one diff
- **GIVEN** a Claude Code reply that edits `ws_client.py` twice and writes a new file `test_ws.py`
- **WHEN** the reply ends and its files are read
- **THEN** two files are listed, `ws_client.py` with one diff covering both edits against its content before the first, and `test_ws.py` as all added lines

#### Scenario: a binary file is listed without a diff
- **GIVEN** a reply that writes a 3 MB file
- **WHEN** its files are read
- **THEN** the file is listed with its counts and the diff is omitted as too large

### Requirement: Open a changed file's diff in a drawer
A row of "Files changed" whose reply has a recorded diff MUST open a drawer on the
right, 640 wide and starting under the title bar, holding that file's diff for
that reply: the path with its added and removed counts, "<n> of <N>" with previous
and next file and a close control (Esc closes too), and the diff with old and new
line numbers, hunk headers and added and removed lines marked. The open file's row
MUST be highlighted in the card. A reply recorded before this existed keeps its
estimated rows, which open nothing.

#### Scenario: the drawer walks the reply's files
- **GIVEN** a reply with two changed files, both with diffs
- **WHEN** the owner clicks the first row and then next file
- **THEN** the drawer shows "1 of 2" with the first file's diff, then "2 of 2" with the second's, and the second row is highlighted
- **AND** Esc closes the drawer

## MODIFIED Requirements

### Requirement: Summarise the files a reply changed
Under an assistant reply that is no longer streaming, the thread MUST show a
"Files changed" card listing each file the reply changed, with the lines added and
removed, read from the reply's recorded files (see "Record what each reply changed
in each file"); a reply recorded before files were recorded falls back to the
files its tool calls wrote, with repeated edits to one file summed into one row. A
reply that changed no file shows no card. The card sits inside the reply, after
its text and before its token line, and its title carries no count.

#### Scenario: a reply's file edits are summed into one row per file
- **GIVEN** an assistant reply whose tool calls edit one file twice, write a second file, and read a third
- **WHEN** the thread renders it
- **THEN** the Files changed card lists the two written files only, one row each, with their added and removed line counts
- **AND** a reply with no file-writing tool call shows no card
