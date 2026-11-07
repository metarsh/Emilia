+++
title = "Requests"
+++

# Requests

Search linked content channels and request a title when it is missing. Start a private chat with the bot to receive status notifications.

## User commands

- `/req [query]`: Search or create a request; provide a query or reply to text or a caption. Aliases: `/request`, `/searchreq`.
- `#req [query]`: Request using a hashtag or replied title. Aliases: `#request`.
- `/reqs`: List your requests. Aliases: `/myrequests`, `/requests`.
- `/reqstatus <id>`: Check a request's status. Aliases: `/requeststatus`.

## Admin commands

- `/setreq <channel>`: Set the request destination by -100 ID or username. Aliases: `/setrequest`, `/setreqchannel`.
- `/unsetreq`: Remove the request destination. Aliases: `/unsetrequest`.
- `/addchannel <channel>`: Add a content channel to search. Aliases: `/addcontentchannel`.
- `/rmchannel <channel>`: Remove a content channel. Aliases: `/delchannel`, `/removechannel`.
- `/channels`: Show content channels and request settings. Aliases: `/reqchannels`, `/reqsettings`.
- `/reqmode <on|off>`: Enable or disable requests. Aliases: `/requestmode`.
- `/reqlimit [number|off]`: Show or set a daily limit; off or 0 allows unlimited requests. Aliases: `/requestlimit`.
- `/reqdone <id> [post_link]`: Mark a request fulfilled and notify subscribers; a replied media post can supply the link. Aliases: `/fulfillreq`, `/requestdone`.
- `/reqreject <id> [reason]`: Reject a request and notify subscribers. Aliases: `/requestreject`, `/delreq`.

## Requirements

The bot must be a member of each content channel. Adding a private content channel requires current administrator access there.

For `/setreq`, both you and the bot need posting rights in the destination channel, as well as your normal administrator rights in the source group.

Request searches and group settings support connected private chats. `/reqdone` and `/reqreject` also work through a connection to the original request group or its destination channel and recheck your administrator rights there. Request subscriptions belong to named user accounts.

## Example

```
/req One Piece
```
