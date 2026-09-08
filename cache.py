"""Content-addressed cache for expensive derived previews (image/video -> PDF).

Never reachable through viewer URLs -- security.safe_resolve always denies
CACHE_DIR regardless of denylist.txt contents.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

CACHE_DIR = Path("/workspace/.osf_view_cache")


def _key_path(relpath: str, size: int, mtime: float, suffix: str) -> Path:
    h = hashlib.sha256(f"{relpath}:{size}:{mtime}".encode("utf-8", "replace")).hexdigest()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{h}{suffix}"


def get(relpath: str, size: int, mtime: float, suffix: str) -> bytes | None:
    p = _key_path(relpath, size, mtime, suffix)
    if p.exists():
        try:
            return p.read_bytes()
        except OSError:
            return None
    return None


def put(relpath: str, size: int, mtime: float, suffix: str, data: bytes) -> Path:
    p = _key_path(relpath, size, mtime, suffix)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(p)
    return p
