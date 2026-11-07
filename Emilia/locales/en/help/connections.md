+++
title = "Connections"
+++

# Connections

Manage a group or channel from a private chat with the bot. Both you and the bot must be current members. Administrators may connect; ordinary members need `/allowconnection on`.

## Commands

- `/connect [chat ID or @username]`: Connect in PM, or get a connection button in a group or channel. Basic-group IDs are supported. Mutes, temporary bans and CAPTCHA require a supergroup; join requests require a supergroup or channel.
- `/connection`: Show the selected chat and the commands registered for its scope.
- `/disconnect`: Clear the active connection, including one you can no longer access.
- `/reconnect`: Recheck access and reconnect to your last chat.
- `/allowconnection [on|off]`: Administrators can allow or disallow member connections in a group or channel, including from a connected private chat.

Connected commands retain their normal permissions and disabled-command policy. Group-only commands cannot act on a channel. Settings, notes, filters, requests and explicit-user moderation support connections where listed by `/connection`.

Connected groups also support `/resetwarn`, `/zombies` and `/kickdead`. Connected supergroups support `/slowmode`, `/setsticker`, `/unbanall` and `/unmuteall`. Groups and channels support `/disable`, `/enable`, `/disabled`, `/disabledel` and `/disableable`.

Commands that delete a replied-to group message, purge messages, pin a replied-to message or manage forum topics require their original group context.

## Example

```
/connect -1001234567890
/connection
/ban @username
/disconnect
```
