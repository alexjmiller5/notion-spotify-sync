"""Unit tests for playlist_builder — httpx.MockTransport, no network."""

import httpx

from core.config import Settings
from core.playlist_builder import create_playlist, find_track_uri
from core.spotify_client import SpotifyClient

SETTINGS = Settings(
    notion_token="nt",
    spotify_client_id="cid",
    spotify_client_secret="csec",
    spotify_refresh_token="rtok",
)


def make_client(handler):
    return SpotifyClient(SETTINGS, http=httpx.Client(transport=httpx.MockTransport(handler)))


def token_response():
    return httpx.Response(200, json={"access_token": "tok1", "expires_in": 3600})


def test_find_track_uri_searches_and_returns_first_uri():
    seen = {}

    def handler(request):
        if request.url.host == "accounts.spotify.com":
            return token_response()
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json={"tracks": {"items": [{"uri": "spotify:track:abc123"}]}})

    uri = find_track_uri(make_client(handler), "Johnny B. Goode", "Chuck Berry")
    assert uri == "spotify:track:abc123"
    assert seen["params"]["type"] == "track"
    assert seen["params"]["limit"] == "1"
    assert "Johnny B. Goode" in seen["params"]["q"]
    assert "Chuck Berry" in seen["params"]["q"]


def test_find_track_uri_returns_none_when_no_match():
    def handler(request):
        if request.url.host == "accounts.spotify.com":
            return token_response()
        return httpx.Response(200, json={"tracks": {"items": []}})

    assert find_track_uri(make_client(handler), "Nope", "Nobody") is None


def test_create_playlist_is_private_and_batches_adds_in_100s():
    import json

    calls = []

    def handler(request):
        if request.url.host == "accounts.spotify.com":
            return token_response()
        path = request.url.path
        if path == "/v1/me":
            return httpx.Response(200, json={"id": "alex"})
        if path == "/v1/users/alex/playlists":
            calls.append(("create", json.loads(request.read())))
            return httpx.Response(201, json={"id": "pl1", "external_urls": {"spotify": "u"}})
        if path == "/v1/playlists/pl1/tracks":
            calls.append(("add", json.loads(request.read())["uris"]))
            return httpx.Response(201, json={"snapshot_id": "s"})
        raise AssertionError(f"unexpected path {path}")

    uris = [f"spotify:track:{i}" for i in range(250)]
    playlist = create_playlist(make_client(handler), "50s Gold", "desc", uris)

    assert playlist["id"] == "pl1"
    create_body = calls[0][1]
    assert create_body["public"] is False
    assert create_body["name"] == "50s Gold"
    batches = [c[1] for c in calls if c[0] == "add"]
    assert [len(b) for b in batches] == [100, 100, 50]
    assert batches[0][0] == "spotify:track:0"
    assert batches[2][-1] == "spotify:track:249"


def test_create_playlist_with_no_tracks_makes_no_add_calls():
    calls = []

    def handler(request):
        if request.url.host == "accounts.spotify.com":
            return token_response()
        if request.url.path == "/v1/me":
            return httpx.Response(200, json={"id": "alex"})
        calls.append(request.url.path)
        return httpx.Response(201, json={"id": "pl1"})

    create_playlist(make_client(handler), "Empty", None, [])
    assert calls == ["/v1/users/alex/playlists"]
