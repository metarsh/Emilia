+++
title = "Notes"
children = ["notes-examples", "formatting"]
+++

# Notes

Store reusable text messages, media, and announcements for your group.

## User commands

- `/get <name>`: Retrieve a saved note. Also triggers via `#name`.
- `/notes`: List all group notes. Alias: `/saved`.

## Admin commands

- `/save <name> [text]`: Save note with text, or by reply.
- `/clear <name>`: Delete a saved note.
- `/privatenotes [on|off]`: Toggle delivering notes in private chat.

## Owner commands

- `/clearall`: Delete all notes after confirmation. This cannot be undone.

## Example

```
/save rules Be kind.
/get rules
```
