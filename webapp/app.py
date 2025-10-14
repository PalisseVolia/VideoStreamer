import mimetypes
import os
from pathlib import Path
from typing import Iterable

from flask import (
    Flask,
    Response,
    abort,
    current_app,
    redirect,
    render_template,
    request,
    url_for,
)

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_VIDEO_ROOT = (BASE_DIR.parent / "videos").resolve()
DEFAULT_CHUNK_SIZE = 1024 * 1024  # 1 MiB


def create_app(video_root: Path | None = None) -> Flask:
    """Create the Flask application."""
    app = Flask(__name__)
    app.config["VIDEO_ROOT"] = (video_root or DEFAULT_VIDEO_ROOT).resolve()
    app.config.setdefault("VIDEO_CHUNK_SIZE", DEFAULT_CHUNK_SIZE)

    @app.route("/")
    def index() -> Response:
        return redirect(url_for("browse", subpath=""))

    @app.route("/browse/", defaults={"subpath": ""})
    @app.route("/browse/<path:subpath>")
    def browse(subpath: str) -> str:
        target = _resolve_subpath(app, subpath)
        if not target.exists():
            abort(404)
        if target.is_file():
            return redirect(url_for("watch", subpath=subpath))

        directories, files = _list_directory(target)
        breadcrumbs = _build_breadcrumbs(subpath)
        return render_template(
            "browse.html",
            breadcrumbs=breadcrumbs,
            directories=directories,
            files=files,
            current_path=subpath,
        )

    @app.route("/watch/<path:subpath>")
    def watch(subpath: str) -> str:
        target = _resolve_subpath(app, subpath)
        if not target.exists() or not target.is_file():
            abort(404)
        mimetype = _guess_mimetype(target)
        breadcrumbs = _build_breadcrumbs(subpath)
        return render_template(
            "watch.html",
            breadcrumbs=breadcrumbs,
            video_path=subpath,
            mimetype=mimetype,
            filename=target.name,
        )

    @app.route("/video/<path:subpath>")
    def video_stream(subpath: str) -> Response:
        target = _resolve_subpath(app, subpath)
        if not target.exists() or not target.is_file():
            abort(404)
        return _range_stream(target)

    return app


def _resolve_subpath(app: Flask, subpath: str) -> Path:
    root: Path = app.config["VIDEO_ROOT"]
    target = (root / subpath).resolve()
    if root not in target.parents and target != root:
        abort(404)
    return target


def _list_directory(path: Path) -> tuple[list[str], list[str]]:
    directories: list[str] = []
    files: list[str] = []
    for child in sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
        if child.is_dir():
            directories.append(child.name)
        elif _is_video(child):
            files.append(child.name)
    return directories, files


def _is_video(path: Path) -> bool:
    mimetype, _ = mimetypes.guess_type(path.name)
    return mimetype is not None and mimetype.startswith("video/")


def _guess_mimetype(path: Path) -> str:
    mimetype, _ = mimetypes.guess_type(path.name)
    return mimetype or "application/octet-stream"


def _build_breadcrumbs(subpath: str) -> list[tuple[str, str]]:
    breadcrumbs: list[tuple[str, str]] = [("Home", url_for("browse", subpath=""))]
    if not subpath:
        return breadcrumbs
    parts = subpath.split("/")
    accumulated: list[str] = []
    for part in parts:
        accumulated.append(part)
        breadcrumbs.append(
            (
                part,
                url_for("browse", subpath="/".join(accumulated)),
            )
        )
    return breadcrumbs


def _range_stream(path: Path) -> Response:
    range_header = request.headers.get("Range", None)
    file_size = path.stat().st_size
    mimetype = _guess_mimetype(path)

    chunk_size: int = current_app.config.get("VIDEO_CHUNK_SIZE", DEFAULT_CHUNK_SIZE)

    if range_header is None:
        response = Response(
            _file_generator(path, 0, file_size - 1, chunk_size=chunk_size),
            mimetype=mimetype,
            direct_passthrough=True,
        )
        response.headers.add("Content-Length", str(file_size))
        response.headers.add("Accept-Ranges", "bytes")
        return response

    byte1, byte2 = _parse_range(range_header, file_size)
    length = byte2 - byte1 + 1
    response = Response(
        _file_generator(path, byte1, byte2, chunk_size=chunk_size),
        status=206,
        mimetype=mimetype,
        direct_passthrough=True,
    )
    response.headers.add("Content-Range", f"bytes {byte1}-{byte2}/{file_size}")
    response.headers.add("Accept-Ranges", "bytes")
    response.headers.add("Content-Length", str(length))
    return response


def _parse_range(range_header: str, file_size: int) -> tuple[int, int]:
    if not range_header.startswith("bytes="):
        abort(416)
    ranges = range_header.replace("bytes=", "", 1).strip().split("-", 1)
    if len(ranges) != 2:
        abort(416)
    start_str, end_str = [part.strip() for part in ranges]
    if start_str:
        try:
            start = int(start_str)
        except ValueError:
            abort(416)
        if start >= file_size or start < 0:
            abort(416)
        end = file_size - 1
        if end_str:
            try:
                end = int(end_str)
            except ValueError:
                abort(416)
    else:
        try:
            suffix_length = int(end_str)
        except ValueError:
            abort(416)
        if suffix_length <= 0:
            abort(416)
        if suffix_length >= file_size:
            start = 0
        else:
            start = file_size - suffix_length
        end = file_size - 1
    if end_str:
        if end < start or end >= file_size:
            abort(416)
    if start > end or end >= file_size:
        abort(416)
    return start, end


def _file_generator(path: Path, start: int, end: int, chunk_size: int = DEFAULT_CHUNK_SIZE) -> Iterable[bytes]:
    with path.open("rb") as file:
        file.seek(start)
        remaining = end - start + 1
        while remaining > 0:
            chunk = file.read(min(chunk_size, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
