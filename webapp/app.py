from __future__ import annotations

import mimetypes
import os
from pathlib import Path
from typing import Generator, Optional, Tuple

from flask import (
    Flask,
    abort,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)


# Root directory containing videos
DEFAULT_VIDEO_ROOT = Path("/mnt/data/videos").resolve()


def create_app() -> Flask:
    app = Flask(__name__)

    video_root = Path(os.environ.get("VIDEO_ROOT", DEFAULT_VIDEO_ROOT)).resolve()

    if not video_root.exists() or not video_root.is_dir():
        # Fail fast with a clear error if the configured root is invalid
        raise RuntimeError(f"Video root does not exist or is not a directory: {video_root}")

    # Store on app for reuse
    app.config["VIDEO_ROOT"] = video_root

    @app.route("/")
    def index():
        return redirect(url_for("browse"))

    @app.route("/browse")
    def browse():
        rel_path = request.args.get("path", "").strip()
        directory = safe_path(app, rel_path)
        if not directory.exists() or not directory.is_dir():
            abort(404)

        # List dirs and files (non-recursive)
        entries = list(directory.iterdir())
        dirs = sorted([e for e in entries if e.is_dir() and not e.name.startswith(".")], key=lambda p: p.name.lower())
        files = sorted([e for e in entries if e.is_file() and not e.name.startswith(".")], key=lambda p: p.name.lower())

        # Only display likely video files
        video_files = [f for f in files if is_probable_video(f)]

        parent_rel = relative_to_root(app, directory.parent) if directory != app.config["VIDEO_ROOT"] else None

        return render_template(
            "browse.html",
            current_rel=rel_path,
            parent_rel=parent_rel,
            dirs=[(d.name, join_rel(rel_path, d.name)) for d in dirs],
            videos=[(f.name, join_rel(rel_path, f.name)) for f in video_files],
        )

    @app.route("/watch/<path:rel>")
    def watch(rel: str):
        file_path = safe_path(app, rel)
        if not file_path.exists() or not file_path.is_file():
            abort(404)
        if not is_probable_video(file_path):
            abort(415)

        mime, _ = mimetypes.guess_type(file_path.name)
        return render_template("watch.html", rel=rel, filename=file_path.name, mime=mime or "video/mp4")

    @app.route("/api/list")
    def api_list():
        rel_path = request.args.get("path", "").strip()
        directory = safe_path(app, rel_path)
        if not directory.exists() or not directory.is_dir():
            abort(404)
        entries = list(directory.iterdir())
        result = {
            "path": rel_path,
            "dirs": sorted([e.name for e in entries if e.is_dir() and not e.name.startswith(".")], key=str.lower),
            "videos": sorted([e.name for e in entries if e.is_file() and is_probable_video(e)], key=str.lower),
        }
        return jsonify(result)

    @app.route("/video/<path:rel>", methods=["GET", "HEAD"])
    def video(rel: str):
        file_path = safe_path(app, rel)
        if not file_path.exists() or not file_path.is_file():
            abort(404)

        file_size = file_path.stat().st_size
        mime, _ = mimetypes.guess_type(file_path.name)
        content_type = mime or "application/octet-stream"

        # Handle Range requests for efficient seeking/streaming
        range_header = request.headers.get("Range", None)
        if range_header:
            byte_range = parse_range(range_header, file_size)
            if byte_range is None:
                # Unsatisfiable range
                response = make_response("", 416)
                response.headers["Content-Range"] = f"bytes */{file_size}"
                response.headers["Accept-Ranges"] = "bytes"
                return response
            start, end = byte_range
            length = end - start + 1

            if request.method == "HEAD":
                response = make_response("", 206)
            else:
                response = make_response(iter_file_chunks(file_path, start, end), 206)

            response.headers["Content-Type"] = content_type
            response.headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"
            response.headers["Accept-Ranges"] = "bytes"
            response.headers["Content-Length"] = str(length)
            response.headers["Cache-Control"] = "private, max-age=3600"
            return response

        # No Range header: stream entire file efficiently
        if request.method == "HEAD":
            response = make_response("", 200)
            response.headers["Content-Length"] = str(file_size)
            response.headers["Content-Type"] = content_type
            response.headers["Accept-Ranges"] = "bytes"
            response.headers["Cache-Control"] = "private, max-age=3600"
            return response

        # For full file transfers, use a generator to avoid loading into memory
        response = make_response(iter_file_chunks(file_path, 0, file_size - 1), 200)
        response.headers["Content-Length"] = str(file_size)
        response.headers["Content-Type"] = content_type
        response.headers["Accept-Ranges"] = "bytes"
        response.headers["Cache-Control"] = "private, max-age=3600"
        return response

    return app


def safe_path(app: Flask, rel: str) -> Path:
    root: Path = app.config["VIDEO_ROOT"]
    # Normalize and prevent path traversal
    candidate = (root / rel).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        abort(403)
    return candidate


def relative_to_root(app: Flask, path: Path) -> str:
    root: Path = app.config["VIDEO_ROOT"]
    try:
        return str(path.resolve().relative_to(root))
    except Exception:
        return ""


def join_rel(base: str, name: str) -> str:
    base = base.strip()
    if not base:
        return name
    return f"{base}/{name}"


def is_probable_video(path: Path) -> bool:
    mime, _ = mimetypes.guess_type(path.name)
    if mime and mime.startswith("video/"):
        return True
    # Common containers that may not map to video/* reliably
    return path.suffix.lower() in {".mp4", ".m4v", ".mkv", ".webm", ".mov", ".avi", ".wmv"}


def parse_range(range_header: str, file_size: int) -> Optional[Tuple[int, int]]:
    # Expected formats: bytes=START-END | bytes=START- | bytes=-SUFFIX
    if not range_header.lower().startswith("bytes="):
        return None
    ranges = range_header.split("=", 1)[1].strip()
    # We only support a single range
    if "," in ranges:
        return None
    start_str, end_str = (ranges.split("-", 1) + [""])[:2]
    try:
        if start_str == "":
            # suffix length
            suffix = int(end_str)
            if suffix <= 0:
                return None
            start = max(file_size - suffix, 0)
            end = file_size - 1
        else:
            start = int(start_str)
            if end_str == "":
                end = file_size - 1
            else:
                end = int(end_str)
        if start < 0 or end < start or start >= file_size:
            return None
        end = min(end, file_size - 1)
        return start, end
    except ValueError:
        return None


def iter_file_chunks(path: Path, start: int, end: int, chunk_size: int = 1024 * 1024) -> Generator[bytes, None, None]:
    with open(path, "rb") as f:
        f.seek(start)
        remaining = end - start + 1
        while remaining > 0:
            read_size = min(chunk_size, remaining)
            data = f.read(read_size)
            if not data:
                break
            remaining -= len(data)
            yield data


# Jinja templates live under webapp/templates
# Create the Flask app instance for Gunicorn
app = create_app()
