+++
title = "Lock examples"
hidden = true
+++

# Lock examples

Use lock names exactly as `/locktypes` lists them.

## Media

```
/lock photo video gif
/unlock photo video
```

## Links and exceptions

```
/lock url invitelink
/allowlist example.com
/rmallowlist example.com
```

## Custom emoji

Reply to a custom emoji message when adding its packs:

```
/lock emojicustom
/allowlist emojipack:<>
```

## Reactions

```
/lock reaction outsidereaction
```
