## ADDED Requirements

### Requirement: Open a parallel thread as a private-chat topic
On Telegram `/thread` MUST open a parallel thread as a private-chat topic
created with `createForumTopic`, named with the thread's mark, and post the
mark into it. Messages in that topic drive the parallel conversation. A private
chat's topics only exist when someone created them, so every private-chat topic
is its own conversation. When the bot's private-chat topics are off, `/thread`
answers that the bot's Threaded Mode must be turned on in BotFather, and opens
nothing.

#### Scenario: /thread creates a named private-chat topic
- **GIVEN** a paired Telegram private chat with topics enabled for the bot
- **WHEN** the owner sends `/thread deploy check`
- **THEN** a topic named `🧵#1 deploy check` is created in the private chat
- **AND** messages in that topic run in their own conversation

#### Scenario: /thread explains how to enable topics when they are off
- **GIVEN** a paired Telegram private chat where the bot's topics are off
- **WHEN** the owner sends `/thread`
- **THEN** the bot answers that Threaded Mode must be turned on in BotFather and creates nothing
