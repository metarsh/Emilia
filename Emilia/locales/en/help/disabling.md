+++
title = "Disabling"
+++

# Disabling

Disable selected bot commands, including anime commands, in a group or channel or through a connected private chat. Administrators can still use disabled commands.

## Admin commands

- `/disableable`: List commands that support disabling.
- `/disable <command> [command ...]`: Disable command names.
- `/enable <command> [command ...]`: Enable disabled commands.
- `/disabled`: List disabled commands.
- `/disabledel <on|off>`: Delete attempts to use disabled commands.

Use names listed by `/disableable`. Declared alias groups such as `pkang|packkang` can be disabled together, or you can disable an individual alias. Deletion applies to commands sent in the selected chat; a connected private-chat attempt is kept in private.

## Example

```
/disable wiki gif
```
