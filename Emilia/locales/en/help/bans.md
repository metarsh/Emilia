+++
title = "Bans"
+++

# Bans and mutes

I can remove disruptive members or stop them sending messages. A kicked member can rejoin; a banned member must be unbanned first.

Reply to the member you want to moderate, or give their username, mention, or numeric ID. Reasons are optional. I need Ban users rights; deleting a message also needs Delete messages.

Replace `<...>` with required input; `[...]` is optional. Do not type those brackets.

**Admin commands:**

- `/ban [user] [reason]`: Ban a member from the group.
- `/dban [reason]`: Reply to a message to ban its sender and delete that message.
- `/sban [user] [reason]`: Ban a member without sending a confirmation message.
- `/tban [user] <duration> [reason]`: Ban a member for a set time.
- `/unban [user]`: Allow a banned member to rejoin.
- `/kick [user] [reason]`: Remove a member while allowing them to rejoin.
- `/dkick [reason]`: Reply to a message to kick its sender and delete that message.
- `/skick [user] [reason]`: Kick a member without sending a confirmation message.
- `/mute [user] [reason]`: Stop a member sending messages or adding reactions. Use `/dmute` by reply to also delete their message. `/smute` removes your command and sends no confirmation.
- `/tmute [user] <duration> [reason]`: Mute a member for a set time. Alias: `/tempmute`.
- `/unmute [user]`: Restore a muted member's sending permissions.
- `/dnd [on|off]`: View or change whether new members without usernames are kicked. Bots and protected admins are excluded.
- `/zombies [clean]`: Find deleted accounts. Add `clean` to remove them.
- `/kickdead`: Kick members shown as "last seen a long time ago". Protected admins are excluded; privacy settings can affect this status.
- `/unbanall`: Unban all banned users and sender channels in a supergroup.
- `/unmuteall`: Reset muted members to the supergroup's default permissions.

**Tips:**

- Timed bans accept times such as `4m`, `2h`, or `3d`. Timed mutes also accept weeks, such as `1w`.
- Mutes, timed bans, `/unbanall`, and `/unmuteall` need a supergroup, Telegram's upgraded group type.
- You can moderate channel senders in a supergroup, but cannot target anonymous group admins or the group's linked discussion channel.
- These commands work in connected private chats except `/dban`, `/dkick`, and `/dmute`, which need a reply in the group. In private, specify the user.

**Examples:**

- Reply to a member's message to mute them for 2 hours:\
  `/tmute 2h Off-topic flooding`
- Unban a member:\
  `/unban @username`
