<h1 align="center">✨ Emilia ✨</h1>

![Emilia](https://pic-bstarstatic.akamaized.net/ugc/9e98b6c8872450f3e8b19e0d0aca02deff02981f.jpg@1200w_630h_1e_1c_1f.webp)


[Emilia](https://t.me/Elf_Robot) is a Telegram group-management bot with moderation, greetings, notes, filters, anime tools, music, chatbot and clone bots. It uses Python 3.12, MongoDB and Redis.

## Support

If you face any issues, feel free to contact [SpiralTechDivision](https://t.me/SpiralTechDivision) on telegram, i will be happy to help.

<p align="center">
    <a href="https://python.org">
        <img src="https://forthebadge.com/images/badges/made-with-python.svg" alt="Made with Python">
    </a>
    <a href="https://github.com/metarsh">
        <img src="https://forthebadge.com/images/badges/built-with-love.svg" alt="Built with Love">
    </a>
    <br>
    <img src="https://img.shields.io/github/license/metarsh/Emilia?style=for-the-badge&logo=appveyor&v=1" alt="License">
</p>

## Installation

### Install locally or on a VPS (manual setup)

Install [Python 3.12](https://www.python.org/downloads/), [FFmpeg](https://www.ffmpeg.org/), [Node.js](https://nodejs.org/en/download). Make MongoDB and Redis available, then:

```sh
git clone https://github.com/metarsh/Emilia
cd Emilia
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

### Configure

Fill your private `.env` using [.env.example](.env.example) as a reference. Put your [cookies](https://github.com/yt-dlp/yt-dlp/wiki/Extractors#exporting-youtube-cookies) file in the current working directory for music to work.

### Run directly

```sh
python -m Emilia
```


### Run using docker (best way)

Install [Docker](https://docs.docker.com/engine/install/) and [Docker Compose](https://docs.docker.com/compose/install)

### Configure

Fill your private `.env` using [.env.example](.env.example) as a reference. Put your [cookies](https://github.com/yt-dlp/yt-dlp/wiki/Extractors#exporting-youtube-cookies) file in the current working directory for music to work. You don't need to setup redis if using docker.

```
chmod 600 .env www.youtube.com_cookies.txt
docker compose build
```

### Start everything

```
docker compose up -d
```

### View logs

```
docker compose logs -f emilia
```

## Developing modules

Use `command()` to register command handlers.

```python
from pyrogram import filters

from Emilia.custom_filter import command


@command(["ping", "pong"], filters=filters.group)
async def ping(client, message):
    arguments = message.command[1:]
    await message.reply_text(" ".join(arguments) or "Pong!")
```
