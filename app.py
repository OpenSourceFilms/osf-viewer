#!/usr/bin/env python3
"""osf_viewer: universal read-only file inspection service.

Binds 127.0.0.1:3930 only. Reverse-proxied by Cloudflare Tunnel at
https://files.opensourcefilms.org/__view__/... (added only after this
service passes its local test matrix -- see DOCS.md).

Route contract:
  GET /__view__/<relpath>                -> HTML inspection hub
  GET /__view__/<relpath>/text           -> guaranteed text/plain report
  GET /__view__/<relpath>/preview.pdf    -> visual PDF, or 404 if none exists
  GET /__view__/<relpath>/raw            -> original bytes, streamed
  GET /__view_health__                   -> "ok"

Archive members are addressed as <archive_relpath>!<member_internal_path>,
e.g. /__view__/foo.zip!inner/dir/file.txt/text
"""
from __future__ import annotations

import html
import json
import shutil
import sys
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

sys.path.insert(0, str(Path(__file__).parent))
import security
import inspectors

ROOT = Path("/workspace")
DENYLIST_FILE = Path("/workspace/services/osf_viewer/denylist.txt")
HOST = "127.0.0.1"
PORT = 3930

_DENYLIST_CACHE: list[Path] = []
_DENYLIST_LOADED_AT = 0.0


def denylist() -> list[Path]:
    global _DENYLIST_CACHE, _DENYLIST_LOADED_AT
    now = time.time()
    if now - _DENYLIST_LOADED_AT > 30:
        _DENYLIST_CACHE = security.load_denylist(ROOT, DENYLIST_FILE)
        _DENYLIST_LOADED_AT = now
    return _DENYLIST_CACHE


def _denied_predicate():
    """Bound deny-check for the current denylist, shared by every listing.

    Every place that lists directory entries (the HTML hub and inspectors'
    /text directory listing) must filter through this, not a second
    hardcoded check -- it is the exact same predicate safe_resolve() uses
    for direct-fetch 403s, so a listing can never show a name that a direct
    request for that name would deny.
    """
    dl = denylist()
    root = ROOT
    return lambda p: security.is_denied(p, dl, root)


PREFIX = "/__view__/"
SUFFIXES = {
    "/text": "text",
    "/preview.pdf": "preview_pdf",
    "/raw": "raw",
}


def parse_route(raw_path: str) -> tuple[str, str] | None:
    """Return (relpath, mode) or None if not a viewer route."""
    if not raw_path.startswith(PREFIX):
        return None
    rest = raw_path[len(PREFIX):]
    for suffix, mode in SUFFIXES.items():
        if rest.endswith(suffix):
            return rest[: -len(suffix)], mode
        if rest == suffix.lstrip("/"):
            return "", mode
    return rest, "hub"


def split_archive_member(relpath: str) -> tuple[str, str | None]:
    if "!" in relpath:
        archive_rel, member = relpath.split("!", 1)
        return archive_rel, unquote(member)
    return relpath, None


def viewer_url(relpath: str, mode: str = "hub") -> str:
    encoded = quote(relpath)
    if mode == "hub":
        return f"{PREFIX}{encoded}"
    suffix = {"text": "/text", "preview_pdf": "/preview.pdf", "raw": "/raw"}[mode]
    return f"{PREFIX}{encoded}{suffix}"


class ViewerHandler(BaseHTTPRequestHandler):
    server_version = "osf_viewer/1.0"

    def log_message(self, fmt, *args):  # noqa: A003 - stdlib signature
        sys.stderr.write("%s - - [%s] %s\n" % (self.address_string(), self.log_date_time_string(), fmt % args))

    def _send_text(self, code: int, body: str, content_type: str = "text/plain; charset=utf-8"):
        data = body.encode("utf-8", errors="replace")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _send_bytes(self, code: int, data: bytes, content_type: str):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _stream_file(self, path: Path, content_type: str):
        size = path.stat().st_size
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(size))
        self.end_headers()
        if self.command == "HEAD":
            return
        with open(path, "rb") as f:
            shutil.copyfileobj(f, self.wfile, length=1024 * 1024)

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        try:
            self._dispatch()
        except Exception:  # noqa: BLE001 - absolute last resort, never a bare 500 with no body
            tb = traceback.format_exc()
            sys.stderr.write(tb)
            try:
                self._send_text(500, "internal error, this should not happen:\n\n" + tb)
            except Exception:  # noqa: BLE001
                pass

    def _dispatch(self):
        parsed = urlsplit(self.path)
        raw_path = unquote(parsed.path)

        if raw_path == "/__view_health__":
            self._send_text(200, "ok")
            return

        parsed_route = parse_route(raw_path)
        if parsed_route is None:
            self._send_text(404, "not found: only /__view__/<path> routes exist here")
            return

        relpath, mode = parsed_route
        archive_rel, member = split_archive_member(relpath)

        dl = denylist()
        try:
            real = security.safe_resolve(ROOT, archive_rel, dl)
        except PermissionError as exc:
            self._send_text(403, f"denied: {exc}")
            return
        except FileNotFoundError:
            self._send_text(404, f"no such file: {archive_rel}")
            return

        if member is not None:
            self._handle_member(real, archive_rel, member, mode)
            return

        if mode == "raw":
            self._handle_raw(real)
            return
        if mode == "preview_pdf":
            self._handle_preview_pdf(real, None, archive_rel)
            return
        if mode == "text":
            self._send_text(200, inspectors.get_text(real, None, archive_rel, is_denied=_denied_predicate()))
            return
        self._handle_hub(real, archive_rel)

    def _handle_raw(self, real: Path):
        if real.is_dir():
            self._send_text(400, "cannot stream a directory as raw")
            return
        ctype = inspectors._magic_mime(real, real.name) or "application/octet-stream"
        self._stream_file(real, ctype)

    def _handle_preview_pdf(self, real: Path | None, data: bytes | None, relpath: str):
        st = real.stat() if real else None
        size = st.st_size if st else (len(data) if data else 0)
        mtime = st.st_mtime if st else 0.0
        pdf = inspectors.get_preview_pdf(real, data, relpath, relpath, size, mtime)
        if pdf is None:
            self._send_bytes(404, json.dumps({"error": "no visual representation for this file type"}).encode(),
                              "application/json")
            return
        self._send_bytes(200, pdf, "application/pdf")

    def _handle_member(self, archive_real: Path, archive_rel: str, member: str, mode: str):
        try:
            data = inspectors.read_archive_member(archive_real, None, archive_rel, member)
        except Exception as exc:  # noqa: BLE001
            self._send_text(200, f"[could not extract archive member {member!r}: {exc!r}]")
            return
        hint = f"{archive_rel}!{member}"
        if mode == "raw":
            ctype = inspectors._magic_mime(None, member) or "application/octet-stream"
            self._send_bytes(200, data, ctype)
            return
        if mode == "preview_pdf":
            self._handle_preview_pdf(None, data, hint)
            return
        if mode == "text":
            self._send_text(200, inspectors.get_text(None, data, hint))
            return
        self._handle_hub(None, hint, member_bytes=data)

    def _handle_hub(self, real: Path | None, relpath: str, member_bytes: bytes | None = None):
        relpath = relpath.rstrip("/")
        kind = inspectors.identify(real, relpath)
        text_url = viewer_url(relpath, "text")
        pdf_url = viewer_url(relpath, "preview_pdf")
        raw_url = viewer_url(relpath, "raw")
        rows = [
            f"<h1>{html.escape(relpath or '/')}</h1>",
            f"<p><b>kind:</b> {html.escape(kind)}</p>",
            f"<p><a href=\"{text_url}\">/text</a> &middot; "
            f"<a href=\"{pdf_url}\">/preview.pdf</a> &middot; "
            f"<a href=\"{raw_url}\">/raw</a></p>",
        ]
        pred = _denied_predicate()
        if kind == "directory" and real is not None:
            rows.append("<ul>")
            visible = [e for e in sorted(real.iterdir(), key=lambda p: p.name) if not pred(e)]
            for entry in visible[:2000]:
                child_rel = f"{relpath}/{entry.name}".lstrip("/")
                rows.append(f'<li><a href="{viewer_url(child_rel)}">{html.escape(entry.name)}'
                            f'{"/" if entry.is_dir() else ""}</a></li>')
            rows.append("</ul>")
        elif kind == "archive":
            try:
                members = inspectors.list_archive_members(real, member_bytes, relpath)
                rows.append(f"<p>{len(members)} member(s):</p><ul>")
                for name, size in members:
                    member_rel = f"{relpath}!{name}"
                    rows.append(f'<li><a href="{viewer_url(member_rel)}">{html.escape(name)}</a> '
                                f"({size} bytes)</li>")
                rows.append("</ul>")
            except Exception as exc:  # noqa: BLE001
                rows.append(f"<p>could not list archive members: {html.escape(repr(exc))}</p>")
        rows.append(f"<pre>{html.escape(inspectors.get_text(real, member_bytes, relpath, is_denied=pred)[:20000])}</pre>")
        body = "<html><body>" + "\n".join(rows) + "</body></html>"
        self._send_text(200, body, content_type="text/html; charset=utf-8")


def main():
    Path("/workspace/.osf_view_cache").mkdir(parents=True, exist_ok=True)
    httpd = ThreadingHTTPServer((HOST, PORT), ViewerHandler)
    print(f"osf_viewer listening on {HOST}:{PORT}", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
