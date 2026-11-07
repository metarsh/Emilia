+++
title = "Admin"
children = ["bans", "purges", "misc"]
+++

# Admin

Manage administrators and group settings.

## User commands

- `/admins`: List group admins. Alias: `/adminlist`.
- `/admincache`: Refresh admin cache.

## Admin commands

- `/promote [user] [title]`: Promote with limited rights.
- `/fullpromote [user] [title]`: Promote with full rights.
- `/demote [user]`: Demote an admin.
- `/title [user] <title>`: Set custom admin title.
- `/forcecachechat`: Refresh cached group info.
- `/setgpic`: Set group photo by reply.
- `/setgtitle <title>`: Set group title.
- `/setdesc <description>`: Set group description.
- `/setsticker`: Set group sticker pack by reply.
- `/slowmode [seconds]`: View or set slow mode.
- `/anonadmin [on|off]`: Toggle anonymous admin verification. Owner actions always require verification.

## Usage notes

- Target users by reply, username, mention, or ID.
- Only the group owner can demote admins who can promote others.
- Connected PM supports admin commands, `/admins`, `/admincache`, `/setgpic`, `/setgtitle`, `/setdesc`, `/setsticker`, `/slowmode`, and `/anonadmin`.
- `/setgpic` and `/setsticker` work via PM reply. Purges and deleting replied messages require the group chat.
- Slow mode values: `0` to disable, or `5`, `10`, `30`, `60`, `300`, `900`, `3600` seconds.
- Without anon bypass, verify with an account holding required rights. Linked channels gain no admin rights.
