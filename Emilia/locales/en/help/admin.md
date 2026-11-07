+++
title = "Admin"
children = ["bans", "purges", "misc"]
+++

# Admin

Manage administrators and group settings.

## User commands

- `/admins`: List the group admins. Alias: `/adminlist`.
- `/admincache`: Refresh the group admin cache. Use when you think admin commands are not working properly.

## Admin commands

- `/promote [user] [title]`: Promote a user with limited admin rights.
- `/fullpromote [user] [title]`: Promote a user with all available admin rights.
- `/demote [user]`: Remove user from admin.
- `/title [user] <title>`: Set an admin's custom title.
- `/forcecachechat`: Refresh the stored group information.
- `/setgpic`: Reply to a photo or image document to set the group picture.
- `/setgtitle <title>`: Set the group title.
- `/setdesc <description>`: Set the group description.
- `/setsticker`: Reply to a sticker from a pack to set a supergroup's sticker pack.
- `/slowmode [seconds]`: Show or change a supergroup's slow mode.
- `/anonadmin [on|off]`: Allow anonymous group admins to perform ordinary admin actions without verification. Owner and named-account actions still require verification.

## Usage notes

For user commands above, reply to the target or supply a username, mention, or numeric ID. Demoting an admin who can promote others requires the group owner.

Administrator management, `/admins`, `/admincache`, `/setgpic`, `/setgtitle`, `/setdesc`, `/setsticker`, `/slowmode` and `/anonadmin` support connected private chats. For `/setgpic` and `/setsticker`, reply to the photo or sticker in your private chat. Group message deletion and purge require a reply in the original group.

Slow mode accepts `0`, `5`, `10`, `30`, `60`, `300`, `900`, or `3600` seconds; `0` disables it.

When anonymous bypass is off, tap the verification button using an account with the required group rights. A channel posting into the group gains no group-admin rights.
