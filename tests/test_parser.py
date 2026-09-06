from datetime import datetime

from ourbit_selfbot.parser import FUTURES, SPOT, parse_delisting, parse_listing
from ourbit_selfbot.utils import UTC
from tests.samples import (
    CASHTAG_ONLY,
    DELIST_FUTURES_MANY,
    DELIST_FUTURES_ONE,
    DELIST_OURBIT_MANY,
    FUTURES_ABC,
    FUTURES_AIINU,
    FUTURES_HAJIMI,
    NOT_A_LISTING,
    SPOT_FLORK,
    SPOT_ORBIO,
    SPOT_TOKEN123,
)


def test_spot_flork_extraction():
    listing = parse_listing(SPOT_FLORK)
    assert listing is not None
    assert listing.listing_type == SPOT
    assert listing.symbol == "FLORK"
    assert listing.pair == "FLORK/USDT"
    assert listing.article_url == "https://www.ourbit.com/support/articles/17827791513547"
    assert listing.trading_datetime_utc == datetime(2026, 9, 1, 15, 50, tzinfo=UTC)
    assert "versatile OG meme" in (listing.description or "")


def test_spot_orbio_extraction():
    listing = parse_listing(SPOT_ORBIO)
    assert listing is not None
    assert listing.listing_type == SPOT
    assert listing.symbol == "ORBIO"
    assert listing.pair == "ORBIO/USDT"
    assert listing.trading_datetime_utc == datetime(2026, 9, 2, 3, 30, tzinfo=UTC)
    assert listing.article_url.endswith("17827791513549")


def test_futures_aiinu_uses_launch_time_not_futures_date():
    listing = parse_listing(FUTURES_AIINU)
    assert listing is not None
    assert listing.listing_type == FUTURES
    assert listing.symbol == "AIINU"
    assert listing.pair == "AIINU/USDT"
    assert listing.leverage == 20
    assert listing.margin_modes == ["cross", "isolated"]
    assert listing.platform_availability is True
    assert listing.trading_datetime_utc == datetime(2026, 8, 29, 2, 20, tzinfo=UTC)
    assert listing.trading_datetime_utc.day != 26


def test_dynamic_symbols_are_not_hardcoded():
    spot = parse_listing(SPOT_TOKEN123)
    futures = parse_listing(FUTURES_ABC)
    assert spot is not None and spot.symbol == "TOKEN123"
    assert spot.pair == "TOKEN123/USDT"
    assert futures is not None and futures.symbol == "ABC"
    assert futures.pair == "ABC/USDT"
    assert futures.leverage == 50
    assert futures.margin_modes == ["isolated"]


def test_non_listing_messages_are_ignored():
    assert parse_listing(NOT_A_LISTING) is None
    assert parse_listing(CASHTAG_ONLY) is None
    assert parse_listing("") is None
    assert parse_listing("hello world") is None


def test_futures_cjk_symbol_is_not_ignored():
    listing = parse_listing(FUTURES_HAJIMI)
    assert listing is not None
    assert listing.listing_type == FUTURES
    assert listing.symbol == "哈基米"
    assert listing.pair == "哈基米/USDT"
    assert listing.leverage == 20
    assert listing.margin_modes == ["cross", "isolated"]
    assert listing.platform_availability is True
    assert listing.trading_datetime_utc == datetime(2026, 9, 6, 6, 30, tzinfo=UTC)
    assert listing.article_url.endswith("17827791513582")


def test_cashtag_alone_is_not_a_listing():
    text = "🚀#Ourbit $XYZ is pumping!\nCome trade now."
    assert parse_listing(text) is None


def test_delisting_futures_many_pairs():
    notice = parse_delisting(DELIST_FUTURES_MANY)
    assert notice is not None
    assert notice.market == "futures"
    assert notice.pairs[0] == "DDOGUSDT"
    assert notice.pairs[-1] == "URNMUSDT"
    assert "VUSDT" in notice.pairs
    assert notice.delisting_datetime_utc == datetime(2026, 9, 5, 7, 0, tzinfo=UTC)
    assert notice.article_url.endswith("17827791513574")
    assert parse_listing(DELIST_FUTURES_MANY) is None


def test_delisting_generic_ourbit_pairs():
    notice = parse_delisting(DELIST_OURBIT_MANY)
    assert notice is not None
    assert notice.market == "ourbit"
    assert notice.pairs == [
        "KINSUSDT",
        "VLRUSDT",
        "OVLUSDT",
        "UCNUSDT",
        "VIGIUSDT",
        "V4AIUSDT",
    ]
    assert notice.delisting_datetime_utc == datetime(2026, 9, 3, 8, 0, tzinfo=UTC)


def test_delisting_single_futures_pair():
    notice = parse_delisting(DELIST_FUTURES_ONE)
    assert notice is not None
    assert notice.market == "futures"
    assert notice.pairs == ["ASXUSDT"]
    assert notice.delisting_datetime_utc == datetime(2026, 9, 2, 8, 0, tzinfo=UTC)
    assert parse_delisting(SPOT_FLORK) is None
    assert parse_delisting(NOT_A_LISTING) is None
