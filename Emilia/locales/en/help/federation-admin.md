+++
title = "Federation moderation"
hidden = true
+++

# Federation moderation

Manage federation bans across federated chats.

## Federation admin commands

- `/fban [user] [reason]`: Ban a user across the federation. Reason required if enabled by owner.
- `/unfban [user] [reason]`: Remove a federation ban.
- `/feddemoteme <federation_id>`: Resign from your federation admin role. Alias: `/fdemoteme`.

## Usage notes

- Target by reply, username, mention, or ID.
- In groups, actions apply to the linked federation; in private, commands require the fed owner.
- Federation bans propagate to subscribed federations. Owners and fed admins cannot be banned from their own federation.

## Example

```
/fban @username Spam
```
