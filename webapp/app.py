import mimetypes
import os
import subprocess
import tempfile
import logging
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
# DEFAULT_VIDEO_ROOT = (BASE_DIR.parent / "videos").resolve()  # this is for project folder
DEFAULT_VIDEO_ROOT = Path("/mnt/data/videos").resolve()
DEFAULT_THUMBNAIL_ROOT = (BASE_DIR.parent / "thumbnails").resolve()

def create_app(video_root: Path | None = None) -> Flask:
    """Create the Flask application."""
    app = Flask(__name__)
    # Basic logger for thumbnail issues
    app.logger.setLevel(logging.INFO)
    app.config["VIDEO_ROOT"] = (video_root or DEFAULT_VIDEO_ROOT).resolve()
    # Thumbnails are stored in the project folder for speed, independent of the video drive
    app.config["THUMBNAIL_ROOT"] = DEFAULT_THUMBNAIL_ROOT

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

    @app.route("/video/<path:subpath>")
    def video_stream(subpath: str) -> Response:
        target = _resolve_subpath(app, subpath)
        if not target.exists() or not target.is_file():
            abort(404)
        return _range_stream(target)

    @app.route("/thumb/<path:subpath>")
    def thumbnail(subpath: str) -> Response:
        """Serve or generate a cached thumbnail for the given video subpath."""
        video_path = _resolve_subpath(app, subpath)
        if not video_path.exists() or not video_path.is_file() or not _is_video(video_path):
            abort(404)

        thumb_path = _thumbnail_path(app, subpath)
        try:
            # Ensure directory exists
            thumb_path.parent.mkdir(parents=True, exist_ok=True)

            # Generate if missing or stale versus source video
            needs_generate = True
            if thumb_path.exists():
                try:
                    needs_generate = thumb_path.stat().st_mtime < video_path.stat().st_mtime
                except OSError:
                    needs_generate = True

            if needs_generate:
                app.logger.info("Generating thumbnail for %s -> %s", video_path, thumb_path)
                _generate_thumbnail(video_path, thumb_path, logger=app.logger)

            if not thumb_path.exists():
                abort(404)

            return send_file(
                thumb_path,
                mimetype="image/jpeg",
                as_attachment=False,
                conditional=True,
                download_name=thumb_path.name,
                etag=True,
                last_modified=thumb_path.stat().st_mtime,
            )
        except PermissionError:
            app.logger.exception("Permission error creating thumbnail: %s", thumb_path)
            abort(403)

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
                    "thumb_url": url_for("thumbnail", subpath=relative),
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


def _thumbnail_path(app: Flask, subpath: str) -> Path:
    """Compute the thumbnail path for a given video subpath within THUMBNAIL_ROOT."""
    normalized = PurePosixPath(subpath)
    if normalized.is_absolute() or ".." in normalized.parts:
        abort(404)
    # Mirror the directory structure, but ensure JPEG extension
    stem = normalized.stem + ".jpg"
    return app.config["THUMBNAIL_ROOT"].joinpath(*normalized.parent.parts, stem)


def _generate_thumbnail(video_path: Path, thumb_path: Path, *, second: float = 1.5, logger: logging.Logger | None = None) -> None:
    """Generate a thumbnail using ffmpeg if available.

    Writes to a temporary file and then moves into place for atomicity.
    If ffmpeg is not available or fails, leaves the file absent.
    """
    # Prefer a small-ish width for grid thumbnails
    # Use a temporary file that preserves the .jpg extension so ffmpeg can infer format
    fd, tmp_name = tempfile.mkstemp(suffix=".jpg", dir=str(thumb_path.parent))
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass

        # Build ffmpeg command. Place -ss before -i for faster seek.
        # Scale down to max width 480, keep aspect ratio.
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-y",
            "-ss",
            str(max(0.0, float(second))),
            "-i",
            str(video_path),
            "-frames:v",
            "1",
            "-vf",
            # Avoid shell quoting issues by not embedding quotes
            "scale=min(480,iw):-2",
            "-q:v",
            "3",
            str(tmp_path),
        ]
        if logger:
            logger.debug("Running ffmpeg: %s", " ".join(cmd))
        try:
            subprocess.run(cmd, check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            if logger:
                logger.error("ffmpeg failed: %s", e.stderr.decode(errors="ignore") if e.stderr else str(e))
            raise

        # Ensure parent exists (should already) then move into place
        thumb_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path.replace(thumb_path)
    except FileNotFoundError as e:
        if logger:
            logger.error("ffmpeg executable not found: %s", e)
        # ffmpeg missing
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass
    except subprocess.CalledProcessError:
        # ffmpeg failed or not installed; best effort: clean temp and skip
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass


app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
