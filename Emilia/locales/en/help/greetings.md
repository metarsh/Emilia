+++
title = "Greetings"
children = ["greetings-examples", "captcha", "formatting"]
+++

# Greetings

Welcome new members and send a goodbye when they leave.

## Admin commands

- `/welcome [on|off|noformat]`: Preview the welcome or toggle it; noformat shows its saved source.
- `/goodbye [on|off]`: Preview the goodbye or toggle it.
- `/setwelcome`: Reply to text or media to save a welcome.
- `/resetwelcome`: Restore the default welcome.
- `/setgoodbye [text]`: Save inline text or replied content as the goodbye.
- `/resetgoodbye`: Restore the default goodbye.
- `/cleanservice [on|off]`: Show or change service-message deletion.
- `/cleanwelcome [on|off]`: Show or change deletion of old greeting messages.

## Example

Send a message containing `Welcome, {mention}! Read the group rules.` Then reply to it:

```
/setwelcome
```
