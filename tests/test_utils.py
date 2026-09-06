from datetime import datetime

from ourbit_selfbot.utils import (
    UTC,
    combine_utc_datetime,
    format_listing_when,
    markdown_bold_to_html,
    to_persian_digits,
    utc_to_tehran,
)


def test_flork_utc_to_tehran_and_jalali():
    utc_dt = combine_utc_datetime("September 1 2026", "15:50")
    assert utc_dt == datetime(2026, 9, 1, 15, 50, tzinfo=UTC)
    text, tehran, jalali = format_listing_when(utc_dt)
    assert tehran.hour == 19 and tehran.minute == 20
    assert jalali.day == 10
    assert "شهریور" in text
    assert "۱۰ شهریور" in text
    assert "۱۹:۲۰" in text


def test_orbio_utc_to_tehran_and_jalali():
    utc_dt = combine_utc_datetime("September 2 2026", "03:30")
    text, tehran, jalali = format_listing_when(utc_dt)
    assert tehran.hour == 7 and tehran.minute == 0
    assert jalali.day == 11
    assert "۱۱ شهریور" in text
    assert "۰۷:۰۰" in text


def test_aiinu_utc_to_tehran_and_jalali():
    utc_dt = combine_utc_datetime("August 29 2026", "02:20")
    text, tehran, jalali = format_listing_when(utc_dt)
    assert utc_to_tehran(utc_dt).hour == 5
    assert jalali.day == 7
    assert "۷ شهریور" in text or "۰۷ شهریور" in text
    assert "۰۵:۵۰" in text


def test_persian_digits():
    assert to_persian_digits("19:20") == "۱۹:۲۰"
    assert to_persian_digits(20) == "۲۰"
    assert to_persian_digits(50) == "۵۰"


def test_bold_conversion_keeps_cashtag():
    html = markdown_bold_to_html("با نگهداری **$ORBIO** می‌توانید **اعتبار OpenRouter** دریافت کنید.")
    assert html == "با نگهداری <b>$ORBIO</b> می‌توانید <b>اعتبار OpenRouter</b> دریافت کنید."


def test_force_rtl_message_prefixes_lines():
    from ourbit_selfbot.utils import ALM, RLE, RLM, force_rtl_message, ltr, rtl

    wrapped = force_rtl_message("سلام دنیا")
    assert wrapped.startswith(ALM)
    assert RLM in wrapped
    assert rtl("متن فارسی").startswith(RLE)
    assert "FLORK" in ltr("#FLORK")


def test_rtl_paragraph_keeps_leading_english():
    from ourbit_selfbot.utils import ALM, RLI, isolate_latin_tokens, rtl_paragraph

    original = "PAIR اولین لانچ‌پد چند‌پولی در Robinhood است که به کاربران امکان می‌دهد توکن‌ها را به‌صورت همزمان به سبدی از توکن‌های سهام کانونی متصل کنند."
    prepared = rtl_paragraph(isolate_latin_tokens(original))
    assert prepared.startswith(ALM)
    assert RLI in prepared
    assert prepared.index("PAIR") > 0
    assert "اولین لانچ‌پد" in prepared
    assert "Robinhood" in prepared
    # English start is preserved; only invisible RTL marks are added before it.
    without_marks = original.replace("PAIR", "").strip()
    assert "اولین" in without_marks
