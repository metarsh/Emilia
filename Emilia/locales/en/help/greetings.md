+++
title = "Greetings"
children = ["greetings-examples", "captcha", "formatting"]
+++

# Greetings

Welcome incoming members and send farewell messages.

## Admin commands

- `/welcome [on|off|noformat]`: Preview welcome, toggle it, or inspect raw source with `noformat`.
- `/goodbye [on|off]`: Preview goodbye or toggle it.
- `/setwelcome`: Reply to text or media to set welcome message.
- `/resetwelcome`: Reset welcome message to default.
- `/setgoodbye [text]`: Set goodbye message via text or reply.
- `/resetgoodbye`: Reset goodbye message to default.
- `/cleanservice [on|off]`: Toggle auto-deleting join and leave service notifications.
- `/cleanwelcome [on|off]`: Toggle deleting previous welcome messages on new arrivals.

## Example

Reply to your welcome text or media:

```
/setwelcome
```
