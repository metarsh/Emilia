+++
title = "Topics"
+++

# Topics

Manage forum topics.

## Admin commands

- `/topics`: List open topics with close and delete buttons.
- `/newtopic <name>`: Create a topic.
- `/renametopic <name> [| topic_id]`: Rename the current topic, or select a topic when outside one.
- `/opentopic [topic_id]`: Reopen the current topic or choose a closed topic.
- `/closetopic [topic_id]`: Close the current topic or choose a topic.
- `/deletetopic [topic_id]`: Delete the current topic or choose a topic.

## Example

```
/newtopic Games
```

<details>
<summary>Explicit topic IDs</summary>

```
/renametopic Games | 123
/closetopic 123
/opentopic 123
```

</details>
