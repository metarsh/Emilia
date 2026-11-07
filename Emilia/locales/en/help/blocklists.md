+++
title = "Blocklists"
children = ["blocklists-examples"]
+++

# Blocklists

Filter unwanted words, phrases, filenames, and custom emoji packs.

## Admin commands

- `/addblocklist <trigger> [reason]`: Add trigger; quote multiple words. Alias: `/addblacklist`.
- `/rmblocklist <trigger>`: Remove trigger. Aliases: `/rmblacklist`, `/unblocklist`, `/unblacklist`.
- `/blocklist`: List active triggers. Alias: `/blacklist`.
- `/blocklistmode [action] [duration]`: Set action to nothing, ban, mute, kick, warn, tban, tmute. Alias: `/blacklistmode`.
- `/blocklistdelete [on|off]`: Toggle deleting matching messages; enabled by default.
- `/setblocklistreason [reason]`: Set default action reason.
- `/resetblocklistreason`: Clear default reason.

## Owner commands

- `/unblocklistall`: Delete all triggers after confirmation. This cannot be undone. Alias: `/unblacklistall`.

## Usage notes

- Approved users and admins are exempt.
- Wildcards: `?` matches one non-space char; `*` matches multiple.
- Custom emoji: reply to emoji with `/addblocklist emojipack:<>`.
- Timed punishments require a duration like `2h`.

## Example

```
/addblocklist "buy now" Advertising
```
