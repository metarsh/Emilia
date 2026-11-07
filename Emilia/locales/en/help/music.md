+++
title = "Music"
children = ["playlists"]
+++

# Music

Play audio or video in a group voice chat through the main bot. Start the voice chat first.

## User commands

- `/play [query or link]`: Play audio; provide a search query or link, or reply to text, audio, voice, or video.
- `/vplay [query or link]`: Play video using the same input forms.
- `/now`: Show the current track and playback controls.
- `/queue`: List queued tracks.
- `/lyrics <song>`: Find lyrics for a song.

## Session controls

- `/pause`: Pause playback.
- `/resume`: Resume playback.
- `/skip`: Skip the current track.
- `/end`: Stop playback and clear the queue. Alias: `/cend`.
- `/remove <position>`: Remove a track at its position in `/queue`.
- `/clearqueue`: Empty the upcoming queue.
- `/loop <off|one|all>`: Choose whether to repeat the current track or queue.
- `/shuffle <on|off>`: Enable or disable queue shuffling.

## Admin commands

- `/autoplay [on|off]`: Show or change recommendations when the queue ends. Alias: `/cplay`.
- `/playmenu [on|off]`: Show or change the search-result selection menu.

## Example

```
/play Never Gonna Give You Up
```
