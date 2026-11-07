+++
title = "Warnings"
+++

# Warnings

Track member warnings and enforce limits.

## User commands

- `/warns [user]`: View warning count. Only admins can view others.

## Admin commands

- `/warn [user] [reason]`: Warn a user. Aliases: `/dwarn` to delete replied message, `/swarn` for silent.
- `/resetwarn [user]`: Clear a user's warnings. Aliases: `/rmwarns`, `/resetwarns`.
- `/warnlimit <number>`: Set warning limit 1 to 50. Requires change info rights. Alias: `/setwarnlimit`.
- `/warnmode <action> [duration]`: Set action to ban, kick, mute, tban, tmute. Timed actions require duration. Alias: `/setwarnmode`.
- `/warnings`: View warning settings.

## Owner commands

- `/resetallwarns`: Clear all chat warnings after confirmation. This cannot be undone.

## Usage notes

- Works in connected PM except `/dwarn` which requires a group reply.
- Mute and timed ban actions require a supergroup.
- Channels and anon admins cannot receive warnings.

## Example

Reply to a message:

```
/warn Advertising
```
