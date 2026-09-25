## 1. Resend

- [x] 1.1 `ChatService.get_user_message`, `ChatAttachmentService.reattach`, `ChatMediaStore.present`
- [x] 1.2 Resend route, `ATTACHMENT_EXPIRED` / `MESSAGE_NOT_FOUND`, contract + codegen
- [x] 1.3 Web Retry through the resend route; no Retry on a refused send

## 2. Draft first message

- [x] 2.1 A refused first message restores text and chips into the new conversation's composer and shows the error

## 3. Tests and docs

- [x] 3.1 Backend unit + integration, vitest, acceptance markers
- [x] 3.2 Chat guide, architecture page, error-code and REST references
