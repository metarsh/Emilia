+++
title = "Message styling"
hidden = true
+++

# Message styling

Syntax reference for formatting saved messages, captions, and inline buttons.

## Text formatting

- Bold: `**bold**`
- Italic: `__italic__`
- Underline: `--underline--`
- Strikethrough: `~~strikethrough~~`
- Spoiler: `||spoiler||`
- Text link: `[Example](https://example.com)`
- Inline code: `` `code` ``

## Inline buttons

Syntax: `[Button Label](buttonurl://url)`

- Standard: `[Open](buttonurl://example.com)`
- Primary: `[Open](buttonurl#primary://example.com)`
- Success: `[Done](buttonurl#success://example.com)`
- Danger: `[Delete](buttonurl#danger://example.com)`

To place buttons on the same row, append `:same` to the URL:

```
[First](buttonurl://example.com)
[Second](buttonurl://example.com/second:same)
```

## Example

```
/filter links Choose a link.
[Website](buttonurl#primary://example.com)
[Help](buttonurl://example.com/help:same)
```
