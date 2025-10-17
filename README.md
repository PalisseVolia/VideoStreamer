# Video Streamer

This repository provides a lightweight Flask application that makes the contents of the `videos/` directory streamable from a Linux server. Place your video files (with any folder structure) inside the `videos` directory, start the web app, and share the server's address with friends so they can browse and stream the clips.

## Prerequisites

* Python 3.10 or newer
* `pip` for installing dependencies

## Setup

1. (Optional) Create and activate a virtual environment.
2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```
3. Ensure your videos are in the `videos/` directory. You may organize them in subfolders.

## Running the app

Start the Flask app with:

```bash
python -m flask --app webapp.app run --host 0.0.0.0 --port 5000
```

The application will be available at `http://<server-ip>:5000/`.

### Environment variables

* `PORT`: (Optional) When running `python webapp/app.py`, you can override the default port (5000).
* `VIDEO_ROOT`: (Optional) Programmatic access is available through `create_app(video_root=...)` if you import the app in another script.

## Features

* Browse videos organized in nested folders.
* Stream videos with HTTP range requests, enabling browser seeking.
* Responsive UI styled with Bootstrap.
* Cached thumbnails generated on-demand with ffmpeg and stored locally.

## Sharing the app outside your home network

By default Flask serves the app only within your local network. To let friends stream from elsewhere you need to expose your server safely:

1. **Use HTTPS and authentication** – Never expose the raw Flask dev server directly. Run it behind a reverse proxy (for example Nginx, Caddy, or Traefik) that terminates HTTPS using Let's Encrypt certificates and enables HTTP basic auth or another login layer.
2. **Port forwarding or tunnelling** – Either forward an external port on your router to the host running the app (e.g. `external:443 -> internal:5000`) or use a tunnelling solution such as Cloudflare Tunnel, Tailscale Funnel, or an SSH reverse tunnel so your server remains reachable even if you do not control the router.
3. **Point a hostname** – Configure a DNS record (e.g. via a dynamic DNS provider) so your friends can reach the server with a stable URL that matches your TLS certificate.
4. **Harden the host** – Keep the server updated, restrict firewall rules to only the proxy port, and consider adding OS-level users or VPN access for trusted friends.

Once the reverse proxy is handling HTTPS and authentication, keep running the Flask app bound to `0.0.0.0` on an internal port. The proxy will forward external requests to it securely.

## Notes

* Only files detected as video types (based on MIME type) are listed.
* If you add new files while the server is running, refresh the page to see them.

### Thumbnails

The browse grid uses cached thumbnails generated on-demand with `ffmpeg` and stored under the project `thumbnails/` folder (not the external videos drive).

Install `ffmpeg` and ensure it is available on PATH for the user running the app:

- Windows (winget): `winget install --id=Gyan.FFmpeg`
- Windows (Chocolatey): `choco install ffmpeg`
- macOS (Homebrew): `brew install ffmpeg`
- Debian/Ubuntu: `sudo apt-get install ffmpeg`

Verify:

```bash
ffmpeg -version
```

On first request to a thumbnail URL (e.g. `/thumb/folder/Video.mp4`) the server generates a JPEG once and serves it; subsequent requests are served from disk. If generation fails, a 404 is returned and the server log will include details (e.g., ffmpeg missing or filter failure).





## General hosting
```bash
gunicorn -w 2 -b 127.0.0.1:5000 webapp.app:app
```

```bash
cloudflared tunnel create VideoStreamer
```
Created tunnel VideoStreamer with id 3da517fa-4313-43bb-8b88-8df37a494d8b

```bash
cloudflared tunnel route dns VideoStreamer app.gameclips.win
```
Added CNAME app.gameclips.win which will route to this tunnel tunnelID=3da517fa-4313-43bb-8b88-8df37a494d8b

```bash
cloudflared tunnel list
cloudflared tunnel info VideoStreamer
ls -l ~/.cloudflared /root/.cloudflared 2>/dev/null
```
You can obtain more detailed information for each tunnel with `cloudflared tunnel info <name/uuid>`
ID                                   NAME          CREATED              CONNECTIONS
3da517fa-4313-43bb-8b88-8df37a494d8b VideoStreamer 2025-10-14T02:18:41Z
Your tunnel 3da517fa-4313-43bb-8b88-8df37a494d8b does not have any active connection.
/home/palissev/.cloudflared:
total 8
-r-------- 1 palissev palissev 175 Oct 14 02:18 3da517fa-4313-43bb-8b88-8df37a494d8b.json
-rw------- 1 palissev palissev 266 Oct 14 02:52 cert.pem

```bash
/home/palissev/VideoStreamer/.venv/bin/pip install flask gunicorn
```

```bash
bash -lc 'cd ~/VideoStreamer && git pull --ff-only && [ -f requirements.txt ] && /home/palissev/VideoStreamer/.venv/bin/pip install -r requirements.txt || true && sudo systemctl restart flask-gunicorn && systemctl status --no-pager --lines=3 flask-gunicorn'
```
