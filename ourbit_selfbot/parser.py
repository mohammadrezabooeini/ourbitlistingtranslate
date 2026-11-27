"""Detect Ourbit listings and extract structured fields. Symbol-agnostic."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime

from .utils import combine_utc_datetime

logger = logging.getLogger(__name__)

SPOT = "spot"
FUTURES = "futures"
DELISTING = "delisting"

OURBIT_RE = re.compile(r"#?Ourbit", re.IGNORECASE)
NEW_LISTING_RE = re.compile(r"\[\s*New\s+Listing\s*\]|New\s+Listing", re.IGNORECASE)
PERP_RE = re.compile(r"Perpetual\s+Futures", re.IGNORECASE)
FUTURES_WORD_RE = re.compile(r"\bFutures\b", re.IGNORECASE)

# ASCII tickers (FLORK) and CJK names (哈基米).
SYMBOL_RE = r"[A-Za-z0-9\u4e00-\u9fff]{1,32}"

SPOT_TRADING_RE = re.compile(
    rf"Trading for\s+\$?(?P<symbol>{SYMBOL_RE})/USDT:\s*"
    r"(?P<time>\d{1,2}:\d{2}),\s*"
    r"(?P<date>[A-Za-z]+\s+\d{1,2},?\s+\d{4})\s*\(UTC\)",
    re.IGNORECASE,
)

LAUNCH_TIME_RE = re.compile(
    rf"\$?(?P<symbol>{SYMBOL_RE})/USDT\s+Launch Time:\s*"
    r"(?P<date>[A-Za-z]+\s+\d{1,2},?\s+\d{4}),\s*"
    r"(?P<time>\d{1,2}:\d{2})\s*\(UTC\)",
    re.IGNORECASE,
)

TICKER_RE = re.compile(rf"\$({SYMBOL_RE})")
LEVERAGE_RE = re.compile(r"Up to\s+(\d+)\s*x", re.IGNORECASE)
ABOUT_RE = re.compile(
    r"About\s+[^\n]+\n+(?P<body>.*?)(?=\n\s*(?:👉|For more information)|\Z)",
    re.IGNORECASE | re.DOTALL,
)
URL_RE = re.compile(r"https?://[^\s\)\]]+", re.IGNORECASE)
PLATFORM_RE = re.compile(r"Accessible on\s+ourbit\.com", re.IGNORECASE)
DELIST_PROCESS_RE = re.compile(
    r"The delisting process will commence on\s+"
    r"(?P<time>\d{1,2}:\d{2}),\s*"
    r"(?P<date>[A-Za-z]+\s+\d{1,2},?\s+\d{4})\s*\(UTC\)",
    re.IGNORECASE,
)
DELIST_PAIRS_RE = re.compile(
    r"(?:that|pairs:)\s+(?P<chunk>.+?)\s+will be delisted from Ourbit"
    r"(?P<market>\s+Futures|\s+Spot)?",
    re.IGNORECASE | re.DOTALL,
)
PAIR_TOKEN_RE = re.compile(rf"({SYMBOL_RE}USDT)", re.IGNORECASE)


@dataclass
class ListingData:
    listing_type: str
    symbol: str
    pair: str
    trading_datetime_utc: datetime | None = None
    article_url: str | None = None
    description: str | None = None
    leverage: int | None = None
    margin_modes: list[str] = field(default_factory=list)
    platform_availability: bool = False
    raw_text: str = ""


@dataclass
class DelistingData:
    pairs: list[str]
    market: str
    delisting_datetime_utc: datetime
    article_url: str | None = None
    raw_text: str = ""


def parse_listing(text: str | None) -> ListingData | None:
    """Return structured listing data, or None if this is not an Ourbit listing."""
    if not text or not text.strip():
        return None

    if not OURBIT_RE.search(text) or not NEW_LISTING_RE.search(text):
        return None

    listing_type = detect_listing_type(text)
    if listing_type is None:
        return None

    try:
        if listing_type == SPOT:
            return _parse_spot(text)
        return _parse_futures(text)
    except Exception:
        logger.exception("Failed to parse listing message")
        return None


def parse_delisting(text: str | None) -> DelistingData | None:
    """Return structured delisting data, or None if this is not a delisting notice."""
    if not text or not text.strip():
        return None
    if not OURBIT_RE.search(text):
        return None
    if not re.search(r"will be delisted", text, re.IGNORECASE):
        return None
    if NEW_LISTING_RE.search(text):
        return None

    process = DELIST_PROCESS_RE.search(text)
    pairs_match = DELIST_PAIRS_RE.search(text)
    if process is None or pairs_match is None:
        return None

    pairs = [
        _normalize_symbol(token) for token in PAIR_TOKEN_RE.findall(pairs_match.group("chunk"))
    ]
    if not pairs:
        return None

    market_raw = (pairs_match.group("market") or "").strip().lower()
    if market_raw == "futures":
        market = "futures"
    elif market_raw == "spot":
        market = "spot"
    else:
        market = "ourbit"

    try:
        dt_utc = combine_utc_datetime(process.group("date"), process.group("time"))
    except ValueError:
        logger.exception("Failed to parse delisting datetime")
        return None

    return DelistingData(
        pairs=pairs,
        market=market,
        delisting_datetime_utc=dt_utc,
        article_url=_extract_article_url(text),
        raw_text=text,
    )


def detect_listing_type(text: str) -> str | None:
    if _looks_like_spot(text):
        return SPOT
    if _looks_like_futures(text):
        return FUTURES
    return None


def _looks_like_spot(text: str) -> bool:
    """Spot listings always carry a 'Trading for SYMBOL/USDT' time.

    Older posts also say 'Spot Trading Market'. Innovation Zone posts do not,
    so that phrase is not required.
    """
    return bool(SPOT_TRADING_RE.search(text))


def _looks_like_futures(text: str) -> bool:
    has_launch = bool(LAUNCH_TIME_RE.search(text))
    has_futures_context = bool(PERP_RE.search(text) or FUTURES_WORD_RE.search(text))
    return has_launch and has_futures_context


def _parse_spot(text: str) -> ListingData:
    match = SPOT_TRADING_RE.search(text)
    if not match:
        raise ValueError("Spot listing is missing a Trading for .../USDT datetime")

    symbol = _normalize_symbol(match.group("symbol"))
    pair = f"{symbol}/USDT"
    dt_utc = combine_utc_datetime(match.group("date"), match.group("time"))
    description = _extract_description(text)
    return ListingData(
        listing_type=SPOT,
        symbol=symbol,
        pair=pair,
        trading_datetime_utc=dt_utc,
        article_url=_extract_article_url(text),
        description=description,
        raw_text=text,
    )


def _parse_futures(text: str) -> ListingData:
    match = LAUNCH_TIME_RE.search(text)
    if not match:
        raise ValueError("Futures listing is missing a Launch Time datetime")

    symbol = _normalize_symbol(match.group("symbol"))
    pair = f"{symbol}/USDT"
    dt_utc = combine_utc_datetime(match.group("date"), match.group("time"))
    return ListingData(
        listing_type=FUTURES,
        symbol=symbol,
        pair=pair,
        trading_datetime_utc=dt_utc,
        article_url=_extract_article_url(text),
        leverage=_extract_leverage(text),
        margin_modes=_extract_margin_modes(text),
        platform_availability=bool(PLATFORM_RE.search(text)),
        raw_text=text,
    )


def _normalize_symbol(symbol: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9]+", symbol):
        return symbol.upper()
    return symbol


def _extract_description(text: str) -> str | None:
    match = ABOUT_RE.search(text)
    if not match:
        return None
    body = match.group("body").strip()
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    return body or None


def _extract_article_url(text: str) -> str | None:
    urls = URL_RE.findall(text)
    for url in urls:
        cleaned = url.rstrip(").,;\"'")
        if "ourbit.com" in cleaned.lower():
            return cleaned
    return urls[0].rstrip(").,;\"'") if urls else None


def _extract_leverage(text: str) -> int | None:
    match = LEVERAGE_RE.search(text)
    if not match:
        return None
    return int(match.group(1))


def _extract_margin_modes(text: str) -> list[str]:
    modes: list[str] = []
    lower = text.lower()
    if re.search(r"\bcross\b", lower):
        modes.append("cross")
    if re.search(r"\bisolated\b", lower):
        modes.append("isolated")
    return modes


def preserve_terms_for(listing: ListingData) -> list[str]:
    """Terms the translator must leave untouched."""
    terms = {
        listing.symbol,
        f"${listing.symbol}",
        f"#{listing.symbol}",
        listing.pair,
        "USDT",
        "Ourbit",
        "OURBIT",
        "OpenRouter",
    }
    if listing.description:
        terms.update(f"${m}" for m in TICKER_RE.findall(listing.description))
        terms.update(TICKER_RE.findall(listing.description))
    return [term for term in terms if term]
