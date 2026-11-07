+++
title = "Anime group settings"
hidden = true
anime = true
+++

# Anime group settings

Control anime features in groups or channels and link their sender identity to an AniList account.

## Admin commands

- `/anisettings`: Open adult-content, notification, and display settings.
- `/disable <command> [command ...]`: Disable anime command names.
- `/enable <command> [command ...]`: Enable anime commands again.
- `/disabled`: List disabled commands in the selected group or channel.

## Chat owner commands

- `/aniconnect [chat ID or @username]`: Link your group or channel to your AniList account. Supply the chat in private, or run it as a named owner in that chat.
- `/anidisconnect [chat ID or @username]`: Remove that account link.

## Usage notes

Account links require current ownership and let searches sent as that chat use your account. Ownership is checked again when the link is used. A Telegram discussion link does not authorize AniList account access.

`/anisettings`, `/disable`, `/enable` and `/disabled` support connected private chats. An AniList account link and a bot command connection are separate settings. Administrators can still use disabled commands.

<details>
<summary>Anime commands that support disabling</summary>

`anime`, `anilist`, `character`, `manga`, `airing`, `anihelp`, `schedule`, `fillers`, `top`, `anireverse`, `watch`, `flex`, `user`, `ame`, `activity`, `favourites`, `gettags`, `getgenres`, `aniconnect`, `anidisconnect`, `browse`, `studio`.

</details>

## Example

```
/disable anime anilist
/enable anime anilist
```
