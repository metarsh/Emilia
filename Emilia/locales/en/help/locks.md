+++
title = "Locks"
children = ["lock-types", "locks-examples"]
+++

# Locks

Delete selected kinds of content or restrict what members may send.

## User commands

- `/locktypes`: List supported lock names.

## Admin commands

- `/lock <type> [type ...]`: Enable one or more locks.
- `/unlock <type> [type ...]`: Disable one or more locks.
- `/locks`: Show the group's active locks.
- `/lockwarns [on|off]`: Show or change whether lock violations add warnings.
- `/allowlist [item ...]`: Show or add trusted URLs, bots, or emoji packs.
- `/rmallowlist <item> [item ...]`: Remove saved allowlist entries.
- `/rmallowlistall`: Clear the whole allowlist after confirmation. This cannot be undone.

## Usage notes

Admins and approved members are not affected by locks. Reply to a custom emoji message with `/allowlist emojipack:<>` to allow its packs. Use `/locktypes` to check names before locking content.

## Example

```
/lock photo video
```
