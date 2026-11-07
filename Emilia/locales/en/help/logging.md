+++
title = "Logging"
+++

# Logging

Record moderation and bot actions in a designated channel.

## Commands

- `/logchannel`: Show current log channel.
- `/unsetlog`: Unlink and disable log channel.
- `/setlog [channel ID or @username]`: Set log destination. Group owner only, run in group or connected PM, or reply to a forwarded channel post.

## Usage notes

- Both you and the bot must have admin posting rights in the destination channel.

## Example

```
/setlog @my_log_channel
/logchannel
```
