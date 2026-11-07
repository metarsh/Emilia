+++
title = "Join requests"
children = ["captcha"]
+++

# Join requests

Process Telegram join requests.

## Admin commands

- `/autoapprove [mode]`: Show or choose a join-request mode.

## Modes

| Mode | Behavior |
| --- | --- |
| `off` | Leave requests for admins; default. |
| `on` | Approve every request. |
| `antispam` | Check federation bans and antispam system before approval. |
| `rules` | Run antispam checks, then requires user to accept the rules. |
| `captcha` | Run antispam checks, then requires user to solve private captcha. |

## Example

```
/autoapprove captcha
```