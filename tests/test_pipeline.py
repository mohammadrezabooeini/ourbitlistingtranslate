import pytest

from ourbit_selfbot.config import TELEGRAM_CAPTION_LIMIT
from ourbit_selfbot.formatter import format_delisting, format_listing
from ourbit_selfbot.parser import parse_delisting, parse_listing
from ourbit_selfbot.telegram_client import (
    decide_send_mode,
    should_ignore_untracked_edit,
    should_notify_spot_user,
    source_has_attached_photo,
)
from ourbit_selfbot.translator import PassthroughBackend, Translator
from tests.samples import DELIST_FUTURES_MANY, FUTURES_AIINU, NOT_A_LISTING, SPOT_FLORK


@pytest.mark.asyncio
async def test_spot_description_is_translated_futures_is_not():
    calls: list[str] = []

    class SpyBackend:
        async def translate(self, text: str, preserve_terms):
            calls.append(text)
            return "ترجمه آزمایشی"

    translator = Translator(SpyBackend())

    spot = parse_listing(SPOT_FLORK)
    futures = parse_listing(FUTURES_AIINU)
    assert spot is not None and futures is not None

    translated = await translator.translate_spot_description(spot.description or "")
    spot_html = format_listing(spot, translated_description=translated)
    futures_html = format_listing(futures)

    assert calls == [spot.description]
    assert "ترجمه آزمایشی" in spot_html
    assert "Translating" not in futures_html
    assert "versatile OG meme" not in spot_html


@pytest.mark.asyncio
async def test_passthrough_translator_does_not_crash():
    translator = Translator(PassthroughBackend())
    result = await translator.translate_spot_description("The versatile OG meme.")
    assert "versatile OG meme" in result


def test_non_listing_does_not_produce_output():
    assert parse_listing(NOT_A_LISTING) is None
    assert parse_delisting(NOT_A_LISTING) is None


def test_delisting_is_formatted_without_translation():
    notice = parse_delisting(DELIST_FUTURES_MANY)
    html = format_delisting(notice)
    assert "DDOGUSDT" in html
    assert "کاربران عزیز اوربیت" in html
    assert decide_send_mode(has_photo=False, formatted=html) == "text"


def test_text_only_when_source_has_no_photo():
    listing = parse_listing(SPOT_FLORK)
    formatted = format_listing(listing, translated_description="توضیح")
    assert decide_send_mode(has_photo=False, formatted=formatted) == "text"


def test_same_photo_plus_caption_when_source_has_photo():
    listing = parse_listing(SPOT_FLORK)
    formatted = format_listing(listing, translated_description="توضیح")
    assert decide_send_mode(has_photo=True, formatted=formatted) == "photo_caption"


def test_webpage_preview_is_not_treated_as_photo():
    from telethon.tl.types import MessageMediaPhoto, MessageMediaWebPage, WebPageEmpty

    webpage_event = type("Event", (), {})()
    webpage_event.media = MessageMediaWebPage(webpage=WebPageEmpty(id=1))
    webpage_event.photo = object()
    assert source_has_attached_photo(webpage_event) is False

    photo_event = type("Event", (), {})()
    photo_event.media = MessageMediaPhoto()
    assert source_has_attached_photo(photo_event) is True


def test_photo_then_text_when_caption_is_too_long():
    oversized = "x" * (TELEGRAM_CAPTION_LIMIT + 50)
    assert decide_send_mode(has_photo=True, formatted=oversized) == "photo_then_text"


def test_spot_notify_only_for_first_spot_post():
    assert should_notify_spot_user("spot", already_posted=False, notify_user="@someone") is True
    assert should_notify_spot_user("spot", already_posted=True, notify_user="@someone") is False
    assert should_notify_spot_user("futures", already_posted=False, notify_user="@someone") is False
    assert should_notify_spot_user("delisting", already_posted=False, notify_user="@someone") is False
    assert should_notify_spot_user("spot", already_posted=False, notify_user=None) is False


def test_untracked_edits_are_not_posted_as_new():
    assert should_ignore_untracked_edit(is_edit=True, previously_seen=False) is True
    assert should_ignore_untracked_edit(is_edit=True, previously_seen=True) is False
    assert should_ignore_untracked_edit(is_edit=False, previously_seen=False) is False
