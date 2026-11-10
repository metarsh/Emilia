+++
title = "Blocklists"
children = ["blocklists-examples"]
+++

# Blocklists

I can act on unwanted words, phrases, filenames, and custom emoji packs. Save what you want to block, then choose the action.

Admins and approved members are exempt.

Replace `<...>` with required input; `[...]` is optional. Do not type those brackets.

**Admin commands:**

- `/addblocklist <trigger> [reason]`: Add a trigger. Put phrases in quotes. A reason here takes priority over the default reason. Alias: `/addblacklist`.
- `/rmblocklist <trigger>`: Remove a trigger using its saved text, without quotes, even for a phrase. Aliases: `/rmblacklist`, `/unblocklist`, `/unblacklist`.
- `/blocklist`: List saved triggers. Alias: `/blacklist`.
- `/blocklistmode [action] [duration]`: View or choose `nothing`, `ban`, `mute`, `kick`, `warn`, `tban`, or `tmute`. Timed actions need a duration. Alias: `/blacklistmode`.
- `/blocklistdelete [on|off]`: View or change whether matching messages are deleted. Deletion is on by default.
- `/setblocklistreason [reason]`: View or change the default reason for an action.
- `/resetblocklistreason`: Clear the default reason.

**Owner commands:**

- `/unblocklistall`: Delete every trigger after confirmation. This cannot be undone. Alias: `/unblacklistall`.

`nothing` means no ban, mute, kick, or warning; matching messages are still deleted if `/blocklistdelete` is on. Use `/blocklistmode` to check the action before adding triggers.

**Examples:**

- Block an advertising phrase:\
  `/addblocklist "buy now" Advertising`
- Mute matching senders for 2 hours:\
  `/blocklistmode tmute 2h`

**Tips:**

- `?` matches one character other than a space; `*` matches any number of characters other than spaces.
- To block a custom emoji pack, reply to one of its emoji with `/addblocklist emojipack:<>`. Type `<>` literally; the reply supplies the pack.
- Use the examples guide below for more trigger patterns.
