+++
title = "Admin"
children = ["bans", "purges", "misc"]
+++

# Admin

I can manage your group's admins and settings. New here? Open `/help bot` for adding me to a group and choosing my admin rights.

To choose a user below, reply to their message or give their username, mention, or numeric ID. The title is optional for promotions.

Replace `<...>` with required input; `[...]` is optional. Do not type those brackets.

**User commands:**

- `/admins`: List the group's admins. Alias: `/adminlist`.
- `/admincache`: Refresh my list of admins if your admin commands are not working.

**Admin commands:**

- `/promote [user] [title]`: Give someone rights to invite users, change group info, delete messages, and pin messages.
- `/fullpromote [user] [title]`: Give the same rights plus permission to ban users, add admins, and manage voice chats.
- `/demote [user]`: Remove someone's admin rights.
- `/title [user] <title>`: Change an admin's custom title.
- `/forcecachechat`: Refresh saved group details if I am using outdated information about the group.
- `/setgpic`: Reply to a photo or image document to make it the group picture.
- `/setgtitle <title>`: Change the group name.
- `/setdesc <description>`: Change the group description.
- `/setsticker`: Reply to a sticker to use its pack as the supergroup's sticker pack.
- `/slowmode [seconds]`: View or change how long members must wait between messages.
- `/anonadmin [on|off]`: Let anonymous admins use ordinary admin commands without verifying their account.

**Tips:**

- Only the group owner can demote an admin who has permission to promote others.
- Slow mode accepts `0`, `5`, `10`, `30`, `60`, `300`, `900`, or `3600` seconds. Use `0` to turn it off.
- When anonymous verification is required, tap the button with an account that has the needed group rights. Owner-only commands and commands tied to a named account still need verification. Posting as a channel does not give you admin rights.

You can manage admins and use `/admins`, `/admincache`, `/setgpic`, `/setgtitle`, `/setdesc`, `/setsticker`, `/slowmode`, and `/anonadmin` from a connected private chat. Reply to the photo or sticker there. Deleting or purging group messages needs a reply in the group.

**Examples:**

- Give a member limited admin rights:\
  `/promote @username`
- Set a 10-second wait between messages:\
  `/slowmode 10`
