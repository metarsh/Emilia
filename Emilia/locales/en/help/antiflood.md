+++
title = "Antiflood"
+++

# Antiflood

Protect the chat against message flooding and fast bursts. Requires ban and delete rights.

## User commands

- `/flood`: Show current flood settings.

## Admin commands

- `/setflood <count|on|off>`: Set consecutive message limit or toggle protection. Alias: `/antiflood`.
- `/setfloodtimer <count> <seconds>`: Limit messages allowed within seconds. Use `/setfloodtimer off` to disable.
- `/setfloodmode <action> [duration]`: Set action to ban, mute, kick, tban, or tmute. Timed actions require duration. Alias: `/floodmode`.
- `/clearflood <on|off>`: Toggle deleting flood-triggering messages.

## Example

```
/setflood 7
/setfloodmode tmute 2h
/clearflood on
/setfloodtimer 10 30
```
