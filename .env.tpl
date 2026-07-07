# Canonical secrets manifest — 1Password secret references only, SAFE to commit.
# Local dev:       op run --env-file=.env.tpl -- <cmd>   (see justfile)
# Push to Modal:   just sync-secrets
NOTION_TOKEN=op://OpenClaw/OpenClaw Notion Internal Integration Secret/credential
# Spotify creds live in a to-be-created 'Spotify API' item in OpenClaw — see README
SPOTIFY_CLIENT_ID=op://OpenClaw/Spotify API/client_id
SPOTIFY_CLIENT_SECRET=op://OpenClaw/Spotify API/client_secret
SPOTIFY_REFRESH_TOKEN=op://OpenClaw/Spotify API/refresh_token
