## MODIFIED Requirements

### Requirement: Attach files from the Chat page composer
The Chat page's composer MUST let the owner attach files three ways: an attach
button that opens the file picker, dropping files onto the composer, and
pasting an image. While files are dragged over it, only the reply box changes
— an accent border and the placeholder "Drop to attach" — with no overlay over
the page. Each attached file MUST show as a chip with its name, its size and a
control that removes it, and it MUST be uploaded at once, the chip saying so
while it uploads. A file over 20 MB, or one past the tenth, MUST NOT be
attached or uploaded: it is dropped, and one line under the reply box says
"<file> was not attached: <reason>. Up to 10 files, 20 MB each." — the limits
appear nowhere else. A file the daemon refuses on upload (an unsupported type)
MUST stay on its chip with the reason and is never sent. Send MUST be disabled
while any upload is in flight or failed, so a message never leaves without a
file its owner attached; a message with only attachments may be sent. Sending
clears the chips, and the files travel with the message by the ids their
uploads returned.

#### Scenario: attaching a file shows a chip and sends it with the message
- **GIVEN** an open conversation on the Chat page
- **WHEN** the owner attaches a file with the attach button and sends a message
- **THEN** a chip with the file's name and size appears, and the message is sent with that file's upload id
- **AND** the chips are cleared after the send

#### Scenario: send waits for uploads in flight
- **GIVEN** a file whose upload has not finished
- **WHEN** the owner looks at the composer
- **THEN** its chip says it is uploading and Send is disabled until the upload finishes

#### Scenario: a failed upload says why and is not sent
- **GIVEN** a file the daemon refuses
- **WHEN** its upload fails
- **THEN** its chip shows the reason and Send is disabled
- **AND** removing the chip enables Send again

#### Scenario: a file past the limits is not attached and the reply box says why
- **GIVEN** the composer of an open conversation
- **WHEN** the owner picks a file over 20 MB
- **THEN** nothing is uploaded and no chip appears
- **AND** one line under the reply box names the file, the reason and the limits

#### Scenario: a pasted image is attached
- **GIVEN** the composer has focus
- **WHEN** the owner pastes an image
- **THEN** it is attached and uploaded like a picked file
