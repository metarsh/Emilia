+++
title = "Connections"
+++

# Connections

Want to update your group's notes, filters, or settings without filling the group with commands? Connect to it here, then send me those commands in private.

Both you and I must still be in the chat. Admins can connect by default. Other members can connect only if an admin enables `/allowconnection on`.

A connection selects the chat your private commands will affect. Check `/connection` before changing settings or moderating a member.

Replace `<...>` with required input; `[...]` is optional. Do not type those brackets.

**Commands:**

- `/connect [chat ID or @username]`: Connect to a group or channel from private chat. In the group or channel, get a button to connect to that chat.
- `/connection`: See your connected chat and the commands you can use there.
- `/disconnect`: Disconnect, even if you can no longer access the chat.
- `/reconnect`: Connect to your last chat again, if you still have access.

**Admin commands:**

- `/allowconnection [on|off]`: View or change whether ordinary members may connect. You can also change this from a connected private chat.

**Examples:**

- Connect using a chat ID:\
  `/connect -1001234567890`
- Connect using a public username:\
  `/connect @yourgroup`
- Check which commands are available:\
  `/connection`
- Ban a member in the connected group, if you have the required admin rights:\
  `/ban @username`
- Leave the connection:\
  `/disconnect`

**Tips:**

- Use `/id` in your chat to find its ID.
- Your usual permissions still apply, including any commands disabled in that chat.
- Basic-group IDs work too. Mutes, temporary bans, and CAPTCHA need a supergroup, Telegram's upgraded group type. Join requests need a supergroup or channel.
- Settings, notes, filters, requests, and moderation with a specified user work where listed by `/connection`. Group-only commands cannot be used on channels.
- Connected groups support `/resetwarn`, `/zombies`, and `/kickdead`. Connected supergroups also support `/slowmode`, `/setsticker`, `/unbanall`, and `/unmuteall`.
- Both groups and channels support `/disable`, `/enable`, `/disabled`, `/disabledel`, and `/disableable`.
- To delete or purge group messages, pin a message by reply, or manage topics, send the command in the original group.
