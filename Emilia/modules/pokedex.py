from Emilia.application import LOGGER
from Emilia.custom_filter import command
from Emilia.locales import tr
from Emilia.utils.command_help import reply_usage
from Emilia.utils.http import get


@command("pokedex", disable=True)
async def PokeDex(_, message):
    if len(message.text.split()) != 2:
        await reply_usage(message, PokeDex)
        return

    pokemon = message.text.split(None, 1)[1]
    pokedex_url = f"https://pokeapi.co/api/v2/pokemon/{pokemon}"

    r = await get(pokedex_url)
    if r.status == 404:
        return await message.reply_text(tr("pokedex.wrong_pokemon_name"))
    r.raise_for_status()
    result = r.json()

    try:
        pokemon_name = result["name"]
        pokedex_id = result["id"]
        types = ", ".join(typo["type"]["name"] for typo in result["types"][:5])
        abilities = ", ".join(ability["ability"]["name"] for ability in result["abilities"][:5])
        height = result["height"]
        weight = result["weight"]
        stats = "\n".join(
            f"{stat['stat']['name']}: {stat['base_stat']}" for stat in result["stats"]
        )

    except (KeyError, TypeError) as e:
        LOGGER.error(str(e))
        return

    caption = tr(
        "pokedex.pokemon_pokedex_type_abilities_height_weight_stats",
        pokemon_name=pokemon_name,
        pokedex_id=pokedex_id,
        types=types,
        abilities=abilities,
        height=height,
        weight=weight,
        stats=stats,
    )
    poke_img = f"https://img.pokemondb.net/artwork/large/{pokemon_name}.jpg"
    await message.reply_photo(photo=poke_img, caption=caption)
