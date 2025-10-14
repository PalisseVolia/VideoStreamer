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
