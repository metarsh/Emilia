+++
title = "Filter examples"
hidden = true
+++

# Filter examples

Examples for creating text, media, and dice triggers.

## Text response

```
/filter hello Hello, {first}!
```

## Multi-word trigger

Wrap multiple words in quotes:

```
/filter "good morning" Good morning, {first}!
```

## Media filter

Reply to a photo, document, video, or sticker:

```
/filter cat
```

## Dice trigger

Match animated emoji results:

```
/filter dice:6 You rolled six!
```

## Remove filters

```
/stop hello
/stop "good morning"
```
