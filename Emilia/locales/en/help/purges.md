+++
title = "Purges"
+++

# Purges

Delete group messages.

## Admin commands

- `/purge`: Reply to the first message to delete it and all messages through this command.
- `/spurge`: Purge the same range but silently.
- `/del`: Reply to a message to delete it and your command.
- `/purgefrom`: Reply to the first message to mark a range.
- `/purgeto`: Reply to the last message to delete the marked range, including both endpoints.

## Example

Reply to the first unwanted message:

```
/purge
```

<details>
<summary>Delete a bounded range</summary>

Reply to its first message:

```
/purgefrom
```

Reply to its last message:

```
/purgeto
```

</details>
