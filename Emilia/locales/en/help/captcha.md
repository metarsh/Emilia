+++
title = "CAPTCHA"
hidden = true
+++

# CAPTCHA

I can stop new members from sending messages or adding reactions until they verify. Choose a button, a maths question, or a text challenge.

**Admin commands:**

- `/captcha [on|off]`: View or change verification for new members.
- `/captchamode [button|math|text|image]`: View or choose the challenge. `image` is the same as `text`.
- `/captcharules [on|off]`: View or change whether members must also accept the rules.
- `/setcaptchatext [text]`: View or change the verification button's label.
- `/resetcaptchatext`: Restore the default button label.
- `/recaptcha [on|off]`: View or change whether returning members must verify again.

**Tips:**

- Button mode uses the welcome message.
- Maths and text modes open an image challenge in private. Users have three attempts and can choose an answer or reply to the challenge.
- You can require rules acceptance after any challenge.
- Challenges expire after 15 minutes. An admin must review anyone still restricted after that.
- Use `/connect` to manage settings that support a connected group. For verification before joining, use the Join requests guide.

**Examples:**

- Enable verification with a text challenge:\
  `/captcha on`\
  `/captchamode text`
- Ask returning members to verify again:\
  `/recaptcha on`
