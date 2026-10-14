"""In-app update download tests (update_checker)."""

import functools
import http.server
import socketserver
import threading

import pytest

from app import update_checker


def test_select_setup_asset_prefers_setup_exe():
    assets = [
        {"name": "RemoteDesk.exe", "download_url": "https://example.invalid/RemoteDesk.exe"},
        {"name": "Setup-RemoteDesk-1.0.2.exe",
         "download_url": "https://example.invalid/Setup-RemoteDesk-1.0.2.exe"},
        {"name": "notes.txt", "download_url": "https://example.invalid/notes.txt"},
    ]
    picked = update_checker.select_setup_asset(assets)
    assert picked["name"] == "Setup-RemoteDesk-1.0.2.exe"


def test_select_setup_asset_falls_back_to_any_exe():
    assets = [{"name": "RemoteDesk.exe", "download_url": "https://example.invalid/x.exe"}]
    assert update_checker.select_setup_asset(assets)["name"] == "RemoteDesk.exe"
    assert update_checker.select_setup_asset([]) is None
    assert update_checker.select_setup_asset(None) is None


class _Handler(http.server.BaseHTTPRequestHandler):
    payload = b"FAKE-INSTALLER-BYTES" * 100

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Length", str(len(self.payload)))
        self.end_headers()
        self.wfile.write(self.payload)

    def log_message(self, *args):
        pass


@pytest.fixture()
def local_server(tmp_path):
    with socketserver.TCPServer(("127.0.0.1", 0), _Handler) as httpd:
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        yield f"http://127.0.0.1:{httpd.server_address[1]}/Setup-RemoteDesk-1.0.2.exe"
        httpd.shutdown()


def test_download_writes_file_with_progress(tmp_path, local_server):
    seen = []

    def _progress(done, total):
        seen.append((done, total))

    path, error = update_checker.download_update(
        local_server, dest_dir=tmp_path, progress_callback=_progress)
    assert error is None
    assert path is not None
    data = open(path, "rb").read()
    assert data == _Handler.payload
    assert seen and seen[-1][0] == len(_Handler.payload)
    assert seen[-1][1] == len(_Handler.payload)


def test_download_failure_returns_error_not_raise(tmp_path):
    path, error = update_checker.download_update(
        "http://127.0.0.1:1/nope.exe", dest_dir=tmp_path)
    assert path is None
    assert error is not None and "Download failed" in error
