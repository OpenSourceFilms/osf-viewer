"""Diskless bounded extraction for a single 7z archive member.

Use py7zr's WriterFactory rather than extracting members onto a filesystem.
Archive names are data labels, never filesystem paths. This also limits a
malformed member's actual written bytes even if its metadata understates size.
"""
from __future__ import annotations

import io
from pathlib import PurePosixPath
import threading

from py7zr.io import Py7zIO, WriterFactory


def validate_member_name(name: str) -> None:
    """Reject ambiguous/traversal names before asking py7zr to decode them."""
    if (not isinstance(name, str) or not name
            or "\x00" in name or "\\" in name
            or any(ord(char) < 32 or ord(char) == 127 for char in name)):
        raise ValueError("unsafe archive member name")
    parts = name.split("/")
    if (any(part in ("", ".", "..") for part in parts)
            or PurePosixPath(name).is_absolute() or ":" in parts[0]):
        raise ValueError("unsafe archive member name")


class _BoundedMemberIO(Py7zIO):
    """Seekable thread-safe in-memory sink that refuses over-limit writes."""

    def __init__(self, limit: int):
        self._limit = limit
        self._buffer = io.BytesIO()
        self._lock = threading.RLock()
        self._high_water = 0

    def write(self, data: bytes | bytearray) -> int:
        with self._lock:
            new_end = self._buffer.tell() + len(data)
            if new_end > self._limit:
                raise ValueError("7z member exceeds decompression byte limit")
            count = self._buffer.write(data)
            self._high_water = max(self._high_water, self._buffer.tell())
            return count

    def read(self, size: int | None = None) -> bytes:
        with self._lock:
            return self._buffer.read(-1 if size is None else size)

    def seek(self, offset: int, whence: int = 0) -> int:
        with self._lock:
            target = self._buffer.seek(offset, whence)
            if target > self._limit:
                raise ValueError("7z writer sought beyond byte limit")
            return target

    def flush(self) -> None:
        return None

    def size(self) -> int:
        with self._lock:
            return self._high_water

    def getvalue(self) -> bytes:
        with self._lock:
            return self._buffer.getvalue()


class _SingleMemberFactory(WriterFactory):
    """Fail closed if py7zr requests a different or duplicate output stream."""

    def __init__(self, member: str, limit: int):
        self._member = member
        self._limit = limit
        self.product: _BoundedMemberIO | None = None

    def create(self, filename: str) -> Py7zIO:
        if filename != self._member or self.product is not None:
            raise ValueError("unexpected archive extraction output")
        self.product = _BoundedMemberIO(self._limit)
        return self.product


def read_7z_member(archive, member: str, max_bytes: int) -> bytes:
    """Decode selected member into bounded memory, never a temporary directory."""
    validate_member_name(member)
    if not isinstance(max_bytes, int) or max_bytes < 0:
        raise ValueError("invalid decompression byte limit")
    matches = [entry for entry in archive.list()
               if getattr(entry, "filename", None) == member]
    if len(matches) != 1:
        raise KeyError("missing or duplicate archive member")
    if getattr(matches[0], "is_directory", False):
        raise ValueError("archive member is a directory")
    estimated = getattr(matches[0], "uncompressed", None)
    if not isinstance(estimated, int) or estimated < 0 or estimated > max_bytes:
        raise ValueError("archive member metadata exceeds limit or is unknown")

    factory = _SingleMemberFactory(member, max_bytes)
    # In some py7zr versions nested entries require explicit ancestor targets.
    # Passing their names to a WriterFactory NEVER creates filesystem paths.
    parts = member.split("/")
    targets = ["/".join(parts[:index]) for index in range(1, len(parts))]
    targets.append(member)
    archive.extract(targets=targets, recursive=False, factory=factory)
    if factory.product is None:
        raise ValueError("archive decoder did not produce requested member")
    value = factory.product.getvalue()
    if len(value) > max_bytes or len(value) != estimated:
        raise ValueError("archive member byte count differs from declared size")
    return value


def read_zip_member(archive, member: str, max_bytes: int) -> bytes:
    """Bound actual ZIP member bytes, rejecting duplicate/ambiguous names."""
    validate_member_name(member)
    if not isinstance(max_bytes, int) or max_bytes < 0:
        raise ValueError("invalid decompression byte limit")
    matches = [info for info in archive.infolist() if info.filename == member]
    if len(matches) != 1:
        raise KeyError("missing or duplicate archive member")
    info = matches[0]
    if info.is_dir() or info.file_size > max_bytes or info.file_size < 0:
        raise ValueError("invalid or oversized ZIP member")
    with archive.open(info, mode="r") as stream:
        content = stream.read(max_bytes + 1)
    if len(content) > max_bytes or len(content) != info.file_size:
        raise ValueError("ZIP decompressed byte count exceeds bounds")
    return content


def read_tar_member(archive, member: str, max_bytes: int) -> bytes:
    """Read regular TAR entries only, never follow TAR symlinks or hardlinks.

    A TAR symlink's TarInfo.size can be zero even when extractfile()
    follows it to a large target. Both declared AND actual bounds matter.
    """
    validate_member_name(member)
    if not isinstance(max_bytes, int) or max_bytes < 0:
        raise ValueError("invalid decompression byte limit")
    matches = [info for info in archive.getmembers() if info.name == member]
    if len(matches) != 1:
        raise KeyError("missing or duplicate archive member")
    info = matches[0]
    if not info.isfile():  # no SYMTYPE, LNKTYPE, directories or device nodes
        raise ValueError("TAR member must be a regular file")
    if info.size < 0 or info.size > max_bytes:
        raise ValueError("TAR member exceeds decompression byte limit")
    reader = archive.extractfile(info)
    if reader is None:
        raise ValueError("TAR member has no readable content")
    with reader:
        content = reader.read(max_bytes + 1)
    if len(content) > max_bytes or len(content) != info.size:
        raise ValueError("TAR decompressed byte count exceeds bounds")
    return content
