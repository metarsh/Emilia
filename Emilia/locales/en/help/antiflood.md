+++
title = "Antiflood"
+++

# Antiflood

If one member sends too many messages, I can act automatically. Admins and approved members are exempt.

I need Ban users and Delete messages rights. Protection is off until enabled. Its starting settings are 10 consecutive messages, a ban, and deletion of the messages that trigger it.

Replace `<...>` with required input; `[...]` is optional. Do not type those brackets.

**User commands:**

- `/flood`: View the current flood settings.

**Admin commands:**

- `/setflood <count|on|off>`: Set a consecutive-message limit, enable protection with `on`, or disable it with `off`. Alias: `/antiflood`.
- `/setfloodtimer <count> <seconds>`: Switch to counting messages from one member within a time window. Use `/setfloodtimer off` to return to consecutive-message counting.
- `/setfloodmode <action> [duration]`: Choose `ban`, `mute`, `kick`, `tban`, or `tmute`. Timed actions need a duration, such as `2h`. Alias: `/floodmode`.
- `/clearflood <on|off>`: Choose whether I delete the messages that trigger protection.

**Examples:**

- Check the settings before making changes:\
  `/flood`
- Set a limit of 7 consecutive messages:\
  `/setflood 7`
- Instead, use a limit of 10 messages within 30 seconds:\
  `/setfloodtimer 10 30`
- Mute members who flood for 2 hours:\
  `/setfloodmode tmute 2h`
- Delete the messages that trigger protection:\
  `/clearflood on`
- Enable protection using its saved settings:\
  `/setflood on`

The timed and consecutive limits are alternatives. While protection is enabled, turning the timer off uses the saved consecutive limit again.
