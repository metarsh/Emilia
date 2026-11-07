+++
title = "Federation ownership"
hidden = true
+++

# Federation ownership

Create, configure, and manage your federation.

## Private commands

- `/newfed <name>`: Create a federation; limit 1 per user, up to 64 chars.
- `/renamefed <name>`: Rename your federation.
- `/delfed`: Delete your federation permanently after confirmation.
- `/fednotif [on|off]`: Toggle private ban notifications.
- `/fedreason [on|off]`: Require reasons for federation bans.

## Group commands

- `/fpromote [user]`: Invite a user as fed admin; requires acceptance.
- `/fdemote [user]`: Demote a federation admin.
- `/ftransfer [user]`: Transfer federation ownership to a fed admin. Alias: `/fedtransfer`.
- `/setfedlog [federation_id]`: Set group or channel as federation log destination.
- `/unsetfedlog`: Remove federation log channel.

## Subscriptions and backups

- `/subfed <federation_id>`: Subscribe to another federation's bans.
- `/unsubfed <federation_id>`: Unsubscribe from a federation.
- `/fedsubs`: List subscribed federations.
- `/fexport [csv|json|xml]`: Export federation bans; default CSV. Alias: `/fedexport`.
- `/fimport`: Reply to an exported ban file to import bans. Alias: `/fedimport`.

## Usage notes

- Setting log channels requires owner status and posting rights in channels.

## Example

```
/newfed Emilia community
```
