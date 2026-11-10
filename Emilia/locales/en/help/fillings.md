+++
title = "Placeholders"
hidden = true
+++

# Placeholders

I can fill in names, mentions, and group details in your saved messages. Add a placeholder exactly as written, including its braces, where you want that information to appear.

**Names and chat details:**

- `{first}`: The user's first name.
- `{last}`: The user's last name, or nothing if they have none.
- `{fullname}`: The user's full name.
- `{username}`: Their username, or a mention if they have none.
- `{mention}`: A mention of the user.
- `{id}`: The user's ID.
- `{chatname}`: The chat's name.
- `{count}`: The member count.

**Message options:**

- `{rules}`: Add a button to the group rules.
- `{preview}`: Enable link previews for this message.
- `{replytag}`: If someone triggers a filter while replying to another message, send the filter reply to that earlier message.
- `{admin}`: Let only admins retrieve a note.
- `{private}`: Open a note in private.
- `{noprivate}`: Send a note in the group.

**Examples:**

- Greet a user by name in a filter:\
  `/filter hello Hello, {first}!`
- Add a rules button to a note:\
  `/save info Read the group rules. {rules}`
- Mention a new member in the welcome. Send this text, then reply to it with `/setwelcome`:\
  `Welcome, {mention}, to {chatname}!`
