+++
title = "Federation ownership"
hidden = true
+++

# Federation ownership

Create and manage your federation.

## Private chat commands

- `/newfed <name>`: Create a federation; one per user, with a name up to 64 characters.
- `/renamefed <name>`: Rename your federation; maximum 64 characters.
- `/delfed`: Delete your federation after confirmation. This cannot be undone.
- `/fednotif [on|off]`: Show or change private ban notifications.
- `/fedreason [on|off]`: Show or change whether federation bans require reasons.

## Group commands

- `/fpromote [user]`: Invite a user to become a federation admin; they must accept.
- `/fdemote [user]`: Remove a federation admin.
- `/ftransfer [user]`: Transfer ownership to an existing federation admin after acceptance. Alias: `/fedtransfer`.
- `/setfedlog [federation_id]`: Set this group or channel as your federation's log destination; also supports a connected private chat.
- `/unsetfedlog`: Remove your federation's log destination from a group, channel or connected private chat.

Log commands require your named federation-owner account and permission to change the selected chat's settings. The bot needs posting rights when the destination is a channel.

## Subscriptions and backups

- `/subfed <federation_id>`: Subscribe your federation to another federation's bans.
- `/unsubfed <federation_id>`: Stop receiving another federation's bans.
- `/fedsubs`: List federation subscriptions.
- `/fexport [csv|json|xml]`: Export bans; defaults to CSV. Alias: `/fedexport`.
- `/fimport`: Reply to a CSV, JSON, or XML ban export to import it. Alias: `/fedimport`.

## Example

Create a federation in private chat:

```
/newfed Emilia community
```
