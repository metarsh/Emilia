from Emilia.custom_filter import command
from Emilia.locales import tr
from Emilia.utils.command_help import reply_usage
from Emilia.utils.http import get


@command("github", disable=True)
async def github(_, message):
    if len(message.text.split()) != 2:
        return await reply_usage(message, github)
    username = message.text.split(None, 1)[1]
    URL = f"https://api.github.com/users/{username}"

    r = await get(URL)
    if r.status == 404:
        return await message.reply_text(tr("github.not_found"))
    r.raise_for_status()
    result = r.json()

    url = result["html_url"]
    name = result["name"]
    company = result["company"]
    bio = result["bio"]
    created_at = result["created_at"]
    avatar_url = result["avatar_url"]
    blog = result["blog"]
    location = result["location"]
    repositories = result["public_repos"]
    followers = result["followers"]
    following = result["following"]
    caption = tr(
        "github.github_information_username_bio_profile_link_here_company",
        name=name,
        username=username,
        bio=bio,
        url=url,
        company=company,
        created_at=created_at,
        repositories=repositories,
        blog=blog,
        location=location,
        followers=followers,
        following=following,
    )

    await message.reply_photo(photo=avatar_url, caption=caption)
