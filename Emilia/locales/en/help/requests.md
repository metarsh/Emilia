+++
title = "Requests"
+++

# Requests

Search content channels and allow members to request missing titles.

## User commands

- `/req [query]`: Search or submit a request, or reply to text or caption. Aliases: `/request`, `/searchreq`.
- `#req [query]`: Submit request via hashtag. Alias: `#request`.
- `/reqs`: List your submitted requests. Aliases: `/myrequests`, `/requests`.
- `/reqstatus <id>`: Check request progress. Alias: `/requeststatus`.

## Admin commands

- `/setreq <channel>`: Set destination channel for requests by ID or username. Aliases: `/setrequest`, `/setreqchannel`.
- `/unsetreq`: Remove request channel. Alias: `/unsetrequest`.
- `/addchannel <channel>`: Add searchable content channel. Alias: `/addcontentchannel`.
- `/rmchannel <channel>`: Remove content channel. Aliases: `/delchannel`, `/removechannel`.
- `/channels`: View content channels and settings. Aliases: `/reqchannels`, `/reqsettings`.
- `/reqmode <on|off>`: Toggle requests. Alias: `/requestmode`.
- `/reqlimit [number|off]`: Set daily user request limit. Use `0` or `off` for unlimited. Alias: `/requestlimit`.
- `/reqdone <id> [post_link]`: Mark fulfilled and notify requester, or reply to post. Aliases: `/fulfillreq`, `/requestdone`.
- `/reqreject <id> [reason]`: Reject request and notify requester. Aliases: `/requestreject`, `/delreq`.

## Usage notes

- Bot must have admin posting rights in content and destination channels.
- Adding private channels requires admin rights there.
- Searches, settings, `/reqdone`, and `/reqreject` work in connected PM.

## Example

```
/req One Piece
```
