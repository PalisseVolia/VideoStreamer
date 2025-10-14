import os
import tempfile
import unittest
from pathlib import Path

from webapp.app import create_app


class VideoStreamingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.video_root = Path(self.tempdir.name)
        self.app = create_app(self.video_root)
        self.client = self.app.test_client()

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _write_file(self, relative: str, data: bytes = b"test") -> Path:
        path = self.video_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def test_root_level_video_streams(self) -> None:
        self._write_file("root.mp4", b"0" * 8)
        response = self.client.get("/video/root.mp4")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, b"0" * 8)
        self.assertEqual(response.headers.get("Content-Length"), str(8))
        self.assertEqual(response.headers.get("Accept-Ranges"), "bytes")
        self.assertIn("immutable", response.headers.get("Cache-Control", ""))

    def test_nested_video_streams(self) -> None:
        self._write_file("folder/nested.mp4", b"1" * 5)
        response = self.client.get("/video/folder/nested.mp4")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, b"1" * 5)
        self.assertEqual(response.headers.get("Content-Length"), str(5))

    def test_symlink_target_is_served(self) -> None:
        outside_dir = Path(self.tempdir.name).parent
        outside_file = outside_dir / "outside.mp4"
        outside_file.write_bytes(b"2" * 3)
        symlink = self.video_root / "linked.mp4"
        if symlink.exists() or symlink.is_symlink():
            symlink.unlink()
        try:
            os.symlink(outside_file, symlink)
        except OSError as exc:  # pragma: no cover - platform dependent
            outside_file.unlink(missing_ok=True)
            self.skipTest(f"symlinks not supported: {exc}")
        try:
            response = self.client.get("/video/linked.mp4")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers.get("Content-Length"), str(3))
        finally:
            symlink.unlink(missing_ok=True)
            outside_file.unlink(missing_ok=True)

    def test_path_traversal_is_rejected(self) -> None:
        response = self.client.get("/video/../etc/passwd")
        self.assertEqual(response.status_code, 404)

    def test_range_request_returns_partial_content(self) -> None:
        self._write_file("movie.mp4", b"abcdef")
        response = self.client.get("/video/movie.mp4", headers={"Range": "bytes=2-4"})
        self.assertEqual(response.status_code, 206)
        self.assertEqual(response.data, b"cde")
        self.assertEqual(response.headers.get("Content-Range"), "bytes 2-4/6")
        self.assertEqual(response.headers.get("Content-Length"), "3")

    def test_head_request_returns_metadata(self) -> None:
        self._write_file("head.mp4", b"12345678")
        response = self.client.head("/video/head.mp4")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, b"")
        self.assertEqual(response.headers.get("Content-Length"), "8")
        self.assertEqual(response.headers.get("Accept-Ranges"), "bytes")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
