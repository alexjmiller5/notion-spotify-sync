# /// script
# requires-python = ">=3.13"
# dependencies = ["httpx>=0.28", "pydantic>=2.10", "pydantic-settings>=2.7", "structlog>=25.1"]
# ///
"""Build the '50s Gold' playlist on Spotify from the curated list below.

Draft staged for review in the sandbox Notion Playlists DB as '50s Gold (draft)'.
Additive-only: creates ONE new private playlist, touches nothing existing.

Run (after scripts/spotify_auth.py has minted creds into 1Password):
    op run --env-file=.env.tpl -- uv run scripts/create_50s_playlist.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from core.config import Settings  # noqa: E402
from core.playlist_builder import create_playlist, find_track_uri  # noqa: E402
from core.spotify_client import SpotifyClient  # noqa: E402

PLAYLIST_NAME = "50s Gold"
DESCRIPTION = "1950s rock'n'roll, R&B and doo-wop canon - curated 2026-07-07"

# (track, artist) - all released in the 1950s
TRACKS = [
    ("Johnny B. Goode", "Chuck Berry"),
    ("Maybellene", "Chuck Berry"),
    ("Roll Over Beethoven", "Chuck Berry"),
    ("Tutti Frutti", "Little Richard"),
    ("Long Tall Sally", "Little Richard"),
    ("Good Golly, Miss Molly", "Little Richard"),
    ("Jailhouse Rock", "Elvis Presley"),
    ("Hound Dog", "Elvis Presley"),
    ("Heartbreak Hotel", "Elvis Presley"),
    ("That'll Be the Day", "Buddy Holly"),
    ("Peggy Sue", "Buddy Holly"),
    ("Everyday", "Buddy Holly"),
    ("La Bamba", "Ritchie Valens"),
    ("Donna", "Ritchie Valens"),
    ("Blueberry Hill", "Fats Domino"),
    ("Ain't That a Shame", "Fats Domino"),
    ("I'm Walkin'", "Fats Domino"),
    ("You Send Me", "Sam Cooke"),
    ("Only Sixteen", "Sam Cooke"),
    ("The Great Pretender", "The Platters"),
    ("Only You (And You Alone)", "The Platters"),
    ("Smoke Gets In Your Eyes", "The Platters"),
    ("I Walk the Line", "Johnny Cash"),
    ("Folsom Prison Blues", "Johnny Cash"),
    ("What'd I Say", "Ray Charles"),
    ("I Got a Woman", "Ray Charles"),
    ("All I Have to Do Is Dream", "The Everly Brothers"),
    ("Wake Up Little Susie", "The Everly Brothers"),
    ("Bye Bye Love", "The Everly Brothers"),
    ("Bo Diddley", "Bo Diddley"),
    ("Who Do You Love?", "Bo Diddley"),
    ("Great Balls of Fire", "Jerry Lee Lewis"),
    ("Whole Lotta Shakin' Goin' On", "Jerry Lee Lewis"),
    ("The Wallflower (Dance with Me, Henry)", "Etta James"),
    ("Shake, Rattle and Roll", "Big Joe Turner"),
    ("Rock Around the Clock", "Bill Haley & His Comets"),
    ("Blue Suede Shoes", "Carl Perkins"),
    ("Be-Bop-A-Lula", "Gene Vincent"),
    ("Summertime Blues", "Eddie Cochran"),
    ("Earth Angel", "The Penguins"),
    ("In the Still of the Night", "The Five Satins"),
    ("Why Do Fools Fall in Love", "Frankie Lymon & The Teenagers"),
    ("Come Go with Me", "The Del-Vikings"),
    ("Get a Job", "The Silhouettes"),
    ("Yakety Yak", "The Coasters"),
    ("There Goes My Baby", "The Drifters"),
    ("Lonely Teardrops", "Jackie Wilson"),
    ("Sea of Love", "Phil Phillips"),
    ("Dream Lover", "Bobby Darin"),
    ("Mack the Knife", "Bobby Darin"),
]


def main() -> None:
    client = SpotifyClient(Settings())
    uris, misses = [], []
    for name, artist in TRACKS:
        uri = find_track_uri(client, name, artist)
        (uris if uri else misses).append(uri or f"{artist} - {name}")
        print(("found " if uri else "MISS  ") + f"{artist} - {name}")

    playlist = create_playlist(client, PLAYLIST_NAME, DESCRIPTION, uris)
    url = playlist.get("external_urls", {}).get("spotify", playlist["id"])
    print(f"\nCreated private playlist '{PLAYLIST_NAME}' with {len(uris)} tracks: {url}")
    if misses:
        print("Not found on Spotify (add manually):\n  " + "\n  ".join(misses))


if __name__ == "__main__":
    main()
