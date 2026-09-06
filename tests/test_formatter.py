import re

from ourbit_selfbot.formatter import custom_emoji, format_delisting, format_futures, format_spot
from ourbit_selfbot.parser import parse_delisting, parse_listing
from tests.samples import (
    DELIST_FUTURES_MANY,
    DELIST_FUTURES_ONE,
    DELIST_OURBIT_MANY,
    FUTURES_ABC,
    FUTURES_AIINU,
    SPOT_FLORK,
    SPOT_ORBIO,
)


def test_custom_emoji_helper_wraps_ids():
    rocket = custom_emoji("🚀")
    assert rocket == '<tg-emoji emoji-id="5145427681680032825">🚀</tg-emoji>'
    calendar = custom_emoji("🗓️")
    assert 'emoji-id="5472279086657199080"' in calendar
    assert "🗓" in calendar


def test_spot_flork_template():
    listing = parse_listing(SPOT_FLORK)
    html = format_spot(
        listing,
        translated_description="یک میم قدیمی و شناخته‌شده با بیش از **۱۰ سال سابقه** است.",
    )
    assert "#FLORK" in html
    assert "۱۰ شهریور" in html
    assert "۱۹:۲۰" in html
    assert "درباره" in html
    assert "FLORK" in html
    assert "۱۰ سال سابقه" in html
    assert "17827791513547" in html
    assert "t.me/ourbitfarsi" in html
    assert "لیستینگ جدید اوربیت" in html
    assert "بازار اسپات" in html
    from ourbit_selfbot.utils import ALM, RLI, RLM

    assert html.startswith(ALM)
    assert RLI in html
    assert "<blockquote>" in html
    quote_start = html.index("<blockquote>")
    assert html.index(RLI, quote_start) < html.index("سال سابقه", quote_start)
    plain = html.replace(ALM, "").replace(RLM, "")
    assert "<b>کی؟</b>\n<blockquote>" in plain
    assert "<b>کی؟</b>\n\n<blockquote>" not in plain
    assert re.search(r"<b>درباره .*</b>\n<blockquote>", plain)
    assert not re.search(r"<b>درباره .*</b>\n\n<blockquote>", plain)
    assert 'emoji-id="5145427681680032825"' in html
    assert 'emoji-id="5409048419211682843"' in html
    assert 'emoji-id="5447410659077661506"' in html
    assert 'emoji-id="6025887340180805506"' in html
    assert 'emoji-id="5325547803936572038"' in html
    assert "<tg-emoji" in html


def test_spot_orbio_template():
    listing = parse_listing(SPOT_ORBIO)
    html = format_spot(
        listing,
        translated_description="با نگهداری **$ORBIO** می‌توانید **اعتبار OpenRouter** دریافت کنید.",
    )
    assert "#ORBIO" in html
    assert "۱۱ شهریور" in html
    assert "۰۷:۰۰" in html
    assert "$ORBIO" in html
    assert "OpenRouter" in html
    assert "17827791513549" in html


def test_futures_aiinu_template():
    listing = parse_listing(FUTURES_AIINU)
    html = format_futures(listing)
    assert "توکن" in html
    assert "AIINU" in html
    assert "AIINU/USDT" in html
    assert "۷ شهریور" in html or "۰۷ شهریور" in html
    assert "۰۵:۵۰" in html
    assert "۲۰ برابر" in html
    assert "کراس و ایزوله" in html
    assert "ourbit.com" in html
    assert "17827791513496" in html
    assert "فیوچرز" in html
    from ourbit_selfbot.utils import ALM, RLM

    plain = html.replace(ALM, "").replace(RLM, "")
    assert "کی؟</b>\n<blockquote>" in plain
    assert "چطور؟</b>\n<blockquote>" in plain
    assert "کی؟</b>\n\n<blockquote>" not in plain
    assert "چطور؟</b>\n\n<blockquote>" not in plain
    assert 'emoji-id="5472279086657199080"' in html
    assert 'emoji-id="5364304072692222643"' in html
    assert 'emoji-id="5145427681680032825"' in html
    assert 'emoji-id="5409048419211682843"' in html


def test_futures_dynamic_symbol_and_leverage():
    listing = parse_listing(FUTURES_ABC)
    html = format_futures(listing)
    assert "توکن" in html
    assert "ABC" in html
    assert "ABC/USDT" in html
    assert "۵۰ برابر" in html
    assert "حالت ایزوله" in html
    assert "کراس و ایزوله" not in html
    assert "AIINU" not in html


def test_futures_cjk_symbol_is_formatted():
    from tests.samples import FUTURES_HAJIMI

    listing = parse_listing(FUTURES_HAJIMI)
    html = format_futures(listing)
    assert "哈基米" in html
    assert "哈基米/USDT" in html
    assert "۲۰ برابر" in html


def test_platform_section_omitted_when_missing():
    listing = parse_listing(FUTURES_AIINU)
    listing.platform_availability = False
    html = format_futures(listing)
    assert "بزن رو وب‌سایت" not in html


def test_delisting_template_is_bold_except_quoted_pairs():
    notice = parse_delisting(DELIST_FUTURES_MANY)
    html = format_delisting(notice)
    from ourbit_selfbot.utils import ALM, RLM

    plain = html.replace(ALM, "").replace(RLM, "")
    assert 'emoji-id="5877397384316592775"' in html
    assert 'emoji-id="5424818078833715060"' in html
    assert 'emoji-id="5271604874419647061"' in html
    assert "<blockquote>" in html
    quoted = re.search(r"<blockquote>(.*?)</blockquote>", plain, re.DOTALL).group(1)
    assert "DDOGUSDT" in quoted
    assert "URNMUSDT" in quoted
    assert "<b>" not in quoted
    assert "خواهند شد" in html
    assert "فیوچرز اوربیت" in html
    assert "۱۴ شهریور" in html
    assert "۱۰:۳۰" in html
    assert "17827791513574" in html
    assert "کاربران عزیز اوربیت" in html
    assert quoted.count("DDOGUSDT") == 1


def test_delisting_single_pair_uses_singular():
    notice = parse_delisting(DELIST_FUTURES_ONE)
    html = format_delisting(notice)
    assert "ASXUSDT" in html
    assert "خواهد شد" in html
    assert "خواهند شد" not in html
    assert "ارز های" not in html


def test_delisting_without_futures_word_uses_ourbit_market():
    notice = parse_delisting(DELIST_OURBIT_MANY)
    html = format_delisting(notice)
    assert "V4AIUSDT" in html
    assert "فیوچرز" not in html
    assert "اوربیت" in html
    assert "خواهند شد" in html
