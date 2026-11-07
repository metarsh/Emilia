+++
title = "Connections"
+++

# Connections

Manage a group or channel directly from private chat.

## Commands

- `/connect [chat ID or @username]`: Connect in PM, or generate connect button in a group or channel.
- `/connection`: Show active connected chat and supported commands.
- `/disconnect`: Disconnect from current chat.
- `/reconnect`: Reconnect to previously connected chat.
- `/allowconnection [on|off]`: Toggle allowing non-admin member connections.

## Usage notes

- Both you and the bot must be members of the target chat.
- Connected commands enforce normal permissions and disabled command policies.
- Supports notes, filters, settings, warnings, and explicit user moderation.
- Supergroups support: `/slowmode`, `/setsticker`, `/unbanall`, `/unmuteall`, `/zombies`, `/kickdead`.
- Actions requiring a direct message reply (purges, deleting replied messages, topic management) require the group itself.

## Example

```
/connect -1001234567890
/connection
/ban @username
/disconnect
```
