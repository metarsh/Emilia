+++
title = "Locks"
children = ["lock-types", "locks-examples"]
+++

# Locks

I can delete certain kinds of content or restrict what members may send. Lock photos, links, stickers, or other content using the names in the guides below.

Message-content locks exempt admins and approved members.

I need Delete messages and Ban users rights. You need Change group info rights to change locks.

The `all` lock closes the group to member messages. Locks such as `photo`, `text`, and `url` delete matching messages. The `bot` lock kicks newly added bots; reaction locks remove the affected reactions.

Replace `<...>` with required input; `[...]` is optional. Do not type those brackets.

**User commands:**

- `/locktypes`: List the lock names you can use.

**Admin commands:**

- `/lock <type> [type ...]`: Turn on one or more locks.
- `/unlock <type> [type ...]`: Turn off one or more locks.
- `/locks`: View the group's active locks.
- `/lockwarns [on|off]`: View or change whether breaking a lock adds a warning.
- `/allowlist [item ...]`: View or add trusted URLs, bots, or custom emoji packs.
- `/rmallowlist <item> [item ...]`: Remove items from the allowlist.
- `/rmallowlistall`: Clear the entire allowlist after confirmation. This cannot be undone.

**Examples:**

- Lock photos and videos:\
  `/lock photo video`
- Allow photos again:\
  `/unlock photo`

**Tips:**

- Use `/locktypes` to check a name before locking it.
- To allow custom emoji packs, reply to an emoji message with `/allowlist emojipack:<>`. Keep `<>` as written; the reply supplies the pack.
- Open the guides below for all lock types and more examples.
