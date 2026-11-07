+++
title = "Antiflood"
+++

# Antiflood

Act on consecutive messages or a burst within a time window. The bot needs permission to ban users and delete messages.

## User commands

- `/flood`: Show the current flood settings.

## Admin commands

- `/setflood <count|on|off>`: Set a consecutive-message limit, resume protection, or disable it. Alias: `/antiflood`.
- `/setfloodtimer <count> <seconds>`: Enable a timed limit; use `/setfloodtimer` off to disable it.
- `/setfloodmode <action> [duration]`: Set ban, mute, kick, tban, or tmute; tban and tmute require a duration. Alias: `/floodmode`.
- `/clearflood <on|off>`: Choose whether to delete messages that trigger protection.

## Example

```
/setflood on
/setfloodtimer 10 30
```

<details>
<summary>More examples</summary>

```
/setflood 7
/setfloodmode tmute 2h
/clearflood on
/setfloodtimer off
```

</details>
