+++
title = "Federation moderation"
hidden = true
+++

# Federation moderation

I can ban a user across a federation, saving you from banning them in each group separately.

Federation admins and owners can manage bans in a group belonging to that federation. In private chat, only the federation owner can use ban commands, and they apply to their own federation.

Reply to the member you want to moderate, or give their username, mention, or numeric ID.

Replace `<...>` with required input; `[...]` is optional. Do not type those brackets.

**Federation admin commands:**

- `/fban [user] [reason]`: Ban a user across the federation. Include a reason if the owner requires one.
- `/unfban [user] [reason]`: Remove a federation ban.
- `/feddemoteme <federation_id>`: Give up your federation admin role. Alias: `/fdemoteme`.

**Tips:**

- Bans can also apply to federations subscribed to yours.
- A federation's owner and admins cannot be banned from their own federation.

**Examples:**

- Ban a user across the federation:\
  `/fban @username Spam`
- Remove their federation ban:\
  `/unfban @username`
