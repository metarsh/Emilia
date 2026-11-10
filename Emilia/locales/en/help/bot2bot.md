+++
title = "Bot-to-bot"
+++

# Bot-to-bot

Want another bot in your group to send me commands? You can choose which bots I listen to and whether their commands need an admin's approval.

Replace `<...>` with required input; `[...]` is optional. Do not type those brackets.

**Admin commands:**

- `/bot2bot [off|admin|all]`: View or change which bots can send me commands.
- `/bot2botskipreview [on|off]`: View or change whether allowed bots can run commands without admin approval.

**Bot modes:**

- `off`: Ignore commands from other bots. This is the default.
- `admin`: Allow commands from bots that are group admins.
- `all`: Allow commands from any bot in the group.

**Admin review:**

- With skip review set to `off`, an admin must approve or reject each allowed bot command using the buttons I show.
- With skip review set to `on`, allowed bot commands run without that approval step.

**Examples:**

- Listen only to bots that are group admins:\
  `/bot2bot admin`
- Keep admin approval for their commands:\
  `/bot2botskipreview off`
- Ignore all other bots again:\
  `/bot2bot off`
