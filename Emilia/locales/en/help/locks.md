+++
title = "Locks"
children = ["lock-types", "locks-examples"]
+++

# Locks

Restrict messages and delete specific content types in the group.

## User commands

- `/locktypes`: List all supported lock types.

## Admin commands

- `/lock <type ...>`: Lock one or more content types.
- `/unlock <type ...>`: Unlock specified content types.
- `/locks`: View active group locks.
- `/lockwarns [on|off]`: Toggle warning users on lock violations.
- `/allowlist [item ...]`: View or whitelist trusted URLs, bots, or emoji packs.
- `/rmallowlist <item ...>`: Remove items from allowlist.
- `/rmallowlistall`: Clear the entire allowlist after confirmation. This cannot be undone.

## Usage notes

- Admins and approved members are exempt from locks.
- Allow custom emoji packs by replying to an emoji message with `/allowlist emojipack:<>`.

## Example

```
/lock photo video
```
