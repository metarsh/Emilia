+++
title = "Filter examples"
hidden = true
+++

# Filter examples

Use inline text for a short reply, or save a message by replying to it.

## Text

```
/filter hello Hello, {first}!
```

## Multiword trigger

Reply to the message you want to save:

```
/filter "good morning"
```

You can also save inline text:

```
/filter "good morning" Good morning, {first}!
```

## Media

Reply to a photo or sticker:

```
/filter cat
```

## Dice

```
/filter dice:6 You rolled six!
```

## Remove a filter

```
/stop hello
/stop "good morning"
```
