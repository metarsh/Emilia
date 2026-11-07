+++
title = "Join requests"
children = ["captcha"]
+++

# Join requests

Automatically process Telegram join requests.

## Admin commands

- `/autoapprove [mode]`: View or set mode to `off`, `on`, `antispam`, `rules`, or `captcha`.

## Modes

- `off`: Leave requests for admins. Default.
- `on`: Auto-approve all join requests.
- `antispam`: Check antispam and fed bans before approving.
- `rules`: Check bans, then require agreeing to rules in PM.
- `captcha`: Check bans, then require solving captcha in PM.

## Example

```
/autoapprove captcha
```
