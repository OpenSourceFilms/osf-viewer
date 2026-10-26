"""Path resolution and deny-list enforcement for the universal file viewer.

Every inbound relpath must go through safe_resolve() before touching the
filesystem. This is the only thing standing between the public /__view__/
route and the same secrets Copyparty was hardened to hide (2026-09-04
incident) -- the deny list here must stay in sync with the -v deny mounts
in /workspace/start_copyparty.sh (see denylist.txt).
"""
from __future__ import annotations

from pathlib import Path

CACHE_DIRNAME = ".osf_view_cache"

# A deployment policy missing any of these OSF-private roots is unsafe even
# if the remaining denylist has valid syntax. Optional project-specific
# entries may be added without changing this minimum baseline.
REQUIRED_DENY_PATHS = frozenset({
    ".pod-persist", ".cloudflared", ".config", "_BACKUP",
    "_secrets", "secrets", "logs", "start_copyparty.sh",
})


class DenylistUnavailable(RuntimeError):
    """Required Viewer access-control configuration is absent or invalid."""


# Directory names denied WHEREVER they appear in the tree, not just at the
# specific paths listed in denylist.txt. Found 2026-09-08: denylist.txt only
# covered the top-level /workspace/.claude, but 18+ per-subproject .claude/
# directories exist across this volume (pipeline/.claude, melb_acquire/.claude,
# _BACKUP/.claude, .pod-persist/claude-home/.claude, ...), some of which can
# contain shell-snapshot files with full env-var dumps (a real secret-exposure
# class already seen once in this workspace's history). Copyparty's own -v
# deny mounts have the SAME gap (verified: its raw route also serves a nested
# .claude/ untouched) -- that is a separate, still-open finding for Daniel to
# decide on for start_copyparty.sh; this list only tightens what THIS service
# additionally refuses, it does not change Copyparty.
DENIED_BASENAMES = {".claude"}


def load_denylist(root: Path, denylist_file: Path) -> list[Path]:
    """Load the required OSF policy or fail closed.

    A missing, truncated, unreadable or malformed policy MUST NOT silently
    degrade to only the default `.claude` and cache exclusions. Explicit
    paths are root-relative; absolute paths, traversal and symlink escapes
    inside the configuration are rejected rather than ignored.
    """
    if not denylist_file.is_file():
        raise DenylistUnavailable("viewer denylist file is unavailable")
    try:
        lines = denylist_file.read_text(encoding="utf-8").splitlines()
        root_real = root.resolve()
        entries: list[Path] = []
        declared: set[str] = set()
        for line in lines:
            value = line.strip()
            if not value or value.startswith("#"):
                continue
            value = value.rstrip("/")
            parts = value.split("/")
            if (not value or value.startswith("/") or "\\" in value
                    or any(p in ("", ".", "..") for p in parts)):
                raise DenylistUnavailable("viewer denylist contains an unsafe path")
            candidate = root_real.joinpath(*parts).resolve(strict=False)
            try:
                candidate.relative_to(root_real)
            except ValueError as exc:
                raise DenylistUnavailable("viewer denylist escapes the root") from exc
            entries.append(candidate)
            declared.add(value)
    except (OSError, UnicodeError, RuntimeError) as exc:
        if isinstance(exc, DenylistUnavailable):
            raise
        raise DenylistUnavailable("viewer denylist could not be read") from exc

    if not REQUIRED_DENY_PATHS.issubset(declared):
        raise DenylistUnavailable("viewer denylist is missing mandatory exclusions")
    # Cache is always denied even if the file does not name it.
    entries.append((root_real / CACHE_DIRNAME).resolve())
    return entries


def is_denied(real: Path, denylist: list[Path], root: Path) -> bool:
    """Public entry point for the same deny predicate safe_resolve() uses.

    Callers building directory/listing output (app.py's HTML hub,
    inspectors.py's _text_directory) must filter entries through this rather
    than re-implementing a second denial check, so a listing can never show
    an entry name that a direct fetch of that same path would 403.
    """
    # Directory listings pass lexical Path entries, while safe_resolve()
    # checks canonical paths. Apply both checks: deny aliases named .claude,
    # aliases whose target is denied, and symlinks escaping the viewer root.
    root_real = root.resolve(strict=False)
    if _is_denied(real, denylist, root_real):
        return True
    try:
        target = real.resolve(strict=False)
        target.relative_to(root_real)
    except (OSError, RuntimeError, ValueError):
        return True
    return _is_denied(target, denylist, root_real)


def _is_denied(real: Path, denylist: list[Path], root: Path) -> bool:
    for d in denylist:
        if real == d or d in real.parents:
            return True
    try:
        rel_parts = real.relative_to(root).parts
    except ValueError:
        rel_parts = real.parts
    if any(part in DENIED_BASENAMES for part in rel_parts):
        return True
    return False


def safe_resolve(root: Path, relpath: str, denylist: list[Path]) -> Path:
    """Resolve relpath under root.

    Raises PermissionError if the path is malformed, escapes root, or is
    denylisted (caller should respond 403). Raises FileNotFoundError if the
    path is safe but does not exist (caller should respond 404). Returns the
    resolved real Path otherwise.
    """
    if relpath is None or "\x00" in relpath:
        raise PermissionError("invalid path")
    relpath = relpath.lstrip("/")
    parts = [p for p in relpath.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        raise PermissionError("path traversal")

    root_real = root.resolve()
    candidate = root_real.joinpath(*parts) if parts else root_real
    # Reject a protected component even when it is itself a symlink to an
    # otherwise accessible target; the path name is part of the policy.
    if _is_denied(candidate, denylist, root_real):
        raise PermissionError("denylisted")
    # resolve(strict=False): normalizes and follows symlinks for whatever
    # part of the path already exists, without requiring the leaf to exist.
    try:
        real = candidate.resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        raise PermissionError("unresolvable symlink") from exc

    try:
        real.relative_to(root_real)
    except ValueError:
        raise PermissionError("escapes root (symlink or traversal)")

    if _is_denied(real, denylist, root_real):
        raise PermissionError("denylisted")

    if not real.exists():
        raise FileNotFoundError(str(real))

    return real
