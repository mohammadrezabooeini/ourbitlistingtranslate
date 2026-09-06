"""Build destination messages for Spot and Futures listings.

HTML parse mode is used because Telegram Markdown breaks on URLs that
contain underscores or query strings (Instagram/X official links).
The rendered look matches the requested Markdown templates.
"""

from __future__ import annotations

from .config import OFFICIAL_LINKS
from .parser import FUTURES, SPOT, DelistingData, ListingData
from .utils import (
    force_rtl_message,
    format_listing_when,
    html_escape,
    isolate_latin_tokens,
    ltr,
    markdown_bold_to_html,
    rtl,
    rtl_paragraph,
    to_persian_digits,
)

CUSTOM_EMOJIS = {
    "🚀": "5145427681680032825",
    "💵": "5409048419211682843",
    "🌐": "5447410659077661506",
    "🗓": "5472279086657199080",
    "🗓️": "5472279086657199080",
    "😀": "5364304072692222643",
    "🌟": "6025887340180805506",
    "✨": "5325547803936572038",
    "🎁": "5877397384316592775",
    "📣": "5424818078833715060",
    "🔗": "5271604874419647061",
}


def custom_emoji(emoji: str) -> str:
    """Render a Telegram custom emoji, falling back to the Unicode character."""
    fallback = "🗓" if emoji in {"🗓", "🗓️"} else emoji
    emoji_id = CUSTOM_EMOJIS[emoji]
    return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>'


def format_listing(listing: ListingData, translated_description: str | None = None) -> str:
    if listing.listing_type == SPOT:
        return format_spot(listing, translated_description)
    if listing.listing_type == FUTURES:
        return format_futures(listing)
    raise ValueError(f"Unknown listing type: {listing.listing_type}")


def format_delisting(delisting: DelistingData) -> str:
    when = _when_text(delisting.delisting_datetime_utc)
    pair_list = html_escape(_join_pairs(delisting.pairs))
    noun = "ارز" if len(delisting.pairs) == 1 else "ارز های"
    verb = "خواهد شد" if len(delisting.pairs) == 1 else "خواهند شد"
    market = _delisting_market_phrase(delisting.market)
    url = delisting.article_url
    parts = [
        f"<b>{custom_emoji('🎁')}کاربران عزیز اوربیت:</b>",
        "",
        f"<b>{custom_emoji('📣')}به اطلاع شما می‌رسانیم که {noun}:</b>",
        "",
        f"<blockquote>{ltr(pair_list)}</blockquote>",
        "",
        f"<b>از فهرست معاملات {market} در تاریخ {rtl(when)} حذف {verb}.</b>",
    ]
    if url:
        safe_url = html_escape(url)
        parts.extend(
            [
                "",
                f"<b>{custom_emoji('🔗')}：<a href=\"{safe_url}\">{ltr(safe_url)}</a></b>",
            ]
        )
    parts.extend(["", _official_links_block(heading_emoji="🎁", tight=True)])
    return force_rtl_message("\n".join(parts))


def format_spot(listing: ListingData, translated_description: str | None = None) -> str:
    when = _when_line(listing)
    symbol = html_escape(listing.symbol)
    parts = [
        f"<b>{custom_emoji('🚀')} [لیستینگ جدید اوربیت]{custom_emoji('🚀')}</b>",
        "",
        f"<b>{custom_emoji('💵')}توکن</b> {ltr('#' + symbol)}",
        "<b>در بازار اسپات اوربیت لیست شد !</b>",
        "",
        "<b>کی؟</b>",
        f"<blockquote><b>{rtl(when)}</b></blockquote>",
    ]

    about_body = translated_description if translated_description is not None else listing.description
    if about_body:
        description_html = markdown_bold_to_html(isolate_latin_tokens(about_body.strip()))
        parts.extend(
            [
                "",
                f"<b>درباره {ltr(symbol)} :</b>",
                f"<blockquote>{rtl_paragraph(description_html)}</blockquote>",
            ]
        )

    parts.extend(["", _more_info_block(listing.article_url, heading=f"{custom_emoji('🌐')}اطلاعات بیشتر :")])
    parts.extend(["", _official_links_block()])
    return force_rtl_message("\n".join(parts))


def format_futures(listing: ListingData) -> str:
    when = _when_line(listing)
    symbol = html_escape(listing.symbol)
    pair = html_escape(listing.pair)

    parts = [
        f"<b>{custom_emoji('🚀')}[لیستینگ جدید اوربیت!]{custom_emoji('🚀')}</b>",
        "",
        f"{custom_emoji('💵')}<b>توکن {ltr(symbol)}</b>",
        "<b>تو بازار فیوچرز اوربیت لیست شد!</b>",
        "",
        f"<b>{custom_emoji('🗓')} کی؟</b>",
        f"<blockquote><b>{rtl(when)}</b></blockquote>",
    ]

    how_lines = _futures_how_lines(listing, pair)
    if how_lines:
        quote = "\n".join(how_lines)
        parts.extend(
            [
                "",
                f"<b>{custom_emoji('💵')}چطور؟</b>",
                f"<blockquote>{rtl(quote)}</blockquote>",
            ]
        )

    if listing.platform_availability:
        parts.extend(
            [
                "",
                "<b>- بزن رو وب‌سایت</b> " + ltr("ourbit.com") + " <b>یا از اپ OURBIT معامله کن!</b>",
                "",
            ]
        )

    parts.extend(["", _more_info_block(listing.article_url, heading=f"{custom_emoji('😀')} اطلاعات بیشتر:")])
    parts.extend(["", _official_links_block()])
    return force_rtl_message("\n".join(parts))


def _when_line(listing: ListingData) -> str:
    return _when_text(listing.trading_datetime_utc)


def _when_text(dt_utc) -> str:
    if dt_utc is None:
        return "به‌زودی"
    text, _, _ = format_listing_when(dt_utc)
    return text


def _join_pairs(pairs: list[str]) -> str:
    if len(pairs) == 1:
        return pairs[0]
    if len(pairs) == 2:
        return f"{pairs[0]} & {pairs[1]}"
    return ", ".join(pairs[:-1]) + f" & {pairs[-1]}"


def _delisting_market_phrase(market: str) -> str:
    if market == "futures":
        return "فیوچرز اوربیت"
    if market == "spot":
        return "اسپات اوربیت"
    return "اوربیت"


def _futures_how_lines(listing: ListingData, pair: str) -> list[str]:
    lines: list[str] = []
    if listing.leverage is not None:
        leverage_fa = to_persian_digits(listing.leverage)
        lines.append(f"- معامله {ltr(pair)} با اهرم تا <b>{leverage_fa} برابر!</b>")
    margin_line = _margin_line(listing.margin_modes)
    if margin_line:
        lines.append(f"- {margin_line}")
    return lines


def _margin_line(modes: list[str]) -> str | None:
    has_cross = "cross" in modes
    has_isolated = "isolated" in modes
    if has_cross and has_isolated:
        return "حالت‌های کراس و ایزوله، هرجور راحتی!"
    if has_cross:
        return "حالت کراس"
    if has_isolated:
        return "حالت ایزوله"
    return None


def _more_info_block(url: str | None, heading: str) -> str:
    title = f"<b>{heading}</b>"
    if not url:
        return title
    safe_url = html_escape(url)
    return f"{title}\n<a href=\"{safe_url}\">{ltr(safe_url)}</a>"


def _official_links_block(heading_emoji: str = "🌟", tight: bool = False) -> str:
    group = html_escape(OFFICIAL_LINKS["telegram_group"])
    channel = html_escape(OFFICIAL_LINKS["telegram_channel"])
    instagram = html_escape(OFFICIAL_LINKS["instagram"])
    twitter = html_escape(OFFICIAL_LINKS["twitter"])
    sparkle = custom_emoji("✨")
    gap = "" if tight else " "
    links = (
        f"{sparkle} <a href=\"{group}\">گروه تلگرام</a> "
        f"{sparkle} <a href=\"{channel}\">چنل تلگرام</a> "
        f"{sparkle} <a href=\"{instagram}\">اینستاگرام</a> "
        f"{sparkle} <a href=\"{twitter}\">توییتر</a> {sparkle}"
    )
    heading = f"<b>{custom_emoji(heading_emoji)}{gap}لینک‌های رسمی صرافی OURBIT</b>"
    if tight:
        return f"{heading}\n<b>{links}</b>"
    return f"{heading}\n{links}"
