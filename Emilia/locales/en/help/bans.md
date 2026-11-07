+++
title = "Bans and mutes"
+++

# Bans and mutes

Restrict or remove group members.

## Admin commands

- `/ban [user] [reason]`: Ban a user.
- `/dban [reason]`: Ban sender and delete replied message.
- `/sban [user] [reason]`: Ban silently without alert.
- `/tban [user] <duration> [reason]`: Ban temporarily, like `4m`, `2h`, or `3d`.
- `/unban [user]`: Unban a user.
- `/kick [user] [reason]`: Kick a user; they can rejoin.
- `/dkick [reason]`: Kick sender and delete replied message.
- `/skick [user] [reason]`: Kick silently without alert.
- `/mute [user] [reason]`: Mute a user. Aliases: `/dmute` to delete reply, `/smute` for silent.
- `/tmute [user] <duration> [reason]`: Mute temporarily with minutes, hours, days, or weeks. Alias: `/tempmute`.
- `/unmute [user]`: Restore sending rights.
- `/dnd [on|off]`: Kick new members lacking a username.
- `/zombies [clean]`: Find deleted accounts; add clean to remove them.
- `/kickdead`: Kick long-time inactive members. Telegram privacy may affect this.
- `/unbanall`: Unban all banned users and sender channels in a supergroup.
- `/unmuteall`: Unmute all muted members in a supergroup.

## Usage notes

- Target by reply, username, mention, or ID.
- Works in connected PM except `/dban`, `/dkick`, `/dmute` which require a group reply.
- Mutes, timed bans, `/unbanall`, `/unmuteall`, and channel moderation require a supergroup.
- Protected admins, anon admins, and linked channels cannot be targeted. Muted members cannot send messages or reactions.

## Example

```
/tmute 2h Off-topic flooding
```
