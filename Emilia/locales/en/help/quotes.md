+++
title = "Quotes"
+++

# Quotes

I can turn members' messages into quote stickers or images, and show saved group quotes. This guide uses `/q`; the Anime guide's `/quote` sends a random anime quotation.

Replace `<...>` with required input; `[...]` is optional. Do not type those brackets.

**User commands:**

- `/q [count] [color] [p] [r]`: Reply to the first message you want to quote.
- `/qtop`: Browse saved quotes by rating. Group members can choose one to send.
- `/qrand`: Send a random saved quote from the current group.

**Admin commands:**

- `/qrate [on|off]`: View or change quote rating buttons.

**Options:**

- `count`: Quote 1 to 25 consecutive messages. The default is 1; `/q 5` requests 5.
- `color`: Choose a color name, such as `red`, or a color code such as `#ff0000`. Short `#rgb` and full `#rrggbb` codes work.
- `p`: Send an image file instead of a sticker.
- `r`: Include the quoted message's reply in a small bubble. This works when quoting one message.

**Examples:**

- Make a quote sticker. Reply to a message:\
  `/q`
- Quote 5 messages as a red PNG. Reply to the first:\
  `/q 5 #ff0000 p`
