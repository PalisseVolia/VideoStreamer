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

## Notes

* Only files detected as video types (based on MIME type) are listed.
* If you add new files while the server is running, refresh the page to see them.
