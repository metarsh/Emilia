+++
title = "Placeholders"
hidden = true
+++

# Placeholders

Dynamic variables and formatting tags for greetings, notes, and filters.

## User & Chat variables

- `{first}`: User's first name.
- `{last}`: User's last name, or empty if none.
- `{fullname}`: User's full name.
- `{username}`: Username, falling back to a mention.
- `{mention}`: Clickable user mention.
- `{id}`: User's Telegram numeric ID.
- `{chatname}`: Title of the chat.
- `{count}`: Current member count.

## Behavioral tags

- `{rules}`: Attach interactive button opening group rules.
- `{preview}`: Enable web link previews for this message.
- `{replytag}`: Make filter responses reply to the trigger message's reply target.
- `{admin}`: Restrict note retrieval exclusively to admins.
- `{private}`: Send note response in private chat.
- `{noprivate}`: Send note response in group chat.

## Examples

```
/filter hello Hello, {first}!
/save info Read the group rules. {rules}
```
