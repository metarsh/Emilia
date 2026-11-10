+++
title = "Filters"
children = ["filters-examples", "formatting"]
+++

# Filters

I can reply automatically when a message matches a word or phrase you save. Use filters for quick answers or to share text and media.

Triggers match words or phrases in messages and captions, regardless of capitalisation. A trigger such as `hello` matches `hello there`, but not `helloworld`. Saving an existing trigger replaces its reply.

In the examples, leave `{first}` exactly as written; I replace it with the sender's first name.

Replace `<...>` with required input; `[...]` is optional. Do not type those brackets.

**User commands:**

- `/filters`: List the group's filters.

**Admin commands:**

- `/filter <trigger> [text]`: Save a reply for a trigger. Add the text after it, or reply to the text or media you want to save.
- `/stop <trigger>`: Remove a filter so I stop replying to that trigger.

**Owner commands:**

- `/stopall`: Delete every filter after confirmation. This cannot be undone.

**Examples:**

- Reply when someone says hello:\
  `/filter hello Hello, {first}!`
- Save a reply for a phrase:\
  `/filter "good morning" Good morning, {first}!`
- Stop the hello filter:\
  `/stop hello`

**Tips:**

- Put multiword triggers in quotes.
- To save a photo or sticker, reply to it with the filter command.
- Dice triggers include the dice emoji, `dice:6`, and `🎲:6`.
- Use the guides below for more examples, text styling, buttons, and placeholders such as `{first}`.
