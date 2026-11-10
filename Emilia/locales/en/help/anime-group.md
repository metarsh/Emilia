+++
title = "Anime group settings"
hidden = true
anime = true
+++

# Anime group settings

Choose how anime features work in your group or channel. Chat owners can also link an AniList account so searches sent as that chat use their account.

**Admin commands:**

- `/anisettings`: Open adult-content, notification, and display settings.
- `/disable <command> [command ...]`: Turn off anime command names.
- `/enable <command> [command ...]`: Turn them on again.
- `/disabled`: List disabled commands in the selected group or channel.

**Chat owner commands:**

- `/aniconnect [chat ID or @username]`: Link your group or channel to your AniList account. In private, use the buttons to choose a chat, or give its ID or @username. You can also run the command in the group as its owner.
- `/anidisconnect [chat ID or @username]`: Remove that account link.

**Tips:**

- You must still own the chat when the linked account is used. Linking a discussion group to a channel does not grant access to an AniList account.
- `/anisettings`, `/disable`, `/enable`, and `/disabled` work through connected private chats. Admins can still use disabled commands.
- An AniList account link is separate from a connection used to send bot commands in private.

**Commands you can disable:**

`anime`, `anilist`, `character`, `manga`, `airing`, `anihelp`, `schedule`, `fillers`, `top`, `anireverse`, `watch`, `flex`, `user`, `ame`, `activity`, `favourites`, `gettags`, `getgenres`, `aniconnect`, `anidisconnect`, `browse`, `studio`.

**Examples:**

- Disable anime searches:\
  `/disable anime anilist`
- Enable them again:\
  `/enable anime anilist`
