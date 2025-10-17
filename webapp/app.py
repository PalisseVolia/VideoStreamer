import mimetypes
import os
import subprocess
import tempfile
from pathlib import Path, PurePosixPath

from flask import (
    Flask,
    Response,
    abort,
    redirect,
    render_template,
    send_file,
    url_for,
)

BASE_DIR = Path(__file__).resolve().parent
# DEFAULT_VIDEO_ROOT = (BASE_DIR.parent / "videos").resolve() # thsi is for project folder
DEFAULT_VIDEO_ROOT = Path("/mnt/data/videos").resolve()
DEFAULT_THUMBNAIL_SUBDIR = "thumbnails"
DEFAULT_THUMBNAIL_EXTENSION = ".jpg"
DEFAULT_THUMBNAIL_SEEK_SECONDS = 1.5
DEFAULT_THUMBNAIL_WIDTH = 640

def create_app(video_root: Path | None = None) -> Flask:
    """Create the Flask application."""
    app = Flask(__name__)
    resolved_video_root = (video_root or DEFAULT_VIDEO_ROOT).resolve()
    app.config["VIDEO_ROOT"] = resolved_video_root
    thumbnail_root = resolved_video_root.parent / DEFAULT_THUMBNAIL_SUBDIR
    thumbnail_root.mkdir(parents=True, exist_ok=True)
    app.config["THUMBNAIL_ROOT"] = thumbnail_root
    app.config.setdefault("THUMBNAIL_SEEK_SECONDS", DEFAULT_THUMBNAIL_SEEK_SECONDS)
    app.config.setdefault("THUMBNAIL_WIDTH", DEFAULT_THUMBNAIL_WIDTH)

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

        directories, files = _list_directory(app, target, subpath)
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

    @app.route("/video/<path:subpath>")
    def video_stream(subpath: str) -> Response:
        target = _resolve_subpath(app, subpath)
        if not target.exists() or not target.is_file():
            abort(404)
        return _range_stream(target)

    @app.route("/thumbnail/<path:subpath>")
    def thumbnail(subpath: str) -> Response:
        target = _resolve_thumbnail_subpath(app, subpath)
        if not target.exists() or not target.is_file():
            abort(404)
        mimetype = mimetypes.types_map.get(target.suffix.lower(), "image/jpeg")
        return send_file(target, mimetype=mimetype)

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


def _list_directory(app: Flask, path: Path, subpath: str) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
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
            thumbnail_url = _get_thumbnail_url(app, relative)
            files.append(
                {
                    "name": child.name,
                    "display_name": _display_video_label(child.name),
                    "watch_url": url_for("watch", subpath=relative),
                    "stream_url": url_for("video_stream", subpath=relative),
                    "mimetype": _guess_mimetype(child),
                    "thumbnail_url": thumbnail_url,
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
    """Stream ``path`` honouring HTTP range headers."""

    # ``send_file`` handles Range requests when ``conditional=True``.
    # This ensures the underlying WSGI server can use ``wsgi.file_wrapper``
    # (e.g. Gunicorn's ``FileWrapper``) to offload the potentially long-lived
    # file transmission from the worker process.
    #
    # When ``USE_X_SENDFILE`` is enabled the header will be emitted too,
    # allowing a front-end server such as nginx to serve the file directly.
    return send_file(
        path,
        mimetype=_guess_mimetype(path),
        as_attachment=False,
        conditional=True,
        download_name=path.name,
        etag=True,
        last_modified=path.stat().st_mtime,
    )


def _resolve_thumbnail_subpath(app: Flask, subpath: str) -> Path:
    root: Path = app.config["THUMBNAIL_ROOT"]
    normalized = PurePosixPath(subpath)
    if normalized.is_absolute() or ".." in normalized.parts:
        abort(404)
    return root.joinpath(*normalized.parts)


def _get_thumbnail_url(app: Flask, subpath: str) -> str | None:
    thumbnail_path = _ensure_thumbnail(app, subpath)
    if not thumbnail_path:
        return None
    relative = thumbnail_path.relative_to(app.config["THUMBNAIL_ROOT"])
    return url_for("thumbnail", subpath="/".join(relative.parts))


def _ensure_thumbnail(app: Flask, subpath: str) -> Path | None:
    video_path = _resolve_subpath(app, subpath)
    if not video_path.exists() or not video_path.is_file():
        return None

    thumbnail_root: Path = app.config["THUMBNAIL_ROOT"]
    normalized = PurePosixPath(subpath)
    thumbnail_path = thumbnail_root.joinpath(*normalized.parts).with_suffix(DEFAULT_THUMBNAIL_EXTENSION)

    try:
        video_mtime = video_path.stat().st_mtime
    except OSError:
        video_mtime = None

    if thumbnail_path.exists():
        if video_mtime is None:
            return thumbnail_path
        try:
            if thumbnail_path.stat().st_mtime >= video_mtime:
                return thumbnail_path
        except OSError:
            pass

    thumbnail_path.parent.mkdir(parents=True, exist_ok=True)
    if _create_thumbnail(app, video_path, thumbnail_path):
        return thumbnail_path if thumbnail_path.exists() else None
    return None


def _create_thumbnail(app: Flask, video_path: Path, thumbnail_path: Path) -> bool:
    seek_seconds = app.config.get("THUMBNAIL_SEEK_SECONDS", DEFAULT_THUMBNAIL_SEEK_SECONDS)
    width = app.config.get("THUMBNAIL_WIDTH", DEFAULT_THUMBNAIL_WIDTH)
    fd, temp_name = tempfile.mkstemp(dir=thumbnail_path.parent, suffix=thumbnail_path.suffix)
    os.close(fd)
    temp_path = Path(temp_name)
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-ss",
        str(seek_seconds),
        "-i",
        os.fspath(video_path),
        "-frames:v",
        "1",
        "-vf",
        f"scale={width}:-2",
        os.fspath(temp_path),
    ]

    try:
        completed = subprocess.run(command, check=False, capture_output=True)
        if completed.returncode != 0:
            app.logger.warning(
                "Failed to generate thumbnail for %s (exit code %s): %s",
                video_path,
                completed.returncode,
                completed.stderr.decode("utf-8", errors="ignore"),
            )
            return False
        temp_path.replace(thumbnail_path)
        return True
    except FileNotFoundError:
        app.logger.warning("ffmpeg executable not found; cannot generate thumbnail for %s", video_path)
        return False
    except Exception:
        app.logger.exception("Unexpected error while generating thumbnail for %s", video_path)
        return False
    finally:
        if temp_path.exists():
            try:
                temp_path.unlink(missing_ok=True)
            except Exception:
                app.logger.debug("Unable to remove temporary thumbnail %s", temp_path, exc_info=True)


app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
