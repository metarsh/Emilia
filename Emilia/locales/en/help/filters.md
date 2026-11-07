+++
title = "Filters"
children = ["filters-examples", "formatting"]
+++

# Filters

Automatically reply when messages match a saved trigger.

## User commands

- `/filters`: List active group filters.

## Admin commands

- `/filter <trigger> [text]`: Save trigger with text or by reply. Wrap multi-word triggers in quotes.
- `/stop <trigger>`: Delete a saved filter.

## Owner commands

- `/stopall`: Delete all filters after confirmation. This cannot be undone.

## Usage notes

- Dice triggers support dice emoji and roll results, like `dice:6` or `🎲:6`.
- Supports formatting, markdown buttons, and dynamic placeholders.

## Example

```
/filter hello Hello, {first}!
```
