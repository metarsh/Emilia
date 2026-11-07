+++
title = "Blocklist examples"
hidden = true
+++

# Blocklist examples

Choose triggers that match the content you want to block.

## Words and phrases

```
/addblocklist <spam> <reason>
/addblocklist "buy now" Advertising
/rmblocklist buy now
```

## Patterns

```
/addblocklist *.exe Executable files
/addblocklist https://short.example/* Shortened links
```

## Custom emoji

Reply to a message containing the custom emoji:

```
/addblocklist emojipack:<>
```

## Timed action

```
/blocklistmode tmute 2h
```
