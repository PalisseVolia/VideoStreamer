# VideoStreamer

Minimal Flask app to browse and stream large video files from a Linux host directory over the web. Optimized for HTTP Range requests so clients can seek without downloading entire files.

- Root directory: `/mnt/data/videos` (override with `VIDEO_ROOT` env var)
- Browse: `GET /browse?path=<relative-subdir>`
- Watch page: `GET /watch/<relative-path>`
- Direct streaming: `GET /video/<relative-path>` (supports `Range` and `HEAD`)

Service integration is handled externally (systemd + gunicorn). Updating via the provided command will install `requirements.txt` and restart the service.
