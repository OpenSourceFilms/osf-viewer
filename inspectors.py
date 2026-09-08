"""Format dispatch and progressive-degradation inspection logic.

Every public function here is designed to never raise past its own boundary
for a `text` request: on any internal failure it falls back to the generic
binary report so callers can guarantee "the /text endpoint always returns
something useful" (the core contract of this service).
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import mimetypes
import sqlite3
import struct
import subprocess
import tarfile
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Callable, Optional

try:
    import magic as _magic  # python-magic
    _MAGIC = _magic.Magic(mime=True)
    _MAGIC_DESC = _magic.Magic()
except Exception:  # pragma: no cover - degrade gracefully if libmagic is missing
    _MAGIC = None
    _MAGIC_DESC = None

from PIL import Image, ImageDraw
import mutagen
import pypdf
import py7zr
import pyarrow.parquet as pq

import cache as _cache
import office_extract

TEXT_EXTS = {
    "py", "sh", "md", "txt", "json", "yaml", "yml", "toml", "ini", "cfg",
    "log", "xml", "html", "htm", "css", "js", "ts", "rs", "go", "c", "cpp",
    "h", "hpp", "java", "sql", "gitignore", "env", "conf", "bash", "zsh",
}
IMAGE_EXTS = {"png", "jpg", "jpeg", "gif", "bmp", "webp", "tiff", "tif", "ico"}
VIDEO_EXTS = {"mp4", "mov", "mkv", "avi", "webm", "m4v", "flv"}
AUDIO_EXTS = {"mp3", "wav", "flac", "ogg", "m4a", "aac", "wma"}
ARCHIVE_EXTS = {"zip", "tar", "gz", "tgz", "bz2", "tbz2", "xz", "txz", "7z"}
PICKLE_EXTS = {"pt", "pth", "ckpt", "pkl", "pickle"}
OFFICE_KINDS = {"docx", "xlsx", "pptx", "odt", "ods", "odp", "doc", "xls", "ppt", "rtf"}

MAX_MEMBER_EXTRACT = 200 * 1024 * 1024      # zip-bomb guard: single member cap
MAX_ARCHIVE_LIST = 5000                     # cap on enumerated archive members
MAX_TEXT_READ = 20 * 1024 * 1024            # cap on direct text decode
MAX_PDF_TEXT_CHARS = 2_000_000
MAX_HASH_FULL = 50 * 1024 * 1024            # full sha256 only under this size
STRINGS_SCAN_WINDOW = 256 * 1024
STRINGS_MAX_LINES = 200
HEXDUMP_BYTES = 512


def _ext(name: str) -> str:
    return Path(name).suffix.lower().lstrip(".")


def identify(path: Optional[Path], filename_hint: str) -> str:
    """Return a coarse 'kind' string used to route to a handler."""
    if path is not None and path.is_dir():
        return "directory"
    ext = _ext(filename_hint or (path.name if path else ""))
    if ext in PICKLE_EXTS:
        return "pickle"
    if ext in OFFICE_KINDS:
        return ext
    if ext == "pdf":
        return "pdf"
    if ext in IMAGE_EXTS:
        return "image"
    if ext in VIDEO_EXTS:
        return "video"
    if ext in AUDIO_EXTS:
        return "audio"
    if ext in ARCHIVE_EXTS:
        return "archive"
    if ext in {"db", "sqlite", "sqlite3"}:
        return "sqlite"
    if ext == "csv":
        return "csv"
    if ext == "parquet":
        return "parquet"
    if ext == "safetensors":
        return "safetensors"
    if ext in TEXT_EXTS:
        return "text"
    # fall back to libmagic if extension didn't match anything specific
    mime = _magic_mime(path, filename_hint)
    if mime:
        if mime == "application/pdf":
            return "pdf"
        if mime.startswith("image/"):
            return "image"
        if mime.startswith("video/"):
            return "video"
        if mime.startswith("audio/"):
            return "audio"
        if mime.startswith("text/") or mime in ("application/json", "application/xml"):
            return "text"
        if mime in ("application/x-sqlite3", "application/vnd.sqlite3"):
            return "sqlite"
        if mime in ("application/zip", "application/x-tar", "application/gzip",
                    "application/x-7z-compressed", "application/x-bzip2"):
            return "archive"
    if path is not None and _looks_like_sqlite(path):
        return "sqlite"
    return "binary"


def _magic_mime(path: Optional[Path], filename_hint: str) -> Optional[str]:
    if _MAGIC is None:
        return mimetypes.guess_type(filename_hint or "")[0]
    try:
        if path is not None:
            return _MAGIC.from_file(str(path))
    except Exception:
        pass
    return mimetypes.guess_type(filename_hint or "")[0]


def _looks_like_sqlite(path: Path) -> bool:
    try:
        with open(path, "rb") as f:
            return f.read(16) == b"SQLite format 3\x00"
    except OSError:
        return False


# --------------------------------------------------------------------------
# text mode
# --------------------------------------------------------------------------

def get_text(path: Optional[Path], data: Optional[bytes], filename_hint: str,
             is_denied: Optional[Callable[[Path], bool]] = None) -> str:
    """Always returns a string. Never raises.

    is_denied, when given, is applied to directory entries so a /text
    listing can never name an entry that a direct fetch would 403 -- see
    security.is_denied(), the single deny predicate every caller shares.
    """
    kind = identify(path, filename_hint)
    try:
        if kind == "directory":
            return _text_directory(path, is_denied)
        if kind in OFFICE_KINDS:
            return office_extract.get_text(path, data, filename_hint, kind)
        if kind == "text":
            return _text_plain(path, data)
        if kind == "pdf":
            return _text_pdf(path, data)
        if kind == "image":
            return _text_image(path, data)
        if kind == "video":
            return _text_video(path, data, filename_hint)
        if kind == "audio":
            return _text_audio(path, data, filename_hint)
        if kind == "archive":
            return _text_archive(path, data, filename_hint)
        if kind == "sqlite":
            return _text_sqlite(path)
        if kind == "csv":
            return _text_csv(path, data)
        if kind == "parquet":
            return _text_parquet(path)
        if kind == "safetensors":
            return _text_safetensors(path, data)
        if kind == "pickle":
            note = ("Refusing to deserialize pickle-based format for safety "
                    "(no pickle.load / torch.load). Metadata only:\n\n")
            return note + _text_binary(path, data, filename_hint)
    except Exception as exc:  # noqa: BLE001 - this is the safety net by design
        return (f"[{kind} handler failed: {exc!r} -- falling back to generic report]\n\n"
                + _text_binary(path, data, filename_hint))
    return _text_binary(path, data, filename_hint)


def _read_bytes(path: Optional[Path], data: Optional[bytes], cap: Optional[int] = None) -> bytes:
    if data is not None:
        return data if cap is None else data[:cap]
    with open(path, "rb") as f:
        return f.read(cap) if cap else f.read()


def _text_directory(path: Path, is_denied: Optional[Callable[[Path], bool]] = None) -> str:
    entries = sorted(path.iterdir(), key=lambda p: p.name)
    if is_denied is not None:
        entries = [e for e in entries if not is_denied(e)]
    lines = [f"directory: {path}", f"entries: {len(entries)}", ""]
    truncated = len(entries) > 2000
    for e in entries[:2000]:
        try:
            st = e.stat()
            kind = "dir " if e.is_dir() else "file"
            lines.append(f"{kind}  {st.st_size:>12}  {time.strftime('%Y-%m-%d %H:%M', time.localtime(st.st_mtime))}  {e.name}")
        except OSError as exc:
            lines.append(f"???   {'?':>12}  ?                 {e.name}  (stat failed: {exc})")
    if truncated:
        lines.append(f"... truncated, {len(entries) - 2000} more entries not shown")
    return "\n".join(lines) + "\n"


def _text_plain(path: Optional[Path], data: Optional[bytes]) -> str:
    raw = _read_bytes(path, data, cap=MAX_TEXT_READ + 1)
    truncated = len(raw) > MAX_TEXT_READ
    raw = raw[:MAX_TEXT_READ]
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw.decode("latin-1", errors="replace")
    if truncated:
        text += f"\n\n[... truncated at {MAX_TEXT_READ} bytes ...]\n"
    return text


def _text_pdf(path: Optional[Path], data: Optional[bytes]) -> str:
    src = io.BytesIO(_read_bytes(path, data)) if data is not None or path is None else str(path)
    reader = pypdf.PdfReader(src)
    n_pages = len(reader.pages)
    chunks = [f"PDF: {n_pages} page(s)\n"]
    total = 0
    truncated = False
    for i, page in enumerate(reader.pages):
        try:
            t = page.extract_text() or ""
        except Exception as exc:  # noqa: BLE001
            t = f"[page {i+1}: text extraction failed: {exc!r}]"
        if total + len(t) > MAX_PDF_TEXT_CHARS:
            t = t[: max(0, MAX_PDF_TEXT_CHARS - total)]
            truncated = True
        chunks.append(f"\n--- page {i+1} ---\n{t}")
        total += len(t)
        if truncated:
            break
    body = "".join(chunks)
    if total == 0:
        body += ("\n\n[no extractable text found -- this is likely a scanned/image-only "
                  "PDF; visual representation is available at /preview.pdf]")
    if truncated:
        body += f"\n\n[... text truncated at {MAX_PDF_TEXT_CHARS} characters ...]"
    return body


def _text_image(path: Optional[Path], data: Optional[bytes]) -> str:
    src = io.BytesIO(_read_bytes(path, data)) if data is not None else path
    with Image.open(src) as im:
        info = {}
        for k, v in im.info.items():
            try:
                s = str(v)
            except Exception:  # noqa: BLE001
                s = "<unstringifiable>"
            info[k] = s[:500]
        out = {
            "format": im.format,
            "mode": im.mode,
            "size": im.size,
            "info": info,
        }
    return json.dumps(out, indent=2, default=str)


def _run(args: list[str], timeout: int) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, timeout=timeout, check=False)


def _text_video(path: Optional[Path], data: Optional[bytes], filename_hint: str) -> str:
    if path is None:
        return "[video inspection requires a real file on disk; in-archive video preview not supported]"
    try:
        proc = _run(["ffprobe", "-v", "quiet", "-print_format", "json",
                     "-show_format", "-show_streams", str(path)], timeout=30)
    except subprocess.TimeoutExpired:
        return "[ffprobe timed out after 30s]"
    if proc.returncode != 0 or not proc.stdout:
        return f"[ffprobe failed, exit {proc.returncode}]\nstderr:\n{proc.stderr.decode(errors='replace')[:4000]}"
    try:
        parsed = json.loads(proc.stdout.decode(errors="replace"))
        return json.dumps(parsed, indent=2)
    except json.JSONDecodeError:
        return proc.stdout.decode(errors="replace")


def _text_audio(path: Optional[Path], data: Optional[bytes], filename_hint: str) -> str:
    src = path if path is not None else io.BytesIO(_read_bytes(path, data))
    try:
        f = mutagen.File(src)
    except Exception as exc:  # noqa: BLE001
        return f"[mutagen failed to parse audio metadata: {exc!r}]"
    if f is None:
        return "[mutagen could not identify this as a known audio format]"
    lines = [f"length: {getattr(f.info, 'length', '?')}s",
             f"bitrate: {getattr(f.info, 'bitrate', '?')}",
             f"sample_rate: {getattr(f.info, 'sample_rate', '?')}", "", "tags:"]
    try:
        for k, v in (f.tags or {}).items():
            lines.append(f"  {k}: {v}")
    except Exception:  # noqa: BLE001
        pass
    return "\n".join(lines)


def _archive_open(path: Optional[Path], data: Optional[bytes], filename_hint: str):
    ext = _ext(filename_hint)
    src = io.BytesIO(_read_bytes(path, data)) if data is not None else path
    if ext == "zip" or (isinstance(src, (str, Path)) and zipfile.is_zipfile(src)):
        return "zip", zipfile.ZipFile(src)
    if ext == "7z":
        return "7z", py7zr.SevenZipFile(src, mode="r")
    # tar family (tar, tar.gz/tgz, tar.bz2, tar.xz)
    return "tar", tarfile.open(fileobj=src if isinstance(src, io.BytesIO) else None,
                                name=src if isinstance(src, (str, Path)) else None,
                                mode="r:*")


def _text_archive(path: Optional[Path], data: Optional[bytes], filename_hint: str) -> str:
    kind, arc = _archive_open(path, data, filename_hint)
    lines = [f"archive type: {kind}", ""]
    count = 0
    total_uncompressed = 0
    total_compressed = 0
    try:
        if kind == "zip":
            infos = arc.infolist()
            for zi in infos[:MAX_ARCHIVE_LIST]:
                lines.append(f"{zi.file_size:>12}  {zi.compress_size:>12}  {zi.filename}")
                total_uncompressed += zi.file_size
                total_compressed += zi.compress_size
                count += 1
            more = len(infos) - MAX_ARCHIVE_LIST
        elif kind == "7z":
            infos = [zi for zi in arc.list() if not getattr(zi, "is_directory", False)]
            for zi in infos[:MAX_ARCHIVE_LIST]:
                size = getattr(zi, "uncompressed", 0) or 0
                lines.append(f"{size:>12}  {'?':>12}  {zi.filename}")
                total_uncompressed += size
                count += 1
            more = len(infos) - MAX_ARCHIVE_LIST
        else:  # tar
            infos = arc.getmembers()
            for ti in infos[:MAX_ARCHIVE_LIST]:
                lines.append(f"{ti.size:>12}  {'-':>12}  {ti.name}")
                total_uncompressed += ti.size
                count += 1
            more = len(infos) - MAX_ARCHIVE_LIST
    finally:
        try:
            arc.close()
        except Exception:  # noqa: BLE001
            pass
    header = [f"{count} member(s) listed" + (f" (truncated, {more} more not shown)" if more > 0 else ""),
              f"total uncompressed: {total_uncompressed} bytes",
              (f"total compressed: {total_compressed} bytes" if total_compressed else ""),
              "", f"{'size':>12}  {'compressed':>12}  name"]
    return "\n".join([l for l in lines[:2]] + [l for l in header if l] + lines[2:])


def list_archive_members(path: Optional[Path], data: Optional[bytes], filename_hint: str) -> list[tuple[str, int]]:
    """Return [(member_name, size), ...] capped at MAX_ARCHIVE_LIST, for hub links."""
    kind, arc = _archive_open(path, data, filename_hint)
    out = []
    try:
        if kind == "zip":
            for zi in arc.infolist()[:MAX_ARCHIVE_LIST]:
                if not zi.is_dir():
                    out.append((zi.filename, zi.file_size))
        elif kind == "7z":
            for zi in arc.list()[:MAX_ARCHIVE_LIST]:
                if not getattr(zi, "is_directory", False):
                    out.append((zi.filename, getattr(zi, "uncompressed", 0) or 0))
        else:
            for ti in arc.getmembers()[:MAX_ARCHIVE_LIST]:
                if ti.isfile():
                    out.append((ti.name, ti.size))
    finally:
        try:
            arc.close()
        except Exception:  # noqa: BLE001
            pass
    return out


def read_archive_member(path: Optional[Path], data: Optional[bytes], filename_hint: str,
                         member: str) -> bytes:
    """Extract exactly one member into memory, enforcing MAX_MEMBER_EXTRACT."""
    kind, arc = _archive_open(path, data, filename_hint)
    try:
        if kind == "zip":
            info = arc.getinfo(member)
            if info.file_size > MAX_MEMBER_EXTRACT:
                raise ValueError(f"member {member} is {info.file_size} bytes, over the "
                                  f"{MAX_MEMBER_EXTRACT} byte extraction cap")
            return arc.read(member)
        if kind == "7z":
            # py7zr's SevenZipFile has no in-memory read() API -- it only
            # extracts to disk. extract() into a throwaway temp dir under our
            # own cache root (never /workspace directly) and read it back.
            size = None
            for zi in arc.list():
                if zi.filename == member:
                    size = getattr(zi, "uncompressed", 0) or 0
                    break
            if size is None:
                raise KeyError(member)
            if size > MAX_MEMBER_EXTRACT:
                raise ValueError(f"member {member} is {size} bytes, over the "
                                  f"{MAX_MEMBER_EXTRACT} byte extraction cap")
            _cache.CACHE_DIR.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(dir=str(_cache.CACHE_DIR)) as td:
                arc.extract(path=td, targets=[member])
                extracted = Path(td) / member
                if not extracted.is_file():
                    raise KeyError(member)
                return extracted.read_bytes()
        ti = arc.getmember(member)
        if ti.size > MAX_MEMBER_EXTRACT:
            raise ValueError(f"member {member} is {ti.size} bytes, over the "
                              f"{MAX_MEMBER_EXTRACT} byte extraction cap")
        f = arc.extractfile(ti)
        if f is None:
            raise KeyError(member)
        return f.read()
    finally:
        try:
            arc.close()
        except Exception:  # noqa: BLE001
            pass


def _text_sqlite(path: Path) -> str:
    uri = f"file:{path}?mode=ro"
    con = sqlite3.connect(uri, uri=True, timeout=5)
    con.execute("PRAGMA busy_timeout=5000")
    lines = []
    try:
        tables = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        lines.append(f"{len(tables)} table(s): {', '.join(tables)}\n")
        for t in tables:
            lines.append(f"--- {t} ---")
            cols = con.execute(f"PRAGMA table_info('{t}')").fetchall()
            lines.append("columns: " + ", ".join(f"{c[1]} {c[2]}" for c in cols))
            try:
                cnt = con.execute(f"SELECT COUNT(*) FROM '{t}'").fetchone()[0]
                lines.append(f"row count: {cnt}")
            except sqlite3.OperationalError as exc:
                lines.append(f"row count: unavailable ({exc})")
            try:
                rows = con.execute(f"SELECT * FROM '{t}' LIMIT 10").fetchall()
                for r in rows:
                    lines.append("  " + str(tuple(str(v)[:200] for v in r)))
            except sqlite3.OperationalError as exc:
                lines.append(f"  sample rows unavailable ({exc})")
            lines.append("")
    finally:
        con.close()
    return "\n".join(lines)


def _text_csv(path: Optional[Path], data: Optional[bytes]) -> str:
    raw = _read_bytes(path, data, cap=50 * 1024 * 1024 + 1)
    truncated = len(raw) > 50 * 1024 * 1024
    text = raw[: 50 * 1024 * 1024].decode("utf-8", errors="replace")
    reader = csv.reader(io.StringIO(text))
    lines = []
    n_cols = None
    for i, row in enumerate(reader):
        if i == 0:
            n_cols = len(row)
        if i < 50:
            lines.append(", ".join(row))
        else:
            break
    header = [f"columns (from first row): {n_cols}", ""]
    footer = ["", "[more than 50MB of data, line count not fully computed]"] if truncated else []
    return "\n".join(header + lines + footer)


def _text_parquet(path: Path) -> str:
    pf = pq.ParquetFile(str(path))
    lines = [f"schema:\n{pf.schema_arrow}", "", f"num row groups: {pf.num_row_groups}", ""]
    try:
        tbl = pf.read_row_group(0)
        n = min(50, tbl.num_rows)
        sample = tbl.slice(0, n).to_pylist()
        lines.append(f"first {n} row(s) of row group 0:")
        for row in sample:
            lines.append("  " + json.dumps(row, default=str)[:500])
    except Exception as exc:  # noqa: BLE001
        lines.append(f"[could not read row group 0: {exc!r}]")
    return "\n".join(lines)


def _text_safetensors(path: Optional[Path], data: Optional[bytes]) -> str:
    raw = _read_bytes(path, data, cap=8)
    if len(raw) < 8:
        raise ValueError("file too short to be safetensors")
    (header_len,) = struct.unpack("<Q", raw)
    if header_len > 100 * 1024 * 1024:
        raise ValueError("declared header implausibly large, refusing to read")
    if path is not None:
        with open(path, "rb") as f:
            f.seek(8)
            header_bytes = f.read(header_len)
    else:
        header_bytes = _read_bytes(path, data)[8:8 + header_len]
    header = json.loads(header_bytes.decode("utf-8"))
    lines = [f"{len(header)} tensor(s) (metadata only, no tensor data read):", ""]
    for name, meta in header.items():
        if name == "__metadata__":
            continue
        lines.append(f"  {name}: shape={meta.get('shape')} dtype={meta.get('dtype')}")
    if "__metadata__" in header:
        lines.append("")
        lines.append(f"__metadata__: {json.dumps(header['__metadata__'])[:2000]}")
    return "\n".join(lines)


def _sha256_or_fingerprint(path: Optional[Path], data: Optional[bytes]) -> str:
    if data is not None:
        return "sha256:" + hashlib.sha256(data).hexdigest()
    size = path.stat().st_size
    if size <= MAX_HASH_FULL:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return "sha256:" + h.hexdigest()
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read(1024 * 1024))
        f.seek(max(0, size - 1024 * 1024))
        h.update(f.read(1024 * 1024))
    h.update(str(size).encode())
    return f"partial-fingerprint(first+last 1MB + size):{h.hexdigest()}"


def _extract_strings(data: bytes, min_len: int = 4) -> list[str]:
    out = []
    cur = bytearray()
    for b in data:
        if 32 <= b < 127:
            cur.append(b)
        else:
            if len(cur) >= min_len:
                out.append(cur.decode("ascii"))
            cur = bytearray()
        if len(out) >= STRINGS_MAX_LINES:
            break
    if len(cur) >= min_len and len(out) < STRINGS_MAX_LINES:
        out.append(cur.decode("ascii"))
    return out


def _hexdump(data: bytes, base_offset: int = 0) -> str:
    lines = []
    for i in range(0, len(data), 16):
        chunk = data[i:i + 16]
        hexpart = " ".join(f"{b:02x}" for b in chunk)
        asciipart = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append(f"{base_offset + i:08x}  {hexpart:<47}  |{asciipart}|")
    return "\n".join(lines)


def _text_binary(path: Optional[Path], data: Optional[bytes], filename_hint: str) -> str:
    mime = _magic_mime(path, filename_hint) or "unknown"
    desc = None
    try:
        if _MAGIC_DESC is not None and path is not None:
            desc = _MAGIC_DESC.from_file(str(path))
    except Exception:  # noqa: BLE001
        desc = None

    if data is not None:
        size = len(data)
        mtime_s = "n/a (in-memory / archive member)"
        head = data[:STRINGS_SCAN_WINDOW]
        tail = data[-STRINGS_SCAN_WINDOW:] if size > STRINGS_SCAN_WINDOW else b""
        hex_head = data[:HEXDUMP_BYTES]
        hex_tail = data[-HEXDUMP_BYTES:] if size > HEXDUMP_BYTES else b""
        digest = _sha256_or_fingerprint(None, data)
    else:
        st = path.stat()
        size = st.st_size
        mtime_s = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime))
        with open(path, "rb") as f:
            head = f.read(STRINGS_SCAN_WINDOW)
            hex_head = head[:HEXDUMP_BYTES]
            tail = b""
            hex_tail = b""
            if size > STRINGS_SCAN_WINDOW:
                f.seek(max(0, size - STRINGS_SCAN_WINDOW))
                tail = f.read(STRINGS_SCAN_WINDOW)
            if size > HEXDUMP_BYTES:
                f.seek(max(0, size - HEXDUMP_BYTES))
                hex_tail = f.read(HEXDUMP_BYTES)
        digest = _sha256_or_fingerprint(path, None)

    strs = _extract_strings(head) + (_extract_strings(tail) if tail else [])
    strs = strs[:STRINGS_MAX_LINES]

    parts = [
        f"path/hint: {filename_hint or (str(path) if path else '<in-memory>')}",
        f"mime (libmagic): {mime}" + (f"  ({desc})" if desc else ""),
        f"size: {size} bytes",
        f"mtime: {mtime_s}",
        digest,
        "",
        f"strings (>=4 printable chars, first/last {STRINGS_SCAN_WINDOW} bytes scanned, capped at {STRINGS_MAX_LINES}):",
    ]
    parts.extend(strs if strs else ["  (none found)"])
    parts.append("")
    parts.append(f"hex dump, first {len(hex_head)} bytes:")
    parts.append(_hexdump(hex_head))
    if hex_tail:
        tail_off = size - len(hex_tail)
        parts.append("")
        parts.append(f"hex dump, last {len(hex_tail)} bytes:")
        parts.append(_hexdump(hex_tail, base_offset=tail_off))
    return "\n".join(parts)


# --------------------------------------------------------------------------
# preview.pdf mode
# --------------------------------------------------------------------------

def is_native_pdf(path: Optional[Path], filename_hint: str) -> bool:
    return identify(path, filename_hint) == "pdf"


def get_preview_pdf(path: Optional[Path], data: Optional[bytes], filename_hint: str,
                     relpath: str, size: int, mtime: float) -> Optional[bytes]:
    """Return PDF bytes, or None if no visual representation exists (-> 404)."""
    kind = identify(path, filename_hint)
    try:
        if kind == "pdf":
            return _read_bytes(path, data)
        if kind == "image":
            cached = _cache.get(relpath, size, mtime, ".pdf")
            if cached:
                return cached
            src = io.BytesIO(_read_bytes(path, data)) if data is not None else path
            with Image.open(src) as im:
                rgb = im.convert("RGB")
                buf = io.BytesIO()
                rgb.save(buf, format="PDF")
                out = buf.getvalue()
            _cache.put(relpath, size, mtime, ".pdf", out)
            return out
        if kind == "video" and path is not None:
            cached = _cache.get(relpath, size, mtime, ".pdf")
            if cached:
                return cached
            out = _video_contact_sheet(path)
            if out:
                _cache.put(relpath, size, mtime, ".pdf", out)
            return out
        if kind in OFFICE_KINDS:
            return office_extract.get_preview_pdf(path, data, filename_hint, kind, relpath, size, mtime)
    except Exception:  # noqa: BLE001
        return None
    return None


def _video_contact_sheet(path: Path) -> Optional[bytes]:
    try:
        proc = _run(["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(path)], timeout=20)
        fmt = json.loads(proc.stdout.decode(errors="replace")).get("format", {})
        duration = float(fmt.get("duration", 0) or 0)
    except Exception:  # noqa: BLE001
        duration = 0

    frames = []
    if duration > 0:
        n = 6
        timestamps = [duration * (0.05 + 0.9 * i / (n - 1)) for i in range(n)]
        for ts in timestamps:
            frame = _grab_frame(path, ts)
            if frame is not None:
                frames.append((ts, frame))

    if not frames:
        # never fail outright: produce a one-page PDF explaining why
        im = Image.new("RGB", (640, 200), "white")
        d = ImageDraw.Draw(im)
        d.text((10, 10), f"No frames could be extracted from:\n{path.name}\n(duration={duration}s)", fill="black")
        buf = io.BytesIO()
        im.save(buf, format="PDF")
        return buf.getvalue()

    thumb_w = 480
    cols = 3
    rows = (len(frames) + cols - 1) // cols
    sample = frames[0][1]
    thumb_h = int(sample.height * (thumb_w / sample.width))
    sheet = Image.new("RGB", (thumb_w * cols, (thumb_h + 20) * rows), "white")
    draw = ImageDraw.Draw(sheet)
    for i, (ts, im) in enumerate(frames):
        r, c = divmod(i, cols)
        thumb = im.resize((thumb_w, thumb_h))
        x, y = c * thumb_w, r * (thumb_h + 20)
        sheet.paste(thumb, (x, y))
        draw.text((x + 4, y + thumb_h + 2), f"t={ts:.1f}s", fill="black")
    buf = io.BytesIO()
    sheet.save(buf, format="PDF")
    return buf.getvalue()


def _grab_frame(path: Path, ts: float) -> Optional[Image.Image]:
    try:
        proc = subprocess.run(
            ["ffmpeg", "-ss", f"{ts:.3f}", "-i", str(path), "-frames:v", "1",
             "-vf", "scale=480:-1", "-f", "image2pipe", "-vcodec", "png", "-"],
            capture_output=True, timeout=20, check=False,
        )
        if proc.returncode != 0 or not proc.stdout:
            return None
        return Image.open(io.BytesIO(proc.stdout)).convert("RGB")
    except Exception:  # noqa: BLE001
        return None
