"""Timezone conversion, Jalali dates, Persian digits, and logging helpers."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from zoneinfo import ZoneInfo

import jdatetime

UTC = ZoneInfo("UTC")
TEHRAN = ZoneInfo("Asia/Tehran")

PERSIAN_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")

# Unicode bidi marks so Telegram renders Persian as RTL without reversing URLs.
RLM = "\u200F"  # RIGHT-TO-LEFT MARK
ALM = "\u061C"  # ARABIC LETTER MARK
RLE = "\u202B"  # RIGHT-TO-LEFT EMBEDDING
LRE = "\u202A"  # LEFT-TO-RIGHT EMBEDDING
PDF = "\u202C"  # POP DIRECTIONAL FORMATTING
RLI = "\u2067"  # RIGHT-TO-LEFT ISOLATE
PDI = "\u2069"  # POP DIRECTIONAL ISOLATE

JALALI_MONTHS_FA = (
    "فروردین",
    "اردیبهشت",
    "خرداد",
    "تیر",
    "مرداد",
    "شهریور",
    "مهر",
    "آبان",
    "آذر",
    "دی",
    "بهمن",
    "اسفند",
)

JALALI_MONTHS_EN = (
    "Farvardin",
    "Ordibehesht",
    "Khordad",
    "Tir",
    "Mordad",
    "Shahrivar",
    "Mehr",
    "Aban",
    "Azar",
    "Dey",
    "Bahman",
    "Esfand",
)

def setup_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logging.getLogger("telethon").setLevel(logging.WARNING)


def to_persian_digits(value: str | int) -> str:
    return str(value).translate(PERSIAN_DIGITS)


def parse_month_day_year(date_text: str) -> datetime:
    cleaned = re.sub(r"\s+", " ", date_text.strip())
    cleaned = cleaned.replace(",", "")
    last_error: Exception | None = None
    for fmt in ("%B %d %Y", "%b %d %Y"):
        try:
            return datetime.strptime(cleaned, fmt)
        except ValueError as exc:
            last_error = exc
    raise ValueError(f"Unable to parse date: {date_text}") from last_error


def combine_utc_datetime(date_text: str, time_text: str) -> datetime:
    date_part = parse_month_day_year(date_text)
    time_part = datetime.strptime(time_text.strip(), "%H:%M")
    return datetime(
        date_part.year,
        date_part.month,
        date_part.day,
        time_part.hour,
        time_part.minute,
        tzinfo=UTC,
    )


def utc_to_tehran(dt_utc: datetime) -> datetime:
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=UTC)
    return dt_utc.astimezone(TEHRAN)


def tehran_to_jalali(dt_tehran: datetime) -> jdatetime.datetime:
    return jdatetime.datetime.fromgregorian(datetime=dt_tehran)


def format_jalali_log(jdt: jdatetime.datetime) -> str:
    month = JALALI_MONTHS_EN[jdt.month - 1]
    return f"{jdt.day} {month}"


def format_listing_when(dt_utc: datetime) -> tuple[str, datetime, jdatetime.datetime]:
    """Convert UTC listing time to Tehran, then Jalali. Returns (fa_text, tehran, jalali)."""
    tehran = utc_to_tehran(dt_utc)
    jalali = tehran_to_jalali(tehran)
    day = to_persian_digits(jalali.day)
    month = JALALI_MONTHS_FA[jalali.month - 1]
    hour = to_persian_digits(f"{tehran.hour:02d}")
    minute = to_persian_digits(f"{tehran.minute:02d}")
    text = f"{day} {month} ، ساعت {hour}:{minute}"
    return text, tehran, jalali


def telegram_utf16_length(text: str) -> int:
    """Telegram limits are counted in UTF-16 code units."""
    return len(text.encode("utf-16-le")) // 2


def html_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def markdown_bold_to_html(text: str) -> str:
    """Escape HTML, then turn **bold** markers into <b> tags.

    A function replacement is used so cashtags like $ORBIO are not
    treated as regex backreferences.
    """
    escaped = html_escape(text)
    return re.sub(r"\*\*(.+?)\*\*", lambda match: f"<b>{match.group(1)}</b>", escaped)


def ltr(text: str) -> str:
    """Keep tickers, pairs, and URLs left-to-right inside an RTL message."""
    if not text:
        return text
    return f"{LRE}{text}{PDF}"


def rtl(text: str) -> str:
    """Force a text run to render right-to-left."""
    if not text:
        return text
    if text.startswith((RLM, ALM, RLE)):
        return text
    return f"{RLE}{text}{PDF}"


def rtl_paragraph(text: str) -> str:
    """Force RTL paragraph direction even if the first visible word is English.

    Does not move or delete Latin words. Invisible RTL marks are inserted
    immediately before the original text so Telegram/Qt sees an RTL base
    direction, then PAIR/Robinhood stay in place as LTR islands.
    """
    if not text:
        return text
    core = text
    for mark in (ALM, RLM, RLI, RLE):
        if core.startswith(mark):
            core = core[len(mark) :]
    if core.endswith(PDI):
        core = core[: -len(PDI)]
    if core.endswith(PDF):
        core = core[: -len(PDF)]
    return f"{ALM}{RLM}{RLI}{core}{PDI}"


def isolate_latin_tokens(text: str) -> str:
    """Keep English tickers and brand names readable inside an RTL paragraph."""

    def replacer(match: re.Match[str]) -> str:
        token = match.group(1)
        if token.startswith(LRE):
            return token
        return ltr(token)

    return re.sub(
        r"(?<!\u202A)((?:\$|#)?[A-Za-z][A-Za-z0-9._-]{1,})",
        replacer,
        text,
    )


def force_rtl_message(text: str) -> str:
    """Make Telegram treat the whole caption/message as RTL.

    Each non-empty line gets an RTL mark. URLs and Latin identifiers should
    still be wrapped with ltr() by the caller so they are not reversed.
    """
    if not text:
        return text
    lines: list[str] = []
    for line in text.split("\n"):
        if not line.strip() or line.startswith((RLM, ALM, RLE)):
            lines.append(line)
            continue
        lines.append(f"{RLM}{line}")
    body = "\n".join(lines)
    if not body.startswith((ALM, RLM, RLE)):
        body = ALM + body
    elif not body.startswith(ALM):
        body = ALM + body
    return body
