## ADDED Requirements

### Requirement: Show each paired person's platform picture
The people list on a channel's Overview SHALL show each paired person's picture
on the platform beside their name, and their initials when there is no picture
to show. The line under the name SHALL read "Owner · paired <date>". The picture
MUST be asked of the channel's running adapter on this machine when the page
first asks for it: Telegram's newest profile photo (`getUserProfilePhotos`), and
SeaTalk's employee profile picture (`/contacts/v2/profile`, which needs the app's
Get Employee Profile permission). It MUST be kept in a machine-local cache that
is never synced, served from there for a day, and asked for again after that. A
fetch that fails or is refused, and a person with no picture, MUST read as no
picture, show initials, and not be asked again for an hour; a refused refresh
leaves the cached picture in place. Only bytes that are a JPEG, PNG, GIF or WebP
image of at most 2 MB are served. Removing the person or deleting the channel
MUST drop their cached picture, and a person not paired to the channel has none.

#### Scenario: an owner row shows the person's platform picture or their initials
- **GIVEN** a channel with two paired people, one with a picture on the platform and one without
- **WHEN** the owner opens the channel's Overview
- **THEN** the first person's row shows their picture and the other's shows their initials
- **AND** the line under each name reads "Owner · paired <date>"

#### Scenario: a paired person's picture is fetched once and kept a day
- **GIVEN** a running channel and a paired person with a picture on the platform
- **WHEN** the page asks for the picture twice, and again a day later after the person changed it
- **THEN** the platform is asked once for the first two, and the day-old picture is replaced by the new one

#### Scenario: a person with no reachable picture keeps their initials
- **GIVEN** a SeaTalk app without the Get Employee Profile permission
- **WHEN** the page asks for a paired person's picture
- **THEN** there is no picture and the row keeps the person's initials
- **AND** the platform is not asked again for that person within the hour

#### Scenario: a paired person's picture is served from the running adapter
- **GIVEN** a running channel with two paired people, one with a picture
- **WHEN** a client reads `GET /api/v1/channels/{uid}/people/{sender_id}/avatar` for each, and for a sender who is not paired
- **THEN** the first answers 200 with the image, the others 204
- **AND** after the first person is removed their cached picture is gone
