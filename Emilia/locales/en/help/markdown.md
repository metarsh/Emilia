+++
title = "Message styling"
hidden = true
+++

# Message styling

These input examples describe saved messages. Copy the syntax exactly, or format the message in Telegram before saving it by reply.

## Text syntax

| Style | Input |
| --- | --- |
| Bold | `**bold**` |
| Italic | `__italic__` |
| Underline | `--underline--` |
| Strikethrough | `~~strikethrough~~` |
| Spoiler | `||spoiler||` |
| Link | `[Example](https://example.com)` |

## Code

Use single backticks for inline code. Use a fenced code block for multiline code; an optional language follows the opening fence.

Saved text and captions use the same parser with default or styled buttons. Preview saved content before using it.

## Button example

```
/filter links Choose a link.
[Website](buttonurl#primary://example.com)
[Help](buttonurl://example.com/help:same)
```

<details>
<summary>Button styles and rows</summary>

| Style | Input |
| --- | --- |
| Default | `[Open](buttonurl://example.com)` |
| Primary | `[Open](buttonurl#primary://example.com)` |
| Success | `[Done](buttonurl#success://example.com)` |
| Danger | `[Delete](buttonurl#danger://example.com)` |

Append `:same` inside the target to join the previous row:

```
[First](buttonurl://example.com)
[Second](buttonurl://example.com/second:same)
[Third](buttonurl://example.com/third)
```

Use full web URLs for links.

</details>
