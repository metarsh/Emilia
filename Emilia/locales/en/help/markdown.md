+++
title = "Message styling"
hidden = true
+++

# Message styling

You can format notes, filters, and greetings before saving them. Copy the syntax below, or use Telegram's text formatting and save the message by reply.

**Text styles:**

- Bold: `**bold**`
- Italic: `__italic__`
- Underline: `--underline--`
- Strikethrough: `~~strikethrough~~`
- Spoiler: `||spoiler||`
- Link: `[Example](https://example.com)`

**Code:**

Use single backticks around inline code. For several lines, use three backticks before and after the code. You can put a language name after the opening backticks.

Text and media captions support the same styles. Preview your saved message before using it.

A button's label and color only change its appearance. A button labelled Delete still opens its URL; the label does not make it delete anything.

**Buttons:**

Add a button line to your saved message using one of these styles:
- Default: `[Open](buttonurl://example.com)`
- Primary: `[Open](buttonurl#primary://example.com)`
- Success: `[Done](buttonurl#success://example.com)`
- Danger: `[Delete](buttonurl#danger://example.com)`

Use full web URLs for links. To put a button beside the previous one, add `:same` at the end of its target.

**Examples:**

- Send this whole block as one message to save a filter with a blue website button and a second button on the same row:
```
/filter links Choose a link.
[Website](buttonurl#primary://example.com)
[Help](buttonurl://example.com/help:same)
```

- Include these lines together in the message you save. The first two buttons share a row; the third starts a new row:
```
[First](buttonurl://example.com)
[Second](buttonurl://example.com/second:same)
[Third](buttonurl://example.com/third)
```
