+++
title = "Lock types"
hidden = true
+++

# Lock types

Use these names with `/lock` and `/unlock` to choose what to restrict. Message-content locks exempt admins and approved members.

**Messages and formatting:**

- `all`: Close the group to member messages by changing its sending permissions.
- `text`: Text messages and media captions.
- `command`: Messages starting with a Telegram command, such as `/start`.
- `button`: Messages containing buttons.
- `spoiler`: Messages with spoiler formatting.
- `format`: Styled text such as bold, italic, underline, strikethrough, or blockquotes.
- `code`: Monospace or code formatting.
- `rtl`: Right-to-left characters, such as Arabic, Farsi, or Hebrew.

**Media:**

- `album`: Albums of photos or documents.
- `audio`: Audio files, such as music tracks.
- `document`: Files, including uncompressed photos and videos.
- `photo`: Photos.
- `video`: Videos.
- `videonote`: Round video messages.
- `voice`: Recorded voice notes.
- `gif`: GIFs.
- `sticker`: All sticker types.
- `contact`: Shared contacts.
- `location`: Shared locations.
- `poll`: Polls.
- `emojigame`: Telegram mini games such as dice, bowling, or darts.
- `game`: Games sent by bots.
- `emojicustom`: Custom emoji. Use `/allowlist` to allow trusted packs.

**Links and contact details:**

- `url`: Website links recognised by Telegram.
- `invitelink`: Private group or channel invite links, including `t.me/+...` and `t.me/joinchat/...`.
- `email`: Email addresses recognised by Telegram.
- `phone`: Phone numbers recognised by Telegram.

**Bots, forwards, and visitors:**

- `bot`: Kick newly added bots, unless an admin added them.
- `inline`: Messages sent through inline bots such as @gif or @pic.
- `guestbot`: Messages sent through Telegram guest bots. Allowlist trusted guest bots if needed.
- `forward`: All forwarded messages.
- `forwardbot`: Messages originally sent by a bot.
- `forwardchannel`: Messages originally sent by a channel.
- `forwarduser`: Messages originally sent by a user.
- `comment`: Comments from linked-channel users who are not group members.

**Reactions:**

- `reaction`: Reactions added by members who are neither admins nor approved.
- `outsidereaction`: Reactions from people who are not group members.

**Example:**

- Lock website links:\
  `/lock url`
