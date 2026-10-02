"""Build the current and historical song archive using only the Python stdlib."""

import argparse
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile


REPO_ROOT = Path(__file__).resolve().parents[1]
SONG_FIELDS = (
    "id", "open_day", "song_name_jp", "song_name",
    "level_1", "level_2", "level_3", "level_4", "level_5",
    "subtitle", "family", "tag", "type", "sort",
)
SCHEMA = """
CREATE TABLE songs (
    id INTEGER PRIMARY KEY,
    open_day TEXT,
    song_name_jp TEXT NOT NULL,
    song_name TEXT NOT NULL,
    level_1,
    level_2,
    level_3,
    level_4,
    level_5,
    subtitle TEXT,
    family,
    tag TEXT,
    type TEXT,
    sort INTEGER,
    types TEXT NOT NULL CHECK (json_valid(types)),
    is_deleted INTEGER NOT NULL CHECK (is_deleted IN (0, 1)),
    last_seen_commit TEXT,
    last_seen_at TEXT,
    source_json TEXT NOT NULL CHECK (json_valid(source_json))
);
PRAGMA user_version = 1;
"""


def git(repo, *args):
    return subprocess.check_output(
        ["git", "-C", str(repo), *args], text=True, encoding="utf-8"
    ).strip()


def json_text(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def group_songs(songs):
    """Old snapshots repeat songs by category; keep every category once."""
    if not isinstance(songs, list):
        raise ValueError("Song snapshots must be JSON arrays")
    grouped = {}
    for song in songs:
        if not isinstance(song, dict) or type(song.get("id")) is not int:
            raise ValueError("Every song must have an integer id")
        song_id = song["id"]
        if song_id not in grouped:
            grouped[song_id] = {"song": song, "types": []}
        entry = grouped[song_id]
        # Match the fetcher's first-row policy even when old category rows
        # disagree on subtitles or difficulty. Merge only the categories.
        categories = list(song.get("types", []))
        if song.get("type") is not None:
            categories.append({"type": song["type"], "sort": song.get("sort")})
        for category in categories:
            if category not in entry["types"]:
                entry["types"].append(category)
    return grouped


def collect_songs(repo):
    if git(repo, "rev-parse", "--is-shallow-repository") == "true":
        raise ValueError(
            "Full Git history is required; run git fetch --unshallow first"
        )

    current = group_songs(json.loads((repo / "songs.json").read_text(encoding="utf-8")))
    history = git(
        repo, "log", "--all", "--full-history", "--topo-order",
        "--format=%H%x09%cI", "--", "songs.json",
    )
    records = {}
    snapshot_count = 0
    # Newest snapshots win. Do not replace deleted songs with older metadata.
    for revision in history.splitlines():
        commit, committed_at = revision.split("\t")
        if not git(repo, "ls-tree", "--name-only", commit, "--", "songs.json"):
            continue
        snapshot = group_songs(json.loads(git(repo, "show", f"{commit}:songs.json")))
        snapshot_count += 1
        for song_id, entry in snapshot.items():
            if song_id not in records:
                records[song_id] = {
                    **entry,
                    "last_seen_commit": commit,
                    "last_seen_at": committed_at,
                    "is_deleted": song_id not in current,
                }

    # The working file is authoritative, including changes not yet committed.
    for song_id, entry in current.items():
        previous = records.get(song_id)
        unchanged = previous is not None and all(
            previous[key] == entry[key] for key in ("song", "types")
        )
        records[song_id] = {
            **entry,
            "last_seen_commit": previous["last_seen_commit"] if unchanged else None,
            "last_seen_at": previous["last_seen_at"] if unchanged else None,
            "is_deleted": False,
        }
    return records, snapshot_count


def build_database(repo=REPO_ROOT, output=None):
    repo = Path(repo).resolve()
    output = Path(output).resolve() if output else repo / "songs.sqlite3"
    records, snapshot_count = collect_songs(repo)
    columns = (*SONG_FIELDS, "types", "is_deleted", "last_seen_commit", "last_seen_at", "source_json")
    rows = []
    for song_id in sorted(records):
        entry = records[song_id]
        song = entry["song"]
        rows.append((
            *(song.get(field) for field in SONG_FIELDS),
            json_text(entry["types"]),
            int(entry["is_deleted"]),
            entry["last_seen_commit"],
            entry["last_seen_at"],
            json_text(song),
        ))

    # Build and verify a separate file so a failure cannot damage the archive.
    descriptor, temporary_path = tempfile.mkstemp(
        prefix=f".{output.name}.", suffix=".tmp", dir=output.parent
    )
    os.close(descriptor)
    connection = None
    try:
        connection = sqlite3.connect(temporary_path)
        connection.executescript(SCHEMA)
        connection.executemany(
            f"INSERT INTO songs ({', '.join(columns)}) "
            f"VALUES ({', '.join('?' for _ in columns)})",
            rows,
        )
        connection.commit()
        if connection.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise RuntimeError("SQLite integrity check failed")
        connection.close()
        connection = None
        os.chmod(temporary_path, 0o644)
        os.replace(temporary_path, output)
    finally:
        if connection is not None:
            connection.close()
        Path(temporary_path).unlink(missing_ok=True)

    deleted_count = sum(entry["is_deleted"] for entry in records.values())
    return {
        "snapshots": snapshot_count,
        "total": len(records),
        "current": len(records) - deleted_count,
        "deleted": deleted_count,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Output SQLite file (default: songs.sqlite3)")
    args = parser.parse_args()
    counts = build_database(output=args.output)
    print(
        f"Archived {counts['total']} songs: {counts['current']} current, "
        f"{counts['deleted']} deleted, from {counts['snapshots']} Git snapshots."
    )


if __name__ == "__main__":
    main()
