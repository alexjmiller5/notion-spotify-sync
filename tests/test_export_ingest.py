import json
import os
import zipfile
from datetime import date
from pathlib import Path

import pytest

from core.export_ingest import find_export_zip, load_followed_artists, load_playlists

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def export_zip(tmp_path):
    """Build a minimal GDPR export zip from the fixture JSON files."""
    zip_path = tmp_path / "export.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr(
            "Spotify Account Data/Playlist1.json", (FIXTURES / "playlists.json").read_text()
        )
        zf.writestr(
            "Spotify Account Data/YourLibrary.json", (FIXTURES / "your_library.json").read_text()
        )
        zf.writestr("Spotify Account Data/Follow.json", (FIXTURES / "follow.json").read_text())
    return zip_path


def test_load_playlists_parses_names_and_descriptions(export_zip):
    playlists = load_playlists(export_zip)
    assert [p.name for p in playlists] == ["the good stuff", "galaxy"]
    assert playlists[0].description is None
    assert playlists[1].description == "space tunes"


def test_load_playlists_maps_song_fields(export_zip):
    playlists = load_playlists(export_zip)
    song = playlists[0].songs[0]
    assert song.name == "Take My Hand"
    assert song.artist == "Matt Berry"
    assert song.album == "Witchazel"
    assert song.spotify_uri == "spotify:track:6n4iuOHAOIu5LtbXBKrD0f"
    assert song.added_date == date(2025, 2, 27)


def test_load_playlists_skips_non_track_items(export_zip):
    playlists = load_playlists(export_zip)
    # fixture's first playlist has 2 tracks + 1 localTrack; localTrack is skipped
    assert len(playlists[0].songs) == 2
    assert len(playlists[1].songs) == 1


def test_load_followed_artists_reads_your_library(export_zip):
    # Follow.json only holds counts; artist names+uris live in YourLibrary.json
    artists = load_followed_artists(export_zip)
    assert [(a.name, a.spotify_id) for a in artists] == [
        ("GoldLink", "5XenQ7XfcvQdfIbpLEFaKQ"),
        ("The Strokes", "0epOFNiUfyON9EYx7Tpr6V"),
    ]
    # export has no genres/followers — those stay empty until the live API works
    assert artists[0].genres == []
    assert artists[0].followers is None


def make_zip(path, member):
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(member, "{}")
    return path


def test_find_export_zip_picks_newest_account_data(tmp_path):
    old = make_zip(tmp_path / "old.zip", "Spotify Account Data/Follow.json")
    new = make_zip(tmp_path / "new.zip", "Spotify Account Data/Follow.json")
    # newest overall is a streaming-history zip — must be skipped
    decoy = make_zip(tmp_path / "decoy.zip", "Spotify Extended Streaming History/x.json")
    os.utime(old, (0, 0))
    os.utime(new, (1000, 1000))
    os.utime(decoy, (2000, 2000))
    assert find_export_zip(tmp_path) == new


def test_find_export_zip_errors_when_no_account_data(tmp_path):
    make_zip(tmp_path / "history.zip", "Spotify Extended Streaming History/x.json")
    with pytest.raises(FileNotFoundError, match="Spotify Account Data"):
        find_export_zip(tmp_path)


def test_playlist_snapshot_roundtrip(export_zip):
    """Snapshot dump is valid JSON and reloads to identical models."""
    from core.models import Playlist

    playlists = load_playlists(export_zip)
    dumped = json.dumps([p.model_dump(mode="json") for p in playlists])
    reloaded = [Playlist.model_validate(d) for d in json.loads(dumped)]
    assert reloaded == playlists
