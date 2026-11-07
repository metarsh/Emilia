+++
title = "Logging"
+++

# Logging

Record bot actions in a channel. The bot and the administrator choosing the destination must have permission to post there.

## Commands

- `/logchannel`: Show the current destination.
- `/unsetlog`: Remove the destination.
- `/setlog [channel ID or @username]`: The group owner sets the destination in the group or a connected PM. You may also reply to a forwarded channel post; keep its channel attribution visible.

## Example

Add the bot to your log channel as an administrator, then send this in the group or a connected PM as group owner:

```
/setlog @my_log_channel
/logchannel
```
