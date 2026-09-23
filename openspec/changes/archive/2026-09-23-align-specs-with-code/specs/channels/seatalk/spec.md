## MODIFIED Requirements

### Requirement: Load the websocket client library from an operator-supplied directory
The WebSocket client library MUST be an **operator-supplied optional
dependency**, never a vendored one. The only client for SeaTalk's websocket
delivery is the platform's own SDK, distributed from an internal corporate
portal, absent from public PyPI, and published under no public licence — so
Coffer, which is MIT, MUST NOT vendor it into this repository and MUST NOT
declare it as a dependency. Reimplementing its wire protocol is not an
alternative either: none is published. See
[SeaTalk Inbound Over WebSocket](../../../../docs/decisions/seatalk-websocket-inbound.md).

- Coffer looks for it at runtime in a vendor directory —
  `$COFFER_SEATALK_SDK_DIR` when set, otherwise `~/.coffer/vendor` — prepended to
  the import path only when that directory exists, following the same
  per-subsystem environment override convention the rest of the vault uses. The
  import is attempted lazily, at the moment a websocket channel starts, never at
  daemon import time, so an installation without the SDK starts exactly as it
  does today.
- When it cannot be imported, the websocket channel's connection MUST NOT come
  up and the channel MUST say precisely why: its websocket state is
  `sdk_missing`, with a detail naming the directory that was searched and the
  platform documentation that says what to put there. The connection keeps
  retrying on its back-off ladder, so dropping the SDK in needs no daemon
  restart. Nothing crashes, the daemon stays up, every webhook channel keeps
  running, and the reason is reported as that channel's own state rather than
  left in a log for someone to find.
- An installation that never obtains the SDK is fully functional on webhook
  delivery. That is deliberate, because it is what an outside user of this
  project has: websocket delivery is a capability the operator can add, not a
  floor the product is built on.

#### Scenario: a websocket channel without the sdk says what is missing
- **GIVEN** a vendor directory that holds no SeaTalk client library
- **WHEN** an enabled websocket-delivery channel tries to connect
- **THEN** its websocket connection never comes up and its reported state is
  `sdk_missing`, naming the missing library and the directory searched for it
- **AND** the connection keeps retrying, so the library can be dropped in without
  a daemon restart
- **AND** the daemon stays up and every webhook channel keeps working

### Requirement: Render replies as SeaTalk markdown
A reply MUST be converted from the agent's markdown to **SeaTalk's own markdown**
(`format: 1` — bold, italic, inline code, fences, ordered and unordered lists),
chunked to stay under the platform's **4096-byte** message cap: at most 3500
characters and 3900 bytes per chunk, leaving room for escaping to grow the text.
Headings become bold and links become `label (url)`,
neither being supported there. A literal marker character is escaped with a
**SINGLE backslash** — two would be one escape too many, SeaTalk consuming the
first and rendering the second as literal text. A mention tag is lifted out of
the escaping pass and put back after it, the way inline code already is, because
a `seatalk_id` may contain an underscore and the email form of the tag contains
one routinely — an escaped tag reaches the reader as visible source instead of a
name.

#### Scenario: seatalk markdown escapes a literal marker character
- **GIVEN** a reply whose prose contains a SeaTalk formatting character that is
  not markup (e.g. an underscore inside `snake_case`)
- **WHEN** it is rendered for SeaTalk
- **THEN** that character is escaped with a SINGLE backslash so it survives as
  typed, while genuine bold/italic/code/list markup is left as SeaTalk markdown

#### Scenario: a mention target survives the markdown escaper unchanged
- **GIVEN** a mention whose target holds a character the platform's markdown
  escaper would otherwise escape (an id containing an underscore, or an email
  address),
- **WHEN** the reply is rendered for that platform,
- **THEN** the mention markup is delivered byte for byte, while the text around
  it is escaped as usual.

### Requirement: Upload outbound media into the originating chat and thread
`send_media` MUST be wired to SeaTalk's **send-message endpoints** — the ones
`send_text` uses — with the file's bytes carried base64-inline in the message,
and the adapter declares `supports_media` true, so an agent's `MEDIA:` sentinel
returns a file into the same chat **and thread** the turn came from
([channels](../spec.md) "Return outbound media into the originating thread"). An
image is delivered as an `image` message and anything else as a `file` message;
any caption follows as a threaded text message.

#### Scenario: SeaTalk outbound media is delivered into the originating thread
- **GIVEN** a paired SeaTalk channel and a group-thread turn whose reply
  contains a `MEDIA:/absolute/path` sentinel line for a file that exists
- **WHEN** the turn's reply is delivered
- **THEN** SeaTalk receives the file's bytes inline (an image as an `image`
  message, otherwise a `file` message) in that same group and thread — not the
  group main chat — because `supports_media` is true and `send_media` routes on
  the turn's chat_kind + thread_id; any caption follows as a threaded text
  message
