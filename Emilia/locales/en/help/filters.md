+++
title = "Filters"
children = ["filters-examples", "formatting"]
+++

# Filters

Reply automatically when a message matches a saved trigger.

## User commands

- `/filters`: List the group's filters.

## Admin commands

- `/filter <trigger> [text]`: Save a text reply, or reply to the content to save.
- `/stop <trigger>`: Remove a filter.

## Owner commands

- `/stopall`: Delete every filter after confirmation. This cannot be undone.

## Usage notes

Provide text or reply to text or media when saving. Dice triggers include the dice emoji, `dice:6`, and `🎲:6`. Formatting and placeholders are described below.

## Example

```
/filter hello Hello, {first}!
```
