+++
title = "CAPTCHA"
hidden = true
+++

# CAPTCHA

Restrict new members until they verify.

## Admin commands

- `/captcha [on|off]`: Toggle member verification.
- `/captchamode [button|math|text|image]`: Set mode to button, math, text, or image.
- `/captcharules [on|off]`: Require accepting group rules on verification.
- `/setcaptchatext [text]`: Set verification button text.
- `/resetcaptchatext`: Reset button text to default.
- `/recaptcha [on|off]`: Require returning members to verify again.

## Usage notes

- Button mode uses welcome message. Math and text modes send a private 3-attempt image challenge.
- Challenges expire in 15 minutes; unverified members stay restricted until admin review.
- Unverified members cannot send messages or reactions.
- Use `/connect` to set remotely, or Autoapprove for join requests.

## Example

```
/captcha on
/captchamode text
```
