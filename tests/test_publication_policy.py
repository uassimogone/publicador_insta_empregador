import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.publication_policy import (
    already_published_today,
    already_selected_today,
    first_only,
    first_unpublished,
    mark_published_today,
)


class PublicationPolicyTests(unittest.TestCase):
    def test_first_only_keeps_oldest_item(self):
        self.assertEqual(
            first_only(["primeiro", "segundo", "terceiro"]),
            ["primeiro"],
        )

    def test_first_unpublished_never_advances_to_second_item(self):
        posts = [
            {"id": 1, "publicado": True},
            {"id": 2, "publicado": False},
        ]
        self.assertIsNone(first_unpublished(posts))

    def test_daily_selection_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            data_file = Path(directory) / "posts.json"
            today = datetime(2026, 9, 20, 13, 0, tzinfo=timezone.utc)
            data_file.write_text(
                '{"data_selecao": "2026-09-20", "posts": []}',
                encoding="utf-8",
            )
            self.assertTrue(already_selected_today(data_file, today))

    def test_daily_publication_lock_changes_with_brazil_day(self):
        with tempfile.TemporaryDirectory() as directory:
            state_file = Path(directory) / "estado.json"
            first_run = datetime(2026, 9, 20, 13, 0, tzinfo=timezone.utc)
            next_day = datetime(2026, 9, 21, 13, 0, tzinfo=timezone.utc)

            self.assertFalse(already_published_today(state_file, first_run))
            mark_published_today(state_file, first_run)
            self.assertTrue(already_published_today(state_file, first_run))
            self.assertFalse(already_published_today(state_file, next_day))


if __name__ == "__main__":
    unittest.main()
