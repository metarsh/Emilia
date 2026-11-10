+++
title = "Greetings"
children = ["greetings-examples", "captcha", "formatting"]
+++

# Greetings

I can welcome new members and say goodbye when they leave. Save your own text or media to make the messages suit your group.

In the examples, I replace `{mention}` with a mention of the new member and `{first}` with their first name. Keep the braces when saving.

Replace `<...>` with required input; `[...]` is optional. Do not type those brackets.

**Admin commands:**

- `/welcome [on|off|noformat]`: Preview the welcome, turn it on or off, or use `noformat` to see the saved text without formatting.
- `/goodbye [on|off]`: Preview the goodbye or turn it on or off.
- `/setwelcome [text]`: Save a welcome using text after the command or content you reply to.
- `/resetwelcome`: Restore the default welcome.
- `/setgoodbye [text]`: Save a goodbye using text after the command or content you reply to.
- `/resetgoodbye`: Restore the default goodbye.
- `/cleanservice [on|off]`: View or change whether join, leave, and other service messages are deleted.
- `/cleanwelcome [on|off]`: View or change whether old greeting messages are deleted.

**Examples:**

- Save a welcome:\
  `/setwelcome Welcome, {mention}! Read the group rules.`
- Turn welcome messages on:\
  `/welcome on`
- Save a goodbye:\
  `/setgoodbye Goodbye, {first}.`

Use the guides below for media examples, member verification, and formatting.
