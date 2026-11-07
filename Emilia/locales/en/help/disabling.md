+++
title = "Disabling"
+++

# Disabling

Disable specific commands in a group, channel, or via connected PM. Admins can always use disabled commands.

## Admin commands

- `/disableable`: List commands that can be disabled.
- `/disable <command ...>`: Disable one or more commands.
- `/enable <command ...>`: Re-enable disabled commands.
- `/disabled`: List currently disabled commands.
- `/disabledel <on|off>`: Toggle deleting disabled command attempts in chat.

## Usage notes

- Disable aliases together or individually based on `/disableable`.
- Deletion applies in chat; attempts in connected PM are not deleted.

## Example

```
/disable wiki gif
```
