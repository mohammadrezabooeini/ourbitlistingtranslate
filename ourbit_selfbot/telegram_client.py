"""Telethon client, event handlers, and outgoing send/edit logic."""

from __future__ import annotations

import asyncio
import logging
from getpass import getpass
from typing import Literal

from telethon import TelegramClient, events
from telethon.errors import (
    FloodWaitError,
    MediaCaptionTooLongError,
    MessageIdInvalidError,
    MessageNotModifiedError,
)
from telethon.extensions import html as html_parser
from telethon.tl.types import MessageMediaPhoto

from .config import TELEGRAM_CAPTION_LIMIT, Config
from .database import Database
from .formatter import format_delisting, format_listing
from .parser import DELISTING, SPOT, ListingData, parse_delisting, parse_listing, preserve_terms_for
from .translator import Translator
from .utils import JALALI_MONTHS_EN, format_listing_when, telegram_utf16_length

logger = logging.getLogger(__name__)

SendMode = Literal["text", "photo_caption", "photo_then_text"]


def source_has_attached_photo(message) -> bool:
    """True only for a real photo attachment, not a URL link-preview."""
    return isinstance(getattr(message, "media", None), MessageMediaPhoto)


def should_notify_spot_user(
    listing_type: str | None,
    is_edit: bool,
    notify_user: str | int | None,
) -> bool:
    return bool(notify_user) and listing_type == SPOT and not is_edit


def decide_send_mode(
    has_photo: bool,
    formatted: str,
    caption_limit: int = TELEGRAM_CAPTION_LIMIT,
) -> SendMode:
    if not has_photo:
        return "text"
    visible_text, _ = html_parser.parse(formatted)
    if telegram_utf16_length(visible_text) <= caption_limit:
        return "photo_caption"
    return "photo_then_text"


class OurbitSelfBot:
    def __init__(self, config: Config, database: Database, translator: Translator) -> None:
        self.config = config
        self.db = database
        self.translator = translator
        self.client = TelegramClient(
            config.session_path,
            config.api_id,
            config.api_hash,
            flood_sleep_threshold=60,
        )
        self._register_handlers()

    def _register_handlers(self) -> None:
        source = self.config.source_channel

        @self.client.on(events.NewMessage(chats=source))
        async def on_new_message(event: events.NewMessage.Event) -> None:
            await self.handle_new_message(event)

        @self.client.on(events.MessageEdited(chats=source))
        async def on_message_edited(event: events.MessageEdited.Event) -> None:
            await self.handle_edited_message(event)

    async def start(self) -> None:
        password = self.config.telegram_2fa_password
        await self.client.start(
            phone=self.config.phone_number,
            password=password if password else (lambda: getpass("Two-factor password: ")),
        )
        me = await self.client.get_me()
        logger.info("Connected to Telegram")
        logger.info("Logged in as %s (id=%s)", getattr(me, "username", None) or me.id, me.id)
        logger.info("Monitoring source channel: %s", self.config.source_channel)
        logger.info("Destination channel: %s", self.config.destination_channel)
        if self.config.spot_notify_user:
            logger.info("Spot listings also go to user: %s", self.config.spot_notify_user)

    async def run(self) -> None:
        await self.start()
        logger.info("Monitoring source channel...")
        await self.client.run_until_disconnected()

    async def handle_new_message(self, event: events.NewMessage.Event) -> None:
        try:
            await self._process_event(event, is_edit=False)
        except Exception:
            logger.exception("Unhandled error while processing message %s", event.id)

    async def handle_edited_message(self, event: events.MessageEdited.Event) -> None:
        try:
            await self._process_event(event, is_edit=True)
        except Exception:
            logger.exception("Unhandled error while processing edited message %s", event.id)

    async def _process_event(self, event, is_edit: bool) -> None:
        message_id = event.id
        chat_id = event.chat_id
        logger.info(
            "%s: %s",
            "Edited message received" if is_edit else "New message received",
            message_id,
        )
        logger.info("Checking message...")

        existing = self.db.get(chat_id, message_id)
        if not is_edit and existing and existing.destination_message_id is not None:
            logger.info("Duplicate → Skip")
            return

        listing = parse_listing(event.raw_text)
        delisting = None if listing is not None else parse_delisting(event.raw_text)
        if listing is None and delisting is None:
            logger.info("Ignored: Not an Ourbit listing or delisting")
            return

        if listing is not None:
            logger.info("Ourbit Listing detected")
            self._log_listing(listing)
            formatted = await self._build_formatted_message(listing)
            symbol = listing.symbol
            listing_type = listing.listing_type
        else:
            logger.info("Ourbit Delisting detected")
            self._log_delisting(delisting)
            formatted = format_delisting(delisting)
            symbol = ",".join(delisting.pairs)
            listing_type = DELISTING

        logger.info("Formatting message...")

        has_photo = source_has_attached_photo(event)
        logger.info("Photo detected: %s", "YES" if has_photo else "NO")

        if is_edit and existing and existing.destination_message_id is not None:
            await self._edit_destination(existing.destination_message_id, formatted, has_photo)
            self.db.upsert(
                chat_id,
                message_id,
                symbol=symbol,
                listing_type=listing_type,
                destination_message_id=existing.destination_message_id,
            )
            return

        logger.info("Sending to destination...")
        dest_id = await self._send_to_destination(event, formatted, has_photo)
        if dest_id is None:
            logger.error("Failed to send announcement for source message %s", message_id)
            return

        self.db.upsert(
            chat_id,
            message_id,
            symbol=symbol,
            listing_type=listing_type,
            destination_message_id=dest_id,
        )
        logger.info("Successfully sent announcement.")
        if should_notify_spot_user(listing_type, is_edit, self.config.spot_notify_user):
            await self._notify_spot_user(event, formatted, has_photo)

    async def _build_formatted_message(self, listing: ListingData) -> str:
        translated = None
        if listing.listing_type == SPOT and listing.description:
            logger.info("Translating Spot description...")
            translated = await self.translator.translate_spot_description(
                listing.description,
                preserve_terms=preserve_terms_for(listing),
            )
        return format_listing(listing, translated_description=translated)

    def _log_listing(self, listing: ListingData) -> None:
        logger.info("Listing Type: %s", listing.listing_type.upper())
        logger.info("Symbol: %s", listing.symbol)
        if listing.pair:
            logger.info("Pair: %s", listing.pair)
        if listing.trading_datetime_utc is not None:
            utc_dt = listing.trading_datetime_utc
            _, tehran, jalali = format_listing_when(utc_dt)
            logger.info("UTC datetime: %s", utc_dt.strftime("%Y-%m-%d %H:%M"))
            logger.info("Tehran datetime: %s", tehran.strftime("%Y-%m-%d %H:%M"))
            logger.info("Jalali date: %s", f"{jalali.day} {_month_en(jalali.month)}")
        if listing.listing_type != SPOT:
            if listing.leverage is not None:
                logger.info("Leverage: %sx", listing.leverage)
            if listing.margin_modes:
                pretty = " + ".join(mode.capitalize() for mode in listing.margin_modes)
                logger.info("Margin: %s", pretty)

    def _log_delisting(self, delisting) -> None:
        logger.info("Announcement Type: DELISTING")
        logger.info("Pairs: %s", ", ".join(delisting.pairs))
        logger.info("Market: %s", delisting.market)
        utc_dt = delisting.delisting_datetime_utc
        _, tehran, jalali = format_listing_when(utc_dt)
        logger.info("UTC datetime: %s", utc_dt.strftime("%Y-%m-%d %H:%M"))
        logger.info("Tehran datetime: %s", tehran.strftime("%Y-%m-%d %H:%M"))
        logger.info("Jalali date: %s", f"{jalali.day} {_month_en(jalali.month)}")

    async def _notify_spot_user(self, event, formatted: str, has_photo: bool) -> None:
        user = self.config.spot_notify_user
        if user is None:
            return
        logger.info("Sending Spot listing to user %s...", user)
        sent_id = await self._send_to_peer(event, formatted, has_photo, user)
        if sent_id is None:
            logger.error("Failed to send Spot listing to user %s", user)
            return
        logger.info("Successfully sent Spot listing to user %s", user)

    async def _send_to_destination(self, event, formatted: str, has_photo: bool) -> int | None:
        return await self._send_to_peer(
            event, formatted, has_photo, self.config.destination_channel
        )

    async def _send_to_peer(self, event, formatted: str, has_photo: bool, dest) -> int | None:
        mode = decide_send_mode(has_photo, formatted)
        try:
            if mode == "text":
                sent = await self.client.send_message(dest, formatted, parse_mode="html")
                return sent.id

            if mode == "photo_caption":
                try:
                    sent = await self.client.send_file(
                        dest,
                        event.media,
                        caption=formatted,
                        parse_mode="html",
                    )
                    return _first_message_id(sent)
                except MediaCaptionTooLongError:
                    logger.warning("Caption too long; sending photo then text separately.")
                    mode = "photo_then_text"
                except TypeError:
                    logger.warning("Source media is not a sendable file; sending text only.")
                    sent = await self.client.send_message(dest, formatted, parse_mode="html")
                    return sent.id

            photo = await self.client.send_file(dest, event.media)
            text_msg = await self.client.send_message(dest, formatted, parse_mode="html")
            logger.info("Sent photo id=%s and text id=%s", _first_message_id(photo), text_msg.id)
            return text_msg.id
        except FloodWaitError as exc:
            logger.warning("Flood wait: sleeping %s seconds", exc.seconds)
            await asyncio.sleep(exc.seconds + 1)
            return None
        except Exception:
            logger.exception("Telegram send failed")
            return None

    async def _edit_destination(self, dest_message_id: int, formatted: str, has_photo: bool) -> None:
        dest = self.config.destination_channel
        logger.info("Updating destination message %s", dest_message_id)
        try:
            await self.client.edit_message(
                dest,
                dest_message_id,
                formatted,
                parse_mode="html",
            )
            logger.info("Successfully updated destination message.")
        except MessageNotModifiedError:
            logger.info("Destination message already matches the new content.")
        except MessageIdInvalidError:
            logger.warning("Destination message %s can no longer be edited.", dest_message_id)
        except Exception:
            logger.exception("Failed to edit destination message %s", dest_message_id)


def _first_message_id(sent) -> int:
    if isinstance(sent, list):
        return sent[0].id
    return sent.id


def _month_en(month: int) -> str:
    return JALALI_MONTHS_EN[month - 1]
