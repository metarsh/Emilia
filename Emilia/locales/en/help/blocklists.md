+++
title = "Blocklists"
children = ["blocklists-examples"]
+++

# Blocklists

Match unwanted words, phrases, filenames, and custom emoji packs.

## Admin commands

- `/addblocklist <trigger> [reason]`: Add a trigger; for more than 1 word use quotes (""). Alias: `/addblacklist`.
- `/rmblocklist <trigger>`: Remove a trigger. Aliases: `/rmblacklist`, `/unblocklist`, `/unblacklist`.
- `/blocklist`: List saved triggers. Alias: `/blacklist`.
- `/blocklistmode [action] [duration]`: Show or set nothing, ban, mute, kick, warn, tban, or tmute. Alias: `/blacklistmode`.
- `/blocklistdelete [on|off]`: Show or change message deletion; enabled by default.
- `/setblocklistreason [reason]`: Show or set the default action reason.
- `/resetblocklistreason`: Clear the default reason.

## Owner commands

- `/unblocklistall`: Delete every trigger after confirmation. This cannot be undone. Alias: `/unblacklistall`.

## Usage notes

Timed modes require a duration, such as `2h`. Blocklists won't work on approved users and admins.

Use `?` for one nonspace character and `*` for any number of nonspace characters. To block a custom emoji pack, reply to a message containing its emoji with `/addblocklist emojipack:<>`.

## Example

```
/addblocklist "buy now" Advertising
```
