# taiko-song-database-cn

A database of Taiko no Tatsujin(Chinese Ver.) songs

- `太鼓の達人™` is a trademark of `Bandai Namco Entertainment`.
- The repository is not related to `Bandai Namco Entertainment`.
- The copyright of the songs recorded in the this repository belongs to each copyright holder or copyright holders, and the copyrights of Fumens are belong to `Bandai Namco Entertainment`.

## Usage

- simply download the file `songs.json`
- use `https://cdn.ourtaiko.org/api/cnsongs`
- download `songs.sqlite3` for the current songs plus songs removed from the list

### SQLite archive

The `songs` table uses the original `id` from `songs.json` as its integer primary
key (and lookup index). Current songs always use the working `songs.json` data.
Songs missing from that file are recovered from their most recent occurrence in
Git history, across all locally available refs.

- `is_deleted`: `0` if present in current `songs.json`, `1` if absent. Absence does
  not establish why a song was removed or whether the removal is permanent.
- Song fields retain their original names. `types` is a JSON array; repeated
  category rows in old snapshots are combined into one song with all categories.
- `source_json` preserves the original first row for the song in the selected
  snapshot, including optional fields. The combined categories are in `types`.
- `last_seen_commit` and `last_seen_at` identify the Git snapshot supplying the
  data. Both are `NULL` for current data that differs from the latest archived
  version, including newly fetched songs that have not yet been committed.
- Difficulty columns preserve numbers and the `"-"` marker. `family` preserves
  legacy values (`"○"` or `NULL`); JSON booleans are stored as SQLite `0`/`1`.
  Missing optional fields are SQL `NULL`.

```sql
SELECT * FROM songs WHERE id = 120;
SELECT id, song_name, song_name_jp FROM songs WHERE is_deleted = 1 ORDER BY id;
SELECT COUNT(*) FROM songs WHERE is_deleted = 0;
```

Rebuild with Python 3.10+ (standard library only), from a full Git checkout:

```sh
python3 scripts/build_song_database.py
```

The builder refuses shallow clones so incomplete history cannot silently discard
archived songs. Use `git fetch --unshallow` first if necessary. It validates a
temporary database before replacing `songs.sqlite3`. Rebuilding the same inputs
produces the same database. The update workflow fetches full history and rebuilds
the archive after fetching the latest song list.

Run the archive regression tests with:

```sh
python3 -m unittest discover -s tests
```

## Update

The manually triggered update workflow refreshes `songs.json`, `songs_raw.json`,
the dated history snapshot, and `songs.sqlite3` each time the game updates.

## Data Type

``` json
[
    {
        "id": 1, 
        "open_day": "07/25/2023", 
        "song_name_jp": "てんぢく2000", 
        "song_name": "天竺2000", 
        "level_1": 4, 
        "level_2": 7, 
        "level_3": 8, 
        "level_4": 10, 
        "level_5": "-",
        "subtitle": string,
        "family": bool,
        "types": [
          {"type": string, "sort": number},
          ...
          ]
    },
    ...
]
```

## History

A song DB file for that date exists in the `history` folder.
