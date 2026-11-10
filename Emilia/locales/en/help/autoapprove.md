+++
title = "Join requests"
children = ["captcha"]
+++

# Join requests

I can handle join requests for you. Choose whether I approve everyone, check for banned users, or ask people to verify first.

Replace `<...>` with required input; `[...]` is optional. Do not type those brackets.

**Admin commands:**

- `/autoapprove [mode]`: View or change how I handle join requests.

**Modes:**

- `off`: Leave requests for admins to review. This is the default.
- `on`: Approve every request.
- `antispam`: Check federation bans and the anti-spam system before approving.
- `rules`: Run the same checks, then ask the user to accept the rules.
- `captcha`: Run the same checks, then ask the user to solve a CAPTCHA in private.

**Examples:**

- Ask users to solve a CAPTCHA before joining:\
  `/autoapprove captcha`
- Leave requests for admins:\
  `/autoapprove off`

Use the CAPTCHA guide below for verification settings.
