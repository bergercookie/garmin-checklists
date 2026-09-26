"""Fingerprint the watch sources.

Lives on its own so the screenshot capture and the staleness check share one
implementation
"""

from __future__ import annotations

import hashlib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FINGERPRINT = REPO / "docs" / "images" / "watch-source.sha256"


def source_fingerprint() -> str:
    """Hash every Monkey C source and resource, path and contents alike."""
    files = [
        path
        for path in (REPO / "watch").rglob("*")
        if path.is_file() and path.suffix in {".mc", ".xml", ".jungle", ".png"}
    ]
    digest = hashlib.sha256()
    for name in sorted(path.relative_to(REPO).as_posix() for path in files):
        digest.update(name.encode())
        digest.update((REPO / name).read_bytes())
    return digest.hexdigest()
