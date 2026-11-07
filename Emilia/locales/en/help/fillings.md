+++
title = "Placeholders"
hidden = true
+++

# Placeholders

Insert context fields in saved content.

## Context fields

| Field | Replacement |
| --- | --- | --- |
| `{first}` | First name. |
| `{last}` | Last name, or empty. |
| `{fullname}` | Full name. |
| `{username}` | Username, or a mention. |
| `{mention}` | User mention. |
| `{id}` | User ID. |
| `{chatname}` | Chat title. |
| `{count}` | Member count. |

## Message tags

| Tag | Behavior |
| --- | --- |
| `{rules}` | Add a rules button. |
| `{preview}` | Enable link previews for this message. |
| `{replytag}` | Make a filter reply to the triggering message's reply target. |
| `{admin}` | Allow only admins to retrieve a note. |
| `{private}` | Open a note in private. |
| `{noprivate}` | Send a note in the group. |

## Example

```
/filter hello Hello, {first}!
```

<details>
<summary>Rules and greeting examples</summary>

```
/save info Read the group rules. {rules}
```

For a welcome, send `Welcome, {mention}, to {chatname}!` and reply to it with `/setwelcome`.

</details>
