"""Entry point for the Ourbit listing self-bot."""

from __future__ import annotations

import asyncio
import logging
import sys

from .config import load_config
from .database import Database
from .telegram_client import OurbitSelfBot
from .translator import Translator
from .utils import setup_logging

logger = logging.getLogger(__name__)


async def run_bot() -> None:
    setup_logging()
    try:
        config = load_config()
    except Exception:
        logger.exception("Failed to load configuration")
        sys.exit(1)

    database = Database(config.db_path)
    translator = Translator.from_config(config)
    bot = OurbitSelfBot(config, database, translator)

    retry_delay = 5
    while True:
        try:
            await bot.run()
            logger.warning("Disconnected from Telegram. Reconnecting in %s seconds...", retry_delay)
        except KeyboardInterrupt:
            logger.info("Stopped by user.")
            break
        except Exception:
            logger.exception("Telegram connection error. Retrying in %s seconds...", retry_delay)
        await asyncio.sleep(retry_delay)
        retry_delay = min(retry_delay * 2, 60)


def main() -> None:
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
