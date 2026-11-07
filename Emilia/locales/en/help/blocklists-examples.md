+++
title = "Blocklist examples"
hidden = true
+++

# Blocklist examples

Common blocklist triggers and examples.

## Words and phrases

```
/addblocklist "buy now" Advertising
/rmblocklist buy now
```

## Wildcards

```
/addblocklist *.exe Executable files
/addblocklist https://short.example/* Short links
```

## Custom emoji packs

Reply to a message with the custom emoji:

```
/addblocklist emojipack:<>
```

## Timed punishments

```
/blocklistmode tmute 2h
```
