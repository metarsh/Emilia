+++
title = "Federation ownership"
hidden = true
+++

# Federation ownership

Create a federation to share bans across your groups. I can help you manage its admins, subscriptions, logs, and ban backups.

Replace `<...>` with required input; `[...]` is optional. Do not type those brackets.

**Owner commands in private:**

- `/newfed <name>`: Create your federation. You can own one, with a name up to 64 characters.
- `/renamefed <name>`: Rename it using up to 64 characters.
- `/delfed`: Delete it after confirmation. This cannot be undone.
- `/fednotif [on|off]`: View or change private ban notifications.
- `/fedreason [on|off]`: View or change whether bans require a reason.

**Owner commands in a group:**

- `/fpromote [user]`: Invite a user to become a federation admin. They must accept.
- `/fdemote [user]`: Remove a federation admin.
- `/ftransfer [user]`: Transfer ownership to an existing federation admin after they accept. Alias: `/fedtransfer`.
- `/setfedlog [federation_id]`: Use the selected group or channel for federation logs. Also works through a connected private chat.
- `/unsetfedlog`: Remove the log destination from a group, channel, or connected private chat.

For log commands, use your own federation-owner account with permission to change that chat's settings. I need posting rights if the destination is a channel.

**Subscriptions and backups:**

- `/subfed <federation_id>`: Subscribe your federation to another federation's bans.
- `/unsubfed <federation_id>`: Stop receiving another federation's bans.
- `/fedsubs`: List subscriptions.
- `/fexport [csv|json|xml]`: Export bans. The default format is CSV. Alias: `/fedexport`.
- `/fimport`: Reply to a CSV, JSON, or XML ban export to import it. Alias: `/fedimport`.

**Examples:**

- Create a federation in private:\
  `/newfed Emilia community`
- Export its bans:\
  `/fexport json`
