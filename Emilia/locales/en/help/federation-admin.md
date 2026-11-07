+++
title = "Federation moderation"
hidden = true
+++

# Federation moderation

Federation admins and owners manage federation bans. In a group, commands act on its federation; in private, ban commands require the federation owner and act on their federation.

## Federation admin commands

- `/fban [user] [reason]`: Ban a user across the federation. A reason is required when the owner enables that setting.
- `/unfban [user] [reason]`: Remove a federation ban.
- `/feddemoteme <federation_id>`: Remove your own federation admin role. Alias: `/fdemoteme`.

## Usage notes

Reply to a user or supply their username, mention, or ID. Federation bans can also propagate to subscribed federations. Owners and federation admins cannot be banned from their own federation.

## Example

```
/fban @username Spam
```
