import datetime
import json
import os
import requests


song_type_list = [
    "流行音乐",
    "儿童音乐",
    "动漫音乐",
    "博歌乐音乐",
    "游戏音乐",
    "综合音乐",
    "古典音乐",
    "南梦宫原创音乐",
]

OptionalFields = [("subtitle", str), ("family", bool)]


def build_song_types_map(songs_data):
    """按歌曲id聚合所有分类及其sort，并保持首次出现顺序。"""
    types_map = {}

    for song in songs_data:
        song_id = song.get("id")
        if song_id is None:
            continue

        if song_id not in types_map:
            types_map[song_id] = []

        type_item = {"type": song.get("type"), "sort": song.get("sort")}
        if type_item not in types_map[song_id]:
            types_map[song_id].append(type_item)

    return types_map


def fetch_and_save_songs():
    """
    从API获取歌曲数据并保存到public/songs_cn.json
    """
    api_url = os.getenv("TAIKO_API_URL")
    api_token = os.getenv("TAIKO_API_TOKEN")

    if not api_url:
        raise ValueError("环境变量 TAIKO_API_URL 未设置")
    if not api_token:
        raise ValueError("环境变量 TAIKO_API_TOKEN 未设置")

    songs_data = []

    try:
        for i in range(len(song_type_list)):
            current_url = api_url + song_type_list[i]
            response = requests.get(
                current_url,
                headers={
                    "Authorization": api_token,
                    "Content-Type": "application/json",
                },
                params={"page": 1, "pageSize": 600, "sort": 0},
            )
            response.raise_for_status()

            result = response.json()
            current_datas = result["data"]["data"]
            for data in current_datas:
                song_info = data["song_info"]

                # Should not have been present
                if "top_score" in song_info:
                    song_info = {
                        k: v
                        for k, v in song_info.items()
                        if k != "top_score" and k != "isPlayed"
                    }

                # Should have been present
                for field, field_type in OptionalFields:
                    if field not in song_info:
                        song_info[field] = field_type()
                    elif not isinstance(song_info[field], field_type):
                        song_info[field] = field_type(song_info[field])

                songs_data.append(song_info)

        types_map = build_song_types_map(songs_data)

        unique_songs = []
        seen_ids = set()
        for song in songs_data:
            song_id = song.get("id")
            if song_id in seen_ids:
                continue

            song["types"] = types_map.get(song_id, [])
            song.pop("type", None)
            song.pop("sort", None)
            unique_songs.append(song)
            seen_ids.add(song_id)

        songs_data = unique_songs
        songs_data.sort(key=lambda x: x["id"])

        os.makedirs("history", exist_ok=True)

        with open(
            f"history/songs_cn_{int(datetime.datetime.now().timestamp())}.json",
            "x",
            encoding="utf-8",
        ) as f:
            json.dump(
                songs_data,
                f,
                ensure_ascii=False,
            )
        with open("songs.json", "w", encoding="utf-8") as f:
            json.dump(
                songs_data,
                f,
                ensure_ascii=False,
            )
        with open("songs_raw.json", "w", encoding="utf-8") as f:
            json.dump(
                songs_data,
                f,
                ensure_ascii=False,
                indent=2,
            )

    except requests.exceptions.RequestException as e:
        print(f"X 请求失败: {e}")
        raise
    except json.JSONDecodeError as e:
        print(f"X JSON解析失败: {e}")
        raise
    except Exception as e:
        print(f"X 发生错误: {e}")
        raise


if __name__ == "__main__":
    fetch_and_save_songs()
