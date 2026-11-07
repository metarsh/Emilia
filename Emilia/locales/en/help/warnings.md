+++
title = "Warnings"
+++

# Warnings

Track warnings and act when a member reaches the limit.

## User commands

- `/warns [user]`: Show your warnings. Only admins may supply another user.

## Admin commands

- `/warn [user] [reason]`: Warn a user. Use `/dwarn` by reply to delete their message, or `/swarn` for a silent warning. Aliases: `/swarn`, `/dwarn`.
- `/resetwarn [user]`: Clear a user's warnings; reply or supply a user. Aliases: `/rmwarns`, `/resetwarns`.
- `/warnlimit <number>`: Set the warning limit from 1 to 50; requires permission to change group info. Aliases: `/setwarnlimit`.
- `/warnmode <action> [duration]`: Set ban, kick, mute, tban, or tmute; timed actions require a duration. Aliases: `/setwarnmode`.
- `/warnings`: Show the group's warning settings.

## Owner commands

- `/resetallwarns`: Clear every member's warnings after confirmation. This cannot be undone.

## Usage notes

Warning commands, including `/resetwarn` and `/resetallwarns`, support connected private chats. `/dwarn` requires a reply in the original group. Warning actions that mute or temporarily ban require a supergroup.

Automated lock and blocklist warnings apply to named users and record the bot as the issuer. Sender channels and anonymous group identities cannot receive user warnings.

## Example

Reply to the member's message:

```
/warn Advertising
```
