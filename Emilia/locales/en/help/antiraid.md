+++
title = "Antiraid"
+++

# Antiraid

Temporarily ban new members who join during a raid.

## Admin commands

- `/antiraid`: Toggle raid protection immediately.
- `/raidtime <hours>`: Set protection duration in hours.
- `/raidactiontime <hours>`: Set newcomer ban duration in hours.
- `/autoantiraid <threshold|off>`: Auto-enable when join rate reaches 1–1000 members per minute, or off.

## Usage notes

- Defaults: protection lasts 6 hours; newcomers banned 1 hour.
- Automatic raid trigger defaults to 20 joins per minute once configured.

## Example

```
/autoantiraid 20
```
