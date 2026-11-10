+++
title = "Blocklist examples"
hidden = true
+++

# Blocklist examples

Use words, phrases, or patterns to choose what I should block.

**Examples:**

- Add a word with a reason. Replace the placeholders:\
  `/addblocklist <spam> <reason>`
- Add a phrase:\
  `/addblocklist "buy now" Advertising`
- Remove the phrase using its saved text, without the quotes used when adding it:\
  `/rmblocklist buy now`
- Block filenames ending in .exe:\
  `/addblocklist *.exe Executable files`
- Block links using a shortened-link address:\
  `/addblocklist https://short.example/* Shortened links`
- Block a custom emoji pack. Reply to its emoji and keep `<>` exactly as written:\
  `/addblocklist emojipack:<>`
- Mute matching senders for 2 hours:\
  `/blocklistmode tmute 2h`

`?` matches one character other than a space; `*` matches any number of characters other than spaces.
