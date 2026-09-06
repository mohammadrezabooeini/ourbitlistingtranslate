from pathlib import Path

from ourbit_selfbot.database import Database


def test_duplicate_message_is_detected(tmp_path: Path):
    db = Database(tmp_path / "bot.db")
    assert db.already_sent(-1001, 12345) is False

    db.upsert(-1001, 12345, symbol="FLORK", listing_type="spot", destination_message_id=99)
    assert db.already_sent(-1001, 12345) is True

    row = db.get(-1001, 12345)
    assert row is not None
    assert row.symbol == "FLORK"
    assert row.listing_type == "spot"
    assert row.destination_message_id == 99


def test_other_message_ids_are_independent(tmp_path: Path):
    db = Database(tmp_path / "bot.db")
    db.upsert("ourbit", 1, destination_message_id=10)
    assert db.already_sent("ourbit", 1) is True
    assert db.already_sent("ourbit", 2) is False


def test_edit_mapping_is_preserved(tmp_path: Path):
    db = Database(tmp_path / "bot.db")
    db.upsert("src", 7, symbol="ABC", listing_type="futures", destination_message_id=70)
    db.upsert("src", 7, symbol="ABC", listing_type="futures", destination_message_id=70)
    row = db.get("src", 7)
    assert row.destination_message_id == 70
