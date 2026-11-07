+++
title = "Purges"
+++

# Purges

Bulk delete group messages.

## Admin commands

- `/purge`: Delete all messages from replied message up to command.
- `/spurge`: Delete the same range silently.
- `/del`: Delete replied message and the command.
- `/purgefrom`: Mark start message of a purge range.
- `/purgeto`: Mark end message and delete everything in the marked range.

## Examples

Single-point purge:
Reply to first unwanted message:
```
/purge
```

Bounded range purge:
Reply to first message:
```
/purgefrom
```
Reply to last message:
```
/purgeto
```
