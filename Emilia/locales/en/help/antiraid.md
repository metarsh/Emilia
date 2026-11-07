+++
title = "Antiraid"
+++

# Antiraid

Temporarily ban new members when they arrive during a raid.

## Admin commands

- `/antiraid`: Toggle raid protection immediately.
- `/raidtime <hours>`: Set how long protection stays active; use a positive integer.
- `/raidactiontime <hours>`: Set how long new arrivals are banned; use a positive integer.
- `/autoantiraid <threshold|off>`: Enable protection when this many members join within a minute, or disable automatic activation; thresholds accept 1–1000.

## Defaults

Protection lasts 6 hours; new arrivals are banned for 1 hour. Once raid settings exist, automatic activation defaults to 20 joins per minute. Configure it explicitly with `/autoantiraid`.

## Example

```
/autoantiraid 20
```
