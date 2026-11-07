+++
title = "Quotes"
+++

# Quotes

Turn replied messages into a quote sticker or image, then browse saved group quotes.

## User commands

- `/q [count] [color] [p] [r]`: Reply to the first message to quote. Use p for a PNG document or r to include its reply.
- `/qtop`: Open an inline browser of saved quotes by rating; group members can select a quote to send.
- `/qrand`: Send a random saved quote from the current group.

## Admin commands

- `/qrate [on|off]`: Show or change rating buttons.

## Options

| Option | Value |
| --- | --- |
| `count` | 1–25 consecutive messages; defaults to 1. `/q 5` requests 5. |
| `color` | A CSS color name, `#rgb`, or `#rrggbb`. |
| `p` | Send a PNG document. |
| `r` | Include the quoted message's reply in a small bubble when quoting one message. |

## Example

Reply to the first message to quote:

```
/q 5 #ff0000 p
```
