+++
title = "Logging"
+++

# Logging

I can record bot actions in a channel so you can review them later.

Both I and the admin choosing the channel need permission to post there.

Replace `<...>` with required input; `[...]` is optional. Do not type those brackets.

**Commands:**

- `/logchannel`: View the current log channel.
- `/unsetlog`: Stop sending logs to that channel.
- `/setlog [channel ID or @username]`: Set the log channel as group owner. Use this in the group or a connected private chat.

**Example:**

- Add me to your log channel as an admin. Then, as group owner, send:\
  `/setlog @my_log_channel`
- Check the destination:\
  `/logchannel`

You can also set the destination by replying to a forwarded channel post. Its channel name must remain visible.
