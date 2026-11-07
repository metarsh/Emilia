+++
title = "Rules"
children = ["formatting"]
+++

# Rules

Configure and display group rules.

## User commands

- `/rules`: View group rules.

## Admin commands

- `/setrules <text>`: Save group rules. Supports formatting and buttons.
- `/resetrules`: Clear custom rules and restore defaults. Alias: `/clearrules`.
- `/privaterules [on|off]`: Toggle delivering rules in private chat.
- `/setrulesbutton [label]`: Customize rules button label.
- `/resetrulesbutton`: Reset rules button label to default.

## Example

```
/setrules Be kind to others.
/privaterules on
```
