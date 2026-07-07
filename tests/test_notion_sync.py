"""Unit tests for the Notion upsert/dedupe logic — httpx.MockTransport, no network."""

import json
from datetime import date

import httpx
import pytest

from core.models import Playlist, Song
from core.notion_sync import NotionClient, fetch_song_index, song_key, sync_snapshot

CFG = {
    "playlists_data_source_id": "pl-ds",
    "songs_data_source_id": "song-ds",
}


def make_client(handler, mocker):
    mocker.patch("core.notion_sync.time.sleep")  # no real waiting in tests
    http = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://api.notion.com")
    return NotionClient(token="t", http=http)


def song(name="Take My Hand", artist="Matt Berry", uri="spotify:track:abc"):
    return Song(
        name=name, artist=artist, album="Witchazel", spotify_uri=uri, added_date=date(2025, 2, 27)
    )


# --- song_key -----------------------------------------------------------------


def test_song_key_prefers_uri():
    assert song_key(song(uri="spotify:track:abc")) == "spotify:track:abc"


def test_song_key_falls_back_to_artist_and_name():
    assert song_key(song(uri=None)) == "matt berry|take my hand"


# --- NotionClient retry -------------------------------------------------------


def test_429_honors_retry_after_then_succeeds(mocker):
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": "7"}, json={})
        return httpx.Response(200, json={"ok": True})

    sleep = mocker.patch("core.notion_sync.time.sleep")
    http = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://api.notion.com")
    client = NotionClient(token="t", http=http)
    assert client.request("GET", "/v1/pages/x") == {"ok": True}
    assert len(calls) == 2
    assert any(c.args == (7.0,) for c in sleep.call_args_list)


def test_timeout_and_5xx_retry_then_succeed(mocker):
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            raise httpx.ReadTimeout("slow")
        if len(calls) == 2:
            return httpx.Response(502, json={})
        return httpx.Response(200, json={"ok": True})

    client = make_client(handler, mocker)
    assert client.request("POST", "/v1/pages", json={}) == {"ok": True}
    assert len(calls) == 3


def test_4xx_is_not_retried(mocker):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(400, json={"message": "bad"})

    client = make_client(handler, mocker)
    with pytest.raises(httpx.HTTPStatusError):
        client.request("POST", "/v1/pages", json={})
    assert len(calls) == 1


# --- fetch_song_index ---------------------------------------------------------


def page(page_id, uri, name="Take My Hand", artist="Matt Berry", relation_ids=()):
    return {
        "id": page_id,
        "properties": {
            "Name": {"title": [{"plain_text": name}]},
            "Artist": {"rich_text": [{"plain_text": artist}]},
            "Spotify URI": {"rich_text": [{"plain_text": uri}] if uri else []},
            "Playlists": {"relation": [{"id": r} for r in relation_ids], "has_more": False},
        },
    }


def test_fetch_song_index_paginates_and_keys_by_uri(mocker):
    def handler(request):
        body = json.loads(request.content)
        if body.get("start_cursor") is None:
            return httpx.Response(
                200,
                json={
                    "results": [page("p1", "spotify:track:a", relation_ids=["r1"])],
                    "has_more": True,
                    "next_cursor": "c2",
                },
            )
        return httpx.Response(
            200,
            json={
                "results": [page("p2", None, name="B", artist="X")],
                "has_more": False,
                "next_cursor": None,
            },
        )

    client = make_client(handler, mocker)
    index = fetch_song_index(client, "song-ds")
    assert index["spotify:track:a"].page_id == "p1"
    assert index["spotify:track:a"].relation_ids == {"r1"}
    assert index["x|b"].page_id == "p2"


# --- sync_snapshot ------------------------------------------------------------


class Recorder:
    """Route Notion API calls to canned responses and record writes."""

    def __init__(self, playlist_pages=(), song_pages=()):
        self.playlist_pages = list(playlist_pages)
        self.song_pages = list(song_pages)
        self.created = []
        self.patched = []
        self._n = 0

    def __call__(self, request):
        path = request.url.path
        if path == "/v1/data_sources/pl-ds/query":
            return httpx.Response(200, json={"results": self.playlist_pages, "has_more": False})
        if path == "/v1/data_sources/song-ds/query":
            return httpx.Response(200, json={"results": self.song_pages, "has_more": False})
        if path == "/v1/pages" and request.method == "POST":
            body = json.loads(request.content)
            self.created.append(body)
            self._n += 1
            return httpx.Response(200, json={"id": f"new-{self._n}"})
        if path.startswith("/v1/pages/") and request.method == "PATCH":
            self.patched.append((path.removeprefix("/v1/pages/"), json.loads(request.content)))
            return httpx.Response(200, json={"id": path.removeprefix("/v1/pages/")})
        raise AssertionError(f"unexpected call {request.method} {path}")


def playlist_page(page_id, name):
    return {"id": page_id, "properties": {"Name": {"title": [{"plain_text": name}]}}}


def test_sync_creates_playlists_and_songs_from_scratch(mocker):
    rec = Recorder()
    client = make_client(rec, mocker)
    pls = [Playlist(name="galaxy", description="space", songs=[song()])]
    stats = sync_snapshot(client, CFG, pls)
    assert stats == {
        "playlists_created": 1,
        "playlists_updated": 0,
        "songs_created": 1,
        "songs_updated": 0,
    }
    kinds = [c["parent"]["data_source_id"] for c in rec.created]
    assert kinds == ["pl-ds", "song-ds"]
    song_props = rec.created[1]["properties"]
    assert song_props["Playlists"]["relation"] == [{"id": "new-1"}]
    assert song_props["Added"]["date"]["start"] == "2025-02-27"


def test_rerun_is_idempotent_zero_creates(mocker):
    rec = Recorder(
        playlist_pages=[playlist_page("pl1", "galaxy")],
        song_pages=[page("s1", "spotify:track:abc", relation_ids=["pl1"])],
    )
    client = make_client(rec, mocker)
    pls = [Playlist(name="galaxy", songs=[song()])]
    stats = sync_snapshot(client, CFG, pls)
    assert stats["playlists_created"] == 0
    assert stats["songs_created"] == 0
    assert stats["songs_updated"] == 0
    assert rec.created == []
    # existing playlist still gets its Track Count / Last Synced refreshed
    assert rec.patched and rec.patched[0][0] == "pl1"


def test_song_in_two_playlists_is_one_page_with_two_relations(mocker):
    rec = Recorder()
    client = make_client(rec, mocker)
    shared = song()
    pls = [Playlist(name="a", songs=[shared]), Playlist(name="b", songs=[shared])]
    stats = sync_snapshot(client, CFG, pls)
    assert stats["songs_created"] == 1
    song_creates = [c for c in rec.created if c["parent"]["data_source_id"] == "song-ds"]
    assert len(song_creates) == 1
    assert {r["id"] for r in song_creates[0]["properties"]["Playlists"]["relation"]} == {
        "new-1",
        "new-2",
    }


def test_existing_song_gains_new_playlist_relation(mocker):
    rec = Recorder(
        playlist_pages=[playlist_page("pl1", "a")],
        song_pages=[page("s1", "spotify:track:abc", relation_ids=["pl1"])],
    )
    client = make_client(rec, mocker)
    pls = [Playlist(name="a", songs=[song()]), Playlist(name="b", songs=[song()])]
    stats = sync_snapshot(client, CFG, pls)
    assert stats["songs_created"] == 0
    assert stats["songs_updated"] == 1
    song_patches = [p for p in rec.patched if p[0] == "s1"]
    rel = song_patches[0][1]["properties"]["Playlists"]["relation"]
    assert {r["id"] for r in rel} == {"pl1", "new-1"}


def test_merge_preserves_relations_not_in_snapshot(mocker):
    # a relation Alex added by hand must survive a resync
    rec = Recorder(
        playlist_pages=[playlist_page("pl1", "a")],
        song_pages=[page("s1", "spotify:track:abc", relation_ids=["manual"])],
    )
    client = make_client(rec, mocker)
    stats = sync_snapshot(client, CFG, [Playlist(name="a", songs=[song()])])
    assert stats["songs_updated"] == 1
    rel = [p for p in rec.patched if p[0] == "s1"][0][1]["properties"]["Playlists"]["relation"]
    assert {r["id"] for r in rel} == {"manual", "pl1"}
