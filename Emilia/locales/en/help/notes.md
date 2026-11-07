+++
title = "Notes"
children = ["notes-examples", "formatting"]
+++

# Notes

Save reusable text or media for your group.

## User commands

- `/get <name>`: Retrieve a saved note. You can also send #name.
- `/notes`: List saved notes. Aliases: `/saved`.

## Admin commands

- `/save <name> [text]`: Save text, or reply to the content to save.
- `/clear <name>`: Delete a saved note.
- `/privatenotes [on|off]`: Show or change whether notes open in private.

## Owner commands

- `/clearall`: Delete every note after confirmation. This cannot be undone.

## Example

```
/save rules Be kind.
/get rules
```
