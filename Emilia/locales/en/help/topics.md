+++
title = "Topics"
+++

# Topics

I can help you create, rename, close, and reopen forum topics in your group.

These commands work in a group with Topics enabled. Send them in that group; you and I need Manage topics rights.

Inside a topic, commands without an ID use that topic. Outside one, use the topic buttons I show. You do not need to find an ID for ordinary use.

Replace `<...>` with required input; `[...]` is optional. Do not type those brackets.

**Admin commands:**

- `/topics`: List open topics with buttons to close or delete them.
- `/newtopic <name>`: Create a topic.
- `/renametopic <name> [| topic_id]`: Rename the current topic, or give a topic ID when outside it.
- `/opentopic [topic_id]`: Reopen the current topic or choose a closed topic.
- `/closetopic [topic_id]`: Close the current topic or choose a topic.
- `/deletetopic [topic_id]`: Permanently delete the current topic, including its messages, or choose a topic. There is no extra confirmation step.

**Examples:**

- Create a topic:\
  `/newtopic Games`
- For a known topic ID, rename it. Here the `|` is literal:\
  `/renametopic Games | 123`
- Close it:\
  `/closetopic 123`
- Reopen it to allow messages again:\
  `/opentopic 123`
