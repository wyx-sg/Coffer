# TODO: larger work we may do later

Large features and changes the owner agreed are worth doing **some day but not now**.
It is a parking lot, not a plan: nothing here is scheduled, and an entry is not a
commitment to build it the way it is sketched.

- Small bugs and polish do not belong here; fix them, or track them where the
  current work is tracked.
- Work that has started moves out: delete the entry in the PR that opens the
  OpenSpec change (`openspec/changes/<name>/`) or the PR that ships it.
- An entry that was rejected is deleted too; if the reason matters later, it goes
  into the relevant spec's Purpose or an ADR, not here.

## How to add an entry

Append under the area's heading (add the heading if the area has none yet, keeping
the areas in alphabetical order). Copy this block; one `###` per entry, so two
threads appending at once rarely conflict:

```markdown
### <Verb-first title, a few words>

- **Added:** YYYY-MM-DD, from <thread name or PR link>
- **What:** one or two sentences on the capability, in the user's terms.
- **Why later:** why it is worth doing, and why not now.
- **Sketch:** the approach agreed so far, open questions, and comparable products
  looked at (link the discussion draft or research note when there is one).
```

## MCP servers and custom tools

### Refresh custom-tool tokens with OAuth2 client credentials

- **Added:** 2026-11-06, from the thread "梳理 MCP 和自定义工具还缺什么"
- **What:** a custom-tool group whose API gives out a client id and client secret
  instead of a long-lived token: Coffer exchanges them at the token endpoint for a
  short-lived access token, caches it, refreshes it before it expires and sends it
  on each request (Microsoft Graph app-only access, Salesforce, many company API
  gateways).
- **Why later:** only Coffer can do it, because the agent never holds the client
  secret; with a fixed token such an API stops working within an hour or two. No
  current API needs it: SeaTalk exchanges an app id and secret too, but in its own
  format, which standard client credentials would not cover.
- **Sketch:** the client id and secret are stored secrets cited by the
  environment (the secret picker offers "pick existing / create new"); the access
  token is a machine-local secret that never syncs and that no agent sees. The
  token request is `application/x-www-form-urlencoded`, so it lands together with
  form request bodies. Needs an ADR on where the token lives and how a refresh
  failure is reported.

### Tell the person at import that an OAuth server stays in the agent

- **Added:** 2026-11-06, from the thread "梳理 MCP 和自定义工具还缺什么"
- **What:** when an agent's MCP entry needs an OAuth browser login, the import
  says Coffer does not log in to remote servers and leaves the entry in the
  agent, instead of moving it and failing with 401.
- **Why later:** the owner decided Coffer does not do upstream OAuth, because
  Claude Code and Codex log in themselves; the notice only matters once such a
  server shows up. None of the current servers uses OAuth.
- **Sketch:** detect it from the entry (an `oauth` block, or a remote URL with no
  auth header that answers 401 with `WWW-Authenticate` pointing at an
  authorization server), then skip it with a reason, as an SSE entry is skipped.

### Send form-encoded request bodies from custom tools

- **Added:** 2026-11-06, from the thread "梳理 MCP 和自定义工具还缺什么"
- **What:** a custom tool's body can be `application/x-www-form-urlencoded` as
  well as JSON; today the request's Content-Type is fixed to JSON.
- **Why later:** many older APIs and every OAuth token endpoint take form bodies,
  but no current tool needs one. Build it together with OAuth2 client
  credentials if that comes first.
- **Sketch:** a body type switch on the tool (JSON or form); a form body is the
  same `{name}` template filled per field and percent-encoded.

### Upload files from custom tools

- **Added:** 2026-11-06, from the thread "梳理 MCP 和自定义工具还缺什么"
- **What:** a custom tool can send a `multipart/form-data` request with a file,
  for APIs that take attachments, images or packages (Jira or Confluence
  attachments, chat file messages, OCR, artifact stores).
- **Why later:** it is part of turning an HTTP API into tools, but no current
  API needs it, and it needs its own security design.
- **Sketch:** the hard part is where the file comes from. Inline base64 in the
  arguments is simple but floods the agent's context and suits small files only;
  a local path that Coffer reads and uploads means Coffer reads arbitrary files
  for an agent and sends them out, so it needs rules on which directories are
  allowed and whether the person confirms.
