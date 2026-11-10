+++
title = "Antiraid"
+++

# Antiraid

If lots of people join your group to spam, I can temporarily ban new arrivals while you wait out the raid. This applies to all new arrivals while protection is active.

Protection lasts 6 hours by default; each new arrival is banned for 1 hour.

**Automatic protection:**

Saving raid settings or enabling protection also gives you an automatic threshold of 20 joins per minute unless you explicitly choose another threshold or turn it off. Use `/autoantiraid off` if you want manual protection only.

Replace `<...>` with required input; `[...]` is optional. Do not type those brackets.

**Admin commands:**

- `/antiraid`: Turn active protection off, or turn it on if it is inactive. Read my enabled/disabled reply before sending it again.
- `/raidtime <hours>`: Set how many hours protection stays on. Use a positive whole number.
- `/raidactiontime <hours>`: Set how many hours new arrivals are banned for. Use a positive whole number.
- `/autoantiraid <threshold|off>`: Activate protection when this many members join within a minute. Choose 1 to 1000, or use `off` to stop automatic activation.

**Examples:**

- Toggle protection during a raid:\
  `/antiraid`
- Keep protection on for 3 hours:\
  `/raidtime 3`
- Automatically activate at 20 joins in a minute:\
  `/autoantiraid 20`
- Turn automatic protection off:\
  `/autoantiraid off`

Turning active protection off with `/antiraid` also clears the saved raid settings. Set your preferred times and automatic threshold again when needed.
