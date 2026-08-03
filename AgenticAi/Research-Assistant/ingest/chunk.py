"""Chunk markdown docs into ~700 char paragraphs.

Each file in the corpus must start with `<!-- source: <url> -->`; the rest is
markdown. The chunker preserves paragraphs and tags every chunk with the file
URL so downstream search can cite back.
"""
from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

_SOURCE_RE = re.compile(r"<!--\s*source:\s*(\S+)\s*-->", re.IGNORECASE)


def read_source_and_body(path: Path) -> tuple[str, str]:
    text = path.read_text(encoding="utf-8")
    m = _SOURCE_RE.search(text)
    if not m:
        url = f"file://{path.resolve()}"
        body = text
    else:
        url = m.group(1)
        body = text[m.end():].lstrip("\n")
    return url, body


def chunk_text(text: str, max_chars: int = 700) -> list[str]:
    """Split markdown into chunks of <= max_chars, preferring paragraph breaks."""
    paragraphs = re.split(r"\n\s*\n", text.strip())
    chunks: list[str] = []
    buf: list[str] = []
    buf_len = 0
    for p in paragraphs:
        p = p.strip()
        if not p:
            continue
        if buf_len + len(p) + 2 <= max_chars or not buf:
            buf.append(p)
            buf_len += len(p) + 2
        else:
            chunks.append("\n\n".join(buf))
            buf = [p]
            buf_len = len(p)
    if buf:
        chunks.append("\n\n".join(buf))
    return chunks


def iter_corpus(root: Path) -> Iterable[tuple[str, str, str]]:
    """Yield (chunk_id, source_url, chunk_text) for every chunk under `root`."""
    for path in sorted(root.rglob("*.md")):
        url, body = read_source_and_body(path)
        for i, ch in enumerate(chunk_text(body)):
            chunk_id = f"{path.relative_to(root)}::chunk-{i:03d}"
            yield chunk_id, url, ch
