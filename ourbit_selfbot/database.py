"""SQLite storage for duplicate protection and destination message mapping."""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class ProcessedMessage:
    source_channel: str
    source_message_id: int
    symbol: str | None
    listing_type: str | None
    processed_at: str
    destination_message_id: int | None


class Database:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS processed_messages (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        source_channel TEXT NOT NULL,
                        source_message_id INTEGER NOT NULL,
                        symbol TEXT,
                        listing_type TEXT,
                        processed_at TEXT NOT NULL,
                        destination_message_id INTEGER,
                        UNIQUE(source_channel, source_message_id)
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_processed_lookup
                    ON processed_messages (source_channel, source_message_id)
                    """
                )
                conn.commit()
        except sqlite3.Error:
            logger.exception("Failed to initialize database at %s", self.path)
            raise

    def get(
        self, source_channel: str | int, source_message_id: int
    ) -> ProcessedMessage | None:
        channel = str(source_channel)
        try:
            with self._connect() as conn:
                row = conn.execute(
                    """
                    SELECT source_channel, source_message_id, symbol, listing_type,
                           processed_at, destination_message_id
                    FROM processed_messages
                    WHERE source_channel = ? AND source_message_id = ?
                    """,
                    (channel, source_message_id),
                ).fetchone()
        except sqlite3.Error:
            logger.exception("Database read failed for message %s", source_message_id)
            return None

        if row is None:
            return None
        return ProcessedMessage(
            source_channel=row["source_channel"],
            source_message_id=row["source_message_id"],
            symbol=row["symbol"],
            listing_type=row["listing_type"],
            processed_at=row["processed_at"],
            destination_message_id=row["destination_message_id"],
        )

    def already_sent(self, source_channel: str | int, source_message_id: int) -> bool:
        row = self.get(source_channel, source_message_id)
        return bool(row and row.destination_message_id is not None)

    def upsert(
        self,
        source_channel: str | int,
        source_message_id: int,
        symbol: str | None = None,
        listing_type: str | None = None,
        destination_message_id: int | None = None,
    ) -> None:
        channel = str(source_channel)
        now = datetime.now(timezone.utc).isoformat()
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO processed_messages (
                        source_channel, source_message_id, symbol, listing_type,
                        processed_at, destination_message_id
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(source_channel, source_message_id) DO UPDATE SET
                        symbol = COALESCE(excluded.symbol, processed_messages.symbol),
                        listing_type = COALESCE(excluded.listing_type, processed_messages.listing_type),
                        processed_at = excluded.processed_at,
                        destination_message_id = COALESCE(
                            excluded.destination_message_id,
                            processed_messages.destination_message_id
                        )
                    """,
                    (
                        channel,
                        source_message_id,
                        symbol,
                        listing_type,
                        now,
                        destination_message_id,
                    ),
                )
                conn.commit()
        except sqlite3.Error:
            logger.exception(
                "Database write failed for source message %s", source_message_id
            )
            raise
