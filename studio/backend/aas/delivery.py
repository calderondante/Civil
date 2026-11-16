"""Round-trip download of a private cloud bundle, without persistent hosting.

Binds only loopback, exposes exactly one capability URL, suppresses access logs,
and closes immediately after the agent downloads and verifies the file. Final
workspace links let the owner download the resulting MP3/ZIP from the conversation.
"""

import hashlib
import secrets
import threading
import urllib.request
import zipfile
from http.server import BaseHTTPRequestHandler, HTTPServer
from .free_cloud import private_root, private_path, write_bytes, FreeCloudError
from .open_models import file_hash


def download_bundle(directory):
    root = private_root(directory)
    source = private_path(root, "academic-audio.zip")
    if not source.is_file():
        raise FreeCloudError("complete_private_bundle_required")
    token = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path != "/" + token:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Length", str(source.stat().st_size))
            self.send_header("Cache-Control", "private, no-store")
            self.end_headers()
            with source.open("rb") as f:
                while chunk := f.read(1024 * 1024):
                    self.wfile.write(chunk)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        # No proxy is involved for this loopback-only transfer.
        with urllib.request.urlopen(
            f"http://127.0.0.1:{server.server_port}/{token}", timeout=60
        ) as r:
            payload = r.read()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    if hashlib.sha256(payload).hexdigest() != file_hash(source):
        raise FreeCloudError("download_checksum_mismatch")
    downloaded = write_bytes(root, "downloads/academic-audio.zip", payload)
    with zipfile.ZipFile(downloaded) as z:
        if z.testzip() is not None:
            raise FreeCloudError("download_zip_corrupt")
        for name in ["podcast.mp3", "script.md", "script.json", "coverage-audio.json"]:
            write_bytes(root, "downloads/" + name, z.read(name))
        for name in ("differences.json", "transcript.txt"):
            if name in z.namelist():
                write_bytes(root, "downloads/" + name, z.read(name))
        original = private_path(root, "deliverables/podcast.mp3")
        if file_hash(private_path(root, "downloads/podcast.mp3")) != file_hash(
            original
        ):
            raise FreeCloudError("download_audio_checksum_mismatch")
    return {
        "download_verified": True,
        "zip_bytes": len(payload),
        "mp3_bytes": private_path(root, "downloads/podcast.mp3").stat().st_size,
        "sha256": file_hash(downloaded),
    }
