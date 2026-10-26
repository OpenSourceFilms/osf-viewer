"""Bounded-memory directory listings for the public Viewer.

Path.iterdir() on supported Python versions can first materialise the
whole directory using os.listdir(). Scanning with os.scandir() and
retaining only the smallest MAX_DISPLAY names avoids an unbounded
Path list before the advertised 2,000-entry presentation cap.

CPU and scan time still scale with the number of directory entries.
"""
from __future__ import annotations

import heapq
import os
from pathlib import Path
from typing import Callable

MAX_DISPLAY = 2000


def bounded_visible_entries(
    directory: Path,
    is_denied: Callable[[Path], bool] | None = None,
    *,
    limit: int = MAX_DISPLAY,
) -> tuple[list[Path], int]:
    """Return the first *limit* visible names in sorted order and their count.

    Counts only entries allowed by the same deny predicate that protects
    direct fetches. The output list uses O(limit) memory, not O(N) memory.
    The scandir iterator is closed even if path resolution raises.
    """
    if type(limit) is not int or not 1 <= limit <= MAX_DISPLAY:
        raise ValueError("directory display limit must be between 1 and 2000")

    count = 0

    with os.scandir(directory) as iterator:
        def visible():
            nonlocal count
            for raw in iterator:
                child = Path(raw.path)
                if is_denied is not None and is_denied(child):
                    continue
                count += 1
                yield child

        selected = heapq.nsmallest(limit, visible(), key=lambda p: p.name)
    return selected, count
