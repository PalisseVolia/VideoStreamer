import mimetypes
import os
from pathlib import Path, PurePosixPath
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
from werkzeug.http import http_date
from werkzeug.wsgi import FileWrapper

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_VIDEO_ROOT = (BASE_DIR.parent / "videos").resolve()
DEFAULT_CHUNK_SIZE = 1024 * 1024  # 1 MiB


def create_app(video_root: Path | None = None) -> Flask:
    """Create the Flask application."""
    app = Flask(__name__)
    app.config["VIDEO_ROOT"] = (video_root or DEFAULT_VIDEO_ROOT).resolve()
    app.config.setdefault("VIDEO_CHUNK_SIZE", DEFAULT_CHUNK_SIZE)
    app.config.setdefault("VIDEO_CACHE_SECONDS", 4 * 60 * 60)

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

        directories, files = _list_directory(target, subpath)
        breadcrumbs = _build_breadcrumbs(subpath, is_file=False)
        return render_template(
            "browse.html",
            breadcrumbs=breadcrumbs,
            directories=directories,
            files=files,
            current_path=subpath,
            is_root=(subpath == ""),
            current_label=_display_directory_label(Path(subpath).name) if subpath else "All Videos",
        )

    @app.route("/watch/<path:subpath>")
    def watch(subpath: str) -> str:
        target = _resolve_subpath(app, subpath)
        if not target.exists() or not target.is_file():
            abort(404)
        mimetype = _guess_mimetype(target)
        breadcrumbs = _build_breadcrumbs(subpath, is_file=True)
        return render_template(
            "watch.html",
            breadcrumbs=breadcrumbs,
            video_path=subpath,
            mimetype=mimetype,
            filename=target.name,
            display_name=_display_video_label(target.name),
        )

    @app.route("/video/<path:subpath>", methods=["GET", "HEAD"])
    def video_stream(subpath: str) -> Response:
        target = _resolve_subpath(app, subpath)
        if not target.exists() or not target.is_file():
            abort(404)
        if request.method == "HEAD":
            return _video_head_response(target)
        return _range_stream(target)

    return app


def _resolve_subpath(app: Flask, subpath: str) -> Path:
    root: Path = app.config["VIDEO_ROOT"]
    if not subpath:
        return root

    normalized = PurePosixPath(subpath)
    if normalized.is_absolute() or ".." in normalized.parts:
        abort(404)

    target = root.joinpath(*normalized.parts)
    return target


def _list_directory(path: Path, subpath: str) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    directories: list[dict[str, str]] = []
    files: list[dict[str, str]] = []
    for child in sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
        relative = f"{subpath}/{child.name}" if subpath else child.name
        if child.is_dir():
            directories.append(
                {
                    "name": child.name,
                    "display_name": _display_directory_label(child.name),
                    "link": url_for("browse", subpath=relative),
                    "video_count": _count_videos(child),
                }
            )
        elif _is_video(child):
            files.append(
                {
                    "name": child.name,
                    "display_name": _display_video_label(child.name),
                    "watch_url": url_for("watch", subpath=relative),
                    "stream_url": url_for("video_stream", subpath=relative),
                    "mimetype": _guess_mimetype(child),
                }
            )
    return directories, files


def _is_video(path: Path) -> bool:
    mimetype, _ = mimetypes.guess_type(path.name)
    return mimetype is not None and mimetype.startswith("video/")


def _guess_mimetype(path: Path) -> str:
    mimetype, _ = mimetypes.guess_type(path.name)
    return mimetype or "application/octet-stream"


def _build_breadcrumbs(subpath: str, *, is_file: bool) -> list[tuple[str, str]]:
    breadcrumbs: list[tuple[str, str]] = [("Home", url_for("browse", subpath=""))]
    if not subpath:
        return breadcrumbs
    parts = subpath.split("/")
    accumulated: list[str] = []
    for index, part in enumerate(parts):
        last = index == len(parts) - 1
        accumulated.append(part)
        label = _display_video_label(part) if is_file and last else _display_directory_label(part)
        breadcrumbs.append(
            (
                label,
                url_for("browse", subpath="/".join(accumulated)),
            )
        )
    return breadcrumbs


def _display_directory_label(name: str) -> str:
    if not name:
        return "All Videos"
    return name.replace("_", " ").title()


def _display_video_label(name: str) -> str:
    stem = Path(name).stem
    return stem.replace("_", " ").title()


def _count_videos(path: Path) -> int:
    count = 0
    try:
        for child in path.iterdir():
            if child.is_file() and _is_video(child):
                count += 1
    except PermissionError:
        return 0
    return count


def _range_stream(path: Path) -> Response:
    range_header = request.headers.get("Range", None)
    file_size = path.stat().st_size
    mimetype = _guess_mimetype(path)

    chunk_size: int = current_app.config.get("VIDEO_CHUNK_SIZE", DEFAULT_CHUNK_SIZE)

    if range_header is None:
        file_handle = path.open("rb")
        data = _limited_file_wrapper(file_handle, file_size, chunk_size)
        response = Response(data, mimetype=mimetype, direct_passthrough=True)
        response.headers.setdefault("Content-Length", str(file_size))
        response.headers.setdefault("Accept-Ranges", "bytes")
        _apply_stream_headers(response, path, file_size)
        return response

    byte1, byte2 = _parse_range(range_header, file_size)
    length = byte2 - byte1 + 1
    file_handle = path.open("rb")
    file_handle.seek(byte1)
    data = _limited_file_wrapper(file_handle, length, chunk_size)
    response = Response(data, status=206, mimetype=mimetype, direct_passthrough=True)
    response.headers.setdefault("Content-Range", f"bytes {byte1}-{byte2}/{file_size}")
    response.headers.setdefault("Accept-Ranges", "bytes")
    response.headers.setdefault("Content-Length", str(length))
    _apply_stream_headers(response, path, length)
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


def _limited_file_wrapper(file_handle, length: int, chunk_size: int) -> Iterable[bytes]:
    remaining = length
    wrapper = FileWrapper(file_handle, chunk_size)
    try:
        for chunk in wrapper:
            if remaining <= 0:
                break
            if len(chunk) > remaining:
                yield chunk[:remaining]
                break
            remaining -= len(chunk)
            yield chunk
    finally:
        wrapper.close()


def _apply_stream_headers(response: Response, path: Path, content_length: int) -> None:
    cache_seconds = current_app.config.get("VIDEO_CACHE_SECONDS", 0)
    if cache_seconds:
        response.headers.setdefault("Cache-Control", f"public, max-age={cache_seconds}, immutable")
    response.headers.setdefault("X-Accel-Buffering", "no")
    response.headers.setdefault("Last-Modified", http_date(int(path.stat().st_mtime)))
    response.headers.setdefault("Accept-Ranges", "bytes")
    response.headers.setdefault("Content-Length", str(content_length))


def _video_head_response(path: Path) -> Response:
    mimetype = _guess_mimetype(path)
    file_size = path.stat().st_size
    response = Response(status=200)
    response.headers.setdefault("Content-Type", mimetype)
    response.headers.setdefault("Content-Length", str(file_size))
    response.headers.setdefault("Accept-Ranges", "bytes")
    _apply_stream_headers(response, path, file_size)
    return response


app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
