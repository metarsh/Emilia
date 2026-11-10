+++
title = "Warnings"
+++

# Warnings

I can keep track of warnings and take action when a member reaches your limit.

The starting limit is 3 warnings and the action is a ban. After applying the action, I clear that member's warning count. Use `/warnings` to check your group's current settings first.

To warn someone, reply to their message or give their username, mention, or numeric ID. Reasons are optional.

Replace `<...>` with required input; `[...]` is optional. Do not type those brackets.

**User commands:**

- `/warns [user]`: View your warnings. Only admins can check another member.

**Admin commands:**

- `/warn [user] [reason]`: Warn a member. Use `/dwarn` by reply to also delete their message. `/swarn` removes your command and sends no confirmation.
- `/resetwarn [user]`: Clear a member's warnings. Reply to them or specify the user. Aliases: `/rmwarns`, `/resetwarns`.
- `/warnlimit <number>`: Set the limit from 1 to 50. You need permission to change group info. Alias: `/setwarnlimit`.
- `/warnmode <action> [duration]`: Choose `ban`, `kick`, `mute`, `tban`, or `tmute`. Timed actions need a duration, such as `2h` for 2 hours. Alias: `/setwarnmode`.
- `/warnings`: View the group's warning settings.

**Owner commands:**

- `/resetallwarns`: Clear everyone's warnings after confirmation. This cannot be undone.

**Examples:**

- Warn a member by replying to their message:\
  `/warn Advertising`
- Set a limit of 3 warnings:\
  `/warnlimit 3`

**Tips:**

- Warning commands, including `/resetwarn` and `/resetallwarns`, work in connected private chats. `/dwarn` needs a reply in the group.
- Actions that mute or temporarily ban need a supergroup.
- Automatic warnings from locks and blocklists apply to users posting from their own accounts. Channel senders and anonymous group identities cannot receive user warnings.
