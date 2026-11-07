+++
title = "CAPTCHA"
hidden = true
+++

# CAPTCHA

Restrict new members until they verify.

## Admin commands

- `/captcha [on|off]`: Show or change member verification.
- `/captchamode [button|math|text|image]`: Show or choose a challenge; image is same as text.
- `/captcharules [on|off]`: Show or change whether verification also requires accepting the rules.
- `/setcaptchatext [text]`: Show or set the verification button label.
- `/resetcaptchatext`: Restore the default verification button label.
- `/recaptcha [on|off]`: Show or change whether returning members must verify again.

## Verification

Button mode uses the welcome message. Math and text modes open a private image challenge with three attempts; users choose an answer or reply to the challenge. Rules acceptance can follow any mode.

Challenges expire after 15 minutes. An admin must review members still restricted after expiry. Waiting members cannot send messages or add reactions. `/recaptcha` controls returning-member checks.

Use `/connect` for settings that support a connected group, or Autoapprove for join-request verification.

## Example

```
/captcha on
/captchamode text
```
