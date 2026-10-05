## Why

The people list on a channel's Overview shows every paired person as two
initials, although both platforms hold a picture of them. The line under each
name also read "Owner · direct chat · paired <date>": pairing only ever happens
in a direct chat, so "direct chat" was on every row and said nothing, and it
read like a role or a permission.

## What Changes

- Each row shows the person's picture on the platform, and their initials when
  there is none to show. Telegram's comes from `getUserProfilePhotos`; SeaTalk's
  from the employee profile (`/contacts/v2/profile`), which needs the app's
  **Get Employee Profile** permission.
- The picture is fetched by the running adapter when the page first asks for it,
  kept in a machine-local cache (`derived/channel-avatars/`) and fetched again
  after a day. A refused or failed fetch shows initials and is not retried for an
  hour. Removing the person or deleting the channel drops the cached picture.
- New route `GET /api/v1/channels/{uid}/people/{sender_id}/avatar`: the image,
  or 204 when there is none to show.
- The line under the name reads "Owner · paired <date>".

## Impact

- Backend: Telegram and SeaTalk adapters, a picture cache, the channel routes.
- Frontend: the people list, its hook, en/zh copy.
- Specs: channels (requirement and data model), the channels contract.
- Docs: the Channels guide (en/zh), the SeaTalk guide's permissions (en/zh).
