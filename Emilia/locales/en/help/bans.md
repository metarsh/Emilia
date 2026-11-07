+++
title = "Bans and mutes"
+++

# Bans and mutes

Restrict or remove group members.

## Admin commands

- `/ban [user] [reason]`: Ban a user.
- `/dban [reason]`: Reply to a message to ban its sender and delete the message.
- `/sban [user] [reason]`: Ban a user silently.
- `/tban [user] <duration> [reason]`: Ban a user temporarily for a specified time.
- `/unban [user]`: Allow a banned user to rejoin.
- `/kick [user] [reason]`: Remove a user but user can rejoin.
- `/dkick [reason]`: Reply to a message to kick its sender and delete the message.
- `/skick [user] [reason]`: Kick a user silently.
- `/mute [user] [reason]`: Mute a user. Use `/dmute` by reply to delete their message, or `/smute` for muting silently. Aliases: `/dmute`, `/smute`.
- `/tmute [user] <duration> [reason]`: Mute a user temporarily. Alias: `/tempmute`.
- `/unmute [user]`: Restore a user's sending permissions (unmute user).
- `/dnd [on|off]`: Show or change whether new members without usernames are kicked. Bots and protected administrators are excluded.
- `/zombies [clean]`: Find deleted accounts; add clean to remove them.
- `/kickdead`: Kick members Telegram marks as last seen a long time ago; protected administrators are excluded. Telegram privacy settings can affect this status.
- `/unbanall`: Unban banned users and sender channels in a supergroup.
- `/unmuteall`: Restore a supergroup's default permissions for current muted members.

## Usage notes

These commands support connected private chats, except `/dban`, `/dkick` and `/dmute`, which need a reply in the original group. Supply moderation targets by username, mention or numeric ID in private.

Mutes, timed bans, `/unbanall` and `/unmuteall` require a supergroup. Sender-channel moderation also requires a supergroup; anonymous group admins and the group's linked discussion channel cannot be targeted.

Supply a username, mention, or numeric ID, or reply to the target. Use `4m`, `2h`, or `3d` for timed bans. Timed mutes also accept weeks, such as `1w`. Muted users cannot send messages or add reactions.

## Example

Reply to the user's message:

```
/tmute 2h Off-topic flooding
```
