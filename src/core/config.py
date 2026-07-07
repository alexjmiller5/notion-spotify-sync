"""Settings from env vars — Modal Secret in the cloud, `op run` locally.

One field per line in .env.tpl. Instantiate Settings() inside functions,
not at import time, so tests can run without secrets.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    notion_token: str
    # Optional until Alex creates the Spotify developer app (see README)
    spotify_client_id: str | None = None
    spotify_client_secret: str | None = None
    spotify_refresh_token: str | None = None
