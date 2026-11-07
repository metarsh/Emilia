+++
title = "Quotes"
+++

# Quotes

Generate quote stickers or images from replied messages and browse quotes.

## User commands

- `/q [count] [color] [p] [r]`: Reply to create quote sticker. Use `p` for PNG or `r` to include reply context.
- `/qtop`: Browse top-rated group quotes.
- `/qrand`: Send a random saved quote from this group.

## Admin commands

- `/qrate [on|off]`: Toggle rating buttons on quotes.

## Options

- `count`: 1–25 consecutive messages, default 1.
- `color`: CSS color name, `#rgb`, or `#rrggbb`.
- `p`: Send PNG document instead of sticker.
- `r`: Include replied message bubble.

## Example

Reply to a message:

```
/q 5 #ff0000 p
```
