+++
title = "Bot-to-bot"
+++

# Bot-to-bot

Choose which other bots may send commands to this bot.

## Admin commands

- `/bot2bot [off|admin|all]`: Show or choose which bots may request commands.
- `/bot2botskipreview [on|off]`: Show or change whether allowed bot commands skip admin review.

## Modes

| Mode | Allowed senders |
| --- | --- |
| `off` | No other bots; default. |
| `admin` | Bots that are group admins. |
| `all` | Any bot in the group. |