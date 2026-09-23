## MODIFIED Requirements

### Requirement: Render replies as SeaTalk markdown
A reply MUST be converted from the agent's markdown to **SeaTalk's own markdown**
(`format: 1` — bold, italic, inline code, fences, ordered and unordered lists),
chunked to stay under the platform's **4096-byte** message cap in two steps:
the agent's markdown is first split into chunks of at most 3500 characters,
each chunk is then rendered and escaped, and a rendered chunk longer than 3900
UTF-8 bytes is split again at character boundaries until every piece fits, so
neither escaping nor multi-byte text can push a message past the cap.
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
