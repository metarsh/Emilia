+++
title = "Requests"
+++

# Requests

Looking for a film, series, or other title shared in your group's content channels? I can search the linked channels and help you request a missing title.

Start a private chat with me to receive request updates.

Replace `<...>` with required input; `[...]` is optional. Do not type those brackets.

**User commands:**

- `/req [query]`: Search or make a request. Add a title, or reply to text or a caption. Aliases: `/request`, `/searchreq`.
- `#req [query]`: Request using a hashtag or a title you reply to. Alias: `#request`.
- `/reqs`: List your requests. Aliases: `/myrequests`, `/requests`.
- `/reqstatus <id>`: Check a request's status. Alias: `/requeststatus`.

**Admin commands:**

- `/setreq <channel>`: Choose the request destination using a -100 ID or username. Use `/id` in the channel to find its ID. Aliases: `/setrequest`, `/setreqchannel`.
- `/unsetreq`: Remove the request destination. Alias: `/unsetrequest`.
- `/addchannel <channel>`: Add a content channel to search. Alias: `/addcontentchannel`.
- `/rmchannel <channel>`: Remove a content channel. Aliases: `/delchannel`, `/removechannel`.
- `/channels`: View content channels and request settings. Aliases: `/reqchannels`, `/reqsettings`.
- `/reqmode <on|off>`: Turn requests on or off. Alias: `/requestmode`.
- `/reqlimit [number|off]`: View or change the daily limit. Use `off` or `0` for unlimited requests. Alias: `/requestlimit`.
- `/reqdone <id> [post_link]`: Mark a request as fulfilled and notify subscribers. You can reply to a media post to use its link. Aliases: `/fulfillreq`, `/requestdone`.
- `/reqreject <id> [reason]`: Reject a request and notify subscribers. Aliases: `/requestreject`, `/delreq`.

**Examples:**

- Search for or request a title:\
  `/req One Piece`
- View your requests:\
  `/reqs`

**Setup tips:**

- I must be a member of every content channel. You must be a current admin of a private channel to add it.
- For `/setreq`, both you and I need posting rights in the destination channel. You also need admin rights in the source group.
- Searches and group settings work through connected private chats. `/reqdone` and `/reqreject` also work when connected to the original request group or its destination channel, if you have the required admin rights.
- Subscribe to requests using your own user account.
