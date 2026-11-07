import random
import re

from pyrogram.types import LinkPreviewOptions

from Emilia.config import Config
from Emilia.custom_filter import listen
from Emilia.locales import tr

OWO = [
    tr("emilia.emilia_always_here_senpai_w"),
    tr("emilia.called_p"),
    "*bites*",
    tr("emilia.nya_am_here"),
    "*listens*",
    tr("emilia.came_only_3"),
    tr("emilia.want_pat_sneaky_lil_fox"),
    tr("emilia.yes_am_emilia"),
    tr("emilia.nobody_calls_name_am_supreme_p"),
    tr("emilia.well_well_came_now_what"),
    tr("emilia.nya_nya_nyaaaaa"),
    tr("emilia.what_want_kiss_huhhhhh"),
    tr("emilia.yeah_yeah_know_am_underage"),
    ".......",
    tr("emilia.senpai"),
    tr("emilia.ah_might_fall_3"),
    tr("emilia.allow_privilege_distorting_life"),
    tr("emilia.do_have_name_can_call_mine"),
    tr("emilia.time_some_more_fun_strings"),
    tr("emilia.bring_memes_virtual_cookies"),
    tr("emilia.do_believe_love_at_first_chat"),
    tr("emilia.if_were_cat_d_purr"),
    tr("emilia.roses_red_violets_blue_m_here"),
    tr("emilia.can_borrow_kiss_promise_ll_give_back"),
    tr("emilia.m_like_ctrl_c_copy_heart"),
    tr("emilia.m_not_photographer_but_can_definitely_picture_us"),
    tr("emilia.keyboard_because_re_just_type"),
    tr("emilia.do_have_map_just_got_lost_messages"),
    tr("emilia.m_not_bot_but_m_programmed_make_smile"),
    tr("emilia.if_looks_could_gif_d_looping_masterpiece"),
    tr("emilia.must_snowflake_because_ve_fallen"),
    tr("emilia.wi_fi_because_m_feeling_connection"),
    tr("emilia.must_made_copper_tellurium_because_re_cu_te"),
    tr("emilia.name_google_because_have_everything_ve_searching"),
    tr("emilia.name_wi_fi_because_m_feeling_strong_connection"),
    tr("emilia.if_were_fruit_d_fineapple"),
    tr("emilia.campfire_because_re_hot_want_s_more"),
    tr("emilia.if_were_vegetable_d_cute_cumber"),
    tr("emilia.magician_whenever_look_at_everyone_else_disappears"),
    tr("emilia.must_parking_ticket_because_ve_got_fine_written"),
    tr("emilia.bank_loan_because_have_interest_variant"),
    tr("emilia.name_chapstick_because_re_da_balm"),
    tr("emilia.do_have_name_can_call_mine_variant"),
    tr("emilia.m_not_photographer_but_can_definitely_picture_us"),
    tr("emilia.can_follow_home_parents_always_told_follow_dreams"),
    tr("emilia.if_were_vegetable_d_cute_cumber"),
    tr("emilia.campfire_because_re_hot_want_s_more"),
    tr("emilia.french_because_eiffel"),
    tr("emilia.do_have_sunburn_always_hot"),
    tr("emilia.name_google_because_have_everything_ve_searching"),
    tr("emilia.australian_because_when_look_at_feel_like_m"),
    tr("emilia.do_have_name_can_call_mine_variant"),
    tr("emilia.do_believe_fate_because_think_we_were_destined"),
    tr("emilia.name_wi_fi_because_m_really_feeling_connection"),
    tr("emilia.do_have_pencil_cause_want_erase_past_write"),
    tr("emilia.keyboard_because_re_type"),
    tr("emilia.if_were_cat_d_purr_fect"),
    tr("emilia.if_kisses_were_snowflakes_d_send_blizzard"),
    tr("emilia.made_copper_tellurium_because_re_cu_te"),
    tr("emilia.do_have_map_keep_getting_lost_eyes"),
    tr("emilia.campfire_because_re_hot_want_s_more"),
    tr("emilia.do_believe_love_at_first_chat"),
    tr("emilia.bank_loan_because_have_interest"),
    tr("emilia.name_chapstick_because_re_da_balm"),
    tr("emilia.must_snowflake_because_ve_fallen"),
    tr("emilia.wi_fi_because_m_feeling_connection"),
    tr("emilia.must_made_copper_tellurium_because_re_cu_te"),
]


@listen()
async def Emi_(client, message):
    if not message.text or not re.fullmatch(re.escape(Config.BOT_NAME), message.text.strip(), re.I):
        return
    if getattr(client, "is_clone", False):
        return
    uwu = random.choice(OWO)
    await message.reply_text(uwu, link_preview_options=LinkPreviewOptions(is_disabled=True))
