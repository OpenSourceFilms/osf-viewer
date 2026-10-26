"""Derived PDF preview cache with source-identity isolation.

Neither path, size nor mtime alone identifies file contents. In particular,
replaced source documents and archive members can retain all three.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import tempfile

CACHE_DIR = Path("/workspace/.osf_view_cache")


def source_fingerprint(path: Path | None, data: bytes | None) -> str:
    """Fingerprint the source, without caching source paths or their bytes.

    In-memory archive members require a content digest because archive member
    path, size and mtime alone cannot distinguish a changed payload. For disk
    files, metadata (dev/inode/ctime_ns) detects replacements and rewrites even
    when callers preserve original size and modification time. This is a
    *cache invalidation* key, not a cryptographic file-integrity guarantee.
    """
    if data is not None:
        return "bytes:" + hashlib.sha256(data).hexdigest()
    if path is not None:
        st = Path(path).stat()
        return f"file:{st.st_dev}:{st.st_ino}:{st.st_size}:{st.st_ctime_ns}"
    raise ValueError("cache source must be a file or an in-memory payload")


def _key_path(relpath: str, size: int, mtime: float, suffix: str,
              source_identity: str) -> Path:
    if not source_identity:
        raise ValueError("missing preview source identity")
    key = f"{relpath}\0{size}\0{mtime}\0{source_identity}"
    h = hashlib.sha256(key.encode("utf-8", "replace")).hexdigest()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{h}{suffix}"


def get(relpath: str, size: int, mtime: float, suffix: str,
        source_identity: str) -> bytes | None:
    p = _key_path(relpath, size, mtime, suffix, source_identity)
    if p.exists():
        try:
            return p.read_bytes()
        except OSError:
            return None
    return None


def put(relpath: str, size: int, mtime: float, suffix: str, data: bytes,
        source_identity: str) -> Path:
    p = _key_path(relpath, size, mtime, suffix, source_identity)
    # Concurrent preview requests must not share a fixed "<key>.pdf.tmp"
    # name. Give each write its own staging inode and publish after close.
    fd, tmp_name = tempfile.mkstemp(prefix=f".{p.name}.", suffix=".tmp",
                                    dir=str(CACHE_DIR))
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp_name, p)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
    return p
