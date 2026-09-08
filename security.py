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
    """Read denylist.txt (relative-to-root paths, # comments, blank lines ok)."""
    entries: list[Path] = []
    if denylist_file.exists():
        for line in denylist_file.read_text(errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            entries.append((root / line).resolve())
    # the cache dir is always denied, regardless of what denylist.txt says
    entries.append((root / CACHE_DIRNAME).resolve())
    return entries


def is_denied(real: Path, denylist: list[Path], root: Path) -> bool:
    """Public entry point for the same deny predicate safe_resolve() uses.

    Callers building directory/listing output (app.py's HTML hub,
    inspectors.py's _text_directory) must filter entries through this rather
    than re-implementing a second denial check, so a listing can never show
    an entry name that a direct fetch of that same path would 403.
    """
    return _is_denied(real, denylist, root)


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
    # resolve(strict=False): normalizes and follows symlinks for whatever
    # part of the path already exists, without requiring the leaf to exist.
    real = candidate.resolve(strict=False)

    try:
        real.relative_to(root_real)
    except ValueError:
        raise PermissionError("escapes root (symlink or traversal)")

    if _is_denied(real, denylist, root_real):
        raise PermissionError("denylisted")

    if not real.exists():
        raise FileNotFoundError(str(real))

    return real
