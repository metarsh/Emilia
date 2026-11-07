+++
title = "Anime group settings"
hidden = true
anime = true
+++

# Anime group settings

Control anime features in chats and link chat sender identity to AniList.

## Admin commands

- `/anisettings`: Configure NSFW, notification, and display settings.
- `/disable <command ...>`: Disable specific anime commands.
- `/enable <command ...>`: Re-enable anime commands.
- `/disabled`: List disabled anime commands in chat.

## Chat owner commands

- `/aniconnect [chat ID or @username]`: Link chat identity to your AniList account.
- `/anidisconnect [chat ID or @username]`: Unlink AniList account from chat.

## Usage notes

- Account links require owner privileges; searches sent as the chat use this account.
- `/anisettings`, `/disable`, `/enable`, `/disabled` work in connected PM.
- Admins can still use disabled commands.
- Disableable: `anime`, `anilist`, `character`, `manga`, `airing`, `anihelp`, `schedule`, `fillers`, `top`, `anireverse`, `watch`, `flex`, `user`, `ame`, `activity`, `favourites`, `gettags`, `getgenres`, `aniconnect`, `anidisconnect`, `browse`, `studio`.

## Example

```
/disable anime anilist
/enable anime anilist
```
