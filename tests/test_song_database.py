import json
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest

from scripts.build_song_database import build_database


def song(song_id, name, **fields):
    return {
        "id": song_id,
        "song_name": name,
        "song_name_jp": name,
        "level_1": 3,
        "level_5": "-",
        **fields,
    }


class SongDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.repo = Path(self.temporary.name) / "repo"
        self.repo.mkdir()
        self.git("init", "-q")
        self.git("config", "user.name", "Archive test")
        self.git("config", "user.email", "archive-test@example.invalid")
        self.git("config", "commit.gpgsign", "false")
        self.write_songs([
            song(1, "Initial"), song(2, "Removed, old name"), song(3, "Returns"),
        ])
        self.commit("Initial songs")
        self.removed_song = song(
            2, "Removed, latest name", type="Pop", sort=10,
            family="○", extra_field={"preserved": True},
        )
        self.write_songs([
            song(1, "Updated"),
            self.removed_song,
            {**self.removed_song, "type": "Anime", "sort": 20},
        ])
        self.last_seen = self.commit("Update and categorize songs")
        self.write_songs([song(1, "Latest"), song(3, "Returns")])
        self.head = self.commit("Remove song 2 and restore song 3")
        self.output = self.repo / "songs.sqlite3"

    def git(self, *args):
        return subprocess.check_output(
            ["git", "-C", str(self.repo), *args], text=True,
            stderr=subprocess.PIPE,
        ).strip()

    def write_songs(self, songs):
        (self.repo / "songs.json").write_text(
            json.dumps(songs, ensure_ascii=False), encoding="utf-8"
        )

    def commit(self, message):
        self.git("add", "songs.json")
        self.git("commit", "-qm", message)
        return self.git("rev-parse", "HEAD")

    def connection(self):
        connection = sqlite3.connect(self.output)
        connection.row_factory = sqlite3.Row
        self.addCleanup(connection.close)
        return connection

    def test_recovers_latest_deleted_data_and_merges_categories(self):
        counts = build_database(self.repo)
        self.assertEqual(counts, {"snapshots": 3, "total": 3, "current": 2, "deleted": 1})
        connection = self.connection()
        removed = connection.execute("SELECT * FROM songs WHERE id = 2").fetchone()
        self.assertEqual(removed["song_name"], "Removed, latest name")
        self.assertEqual(removed["is_deleted"], 1)
        self.assertEqual(removed["last_seen_commit"], self.last_seen)
        self.assertEqual(json.loads(removed["types"]), [
            {"type": "Pop", "sort": 10}, {"type": "Anime", "sort": 20},
        ])
        self.assertEqual(json.loads(removed["source_json"]), self.removed_song)
        self.assertEqual(removed["family"], "○")
        self.assertEqual(removed["level_1"], 3)
        self.assertEqual(removed["level_5"], "-")
        self.assertIsNone(removed["subtitle"])
        restored = connection.execute("SELECT * FROM songs WHERE id = 3").fetchone()
        self.assertEqual(restored["is_deleted"], 0)
        self.assertEqual(restored["last_seen_commit"], self.head)
        self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        with self.assertRaises(sqlite3.IntegrityError):
            connection.execute("INSERT INTO songs SELECT * FROM songs WHERE id = 2")

    def test_working_file_overrides_history_and_includes_new_songs(self):
        self.write_songs([
            song(1, "Working update"), song(3, "Returns"), song(4, "New", family=False),
        ])
        self.assertEqual(build_database(self.repo)["total"], 4)
        rows = {
            row["id"]: row for row in self.connection().execute("SELECT * FROM songs")
        }
        self.assertEqual(rows[1]["song_name"], "Working update")
        self.assertIsNone(rows[1]["last_seen_commit"])
        self.assertIsNone(rows[4]["last_seen_commit"])
        self.assertIsNone(rows[4]["last_seen_at"])
        self.assertEqual(rows[4]["is_deleted"], 0)
        self.assertEqual(rows[4]["family"], 0)
        self.assertEqual(rows[3]["last_seen_commit"], self.head)

    def test_rebuild_is_identical(self):
        build_database(self.repo)
        original = self.output.read_bytes()
        build_database(self.repo)
        self.assertEqual(self.output.read_bytes(), original)

    def test_invalid_input_does_not_replace_existing_database(self):
        build_database(self.repo)
        original = self.output.read_bytes()
        self.write_songs([{"id": 1}])
        with self.assertRaises(sqlite3.IntegrityError):
            build_database(self.repo)
        self.assertEqual(self.output.read_bytes(), original)
        self.assertEqual(list(self.repo.glob(".songs.sqlite3.*")), [])

    def test_duplicate_metadata_uses_first_row_like_fetcher(self):
        self.write_songs([
            song(1, "First", subtitle="東方", level_5=10, type="Pop", sort=10),
            song(1, "First", subtitle="东方", level_5="-", type="Anime", sort=20),
        ])
        build_database(self.repo)
        row = self.connection().execute("SELECT * FROM songs WHERE id = 1").fetchone()
        self.assertEqual(row["subtitle"], "東方")
        self.assertEqual(row["level_5"], 10)
        self.assertEqual(len(json.loads(row["types"])), 2)

    def test_shallow_history_is_rejected(self):
        shallow = Path(self.temporary.name) / "shallow"
        self.git("clone", "-q", "--depth=1", self.repo.as_uri(), str(shallow))
        with self.assertRaisesRegex(ValueError, "Full Git history is required"):
            build_database(shallow)
        self.assertFalse((shallow / "songs.sqlite3").exists())

    def test_recovers_songs_from_other_local_refs(self):
        self.git("checkout", "-qb", "archived-catalog")
        self.write_songs([song(5, "Other branch")])
        other_commit = self.commit("Songs on another ref")
        self.git("checkout", "--detach", "-q", self.head)
        build_database(self.repo)
        row = self.connection().execute("SELECT * FROM songs WHERE id = 5").fetchone()
        self.assertEqual(row["song_name"], "Other branch")
        self.assertEqual(row["last_seen_commit"], other_commit)
        self.assertEqual(row["is_deleted"], 1)


if __name__ == "__main__":
    unittest.main()
